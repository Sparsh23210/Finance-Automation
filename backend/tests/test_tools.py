"""
test_tools.py - Unit tests for file tools, finance tools, and policy engine.
These tests don't start the server — they call functions directly.
"""
import os
import pytest
from decimal import Decimal

# ── File tool tests ───────────────────────────────────────────────────────────

def test_search_files_finds_invoices():
    from app.tools.files import search_files
    result = search_files("invoice")
    assert "results" in result
    # Should find at least the sample invoice files
    assert len(result["results"]) > 0


def test_search_files_no_match():
    from app.tools.files import search_files
    result = search_files("zzz_no_match_xyz_123")
    assert result["results"] == []


def test_read_document_success():
    from app.tools.files import read_document
    result = read_document("invoices/INV-APEX-2024-001.txt")
    assert "error" not in result
    assert "Apex Supplies" in result["content"]
    assert "45,000" in result["content"]


def test_read_document_path_traversal_blocked():
    from app.tools.files import read_document
    result = read_document("../../etc/passwd")
    assert "error" in result
    assert "denied" in result["error"].lower() or "not found" in result["error"].lower()


def test_read_document_not_found():
    from app.tools.files import read_document
    result = read_document("nonexistent_file.txt")
    assert "error" in result


def test_extract_fields_regex_fallback():
    from app.tools.files import extract_invoice_fields
    text = "Invoice No: INV-TEST-999\nFrom: Test Corp\nAmount: INR 25000.00\nDate: 2024-01-15"
    result = extract_invoice_fields(text, use_llm=False)
    assert result["invoice_number"] is not None
    assert result["amount"] is not None


def test_extract_fields_no_fabrication():
    """If a field is genuinely missing, it must be None — not invented."""
    from app.tools.files import extract_invoice_fields
    text = "Some random text with no invoice data whatsoever."
    result = extract_invoice_fields(text, use_llm=False)
    # Amount should be None if not found
    assert result["amount"] is None


# ── Policy engine tests ───────────────────────────────────────────────────────

def test_threshold_below_limit():
    from app.agent.policy import check_amount_threshold
    result = check_amount_threshold("49999.99")
    assert result["requires_approval"] is False


def test_threshold_above_limit():
    from app.agent.policy import check_amount_threshold
    result = check_amount_threshold("50001.00")
    assert result["requires_approval"] is True


def test_threshold_exactly_at_limit():
    from app.agent.policy import check_amount_threshold
    # Exactly at 50,000 — NOT over, so no approval needed
    result = check_amount_threshold("50000.00")
    assert result["requires_approval"] is False


def test_threshold_over_limit():
    from app.agent.policy import check_amount_threshold
    result = check_amount_threshold("72500.00")
    assert result["requires_approval"] is True


def test_invalid_approver_rejected():
    from app.agent.policy import validate_approval, PolicyError
    with pytest.raises(PolicyError):
        validate_approval("random_person", "approved")


def test_authorized_approver_accepted():
    from app.agent.policy import validate_approval
    # Should not raise
    validate_approval("admin", "approved")


def test_error_classification_retry():
    from app.agent.policy import classify_error
    assert classify_error("Connection timeout", 0, 3) == "retry"


def test_error_classification_duplicate():
    from app.agent.policy import classify_error
    assert classify_error("409 duplicate already exists", 0, 3) == "check_duplicate"


def test_error_classification_abort():
    from app.agent.policy import classify_error
    assert classify_error("some error", 3, 3) == "abort"


def test_error_classification_permission():
    from app.agent.policy import classify_error
    assert classify_error("403 forbidden", 0, 3) == "escalate"


# ── Finance tools tests (using actual seeded DB via HTTP client) ──────────────
# These require the seeded_db fixture, so we use it indirectly via the client

def test_compare_invoice_po_clean(client, seeded_db):
    """Invoice ID 1 (₹45,000) vs PO ID 1 (₹45,000) — should match."""
    r = client.get("/finance/invoices/1")
    assert r.json()["amount"] == "45000.00"
    r2 = client.get("/finance/purchase-orders/1")
    assert r2.json()["amount"] == "45000.00"
    # Manual comparison using Decimal (no float errors)
    inv_amt = Decimal(r.json()["amount"])
    po_amt = Decimal(r2.json()["amount"])
    assert abs(inv_amt - po_amt) <= Decimal("0.01")



