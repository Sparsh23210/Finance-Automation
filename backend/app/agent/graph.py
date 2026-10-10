"""
graph.py - The main agent execution loop using LangGraph.

Architecture:
  UNDERSTAND → EXECUTE → OBSERVE → DECIDE → (loop or terminal node)

Each node is a simple Python function that takes state and returns updated state.
LangGraph wires the conditional edges between them.

The agent runs inside a background thread (FastAPI BackgroundTasks), so we use
a regular synchronous SessionLocal rather than async sessions.
"""
import json
import traceback
from typing import Any

from langgraph.graph import StateGraph, END

from app.agent.state import AgentState, initial_state
from app.agent.planner import understand_task, plan_next_action
from app.agent.policy import check_write_permission, check_amount_threshold, classify_error, PolicyError
from app.agent.ledger import record as ledger_record
from app.config import MAX_AGENT_STEPS, MAX_TOOL_RETRIES, FAULT_INJECT
import app.database as _db
from app.models import Task, ApprovalRequest
from app.tools.registry import get_tool
import app.tools  # triggers __init__ which wires tool functions


# ── Helper: persist state to DB ───────────────────────────────────────────────

def _save_state(task_id: str, state: AgentState):
    """Snapshot the agent state to the DB so it can survive restarts."""
    db = _db.SessionLocal()
    try:
        task = db.get(Task, task_id)
        if task:
            task.status = state["status"]
            # Convert state to a plain dict for JSON storage
            snapshot = dict(state)
            task.state_json = snapshot
            db.commit()
    finally:
        db.close()


def _load_state(task_id: str) -> AgentState | None:
    """Reload a persisted state snapshot (used for resume after restart)."""
    db = _db.SessionLocal()
    try:
        task = db.get(Task, task_id)
        if task and task.state_json:
            return AgentState(**task.state_json)
        return None
    finally:
        db.close()


# ── Fault injection (dev/test only) ──────────────────────────────────────────

def _maybe_inject_fault(tool_name: str, result: dict) -> dict:
    """
    If FAULT_INJECT env var is set, modify the result to simulate failure.
    Only active in development/test environments.
    """
    if not FAULT_INJECT:
        return result
    if FAULT_INJECT == "timeout_after_write" and tool_name == "create_invoice" and result.get("ok"):
        raise TimeoutError("Simulated timeout after successful write")
    if FAULT_INJECT == "wrong_amount" and tool_name == "create_invoice" and result.get("ok"):
        # Corrupt the stored amount in the response to simulate a mismatch
        if result.get("data"):
            result["data"]["amount"] = "99999.99"
    if FAULT_INJECT == "temp_error" and tool_name in ("search_files", "read_document"):
        return {"ok": False, "error": "Simulated temporary tool error"}
    return result


# ── Node: UNDERSTAND ──────────────────────────────────────────────────────────

def node_understand(state: AgentState) -> AgentState:
    """Parse the natural-language request into a structured goal."""
    try:
        goal = understand_task(state["request"], state["workflow"])
        state["goal"] = goal
        if goal.get("task_type") == "po_reconciliation":
            state["workflow"] = "po_reconciliation"
        ledger_record(
            task_id=state["task_id"],
            step=0,
            action="understand_task",
            inputs={"request": state["request"]},
            outputs={"goal": goal},
            status="ok",
            notes=f"Planning mode: {goal.get('_mode', 'unknown')} | Workflow: {state['workflow']}",
        )
    except Exception as e:
        state["errors"].append(f"Understanding failed: {e}")
        state["status"] = "failed"
        state["summary"] = f"Could not parse task: {e}"
    return state


# ── Node: EXECUTE ─────────────────────────────────────────────────────────────

