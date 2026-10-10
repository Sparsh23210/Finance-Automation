# ProofLoop: Evidence-Driven Autonomous AI Finance Agent

ProofLoop is an evidence-driven autonomous AI agent that takes business requests written in natural language and carries them out in a simulated finance application. It can find relevant invoice documents, extract key details, create or update finance records through API tools, and report what happened.

Its central rule is simple: **no evidence, no success claim**. After a write operation, ProofLoop reads the record back from the database and checks the saved fields against the source document. It does not treat a successful tool response or an LLM's statement as proof that the task was completed correctly.

---

## What It Does

- **Parses natural-language requests into structured tasks**: Interprets vendor, amount, constraints, and target workflow.
- **Searches available documents & extracts invoice information**: Safe file operations with path-traversal prevention.
- **Creates & updates finance records using typed tools**: 12 registered tools with schema validation.
- **Detects duplicates & maintains database integrity**: Unique vendor/invoice constraints and idempotency keys.
- **Requests approval for high-value transactions**: Automatic pause and approval workflow for amounts > ₹50,000.
- **Recovers from timeouts safely**: Inspects the database before retrying to prevent double-writes.
- **Verifies saved records field-by-field**: Implements independent readback verification and logs an immutable evidence ledger.
- **Supports dual workflows**: Handles Invoice Entry and Purchase-Order Reconciliation workflows.
- **React + Vite Dashboard**: Dark-mode dashboard for submitting tasks, inspecting step timelines, and viewing live ledger tables.
- **Deterministic fallback mode**: Seamlessly runs 100% offline without requiring an API key.

---

## Architecture

```
User Request
    │
    ▼
┌─────────────────────────────────────────────┐
│  LangGraph Execution Graph                  │
│                                             │
│  UNDERSTAND → EXECUTE ←──────────────────┐  │
│       │           │                      │  │
│       ▼           ▼                      │  │
│   Structured   Tool Registry             │  │
│     Goal       (12 tools)                │  │
│                    │                     │  │
│                    ▼                     │  │
│              Policy Check ──── DENY      │  │
│                    │                     │  │
│                    ▼                     │  │
│            Tool Execution                │  │
│                    │                     │  │
│              ┌─────┴──────┐              │  │
│           Timeout?     Error?            │  │
│              │             │             │  │
│         Check DB      Classify          │  │
│         First!        & Recover ────────┘  │
│              │                             │
│              ▼                             │
│          VERIFY (independent)              │
│              │                             │
│     ┌────────┴────────┐                   │
│  all PASS          any FAIL               │
│     │                  │                  │
│  COMPLETED           FAILED               │
└─────────────────────────────────────────────┘
         │
         ▼
   Evidence Ledger (SQLite)
   Final Report to User
```

---

## Setup & Quickstart

### Prerequisites
- Python 3.10+
- Node.js 18+

### 1. Install & Run Backend
```bash
cd backend
pip install -r requirements.txt
python ..\scripts\seed_demo.py
uvicorn app.main:app --reload --port 8000
```
Interactive API documentation: `http://localhost:8000/docs`

### 2. Install & Run Frontend
```bash
cd frontend
npm install
npm run dev
```
Dashboard: `http://localhost:5173`

*(Alternatively, run `start.bat` on Windows to launch both servers simultaneously).*

---

## Test Coverage

| Scenario | Test |
|---|---|
| Normal invoice creation | `test_create_invoice_success` |
| Duplicate prevention (DB constraint) | `test_duplicate_invoice_blocked` |
| Idempotency key returns existing | `test_idempotency_returns_existing` |
| Repeated task run idempotency | `test_repeated_task_execution_idempotency` |
| High-value flagging (>₹50k) | `test_flag_high_value_invoice` |
| Missing due date | `test_missing_due_date_invoice` |
| Path traversal blocked | `test_read_document_path_traversal_blocked` |
| No fabrication of missing fields | `test_extract_fields_no_fabrication` |
| Threshold below limit | `test_threshold_below_limit` |
| Threshold above limit | `test_threshold_above_limit` |
| Invalid approver rejected | `test_invalid_approver_rejected` |
| Error classification | `test_error_classification_*` |
| Latest invoice selection by date | `test_select_latest_invoice_by_date` |
| Missing/invalid invoice dates | `test_select_latest_invoice_missing_date` |
| PO discrepancy detection & details | `test_compare_invoice_po_discrepancy` |
| Missing PO reported cleanly | `test_compare_invoice_po_not_found` |
| Malformed ID rejected (umber/blank) | `test_validate_invoice_number_rejects_corrupted_fragments` |
| Legitimate multi-vendor ID formats | `test_validate_invoice_number_accepts_valid_business_formats` |
| PO reference document extraction | `test_extract_invoice_po_reference` |
| End-to-end reconciliation & flag | `test_po_reconciliation_end_to_end_discrepancy` |
| Ambiguous vendor → NEEDS_INPUT | `test_plan_after_vendor_ambiguity` |
| High amount → request_approval | `test_plan_requires_approval_for_high_amount` |
| Evidence ledger sanitizes secrets | `test_ledger_sanitizes_secrets` |

To run the automated evaluation suite:
```bash
python scripts/evaluate.py
```
*(All 59 unit, integration, and regression tests pass at 100%).*
