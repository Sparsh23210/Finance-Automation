"""
planner.py - Task understanding and action planning.

Two modes:
1. LLM mode: uses Gemini to parse the request and suggest next actions.
2. Deterministic mode: rule-based planner used when GEMINI_API_KEY is not set.
   This is clearly labelled as non-LLM behavior.

The planner only SUGGESTS the next tool. The agent graph validates and executes it.
"""
import re
import json
from datetime import datetime
from typing import Any

from app.config import LLM_ENABLED


# ── Date Helpers ──────────────────────────────────────────────────────────────

def parse_date_safe(date_str: Any) -> datetime | None:
    """Safely parse date strings into datetime objects across multiple common formats."""
    if not date_str or not isinstance(date_str, str):
        return None
    d = date_str.strip()
    formats = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y/%m/%d",
        "%m/%d/%Y",
        "%b %d, %Y",
        "%d %b %Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(d[:10], fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(d.replace("Z", "+00:00"))
    except Exception:
        return None


def select_latest_invoice(invoices: list[dict], target_number: str | None = None) -> tuple[dict | None, str]:
    """
    Selects the appropriate invoice from candidate invoices:
    - If target_number is specified, selects by exact invoice_number match.
    - Otherwise, selects the newest valid invoice based on parsed invoice_date.
    - Never confuses database insertion order, ID, or file order with invoice date.
    - Explicitly handles missing/invalid dates.
    Returns (selected_invoice, reason_note).
    """
    if not invoices:
        return None, "No candidate invoices provided"

    # 1. Exact invoice number if specified
    if target_number:
        clean_target = str(target_number).strip().upper()
        for inv in invoices:
            if str(inv.get("invoice_number", "")).strip().upper() == clean_target:
                return inv, f"Matched requested invoice identifier {target_number}"

    # 2. Sort by parsed invoice date descending
    with_dates = []
    without_dates = []
    for inv in invoices:
        dt = parse_date_safe(inv.get("invoice_date"))
        if dt:
            with_dates.append((dt, inv))
        else:
            without_dates.append(inv)

    if with_dates:
        # Sort descending so newest date is first
        with_dates.sort(key=lambda x: x[0], reverse=True)
        chosen = with_dates[0][1]
        chosen_date = with_dates[0][0].strftime("%Y-%m-%d")
        return chosen, f"Selected latest valid invoice by date: {chosen.get('invoice_number')} ({chosen_date})"

    if without_dates:
        return without_dates[0], "No valid invoice dates found; selected first available candidate"

    return None, "No valid invoices found"


# ── Deterministic planner (no LLM) ───────────────────────────────────────────

def _det_understand(request: str, workflow: str) -> dict[str, Any]:
    """
    Simple keyword-based task parser.
    Not intelligent — just enough for demo and testing without an API key.
    """
    req_lower = request.lower()

    # Detect vendor name heuristically (after "from" keyword)
    entity = None
    for kw in ["from ", "for ", "by "]:
        idx = req_lower.find(kw)
        if idx != -1:
            raw = request[idx + len(kw):idx + len(kw) + 60]
            raw = re.split(r"[,;.]", raw)[0].strip()
            # Stop if words indicate actions rather than company name
            words = []
            for w in raw.split()[:4]:
                if w.lower() in ("locate", "extract", "find", "compare", "enter", "and", "flag"):
                    break
                words.append(w)
            if words:
                entity = " ".join(words).strip()
            break

    # Detect specific invoice number in request if present
    inv_num_m = re.search(r"\b(INV-[A-Z0-9\-]+|[A-Z]{2,6}-[A-Z0-9\-]{3,20})\b", request)
    inv_num = inv_num_m.group(1).upper() if inv_num_m else None

    # Detect amount threshold
    threshold = None
    m = re.search(r"(?:inr|₹|rs\.?)\s*([\d,]+)", req_lower)
    if m:
        threshold = float(m.group(1).replace(",", ""))

    # Detect if request is asking for PO reconciliation
    is_po = (
        workflow == "po_reconciliation"
        or any(kw in req_lower for kw in [
            "purchase order", "matching po", "compare", "reconcil", "discrepanc", "po reference"
        ])
    )

    if is_po:
        task_type = "po_reconciliation"
        allowed = ["search_files", "read_document", "extract_invoice_fields",
                   "find_vendor", "search_invoices", "get_purchase_order",
                   "compare_invoice_with_po", "update_invoice_status", "verify_invoice"]
    else:
        task_type = "invoice_entry"
        allowed = ["search_files", "read_document", "extract_invoice_fields",
                   "find_vendor", "search_invoices", "get_invoice",
                   "create_invoice", "update_invoice_status",
                   "verify_invoice", "request_approval"]

    return {
        "task_type": task_type,
        "entity": entity,
        "invoice_number": inv_num,
        "required_fields": ["invoice_number", "vendor_name", "amount", "due_date"],
        "success_conditions": ["invoice_stored", "verification_passed"] if not is_po else ["reconciliation_complete"],
        "allowed_actions": allowed,
        "approval_required": threshold is not None,
        "amount_threshold": threshold,
        "currency": "INR",
        "notes": "Parsed by deterministic rule-based planner (no LLM)",
        "_mode": "deterministic",
    }


