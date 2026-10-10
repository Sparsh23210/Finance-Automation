"""
llm.py - Thin adapter over Google Gemini.
All LLM calls go through this module so swapping providers = editing one file.

Key safety rules enforced here:
1. Model output is always parsed and validated before use.
2. Rate-limit and timeout errors are raised as plain exceptions.
3. API keys are never logged.
"""
import json
import re
from typing import Any

from app.config import GEMINI_API_KEY, GEMINI_MODEL, LLM_ENABLED

if LLM_ENABLED:
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    _model = genai.GenerativeModel(GEMINI_MODEL)


def _call(prompt: str, max_tokens: int = 2048) -> str:
    """Raw call to the LLM. Returns the text content."""
    if not LLM_ENABLED:
        raise RuntimeError("LLM not configured (GEMINI_API_KEY missing)")
    response = _model.generate_content(
        prompt,
        generation_config={"max_output_tokens": max_tokens, "temperature": 0.1},
    )
    return response.text


def _extract_json(text: str) -> Any:
    """Extract the first JSON object or array from LLM output."""
    # Try plain parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Find JSON block in markdown code fences
    match = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # Find first { } or [ ] block
    match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    raise ValueError(f"No valid JSON found in LLM response: {text[:300]}")


def understand_task(request: str, workflow: str) -> dict[str, Any]:
    """
    Convert a natural-language request into a structured goal.
    Returns dict with: task_type, entity, required_fields, success_conditions,
    allowed_actions, approval_required, amount_threshold.
    """
    prompt = f"""
You are a task parser for a finance automation system.
Parse the following user request and return a JSON object.

User request: "{request}"
Workflow type: {workflow}

Return ONLY valid JSON with these fields:
{{
  "task_type": "invoice_entry | po_reconciliation | status_update | unknown",
  "entity": "vendor name or null",
  "invoice_number": "specific invoice number if mentioned or null",
  "required_fields": ["list of fields the task needs"],
  "success_conditions": ["list of conditions that mean the task succeeded"],
  "allowed_actions": ["list of tool names from: search_files, read_document, extract_invoice_fields, find_vendor, search_invoices, get_invoice, create_invoice, update_invoice_status, get_purchase_order, compare_invoice_with_po, verify_invoice, request_approval"],
  "approval_required": true or false,
  "amount_threshold": number or null,
  "currency": "INR or null",
  "notes": "any important caveats"
}}

Be conservative: only include actions that are clearly needed.
"""
    text = _call(prompt)
    return _extract_json(text)


def plan_next_action(state: dict) -> dict[str, Any]:
    """
    Given the current task state, decide the next tool to call.
    Returns: {{ "tool": "tool_name", "args": {{}}, "reason": "..." }}
    or {{ "tool": "DONE", "reason": "..." }}
    or {{ "tool": "NEEDS_INPUT", "question": "..." }}
    """
    available_tools = state.get("goal", {}).get("allowed_actions", [])
    prompt = f"""
You are an autonomous finance agent. Based on the current task state below,
decide the SINGLE next action to take.

Task: {state.get('request')}
Goal: {json.dumps(state.get('goal', {}), indent=2)}
Steps completed: {json.dumps(state.get('steps', []), indent=2)}
Errors so far: {json.dumps(state.get('errors', []), indent=2)}
Available tools: {available_tools}

Return ONLY valid JSON:
{{
  "tool": "tool_name or DONE or NEEDS_INPUT or REQUEST_APPROVAL",
  "args": {{}},
  "reason": "why this action"
}}

Rules:
- Choose DONE only if all success_conditions are met and verified.
- Choose NEEDS_INPUT if critical information is missing and no tool can find it.
- Choose REQUEST_APPROVAL if a sensitive write requires human approval.
- Do not repeat a tool call with the same args if it already succeeded.
- Always verify after creating a record before marking DONE.
"""
    text = _call(prompt)
    return _extract_json(text)


def extract_with_llm(text: str) -> dict[str, Any]:
    """Use the LLM to extract invoice fields from raw document text."""
    prompt = f"""
Extract invoice fields from the following document text.
Return ONLY valid JSON. Use null for any field you cannot find.
Never invent or guess values — only extract what is explicitly stated.

Document text:
---
{text[:3000]}
---

Return:
{{
  "invoice_number": "string or null",
  "vendor_name": "string or null",
  "invoice_date": "YYYY-MM-DD or null",
  "due_date": "YYYY-MM-DD or null",
  "amount": "decimal string like '50000.00' or null",
  "currency": "INR or USD etc or null",
  "description": "string or null",
  "_extraction_method": "llm"
}}
"""
    text_out = _call(prompt)
    return _extract_json(text_out)
