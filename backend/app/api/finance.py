"""
finance.py - REST API for the simulated finance application.
Provides vendor lookup, invoice CRUD, and purchase-order retrieval.
The agent uses these endpoints through its HTTP-based finance tool.
"""
from decimal import Decimal
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.models import Vendor, Invoice, PurchaseOrder
from app.schemas import (
    VendorOut, InvoiceCreate, InvoiceOut, InvoiceStatusUpdate, POOut
)

router = APIRouter(prefix="/finance", tags=["finance"])


# ── Helper ────────────────────────────────────────────────────────────────────

def _invoice_to_out(inv: Invoice) -> InvoiceOut:
    return InvoiceOut(
        id=inv.id,
        invoice_number=inv.invoice_number,
        vendor_id=inv.vendor_id,
        vendor_name=inv.vendor.name if inv.vendor else None,
        invoice_date=inv.invoice_date,
        due_date=inv.due_date,
        amount=format(inv.amount_decimal(), '.2f'),
        currency=inv.currency,
        description=inv.description,
        status=inv.status,
        source_ref=inv.source_ref,
        idempotency_key=inv.idempotency_key,
        created_at=inv.created_at,
    )

def _po_to_out(po: PurchaseOrder) -> POOut:
    return POOut(
        id=po.id,
        po_number=po.po_number,
        vendor_id=po.vendor_id,
        vendor_name=po.vendor.name if po.vendor else None,
        po_date=po.po_date,
        amount=format(po.amount_decimal(), '.2f'),
        currency=po.currency,
        description=po.description,
        status=po.status,
    )


# ── Vendors ───────────────────────────────────────────────────────────────────

@router.get("/vendors", response_model=list[VendorOut])
def list_vendors(name: Optional[str] = Query(None), db: Session = Depends(get_db)):
    """Search vendors by partial name match (case-insensitive)."""
    q = db.query(Vendor).filter(Vendor.is_active == True)
    if name:
        q = q.filter(Vendor.name.ilike(f"%{name}%"))
    return q.all()


@router.get("/vendors/{vendor_id}", response_model=VendorOut)
def get_vendor(vendor_id: int, db: Session = Depends(get_db)):
    v = db.get(Vendor, vendor_id)
    if not v:
        raise HTTPException(404, "Vendor not found")
    return v


# ── Invoices ──────────────────────────────────────────────────────────────────

@router.get("/invoices", response_model=list[InvoiceOut])
def list_invoices(
    vendor_id: Optional[int] = Query(None),
    invoice_number: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Search invoices with optional filters."""
    q = db.query(Invoice)
    if vendor_id:
        q = q.filter(Invoice.vendor_id == vendor_id)
    if invoice_number:
        q = q.filter(Invoice.invoice_number.ilike(f"%{invoice_number}%"))
    if status:
        q = q.filter(Invoice.status == status)
    return [_invoice_to_out(i) for i in q.all()]


@router.get("/invoices/{invoice_id}", response_model=InvoiceOut)
def get_invoice(invoice_id: int, db: Session = Depends(get_db)):
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(404, "Invoice not found")
    return _invoice_to_out(inv)


@router.post("/invoices", response_model=InvoiceOut, status_code=201)
def create_invoice(body: InvoiceCreate, db: Session = Depends(get_db)):
    """
    Create a new invoice.
    Uses idempotency_key to prevent duplicate writes if the request is retried.
    Amounts are stored as integer minor units (paise).
    """
    # Idempotency check — same key means same request, return existing record.
    if body.idempotency_key:
        existing = db.query(Invoice).filter_by(idempotency_key=body.idempotency_key).first()
        if existing:
            return _invoice_to_out(existing)

    vendor = db.get(Vendor, body.vendor_id)
    if not vendor:
        raise HTTPException(400, f"Vendor {body.vendor_id} not found")

    # Convert decimal string → integer minor units
    amount_minor = int(Decimal(body.amount) * 100)

    inv = Invoice(
        invoice_number=body.invoice_number,
        vendor_id=body.vendor_id,
        invoice_date=body.invoice_date,
        due_date=body.due_date,
        amount_minor=amount_minor,
        currency=body.currency,
        description=body.description,
        source_ref=body.source_ref,
        idempotency_key=body.idempotency_key,
    )
    db.add(inv)
    try:
        db.commit()
        db.refresh(inv)
    except IntegrityError:
        db.rollback()
        # Duplicate invoice_number + vendor_id combination
        dup = db.query(Invoice).filter_by(
            invoice_number=body.invoice_number, vendor_id=body.vendor_id
        ).first()
        if dup:
            raise HTTPException(409, f"Invoice {body.invoice_number} already exists for this vendor (id={dup.id})")
        raise HTTPException(409, "Duplicate invoice")

    return _invoice_to_out(inv)


@router.patch("/invoices/{invoice_id}/status", response_model=InvoiceOut)
def update_invoice_status(invoice_id: int, body: InvoiceStatusUpdate, db: Session = Depends(get_db)):
    """Update only the status field — agents are not allowed to change amounts directly."""
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(404, "Invoice not found")
    inv.status = body.status
    db.commit()
    db.refresh(inv)
    return _invoice_to_out(inv)


# ── Purchase Orders ───────────────────────────────────────────────────────────

@router.get("/purchase-orders", response_model=list[POOut])
def list_purchase_orders(
    vendor_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(PurchaseOrder)
    if vendor_id:
        q = q.filter(PurchaseOrder.vendor_id == vendor_id)
    return [_po_to_out(p) for p in q.all()]


@router.get("/purchase-orders/{po_id}", response_model=POOut)
def get_purchase_order(po_id: int, db: Session = Depends(get_db)):
    po = db.get(PurchaseOrder, po_id)
    if not po:
        raise HTTPException(404, "Purchase order not found")
    return _po_to_out(po)