def node_execute(state: AgentState) -> AgentState:
    """
    Ask the planner for the next action, validate it, then execute.
    Records the result to the evidence ledger.
    """
    if state["current_step"] >= MAX_AGENT_STEPS:
        state["status"] = "failed"
        state["summary"] = f"Exceeded max steps ({MAX_AGENT_STEPS})"
        return state

    # Get next action from planner
    try:
        action = plan_next_action(dict(state))
    except Exception as e:
        state["errors"].append(f"Planner error: {e}")
        state["status"] = "failed"
        return state

    tool_name = action.get("tool", "DONE")
    args = action.get("args", {})
    reason = action.get("reason", "")

    # ── Terminal actions ──────────────────────────────────────────────────────
    if tool_name == "DONE":
        state["status"] = "running"  # will go to VERIFY node
        state["_next"] = "verify"
        return state

    if tool_name == "NEEDS_INPUT":
        state["status"] = "needs_input"
        state["needs_input_question"] = action.get("question", "More information needed.")
        state["summary"] = action.get("question", "Needs user input")
        ledger_record(state["task_id"], state["current_step"], "needs_input",
                      notes=state["needs_input_question"])
        return state

    if tool_name in ("REQUEST_APPROVAL", "request_approval"):
        return _handle_approval_request(state, args, reason)

    # ── Validate tool name ────────────────────────────────────────────────────
    spec = get_tool(tool_name)
    if not spec or not spec.fn:
        state["errors"].append(f"Unknown tool: '{tool_name}'")
        state["status"] = "failed"
        return state

    # ── Policy check before writes ────────────────────────────────────────────
    if spec.has_side_effects:
        try:
            check_write_permission(tool_name, state)
        except PolicyError as e:
            state["errors"].append(f"Permission denied: {e}")
            state["status"] = "failed"
            ledger_record(state["task_id"], state["current_step"], "permission_denied",
                          tool_name=tool_name, inputs=args, status="error", notes=str(e))
            return state

        # Check amount threshold before create_invoice
        if tool_name == "create_invoice":
            amount = args.get("amount", "0")
            pol = check_amount_threshold(amount)
            if pol.get("requires_approval") and not state["approval_requested"]:
                return _handle_approval_request(state, {
                    "action": "create_invoice",
                    "justification": pol["reason"],
                    "proposed_data": args,
                }, pol["reason"])

    # ── Execute the tool ──────────────────────────────────────────────────────
    step_idx = state["current_step"]
    retry_key = f"{tool_name}:{json.dumps(args, sort_keys=True)}"
    attempt = state["retry_counts"].get(retry_key, 0)

    try:
        result = spec.fn(**args)
        result = _maybe_inject_fault(tool_name, result)
    except TimeoutError:
        # Timeout after write: we don't know if it succeeded.
        # CRITICAL: do NOT retry blindly. Check the DB first.
        state["errors"].append(f"Timeout after {tool_name} — checking DB state before retry")
        step_rec = {"tool": tool_name, "args": args, "result": {"error": "timeout"}, "status": "timeout", "attempt": attempt}
        state["steps"].append(step_rec)
        state["retry_counts"][retry_key] = attempt + 1
        ledger_record(state["task_id"], step_idx, f"timeout_{tool_name}", tool_name=tool_name,
                      inputs=args, status="timeout", notes="Will check DB state before retry")
        state["current_step"] += 1
        state["_next"] = "recover_after_timeout"
        return state
    except Exception as e:
        err = str(e)
        action_type = classify_error(err, attempt, MAX_TOOL_RETRIES)
        step_rec = {"tool": tool_name, "args": args, "result": {"error": err}, "status": "error", "attempt": attempt}
        state["steps"].append(step_rec)
        state["errors"].append(f"{tool_name} error (attempt {attempt}): {err}")
        state["retry_counts"][retry_key] = attempt + 1
        ledger_record(state["task_id"], step_idx, f"error_{tool_name}", tool_name=tool_name,
                      inputs=args, outputs={"error": err}, status="error")
        state["current_step"] += 1
        if action_type == "abort":
            state["status"] = "failed"
        return state

    # ── Handle non-ok results (e.g. 409 Conflict) ──────────────────────────────
    is_ok = result.get("ok", True) if isinstance(result, dict) else True
    status_code = result.get("status_code") if isinstance(result, dict) else None

    # 409 = duplicate invoice already exists — treat as completed (idempotency win)
    if not is_ok and status_code == 409:
        # Try to get the existing invoice by invoice_number
        existing_inv_number = args.get("invoice_number")
        if existing_inv_number:
            from app.tools.finance_tools import search_invoices
            sr = search_invoices(invoice_number=existing_inv_number)
            if sr.get("ok") and sr.get("data"):
                inv = sr["data"][0] if isinstance(sr["data"], list) else sr["data"]
                result = {"ok": True, "data": inv, "_idempotent": True}
                is_ok = True

    step_status = "ok" if is_ok else "error"

    step_rec = {"tool": tool_name, "args": args, "result": result, "status": step_status, "attempt": attempt}
    state["steps"].append(step_rec)

    # If still not ok after duplicate-recovery attempt, abort this tool
    if not is_ok:
        state["errors"].append(f"{tool_name} returned error: {result.get('error', 'unknown')} (status {status_code})")
        # Treat persistent 4xx (except 409) as abort
        if status_code and 400 <= status_code < 500:
            state["status"] = "failed"
        state["current_step"] += 1
        return state

    ev_id = ledger_record(
        task_id=state["task_id"],
        step=step_idx,
        action=f"execute_{tool_name}",
        tool_name=tool_name,
        inputs=args,
        outputs=result,
        status=step_status,
        source_ref=result.get("data", {}).get("source_ref") if isinstance(result.get("data"), dict) else None,
    )
    state["evidence_ids"].append(ev_id)

    # Update state from results
    _update_state_from_result(state, tool_name, args, result)

    state["current_step"] += 1
    state["_next"] = "continue"
    return state


