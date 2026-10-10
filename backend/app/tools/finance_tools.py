"""
finance_tools.py - Tools that call the Finance API.
The agent uses these wrappers rather than hitting the DB directly.
This keeps the agent side stateless and the persistence layer encapsulated.
"""
import os
from decimal import Decimal, InvalidOperation
from typing import Any

# Optional remote finance API base URL (if deployed on separate host/port)
REMOTE_FINANCE_BASE = os.getenv("REMOTE_FINANCE_BASE", "")
_local_client = None


def _get_local_client():
    global _local_client
    if _local_client is None:
        from fastapi.testclient import TestClient
        from app.main import app
        _local_client = TestClient(app, base_url="http://localhost:8000/finance", raise_server_exceptions=False)
    return _local_client


def _req(method: str, path: str, params: dict = None, json: dict = None) -> dict[str, Any]:
    try:
        if REMOTE_FINANCE_BASE:
            import httpx
            with httpx.Client(base_url=REMOTE_FINANCE_BASE, timeout=10) as c:
                r = c.request(method, path, params=params, json=json)
        else:
            client = _get_local_client()
            r = client.request(method, path, params=params, json=json)

        if r.is_success:
            try:
                return {"ok": True, "data": r.json()}
            except Exception:
                return {"ok": True, "data": r.text}
        else:
            return {"ok": False, "error": r.text, "status_code": r.status_code}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _get(path: str, params: dict = None) -> dict[str, Any]:
    return _req("GET", path, params=params)


def _post(path: str, body: dict) -> dict[str, Any]:
    return _req("POST", path, json=body)


def _patch(path: str, body: dict) -> dict[str, Any]:
    return _req("PATCH", path, json=body)


# ── Public tool functions ─────────────────────────────────────────────────────

def find_vendor(name: str) -> dict[str, Any]:
    """Search vendors by name. Returns all partial matches."""
    result = _get("/vendors", {"name": name})
    if not result["ok"]:
        return result
    vendors = result["data"]
    if not vendors:
        return {"ok": True, "vendors": [], "ambiguous": False, "message": f"No vendor found matching '{name}'"}
    if len(vendors) > 1:
        return {
            "ok": True,
            "vendors": vendors,
            "ambiguous": True,
            "message": f"Multiple vendors matched '{name}': {[v['name'] for v in vendors]}",
        }
    return {"ok": True, "vendors": vendors, "ambiguous": False, "message": "Found 1 vendor"}


def search_invoices(vendor_id: int = None, invoice_number: str = None, status: str = None) -> dict[str, Any]:
    params = {}
    if vendor_id:
        params["vendor_id"] = vendor_id
    if invoice_number:
        params["invoice_number"] = invoice_number
    if status:
        params["status"] = status
    return _get("/invoices", params)


def get_invoice(invoice_id: int) -> dict[str, Any]:
    return _get(f"/invoices/{invoice_id}")


def create_invoice(
    invoice_number: str,
    vendor_id: int,
    amount: str,
    currency: str = "INR",
    invoice_date: str = None,
    due_date: str = None,
    description: str = None,
    source_ref: str = None,
    idempotency_key: str = None,
) -> dict[str, Any]:
    """
    Create an invoice. Always pass an idempotency_key derived from
    task_id + invoice_number so retries after timeout don't create duplicates.
    """
    # Validate amount is a parseable decimal before sending
    try:
        Decimal(amount)
    except InvalidOperation:
        return {"ok": False, "error": f"Invalid amount: '{amount}'"}

    body = {
        "invoice_number": invoice_number,
        "vendor_id": vendor_id,
        "amount": amount,
        "currency": currency,
        "invoice_date": invoice_date,
        "due_date": due_date,
        "description": description,
        "source_ref": source_ref,
        "idempotency_key": idempotency_key,
    }
    return _post("/invoices", body)


def update_invoice_status(invoice_id: int, status: str) -> dict[str, Any]:
    return _patch(f"/invoices/{invoice_id}/status", {"status": status})


def get_purchase_order(po_id: int = None, po_number: str = None, vendor_id: int = None) -> dict[str, Any]:
    if po_id:
        return _get(f"/purchase-orders/{po_id}")
    if po_number:
        result = _get("/purchase-orders")
        if not result["ok"]:
            return result
        target = str(po_number).strip().upper()
        for po in result["data"]:
            if str(po.get("po_number", "")).strip().upper() == target:
                return {"ok": True, "data": po}
        return {"ok": False, "error": f"PO '{po_number}' not found"}
    if vendor_id:
        result = _get("/purchase-orders", {"vendor_id": vendor_id})
        if not result["ok"]:
            return result
        pos = result.get("data", [])
        if pos:
            return {"ok": True, "data": pos[0], "all": pos}
        return {"ok": False, "error": f"No purchase orders found for vendor {vendor_id}"}
    return {"ok": False, "error": "Provide po_id, po_number, or vendor_id"}


