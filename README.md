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

## Test Coverage (59 / 59 Tests Passing)

The project includes an automated test suite across three test modules in `backend/tests/`:

### 1. `backend/tests/test_agent.py` (Agent & Workflow Execution — 14 Tests)
| Scenario | Test Function |
|---|---|
| Natural-language invoice task parsing | `test_understand_invoice_task` |
| Natural-language PO reconciliation task parsing | `test_understand_po_task` |
| Execution DAG starts with file search | `test_plan_next_action_starts_with_search` |
| Ambiguous vendor name pauses with `NEEDS_INPUT` | `test_plan_after_vendor_ambiguity` |
| High-value invoice pauses for approval (>₹50k) | `test_plan_requires_approval_for_high_amount` |
| Human rejection prevents unauthorized execution | `test_approval_rejected_prevents_execution` |
| Evidence ledger records and retrieves steps | `test_ledger_record_and_retrieve` |
| Evidence ledger sanitizes secrets/tokens | `test_ledger_sanitizes_secrets` |
| Task submission API accepts requests (HTTP 202) | `test_submit_task_returns_202` |
| Task listing and error handling | `test_list_tasks`, `test_get_task_not_found`, `test_initial_state` |
| Full end-to-end PO reconciliation & discrepancy flag | `test_po_reconciliation_end_to_end_discrepancy` |
| Repeated task run idempotency (no duplicate writes) | `test_repeated_task_execution_idempotency` |

### 2. `backend/tests/test_finance_api.py` (REST API & Persistence — 17 Tests)
| Scenario | Test Function |
|---|---|
| Vendor listing and search filtering | `test_list_vendors_empty`, `test_list_vendors_with_data`, `test_search_vendors_by_name`, `test_get_vendor_not_found` |
| Valid invoice creation | `test_create_invoice_success` |
| Negative amount rejection | `test_create_invoice_negative_amount` |
| Invalid vendor ID rejection | `test_create_invoice_invalid_vendor` |
| Unique constraint prevents duplicate invoices | `test_duplicate_invoice_blocked` |
| Idempotency key returns existing record | `test_idempotency_returns_existing` |
| Status transitions (pending → approved / flagged) | `test_update_status_success`, `test_update_status_invalid` |
| Automatic flagging for invoices > ₹50,000 | `test_flag_high_value_invoice` |
| Purchase order querying & missing PO handling | `test_list_purchase_orders`, `test_get_po_by_id`, `test_po_not_found` |
| Invoice search by vendor ID | `test_search_invoices_by_vendor` |
| Minor integer units preserve monetary accuracy | `test_amount_stored_correctly` |

### 3. `backend/tests/test_tools.py` (Tools, Parsers & Ground-Truth Verification — 28 Tests)
| Scenario | Test Function |
|---|---|
| Safe file searching & missing file handling | `test_search_files_finds_invoices`, `test_search_files_no_match` |
| Document reading & path traversal protection | `test_read_document_success`, `test_read_document_path_traversal_blocked`, `test_read_document_not_found` |
| Field extraction from text invoices | `test_extract_fields_regex_fallback`, `test_extract_fields_no_fabrication` |
| PO reference extraction from invoice text | `test_extract_invoice_fields_po_reference` |
| Missing due date handled gracefully | `test_missing_due_date_invoice` |
| Invoice number validator rejects malformed text (`umber`, blank) | `test_invoice_number_validation_rejects_malformed` |
| Invoice number validator accepts valid business IDs | `test_invoice_number_validation_accepts_valid_business_ids` |
| Select latest invoice by date (not ID or file order) | `test_select_latest_invoice_date_ordering` |
| Missing/invalid invoice dates handled safely | `test_select_latest_invoice_missing_or_invalid_dates` |
| Financial approval policy threshold evaluation | `test_threshold_below_limit`, `test_threshold_above_limit`, `test_threshold_exactly_at_limit`, `test_threshold_over_limit` |
| Approver role permissions | `test_invalid_approver_rejected`, `test_authorized_approver_accepted` |
| Error classification (retry, duplicate, abort, permission) | `test_error_classification_retry`, `test_error_classification_duplicate`, `test_error_classification_abort`, `test_error_classification_permission` |
| Clean PO comparison (matching values) | `test_compare_invoice_po_clean` |
| Discrepancy comparison & variance computation | `test_compare_invoice_po_discrepancy`, `test_compare_invoice_with_po_discrepancy_details` |
| Missing purchase order reported cleanly without fabricating data | `test_get_purchase_order_missing_po` |
| Independent ground-truth database verification | `test_verify_invoice_pass` |

---

## Running the Automated Test & Evaluation Suite

Execute the evaluation script from the repository root:
```bash
python scripts/evaluate.py
```
*(Runs pytest with programmatic JSON metrics; all 59 tests pass 100%).*