def _handle_approval_request(state: AgentState, args: dict, reason: str) -> AgentState:
    """Create a persistent approval record and pause execution."""
    db = _db.SessionLocal()
    try:
        ap = ApprovalRequest(
            task_id=state["task_id"],
            action=args.get("action", "unknown"),
            justification=args.get("justification", reason),
            evidence_summary=args.get("proposed_data", {}),
            decision="pending",
        )
        db.add(ap)
        db.commit()
        db.refresh(ap)
        state["approval_id"] = ap.id
        state["approval_requested"] = True
        state["status"] = "waiting_approval"
        state["summary"] = f"Waiting for approval: {args.get('justification', reason)}"
        ledger_record(state["task_id"], state["current_step"], "request_approval",
                      tool_name="request_approval", inputs=args,
                      outputs={"approval_id": ap.id}, status="ok")
        state["current_step"] += 1
    finally:
        db.close()
    return state


def _update_state_from_result(state: AgentState, tool_name: str, args: dict, result: Any):
    """Extract important values from tool results and store in state."""
    data = result.get("data") if isinstance(result, dict) else result

    if tool_name == "search_files" and isinstance(result, dict):
        state["documents"] = result.get("results", [])

    elif tool_name == "extract_invoice_fields" and isinstance(result, dict):
        # Merge extracted fields (result IS the fields dict)
        state["extracted"].update({k: v for k, v in result.items() if not k.startswith("_") and v is not None})

    elif tool_name == "find_vendor" and isinstance(result, dict):
        state["vendor_info"] = result

    elif tool_name == "create_invoice" and isinstance(result, dict) and result.get("ok"):
        state["invoice_id"] = data.get("id") if isinstance(data, dict) else None

    elif tool_name == "search_invoices" and isinstance(result, dict) and result.get("ok"):
        invoices = result.get("data", [])
        state["candidate_invoices"] = invoices
        if invoices:
            from app.agent.planner import select_latest_invoice
            req_inv_num = state.get("goal", {}).get("invoice_number")
            chosen, note = select_latest_invoice(invoices, target_number=req_inv_num)
            if chosen:
                state["selected_invoice"] = chosen
                state["invoice_id"] = chosen.get("id")
                # Populate extracted fields from chosen invoice
                state["extracted"]["invoice_number"] = chosen.get("invoice_number")
                state["extracted"]["amount"] = chosen.get("amount")
                state["extracted"]["currency"] = chosen.get("currency", "INR")
                state["extracted"]["invoice_date"] = chosen.get("invoice_date")
                state["extracted"]["due_date"] = chosen.get("due_date")
                state["extracted"]["vendor_id"] = chosen.get("vendor_id")
                if chosen.get("source_ref"):
                    state["extracted"]["source_ref"] = chosen.get("source_ref")

    elif tool_name == "get_purchase_order" and isinstance(result, dict) and result.get("ok"):
        po_data = result.get("data", {})
        if isinstance(po_data, dict):
            state["po_id"] = po_data.get("id")
            state["matched_po"] = po_data
            if po_data.get("po_number"):
                state["extracted"]["po_number"] = po_data.get("po_number")

    elif tool_name == "compare_invoice_with_po" and isinstance(result, dict):
        state["reconciliation"] = result
        state["discrepancies"] = result.get("discrepancies", [])
        state["comparisons"] = result.get("comparisons", {})

    elif tool_name == "update_invoice_status" and isinstance(result, dict) and result.get("ok"):
        inv_data = result.get("data", {})
        if isinstance(inv_data, dict) and inv_data.get("status"):
            state["extracted"]["status"] = inv_data.get("status")
            if state.get("selected_invoice"):
                state["selected_invoice"]["status"] = inv_data.get("status")

    elif tool_name == "verify_invoice" and isinstance(result, dict):
        state["verification"] = result.get("checks", {})


# ── Node: VERIFY ──────────────────────────────────────────────────────────────

