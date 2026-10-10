"""
schemas.py - Pydantic models for API request/response validation.
Keeping input and output contracts strict prevents garbage from reaching the agent or DB.
"""
from typing import Any, Optional
from decimal import Decimal
from datetime import datetime
from pydantic import BaseModel, field_validator


# ── Vendor ────────────────────────────────────────────────────────────────────

class VendorOut(BaseModel):
    id: int
    name: str
    code: str
    contact_email: Optional[str] = None
    gstin: Optional[str] = None
    is_active: bool

    model_config = {"from_attributes": True}


# ── Invoice ───────────────────────────────────────────────────────────────────

class InvoiceCreate(BaseModel):
    invoice_number: str
    vendor_id: int
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    amount: str          # Decimal string e.g. "50000.00"
    currency: str = "INR"
    description: Optional[str] = None
    source_ref: Optional[str] = None
    idempotency_key: Optional[str] = None

    @field_validator("invoice_number")
    @classmethod
    def validate_invoice_number(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("invoice_number cannot be empty or blank")
        cleaned = v.strip()
        low = cleaned.lower()
        disallowed = {"umber", "number", "invoice", "invoiceno", "no", "unknown", "null", "none"}
        if low in disallowed or len(cleaned) < 3:
            raise ValueError(f"'{v}' is not a valid invoice identifier")
        has_digit = any(c.isdigit() for c in cleaned)
        has_structure = "-" in cleaned or "/" in cleaned
        if not (has_digit or has_structure):
            raise ValueError(f"'{v}' is not a valid invoice identifier")
        return cleaned

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: str) -> str:
        if Decimal(v) <= 0:
            raise ValueError("amount must be positive")
        return v


class InvoiceStatusUpdate(BaseModel):
    status: str  # pending / approved / paid / flagged

    @field_validator("status")
    @classmethod
    def valid_status(cls, v: str) -> str:
        allowed = {"pending", "approved", "paid", "flagged"}
        if v not in allowed:
            raise ValueError(f"status must be one of {allowed}")
        return v


class InvoiceOut(BaseModel):
    id: int
    invoice_number: str
    vendor_id: int
    vendor_name: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    amount: str           # human-readable decimal string
    currency: str
    description: Optional[str] = None
    status: str
    source_ref: Optional[str] = None
    idempotency_key: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Purchase Order ────────────────────────────────────────────────────────────

class POOut(BaseModel):
    id: int
    po_number: str
    vendor_id: int
    vendor_name: Optional[str] = None
    po_date: Optional[str] = None
    amount: str
    currency: str
    description: Optional[str] = None
    status: str

    model_config = {"from_attributes": True}


# ── Task ──────────────────────────────────────────────────────────────────────

class TaskCreate(BaseModel):
    request: str
    workflow: str = "invoice"   # "invoice" or "po_reconciliation"


class TaskOut(BaseModel):
    id: str
    request: str
    status: str
    workflow: str
    state_json: Optional[Any] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Evidence ──────────────────────────────────────────────────────────────────

class EvidenceOut(BaseModel):
    id: int
    task_id: str
    step: int
    action: str
    tool_name: Optional[str] = None
    inputs: Optional[Any] = None
    outputs: Optional[Any] = None
    status: str
    source_ref: Optional[str] = None
    notes: Optional[str] = None
    timestamp: datetime

    model_config = {"from_attributes": True}


# ── Approval ──────────────────────────────────────────────────────────────────

class ApprovalDecision(BaseModel):
    decision: str      # "approved" or "rejected"
    decided_by: str    # e.g. "admin" (local dev identity)

    @field_validator("decision")
    @classmethod
    def valid_decision(cls, v: str) -> str:
        if v not in {"approved", "rejected"}:
            raise ValueError("decision must be 'approved' or 'rejected'")
        return v


class ApprovalOut(BaseModel):
    id: int
    task_id: str
    action: str
    justification: Optional[str] = None
    evidence_summary: Optional[Any] = None
    decision: Optional[str] = None
    decided_by: Optional[str] = None
    decided_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}
