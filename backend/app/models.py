"""
models.py - All SQLAlchemy ORM models in one file for easy reference.
Keeping them together makes it trivial to see the entire data schema.
"""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import (
    Integer, String, Text, DateTime, Numeric, Boolean,
    ForeignKey, UniqueConstraint, JSON
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Vendor(Base):
    __tablename__ = "vendors"

    id: Mapped[int]           = mapped_column(Integer, primary_key=True)
    name: Mapped[str]         = mapped_column(String(200), nullable=False)
    code: Mapped[str]         = mapped_column(String(50), unique=True, nullable=False)
    contact_email: Mapped[str] = mapped_column(String(200), nullable=True)
    gstin: Mapped[str]        = mapped_column(String(20), nullable=True)
    address: Mapped[str]      = mapped_column(Text, nullable=True)
    is_active: Mapped[bool]   = mapped_column(Boolean, default=True)

    invoices = relationship("Invoice", back_populates="vendor")


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        # Prevent identical invoice numbers from the same vendor being stored twice.
        UniqueConstraint("invoice_number", "vendor_id", name="uq_invoice_vendor"),
    )

    id: Mapped[int]             = mapped_column(Integer, primary_key=True)
    invoice_number: Mapped[str] = mapped_column(String(100), nullable=False)
    vendor_id: Mapped[int]      = mapped_column(Integer, ForeignKey("vendors.id"), nullable=False)
    invoice_date: Mapped[str]   = mapped_column(String(20), nullable=True)   # ISO 8601 string
    due_date: Mapped[str]       = mapped_column(String(20), nullable=True)
    # Store amounts as integer minor units (paise for INR) to avoid float errors.
    amount_minor: Mapped[int]   = mapped_column(Integer, nullable=False)     # e.g. 5000000 = ₹50,000.00
    currency: Mapped[str]       = mapped_column(String(10), default="INR")
    description: Mapped[str]    = mapped_column(Text, nullable=True)
    status: Mapped[str]         = mapped_column(String(30), default="pending")  # pending/approved/paid/flagged
    source_ref: Mapped[str]     = mapped_column(String(300), nullable=True)   # filename or doc ID
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    vendor = relationship("Vendor", back_populates="invoices")

    def amount_decimal(self) -> Decimal:
        """Convert stored minor units back to a human-readable decimal."""
        return Decimal(self.amount_minor) / Decimal(100)


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[int]         = mapped_column(Integer, primary_key=True)
    po_number: Mapped[str]  = mapped_column(String(100), unique=True, nullable=False)
    vendor_id: Mapped[int]  = mapped_column(Integer, ForeignKey("vendors.id"), nullable=False)
    po_date: Mapped[str]    = mapped_column(String(20), nullable=True)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str]   = mapped_column(String(10), default="INR")
    description: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[str]     = mapped_column(String(30), default="open")  # open/closed/cancelled

    vendor = relationship("Vendor")

    def amount_decimal(self) -> Decimal:
        return Decimal(self.amount_minor) / Decimal(100)


class Task(Base):
    """Persistent task state so the agent can resume after restarts."""
    __tablename__ = "tasks"

    id: Mapped[str]           = mapped_column(String(36), primary_key=True)   # UUID
    request: Mapped[str]      = mapped_column(Text, nullable=False)
    status: Mapped[str]       = mapped_column(String(30), default="running")  # running/completed/failed/needs_input/waiting_approval
    workflow: Mapped[str]     = mapped_column(String(50), default="invoice")
    state_json: Mapped[dict]  = mapped_column(JSON, nullable=True)            # full agent state snapshot
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    evidence_entries = relationship("EvidenceEntry", back_populates="task")


class EvidenceEntry(Base):
    """One evidence record per tool invocation / verification check."""
    __tablename__ = "evidence"

    id: Mapped[int]           = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str]      = mapped_column(String(36), ForeignKey("tasks.id"), nullable=False)
    step: Mapped[int]         = mapped_column(Integer, default=0)
    action: Mapped[str]       = mapped_column(String(100), nullable=False)
    tool_name: Mapped[str]    = mapped_column(String(100), nullable=True)
    inputs: Mapped[dict]      = mapped_column(JSON, nullable=True)
    outputs: Mapped[dict]     = mapped_column(JSON, nullable=True)
    status: Mapped[str]       = mapped_column(String(30), default="ok")  # ok/error/skipped
    source_ref: Mapped[str]   = mapped_column(String(300), nullable=True)
    notes: Mapped[str]        = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    task = relationship("Task", back_populates="evidence_entries")


class ApprovalRequest(Base):
    """Persistent approval record so restarts don't lose approval state."""
    __tablename__ = "approval_requests"

    id: Mapped[int]              = mapped_column(Integer, primary_key=True)
    task_id: Mapped[str]         = mapped_column(String(36), ForeignKey("tasks.id"), nullable=False)
    action: Mapped[str]          = mapped_column(String(100), nullable=False)
    justification: Mapped[str]   = mapped_column(Text, nullable=True)
    evidence_summary: Mapped[dict] = mapped_column(JSON, nullable=True)
    decision: Mapped[str]        = mapped_column(String(20), nullable=True)  # pending/approved/rejected
    decided_by: Mapped[str]      = mapped_column(String(100), nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