def node_verify(state: AgentState) -> AgentState:
    """
    Independent verification: validates operations against ground truth.
    Runs after the planner signals DONE.
    """
    wf = state.get("workflow", "invoice")

    if wf == "po_reconciliation":
        reconciliation = state.get("reconciliation", {})
        comparisons = reconciliation.get("comparisons") or state.get("comparisons", {})
        discrepancies = reconciliation.get("discrepancies") or state.get("discrepancies", [])

        checks = {}
        for comp_name, comp_data in comparisons.items():
            if isinstance(comp_data, dict):
                is_match = comp_data.get("match", False)
                if is_match:
                    checks[comp_name] = "PASS"
                else:
                    reason = comp_data.get("reason") or f"Mismatch: expected={comp_data.get('expected')}, got={comp_data.get('actual')}"
                    checks[comp_name] = f"FAIL ({reason})"

        matched_po = state.get("matched_po")
        if matched_po:
            checks["po_matched"] = "PASS"
        else:
            checks["po_matched"] = "FAIL (No matching PO located)"

        if discrepancies:
            # Check if invoice was appropriately flagged in finance system
            inv_id = state.get("invoice_id")
            from app.tools.finance_tools import get_invoice
            r_inv = get_invoice(inv_id) if inv_id else {}
            curr_st = r_inv.get("data", {}).get("status") if r_inv.get("ok") else None
            if curr_st == "flagged":
                checks["discrepancy_action"] = "PASS (Invoice flagged)"
            else:
                checks["discrepancy_action"] = "FAIL (Invoice not flagged despite discrepancies)"
        else:
            checks["discrepancy_action"] = "PASS (Clean match)"

        state["verification"] = checks

        ledger_record(
            task_id=state["task_id"],
            step=state["current_step"],
            action="independent_reconciliation_verify",
            tool_name="verify_po_reconciliation",
            inputs={"invoice_id": state.get("invoice_id"), "po_id": state.get("po_id")},
            outputs={"checks": checks, "discrepancies": discrepancies},
            status="ok",
            notes="Independent PO reconciliation verification",
        )

        if not matched_po:
            state["status"] = "failed"
            state["errors"].append("Reconciliation failed: No matching PO located")
        else:
            state["status"] = "completed"

        state["summary"] = _build_summary(state)
        _save_state(state["task_id"], state)
        return state

    # Otherwise: invoice entry workflow
    if not state.get("invoice_id") and wf == "invoice":
        state["status"] = "completed"
        state["summary"] = _build_summary(state)
        return state

    if state.get("invoice_id"):
        extracted = state.get("extracted", {})
        expected = {
            "invoice_number": extracted.get("invoice_number"),
            "amount": extracted.get("amount"),
            "currency": extracted.get("currency", "INR"),
            "vendor_id": state.get("vendor_info", {}).get("vendors", [{}])[0].get("id") if state.get("vendor_info") else None,
        }
        if extracted.get("due_date"):
            expected["due_date"] = extracted.get("due_date")
        if extracted.get("status"):
            expected["status"] = extracted.get("status")

        from app.tools.finance_tools import verify_invoice
        ver = verify_invoice(state["invoice_id"], expected)
        state["verification"] = ver.get("checks", {})

        ledger_record(
            task_id=state["task_id"],
            step=state["current_step"],
            action="independent_verify",
            tool_name="verify_invoice",
            inputs={"invoice_id": state["invoice_id"], "expected": expected},
            outputs=ver,
            status="ok" if ver.get("all_pass") else "fail",
            notes="Independent post-write verification",
        )

        if not ver.get("all_pass"):
            fails = [k for k, v in ver.get("checks", {}).items() if "FAIL" in str(v)]
            state["errors"].append(f"Verification failed on: {fails}")
            state["status"] = "failed"
            state["summary"] = f"Verification failed: {fails}"
            return state

    state["status"] = "completed"
    state["summary"] = _build_summary(state)
    _save_state(state["task_id"], state)
    return state


