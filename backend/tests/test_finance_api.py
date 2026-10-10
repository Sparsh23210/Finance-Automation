"""
test_finance_api.py - Integration tests for the finance REST API.
Tests run against a real SQLite test DB using the TestClient.
"""
import pytest
from decimal import Decimal


# ── Vendor tests ──────────────────────────────────────────────────────────────

def test_list_vendors_empty(client):
    r = client.get("/finance/vendors")
    assert r.status_code == 200
    assert r.json() == []


def test_list_vendors_with_data(client, seeded_db):
    r = client.get("/finance/vendors")
    assert r.status_code == 200
    assert len(r.json()) == 5


def test_search_vendors_by_name(client, seeded_db):
    r = client.get("/finance/vendors?name=Apex")
    assert r.status_code == 200
    names = [v["name"] for v in r.json()]
    # Both "Apex Supplies Ltd." and "Apex Supply House" should match
    assert len(names) == 2
    assert all("Apex" in n for n in names)


def test_get_vendor_not_found(client, seeded_db):
    r = client.get("/finance/vendors/9999")
    assert r.status_code == 404


# ── Invoice creation ──────────────────────────────────────────────────────────

def test_create_invoice_success(client, seeded_db):
    r = client.post("/finance/invoices", json={
        "invoice_number": "INV-TEST-001",
        "vendor_id": 1,
        "amount": "25000.00",
        "currency": "INR",
        "invoice_date": "2024-04-01",
        "due_date": "2024-05-01",
        "description": "Test invoice",
        "idempotency_key": "pytest-create-001",
    })
    assert r.status_code == 201
    data = r.json()
    assert data["invoice_number"] == "INV-TEST-001"
    assert data["amount"] == "25000.00"
    assert data["vendor_id"] == 1


def test_create_invoice_negative_amount(client, seeded_db):
    r = client.post("/finance/invoices", json={
        "invoice_number": "INV-TEST-NEG",
        "vendor_id": 1,
        "amount": "-100.00",
    })
    assert r.status_code == 422  # Pydantic validation error


def test_create_invoice_invalid_vendor(client, seeded_db):
    r = client.post("/finance/invoices", json={
        "invoice_number": "INV-TEST-BADVEND",
        "vendor_id": 9999,
        "amount": "1000.00",
    })
    assert r.status_code == 400


def test_duplicate_invoice_blocked(client, seeded_db):
    """Creating the same invoice_number + vendor_id twice should return 409."""
    payload = {
        "invoice_number": "INV-DUP-TEST",
        "vendor_id": 1,
        "amount": "5000.00",
        "idempotency_key": "pytest-dup-001",
    }
    r1 = client.post("/finance/invoices", json=payload)
    assert r1.status_code == 201

    # Change idempotency key but same invoice_number + vendor → should 409
    payload["idempotency_key"] = "pytest-dup-002"
    r2 = client.post("/finance/invoices", json=payload)
    assert r2.status_code == 409


def test_idempotency_returns_existing(client, seeded_db):
    """Same idempotency_key returns existing record without creating duplicate."""
    payload = {
        "invoice_number": "INV-IDEM-001",
        "vendor_id": 1,
        "amount": "10000.00",
        "idempotency_key": "pytest-idem-001",
    }
    r1 = client.post("/finance/invoices", json=payload)
    assert r1.status_code == 201
    id1 = r1.json()["id"]

    r2 = client.post("/finance/invoices", json=payload)
    assert r2.status_code == 201
    id2 = r2.json()["id"]

    assert id1 == id2  # Same record returned, no duplicate created


# ── Invoice status update ─────────────────────────────────────────────────────

def test_update_status_success(client, seeded_db):
    r = client.patch("/finance/invoices/1/status", json={"status": "approved"})
    assert r.status_code == 200
    assert r.json()["status"] == "approved"


def test_update_status_invalid(client, seeded_db):
    r = client.patch("/finance/invoices/1/status", json={"status": "deleted"})
    assert r.status_code == 422


def test_flag_high_value_invoice(client, seeded_db):
    """Invoice ID 2 is ₹72,500 — should be flag-able."""
    r = client.patch("/finance/invoices/2/status", json={"status": "flagged"})
    assert r.status_code == 200
    assert r.json()["status"] == "flagged"


# ── Purchase orders ───────────────────────────────────────────────────────────

def test_list_purchase_orders(client, seeded_db):
    r = client.get("/finance/purchase-orders")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_get_po_by_id(client, seeded_db):
    r = client.get("/finance/purchase-orders/1")
    assert r.status_code == 200
    data = r.json()
    assert data["po_number"] == "PO-APEX-2024-001"
    assert data["amount"] == "45000.00"


def test_po_not_found(client, seeded_db):
    r = client.get("/finance/purchase-orders/9999")
    assert r.status_code == 404


# ── Invoice search ────────────────────────────────────────────────────────────

def test_search_invoices_by_vendor(client, seeded_db):
    r = client.get("/finance/invoices?vendor_id=1")
    assert r.status_code == 200
    results = r.json()
    assert len(results) == 2
    assert all(i["vendor_id"] == 1 for i in results)


def test_amount_stored_correctly(client, seeded_db):
    """Verify Decimal amount round-trips through the DB correctly."""
    r = client.post("/finance/invoices", json={
        "invoice_number": "INV-DECIMAL-001",
        "vendor_id": 1,
        "amount": "12345.67",
        "idempotency_key": "pytest-decimal-001",
    })
    assert r.status_code == 201
    assert r.json()["amount"] == "12345.67"
