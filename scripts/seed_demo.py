"""
seed_demo.py - Populate the database with reproducible sample data.
Run: python scripts/seed_demo.py  (from the backend/ directory)

The data is designed to exercise all test scenarios:
- Normal invoices
- Duplicate invoice scenario
- Missing-field scenario
- Amount-over-threshold scenario
- Invoice/PO discrepancy scenario
"""
import sys
import os

# Allow running from backend/ or project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.database import engine, SessionLocal
from app.models import Base, Vendor, Invoice, PurchaseOrder


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Skip if already seeded
        if db.query(Vendor).count() > 0:
            print("Database already seeded. Use --force to re-seed.")
            if "--force" not in sys.argv:
                return

        # Clear existing data
        db.query(Invoice).delete()
        db.query(PurchaseOrder).delete()
        db.query(Vendor).delete()
        db.commit()

        # ── Vendors ───────────────────────────────────────────────────────────
        vendors = [
            Vendor(id=1, name="Apex Supplies Ltd.",  code="APEX001", contact_email="billing@apexsupplies.com",   gstin="27AABCA1234B1Z5", address="12, Industrial Estate, Pune, MH 411019"),
            Vendor(id=2, name="Apex Supply House",   code="APEX002", contact_email="accounts@apexsupplyhouse.in",gstin="27BBBCA5678C2Z6", address="45, Shivaji Nagar, Pune, MH 411005"),
            Vendor(id=3, name="Global Tech Solutions",code="GLOB001", contact_email="finance@globaltechsol.com",  gstin="06CCCCA9012D3Z7", address="78, Sector 14, Gurugram, HR 122001"),
            Vendor(id=4, name="Rapid Logistics Co.", code="RAPID01", contact_email="billing@rapidlogistics.in",  gstin="29DDDDB3456E4Z8", address="22, Whitefield Rd, Bengaluru, KA 560066"),
            Vendor(id=5, name="Zenith Office Mart",  code="ZENTH01", contact_email="ar@zenithoffice.com",        gstin="33EEEEC7890F5Z9", address="99, Anna Salai, Chennai, TN 600002"),
        ]
        db.add_all(vendors)
        db.flush()

        # ── Invoices ──────────────────────────────────────────────────────────
        invoices = [
            # Normal invoices (below threshold)
            Invoice(invoice_number="INV-APEX-2023-099", vendor_id=1, invoice_date="2023-12-01",
                    due_date="2023-12-31", amount_minor=3500000, currency="INR",   # ₹35,000
                    description="Office supplies Q4 2023", status="paid",
                    source_ref="invoices/INV-APEX-2023-099.txt",
                    idempotency_key="seed-INV-APEX-2023-099"),

            Invoice(invoice_number="INV-APEX-2024-001", vendor_id=1, invoice_date="2024-01-15",
                    due_date="2024-02-14", amount_minor=4500000, currency="INR",   # ₹45,000
                    description="Office stationery and supplies for Q1 2024", status="pending",
                    source_ref="invoices/INV-APEX-2024-001.txt",
                    idempotency_key="seed-INV-APEX-2024-001"),

            # High-value invoice (over ₹50,000 threshold)
            Invoice(invoice_number="INV-APEX-2024-002", vendor_id=1, invoice_date="2024-03-10",
                    due_date="2024-04-09", amount_minor=7250000, currency="INR",   # ₹72,500
                    description="IT equipment — 5 laptops", status="flagged",
                    source_ref="invoices/INV-APEX-2024-002.txt",
                    idempotency_key="seed-INV-APEX-2024-002"),

            # Global Tech invoice
            Invoice(invoice_number="INV-GLOB-2024-055", vendor_id=3, invoice_date="2024-02-20",
                    due_date="2024-03-21", amount_minor=2800000, currency="INR",   # ₹28,000
                    description="Cloud hosting services — February 2024", status="approved",
                    source_ref="invoices/INV-GLOB-2024-055.txt",
                    idempotency_key="seed-INV-GLOB-2024-055"),

            # Duplicate invoice (same number + vendor as INV-APEX-2024-001)
            # The DB constraint will block inserting it again. We note it here
            # as a scenario but don't insert it.

            # Missing due_date invoice
            Invoice(invoice_number="INV-RAPID-2024-007", vendor_id=4, invoice_date="2024-01-28",
                    due_date=None, amount_minor=1550000, currency="INR",           # ₹15,500
                    description="Courier and logistics — January 2024", status="pending",
                    source_ref="invoices/INV-RAPID-2024-007.txt",
                    idempotency_key="seed-INV-RAPID-2024-007"),

            # Zenith invoices
            Invoice(invoice_number="INV-ZENTH-2024-012", vendor_id=5, invoice_date="2024-02-05",
                    due_date="2024-03-06", amount_minor=1200000, currency="INR",   # ₹12,000
                    description="Printer cartridges and paper", status="paid",
                    idempotency_key="seed-INV-ZENTH-2024-012"),

            Invoice(invoice_number="INV-ZENTH-2024-018", vendor_id=5, invoice_date="2024-03-15",
                    due_date="2024-04-14", amount_minor=800000, currency="INR",    # ₹8,000
                    description="Office cleaning supplies", status="pending",
                    idempotency_key="seed-INV-ZENTH-2024-018"),

            # Invoice with discrepancy vs PO (amount differs)
            Invoice(invoice_number="INV-GLOB-2024-062", vendor_id=3, invoice_date="2024-03-25",
                    due_date="2024-04-24", amount_minor=3200000, currency="INR",   # ₹32,000 (PO says ₹30,000)
                    description="Software licenses — March 2024", status="pending",
                    idempotency_key="seed-INV-GLOB-2024-062"),
        ]
        db.add_all(invoices)
        db.flush()

        # ── Purchase Orders ───────────────────────────────────────────────────
        pos = [
            PurchaseOrder(po_number="PO-APEX-2024-001", vendor_id=1, po_date="2024-01-10",
                          amount_minor=4500000, currency="INR",                    # ₹45,000 — matches INV-APEX-2024-001
                          description="Office stationery Q1", status="closed"),

            PurchaseOrder(po_number="PO-GLOB-2024-010", vendor_id=3, po_date="2024-02-15",
                          amount_minor=2800000, currency="INR",                    # ₹28,000 — matches INV-GLOB-2024-055
                          description="Cloud hosting Feb 2024", status="closed"),

            # Deliberately mismatched PO for INV-GLOB-2024-062
            PurchaseOrder(po_number="PO-GLOB-2024-015", vendor_id=3, po_date="2024-03-20",
                          amount_minor=3000000, currency="INR",                    # ₹30,000 vs invoice ₹32,000
                          description="Software licenses March 2024", status="open"),
        ]
        db.add_all(pos)
        db.commit()

        print("[OK] Database seeded successfully.")
        print(f"  Vendors:         {db.query(Vendor).count()}")
        print(f"  Invoices:        {db.query(Invoice).count()}")
        print(f"  Purchase Orders: {db.query(PurchaseOrder).count()}")

    except Exception as e:
        db.rollback()
        print(f"Seed failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