def _det_next_action(state: dict) -> dict[str, Any]:
    """
    Deterministic step-by-step planner for invoice_entry workflow.
    Looks at what has been completed and returns the next logical step.
    """
    steps = state.get("steps", [])
    completed_tools = {s["tool"] for s in steps if s.get("status") == "ok"}
    workflow = state.get("workflow", "invoice")
    extracted = state.get("extracted", {})
    vendor_info = state.get("vendor_info")
    invoice_id = state.get("invoice_id")

    entity = state.get("goal", {}).get("entity", "")

    if workflow == "po_reconciliation" or state.get("goal", {}).get("task_type") == "po_reconciliation":
        return _det_po_plan(completed_tools, state)

    # Invoice entry workflow steps in order
    if "search_files" not in completed_tools:
        return {"tool": "search_files", "args": {"query": entity or "invoice"}, "reason": "Find invoice documents"}

    if "read_document" not in completed_tools:
        docs = state.get("documents", [])
        if not docs:
            return {"tool": "NEEDS_INPUT", "question": "No invoice documents found. Please provide a filename.", "reason": "No documents"}
        # Prefer invoice files over vendor files
        invoice_docs = [d for d in docs if "invoice" in d["file"].lower() or d["file"].lower().endswith(".txt")]
        pick = invoice_docs[0] if invoice_docs else docs[0]

        # If user asked for 'latest', inspect candidate invoice files to pick the newest by date
        if "latest" in state.get("request", "").lower() and len(invoice_docs) > 1:
            from app.tools.files import read_document as _read_doc, extract_invoice_fields as _ext_fields
            dated_docs = []
            for d in invoice_docs:
                r = _read_doc(d["file"])
                if r.get("content"):
                    f = _ext_fields(r["content"], use_llm=False)
                    dt = parse_date_safe(f.get("invoice_date"))
                    if dt:
                        dated_docs.append((dt, d))
            if dated_docs:
                dated_docs.sort(key=lambda x: x[0], reverse=True)
                pick = dated_docs[0][1]

        return {"tool": "read_document", "args": {"filename": pick["file"]}, "reason": "Read invoice document"}

    if "extract_invoice_fields" not in completed_tools:
        # Get text from last successful read_document step
        content = ""
        for s in reversed(steps):
            if s["tool"] == "read_document" and s.get("status") == "ok":
                r = s.get("result", {})
                c = r.get("content", "") if isinstance(r, dict) else ""
                if isinstance(c, str) and len(c) > 20:  # must have real content
                    content = c
                    break
        if not content:
            return {"tool": "NEEDS_INPUT", "question": "Could not read document content.", "reason": "No content"}
        return {"tool": "extract_invoice_fields", "args": {"text": content, "use_llm": False}, "reason": "Extract fields from document"}

    if "find_vendor" not in completed_tools:
        vendor_name = extracted.get("vendor_name") or entity or ""
        if not vendor_name:
            return {"tool": "NEEDS_INPUT", "question": "What is the vendor name?", "reason": "Missing vendor"}
        return {"tool": "find_vendor", "args": {"name": vendor_name}, "reason": "Resolve vendor ID"}

    if vendor_info and vendor_info.get("ambiguous"):
        return {"tool": "NEEDS_INPUT", "question": f"Multiple vendors found: {[v['name'] for v in vendor_info.get('vendors', [])]}. Which one?", "reason": "Ambiguous vendor"}

    if "create_invoice" not in completed_tools and not invoice_id:
        v = vendor_info.get("vendors", [{}])[0] if vendor_info else {}
        amount = extracted.get("amount")
        if not amount:
            return {"tool": "NEEDS_INPUT", "question": "Invoice amount not found in document.", "reason": "Missing amount"}

        # Check threshold
        from app.agent.policy import check_amount_threshold
        pol = check_amount_threshold(amount)
        if pol.get("requires_approval") and not state.get("approval_requested"):
            return {
                "tool": "request_approval",
                "args": {
                    "action": "create_invoice",
                    "justification": f"Amount ₹{amount} exceeds threshold",
                    "proposed_data": {
                        "invoice_number": extracted.get("invoice_number"),
                        "vendor_id": v.get("id"),
                        "amount": amount,
                    },
                },
                "reason": "Amount exceeds threshold, need approval",
            }

        idem_key = f"{state['task_id']}-{extracted.get('invoice_number', 'unknown')}"
        return {
            "tool": "create_invoice",
            "args": {
                "invoice_number": extracted.get("invoice_number", "UNKNOWN"),
                "vendor_id": v.get("id"),
                "amount": str(amount),
                "currency": extracted.get("currency", "INR"),
                "invoice_date": extracted.get("invoice_date"),
                "due_date": extracted.get("due_date"),
                "description": extracted.get("description"),
                "source_ref": state.get("documents", [{}])[0].get("file") if state.get("documents") else None,
                "idempotency_key": idem_key,
            },
            "reason": "Create invoice in finance system",
        }

    if "verify_invoice" not in completed_tools and invoice_id:
        return {
            "tool": "verify_invoice",
            "args": {
                "invoice_id": invoice_id,
                "expected": {
                    "invoice_number": extracted.get("invoice_number"),
                    "amount": extracted.get("amount"),
                    "currency": extracted.get("currency", "INR"),
                    "due_date": extracted.get("due_date"),
                },
            },
            "reason": "Independently verify the stored record",
        }

    # Check threshold flagging
    amount = extracted.get("amount")
    if amount and invoice_id:
        from app.agent.policy import check_amount_threshold
        pol = check_amount_threshold(amount)
        if pol.get("requires_approval"):
            flag_done = any(s["tool"] == "update_invoice_status" and s.get("status") == "ok" for s in steps)
            if not flag_done:
                return {
                    "tool": "update_invoice_status",
                    "args": {"invoice_id": invoice_id, "status": "flagged"},
                    "reason": "Flag invoice because amount exceeds threshold",
                }

    return {"tool": "DONE", "reason": "All steps completed and verified"}


