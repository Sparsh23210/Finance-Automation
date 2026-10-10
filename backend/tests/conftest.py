"""
conftest.py - pytest fixtures.

The key challenge: FastAPI's background tasks (agent execution) and the
evidence ledger both use SessionLocal directly — outside FastAPI's DI system.
So in tests we need ALL parts of the app to use the SAME in-memory SQLite.

Solution: Monkey-patch app.database BEFORE any app module is imported,
then ensure every DB call goes through `import app.database as _db; _db.SessionLocal()`.
"""
import os
import sys

# ── Step 1: Set env vars BEFORE any imports ───────────────────────────────────
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_DIR = os.path.dirname(BACKEND_DIR)
SAMPLE_DATA = os.path.join(PROJECT_DIR, "sample_data")

os.environ["DATABASE_URL"]  = "sqlite:///:memory:"
os.environ["GEMINI_API_KEY"] = ""        # deterministic planner
os.environ["WORKSPACE_DIR"]  = SAMPLE_DATA
os.environ["FAULT_INJECT"]   = ""

# Make backend/ importable
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# ── Step 2: Create the shared in-memory engine ─────────────────────────────────
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

_test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,   # all connections share the SAME in-memory DB
)
_TestSession = sessionmaker(bind=_test_engine, autoflush=False, autocommit=False)

# ── Step 3: Patch app.database BEFORE importing the app ───────────────────────
# This must happen before ANY 'from app.xxx import yyy' in this file.
import app.database as _app_db
_app_db.engine       = _test_engine
_app_db.SessionLocal = _TestSession

# ── Step 4: NOW import the app and create tables ──────────────────────────────
from app.database import Base, get_db   # uses patched engine
from app.main import app                 # triggers model registration
from app.models import Vendor, Invoice, PurchaseOrder, Task, EvidenceEntry, ApprovalRequest

Base.metadata.create_all(bind=_test_engine)

# ── Step 5: pytest fixtures ───────────────────────────────────────────────────
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def clean_tables():
    """Truncate all rows before EVERY test — prevents data leaking between tests."""
    db = _TestSession()
    try:
        # Delete in FK-safe order (children before parents)
        db.query(EvidenceEntry).delete()
        db.query(ApprovalRequest).delete()
        db.query(Task).delete()
        db.query(Invoice).delete()
        db.query(PurchaseOrder).delete()
        db.query(Vendor).delete()
        db.commit()
    finally:
        db.close()
    yield


@pytest.fixture
def db():
    """Plain DB session for direct ORM use in tests."""
    session = _TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db):
    """
    TestClient whose get_db() dependency is overridden with the test session.
    The background agent will still use _db.SessionLocal() — which now also
    points to the same in-memory DB because we patched app.database above.
    """
    def override_get_db():
        yield db
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def seeded_db(db):
    """Insert standard test data and return the session."""
    vendors = [
        Vendor(id=1, name="Apex Supplies Ltd.",   code="APEX001",
               contact_email="billing@apex.com", gstin="27AA", is_active=True),
        Vendor(id=2, name="Apex Supply House",    code="APEX002",
               contact_email="info@apexsh.com",  gstin="27BB", is_active=True),
        Vendor(id=3, name="Global Tech Solutions",code="GLOB001",
               contact_email="fin@glob.com",     gstin="06CC", is_active=True),
        Vendor(id=4, name="Rapid Logistics Co.",  code="RAPID01",
               contact_email="bill@rapid.com",   gstin="29DD", is_active=True),
        Vendor(id=5, name="Zenith Office Mart",   code="ZENTH01",
               contact_email="ar@zenith.com",    gstin="33EE", is_active=True),
    ]
    db.add_all(vendors)
    db.flush()

    invoices = [
        Invoice(id=1, invoice_number="INV-APEX-2024-001", vendor_id=1,
                invoice_date="2024-01-15", due_date="2024-02-14",
                amount_minor=4500000, currency="INR",
                description="Office supplies", status="pending",
                idempotency_key="test-inv-001"),
        Invoice(id=2, invoice_number="INV-APEX-2024-002", vendor_id=1,
                invoice_date="2024-03-10", due_date="2024-04-09",
                amount_minor=7250000, currency="INR",
                description="IT equipment", status="flagged",
                idempotency_key="test-inv-002"),
        Invoice(id=3, invoice_number="INV-GLOB-2024-062", vendor_id=3,
                invoice_date="2024-03-25", due_date="2024-04-24",
                amount_minor=3200000, currency="INR",
                description="Software licenses", status="pending",
                idempotency_key="test-inv-003"),
        Invoice(id=4, invoice_number="INV-RAPID-2024-007", vendor_id=4,
                invoice_date="2024-01-28", due_date=None,
                amount_minor=1550000, currency="INR",
                description="Logistics Jan", status="pending",
                idempotency_key="test-inv-004"),
    ]
    db.add_all(invoices)
    db.flush()

    pos = [
        PurchaseOrder(id=1, po_number="PO-APEX-2024-001", vendor_id=1,
                      po_date="2024-01-10", amount_minor=4500000, currency="INR",
                      description="Office stationery", status="closed"),
        PurchaseOrder(id=2, po_number="PO-GLOB-2024-015", vendor_id=3,
                      po_date="2024-03-20", amount_minor=3000000, currency="INR",
                      description="Software licenses", status="open"),
    ]
    db.add_all(pos)
    db.commit()
    return db