def _build_summary(state: AgentState) -> str:
    parts = [f"Task: {state['request'][:80]}"]
    wf = state.get("workflow", "invoice")
    if wf == "po_reconciliation":
        selected_inv = state.get("selected_invoice", {})
        matched_po = state.get("matched_po", {})
        inv_num = selected_inv.get("invoice_number") or state.get("extracted", {}).get("invoice_number", f"ID={state.get('invoice_id')}")
        po_num = matched_po.get("po_number") or state.get("extracted", {}).get("po_number", "PO")
        discrepancies = state.get("discrepancies", [])
        if discrepancies:
            parts.append(f"Reconciliation: Discrepancy flagged for {inv_num} vs {po_num} ({'; '.join(discrepancies)})")
        else:
            parts.append(f"Reconciliation: Clean match between {inv_num} and {po_num}")
    else:
        if state.get("invoice_id"):
            parts.append(f"Invoice created: ID={state['invoice_id']}")

    if state.get("verification"):
        checks = state["verification"]
        evaluated = [k for k, v in checks.items() if v != "NOT_CHECKED"]
        passed = sum(1 for k in evaluated if checks[k] == "PASS" or str(checks[k]).startswith("PASS"))
        parts.append(f"Verification: {passed}/{len(evaluated)} checks passed")

    if state.get("errors"):
        parts.append(f"Errors: {'; '.join(state['errors'][-3:])}")
    return " | ".join(parts)


# ── Node: RECOVER AFTER TIMEOUT ───────────────────────────────────────────────

def node_recover_timeout(state: AgentState) -> AgentState:
    """
    After a timeout during a write, check the DB to see if the record exists.
    If it does, don't retry the write — just record the evidence and continue.
    If it doesn't, it's safe to retry.
    """
    # Find the last timed-out tool call
    timeout_steps = [s for s in state["steps"] if s.get("status") == "timeout"]
    if not timeout_steps:
        return state

    last = timeout_steps[-1]
    tool_name = last["tool"]
    args = last["args"]

    if tool_name == "create_invoice":
        idem_key = args.get("idempotency_key")
        if idem_key:
            from app.tools.finance_tools import _get
            # Check if an invoice with this idempotency key already exists
            result = _get("/invoices", {"idempotency_key": idem_key})
            if result.get("ok") and result.get("data"):
                invoices = result["data"]
                matching = [i for i in invoices if i.get("idempotency_key") == idem_key]
                if matching:
                    # Write DID succeed — don't retry
                    state["invoice_id"] = matching[0]["id"]
                    state["steps"][-1]["status"] = "recovered"
                    ledger_record(state["task_id"], state["current_step"],
                                  "timeout_recovery", notes=f"Write succeeded, found invoice {state['invoice_id']}")
                    state["_next"] = "continue"
                    return state

    # Write did not succeed — safe to retry on next EXECUTE call
    ledger_record(state["task_id"], state["current_step"],
                  "timeout_recovery", notes="Write not found, will retry")
    state["_next"] = "continue"
    return state


# ── Routing functions ─────────────────────────────────────────────────────────

def route_after_execute(state: AgentState) -> str:
    st = state["status"]
    nxt = state.get("_next", "continue")

    if st in ("failed", "needs_input", "waiting_approval"):
        return "end"
    if nxt == "verify":
        return "verify"
    if nxt == "recover_after_timeout":
        return "recover"
    return "execute"   # keep looping


def route_after_recover(state: AgentState) -> str:
    return "execute"


# ── Build the LangGraph ───────────────────────────────────────────────────────

def build_graph():
    g = StateGraph(AgentState)
    g.add_node("understand", node_understand)
    g.add_node("execute", node_execute)
    g.add_node("verify", node_verify)
    g.add_node("recover", node_recover_timeout)

    g.set_entry_point("understand")
    g.add_edge("understand", "execute")
    g.add_conditional_edges("execute", route_after_execute, {
        "execute": "execute",
        "verify":  "verify",
        "recover": "recover",
        "end":     END,
    })
    g.add_conditional_edges("recover", route_after_recover, {
        "execute": "execute",
    })
    g.add_edge("verify", END)

    return g.compile()


_graph = build_graph()


# ── Public entry point ────────────────────────────────────────────────────────

def run_task(task_id: str, request: str, workflow: str, resume: bool = False):
    """
    Main entry point called by the background task.
    If resume=True, reload persisted state (post-approval resumption).
    """
    import app.tools  # ensure tools are wired

    if resume:
        state = _load_state(task_id)
        if not state:
            state = initial_state(task_id, request, workflow)
        # Reset status so the graph continues
        state["status"] = "running"
        state["approval_requested"] = False  # approval was granted
    else:
        state = initial_state(task_id, request, workflow)

    try:
        final_state = _graph.invoke(state)
        _save_state(task_id, final_state)
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[graph] Unhandled error in task {task_id}: {e}\n{tb}")
        db = _db.SessionLocal()
        try:
            task = db.get(Task, task_id)
            if task:
                task.status = "failed"
                task.state_json = {"error": str(e), "traceback": tb}
                db.commit()
        finally:
            db.close()