def test_compare_invoice_po_discrepancy(client, seeded_db):
    """Invoice ID 3 (₹32,000) vs PO ID 2 (₹30,000) — amount discrepancy."""
    inv = client.get("/finance/invoices/3").json()
    po = client.get("/finance/purchase-orders/2").json()
    inv_amt = Decimal(inv["amount"])
    po_amt = Decimal(po["amount"])
    diff = abs(inv_amt - po_amt)
    assert diff > Decimal("0.01")  # Discrepancy detected


def test_verify_invoice_pass(client, seeded_db):
    """Verify that stored values match expected — all should PASS."""
    inv = client.get("/finance/invoices/1").json()
    assert inv["invoice_number"] == "INV-APEX-2024-001"
    assert inv["amount"] == "45000.00"
    assert inv["currency"] == "INR"


def test_missing_due_date_invoice(client, seeded_db):
    """Invoice 4 has no due date — system should handle this gracefully."""
    r = client.get("/finance/invoices/4")
    assert r.status_code == 200
    assert r.json()["due_date"] is None


# ── Invoice Selection & Date Parsing Tests ────────────────────────────────────

def test_select_latest_invoice_date_ordering():
    from app.agent.planner import select_latest_invoice
    candidates = [
        {"id": 4, "invoice_number": "INV-GLOB-2024-055", "invoice_date": "2024-02-20", "amount": "28000.00"},
        {"id": 8, "invoice_number": "INV-GLOB-2024-062", "invoice_date": "2024-03-25", "amount": "32000.00"},
    ]
    # Even though 055 is first in search order, 062 is selected because 2024-03-25 > 2024-02-20
    chosen, note = select_latest_invoice(candidates)
    assert chosen["invoice_number"] == "INV-GLOB-2024-062"
    assert "2024-03-25" in note


def test_select_latest_invoice_missing_or_invalid_dates():
    from app.agent.planner import select_latest_invoice
    candidates = [
        {"id": 1, "invoice_number": "INV-BAD-DATE", "invoice_date": "invalid-date", "amount": "1000.00"},
        {"id": 2, "invoice_number": "INV-NO-DATE", "invoice_date": None, "amount": "2000.00"},
        {"id": 3, "invoice_number": "INV-VALID", "invoice_date": "2024-01-10", "amount": "3000.00"},
    ]
    # Valid date must be chosen over invalid/missing dates
    chosen, note = select_latest_invoice(candidates)
    assert chosen["invoice_number"] == "INV-VALID"


def test_invoice_number_validation_rejects_malformed():
    from app.schemas import InvoiceCreate
    import pydantic
    for bad_id in ["umber", "number", "", "   ", "invoice", "no", "id"]:
        with pytest.raises(pydantic.ValidationError):
            InvoiceCreate(invoice_number=bad_id, vendor_id=1, amount="100.00")


def test_invoice_number_validation_accepts_valid_business_ids():
    from app.schemas import InvoiceCreate
    for good_id in ["INV-GLOB-2024-055", "INV-RAPID-2024-007", "AB-123", "10492", "PO-99/2024"]:
        inv = InvoiceCreate(invoice_number=good_id, vendor_id=1, amount="100.00")
        assert inv.invoice_number == good_id


def test_extract_invoice_fields_po_reference():
    from app.tools.files import extract_invoice_fields
    text = "Invoice Number: INV-GLOB-2024-062\nFrom: Global Tech Solutions\nPO Reference: PO-GLOB-2024-015\nAmount: INR 32,000.00"
    fields = extract_invoice_fields(text, use_llm=False)
    assert fields["invoice_number"] == "INV-GLOB-2024-062"
    assert fields["po_reference"] == "PO-GLOB-2024-015"


def test_get_purchase_order_missing_po(client, seeded_db):
    from app.tools.finance_tools import get_purchase_order
    res = get_purchase_order(po_number="PO-NONEXISTENT-999")
    assert res["ok"] is False
    assert "not found" in res["error"].lower()


def test_compare_invoice_with_po_discrepancy_details(client, seeded_db):
    from app.tools.finance_tools import compare_invoice_with_po
    # Invoice 3 in seeded_db (INV-GLOB-2024-062) vs PO 2 (PO-GLOB-2024-015)
    res = compare_invoice_with_po(invoice_id=3, po_id=2)
    assert res["ok"] is True
    assert res["clean"] is False  # Discrepancy detected
    assert len(res["discrepancies"]) > 0
    # Amount mismatch details present
    amt_comp = res["comparisons"]["amount"]
    assert amt_comp["match"] is False
    assert amt_comp["expected"] == "30000.00"
    assert amt_comp["actual"] == "32000.00"
    assert "difference" in amt_comp