def compare_invoice_with_po(invoice_id: int, po_id: int) -> dict[str, Any]:
    """
    Compare an invoice against a purchase order.
    Returns field-level comparison results and a list of discrepancies.
    """
    inv_result = _get(f"/invoices/{invoice_id}")
    po_result  = _get(f"/purchase-orders/{po_id}")

    if not inv_result["ok"]:
        return {"ok": False, "error": f"Invoice error: {inv_result.get('error', 'not found')}"}
    if not po_result["ok"]:
        return {"ok": False, "error": f"PO error: {po_result.get('error', 'not found')}"}

    inv = inv_result["data"]
    po  = po_result["data"]

    # Compare amounts as Decimal to avoid float issues
    inv_amount = Decimal(str(inv["amount"]))
    po_amount  = Decimal(str(po["amount"]))

    discrepancies = []
    comparisons = {}

    # Vendor match
    vendor_match = inv["vendor_id"] == po["vendor_id"]
    comparisons["vendor"] = {
        "invoice": inv["vendor_id"],
        "po": po["vendor_id"],
        "expected": po.get("vendor_name") or po.get("vendor_id"),
        "actual": inv.get("vendor_name") or inv.get("vendor_id"),
        "match": vendor_match,
        "reason": None if vendor_match else f"Vendor ID mismatch: Invoice vendor {inv.get('vendor_id')} != PO vendor {po.get('vendor_id')}",
    }
    if not vendor_match:
        discrepancies.append(comparisons["vendor"]["reason"])

    # Amount match (within 1 paise tolerance for rounding)
    amount_diff = abs(inv_amount - po_amount)
    amount_match = amount_diff <= Decimal("0.01")
    amt_reason = None if amount_match else f"Amount mismatch: Invoice ₹{inv_amount:,.2f} differs from PO ₹{po_amount:,.2f} by ₹{amount_diff:,.2f}"
    comparisons["amount"] = {
        "invoice": str(inv_amount),
        "po": str(po_amount),
        "expected": str(po_amount),
        "actual": str(inv_amount),
        "difference": str(amount_diff),
        "match": amount_match,
        "reason": amt_reason,
    }
    if not amount_match:
        discrepancies.append(amt_reason)

    # Currency match
    curr_match = str(inv.get("currency", "")).upper() == str(po.get("currency", "")).upper()
    curr_reason = None if curr_match else f"Currency mismatch: {inv.get('currency')} != {po.get('currency')}"
    comparisons["currency"] = {
        "invoice": inv.get("currency"),
        "po": po.get("currency"),
        "expected": po.get("currency"),
        "actual": inv.get("currency"),
        "match": curr_match,
        "reason": curr_reason,
    }
    if not curr_match:
        discrepancies.append(curr_reason)

    # Date sequence
    inv_date = inv.get("invoice_date")
    po_date = po.get("po_date")
    date_match = True
    date_reason = None
    if inv_date and po_date:
        try:
            from datetime import datetime
            d_inv = datetime.strptime(inv_date[:10], "%Y-%m-%d")
            d_po = datetime.strptime(po_date[:10], "%Y-%m-%d")
            if d_inv < d_po:
                date_match = False
                date_reason = f"Invoice date ({inv_date}) predates PO date ({po_date})"
        except Exception:
            pass

    comparisons["date_order"] = {
        "invoice": inv_date,
        "po": po_date,
        "expected": f"On or after PO date ({po_date})",
        "actual": inv_date,
        "match": date_match,
        "reason": date_reason,
    }
    if not date_match and date_reason:
        discrepancies.append(date_reason)

    return {
        "ok": True,
        "invoice_id": invoice_id,
        "po_id": po_id,
        "invoice_number": inv.get("invoice_number"),
        "po_number": po.get("po_number"),
        "comparisons": comparisons,
        "discrepancies": discrepancies,
        "clean": len(discrepancies) == 0,
    }


def verify_invoice(invoice_id: int, expected: dict) -> dict[str, Any]:
    """
    Read the stored invoice back from the DB and compare against expected values.
    Returns per-field PASS/FAIL/NOT_CHECKED results.
    This is called by the verifier — independent of whatever the LLM said.
    """
    result = _get(f"/invoices/{invoice_id}")
    if not result["ok"]:
        return {"ok": False, "checks": {}, "error": result["error"]}

    stored = result["data"]
    checks = {}

    for field in ["invoice_number", "vendor_id", "amount", "currency", "due_date", "status"]:
        if field not in expected or expected[field] is None:
            checks[field] = "NOT_CHECKED"
            continue
        exp_val = str(expected[field])
        got_val = str(stored.get(field, ""))
        # For amounts, compare as Decimal
        if field == "amount":
            try:
                match = abs(Decimal(exp_val) - Decimal(got_val)) <= Decimal("0.01")
            except Exception:
                match = exp_val == got_val
        else:
            match = exp_val.strip() == got_val.strip()
        checks[field] = "PASS" if match else f"FAIL (expected={exp_val}, got={got_val})"

    all_pass = all(v == "PASS" for v in checks.values() if v != "NOT_CHECKED")
    return {
        "ok": True,
        "invoice_id": invoice_id,
        "stored": stored,
        "checks": checks,
        "all_pass": all_pass,
    }