def _det_po_plan(completed_tools: set, state: dict) -> dict[str, Any]:
    """
    Deterministic step-by-step planner for purchase-order reconciliation.
    Identifies the correct vendor, finds the latest valid invoice by date,
    retrieves the matching PO reference, and compares fields to flag discrepancies.
    """
    steps = state.get("steps", [])
    entity = state.get("goal", {}).get("entity", "")
    target_inv_num = state.get("goal", {}).get("invoice_number")
    extracted = state.get("extracted", {})

    # Step 1: Find vendor
    if "find_vendor" not in completed_tools:
        return {"tool": "find_vendor", "args": {"name": entity or ""}, "reason": "Find vendor"}

    vendor = state.get("vendor_info", {})
    vid = vendor.get("vendors", [{}])[0].get("id") if vendor else None

    # Step 2: Search invoices for this vendor
    if "search_invoices" not in completed_tools:
        return {"tool": "search_invoices", "args": {"vendor_id": vid}, "reason": "Find invoices for vendor"}

    candidate_invoices = state.get("candidate_invoices", [])
    if not candidate_invoices:
        for s in reversed(steps):
            if s["tool"] == "search_invoices" and s.get("status") == "ok":
                candidate_invoices = s.get("result", {}).get("data", [])
                break

    if not candidate_invoices:
        return {"tool": "NEEDS_INPUT", "question": f"No invoices found in database for vendor '{entity}'.", "reason": "No invoices"}

    # Ensure invoice is selected using select_latest_invoice
    inv = state.get("selected_invoice")
    if not inv:
        inv, _ = select_latest_invoice(candidate_invoices, target_number=target_inv_num)
        if inv:
            state["selected_invoice"] = inv
            state["invoice_id"] = inv["id"]

    inv_id = state.get("invoice_id")
    if not inv_id:
        return {"tool": "NEEDS_INPUT", "question": "Could not select a valid invoice to reconcile.", "reason": "No invoice selected"}

    # Step 3: Find PO Reference
    po_ref = extracted.get("po_reference")
    source_ref = inv.get("source_ref") or f"invoices/{inv.get('invoice_number')}.txt"

    if not po_ref and "read_document" not in completed_tools:
        # Check if invoice has a file to read
        docs = state.get("documents", [])
        matching_file = None
        for d in docs:
            if inv.get("invoice_number", "").lower() in d.get("file", "").lower():
                matching_file = d.get("file")
                break
        if not matching_file:
            matching_file = source_ref

        return {"tool": "read_document", "args": {"filename": matching_file}, "reason": "Read invoice document to extract PO reference"}

    if not po_ref and "extract_invoice_fields" not in completed_tools:
        content = ""
        for s in reversed(steps):
            if s["tool"] == "read_document" and s.get("status") == "ok":
                r = s.get("result", {})
                content = r.get("content", "") if isinstance(r, dict) else ""
                break
        if content:
            return {"tool": "extract_invoice_fields", "args": {"text": content, "use_llm": False}, "reason": "Extract PO reference and fields"}

    # Step 4: Locate matching purchase order
    po_ref = state.get("extracted", {}).get("po_reference")
    if "get_purchase_order" not in completed_tools:
        if po_ref:
            return {"tool": "get_purchase_order", "args": {"po_number": po_ref}, "reason": f"Locate referenced purchase order '{po_ref}'"}
        elif vid:
            return {"tool": "get_purchase_order", "args": {"vendor_id": vid}, "reason": "Find purchase orders for vendor"}
        else:
            return {"tool": "NEEDS_INPUT", "question": "No PO reference found on invoice.", "reason": "Missing PO reference"}

    po_id = state.get("po_id")
    if not po_id:
        po_step = next((s for s in reversed(steps) if s["tool"] == "get_purchase_order"), None)
        err = po_step.get("result", {}).get("error", "No matching PO exists") if po_step else "PO not found"
        return {"tool": "DONE", "reason": f"No matching purchase order exists: {err}"}

    # Step 5: Compare invoice with PO
    if "compare_invoice_with_po" not in completed_tools:
        return {"tool": "compare_invoice_with_po", "args": {"invoice_id": inv_id, "po_id": po_id}, "reason": "Compare invoice fields against purchase order"}

    # Step 6: If discrepancies detected, flag the invoice
    discrepancies = state.get("discrepancies", [])
    if discrepancies and "update_invoice_status" not in completed_tools:
        return {
            "tool": "update_invoice_status",
            "args": {"invoice_id": inv_id, "status": "flagged"},
            "reason": f"Flag invoice due to discrepancies: {'; '.join(discrepancies)}",
        }

    return {"tool": "DONE", "reason": "Purchase order reconciliation complete"}


# ── Public API ────────────────────────────────────────────────────────────────

def understand_task(request: str, workflow: str) -> dict[str, Any]:
    if LLM_ENABLED:
        try:
            from app.agent.llm import understand_task as llm_understand
            result = llm_understand(request, workflow)
            result["_mode"] = "llm"
            return result
        except Exception as e:
            print(f"[planner] LLM understanding failed ({e}), using deterministic fallback")
    return _det_understand(request, workflow)


def plan_next_action(state: dict) -> dict[str, Any]:
    if LLM_ENABLED:
        try:
            from app.agent.llm import plan_next_action as llm_plan
            return llm_plan(state)
        except Exception as e:
            print(f"[planner] LLM planning failed ({e}), using deterministic fallback")
    return _det_next_action(state)
