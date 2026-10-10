"""
state.py - Agent state definition.

The state is a plain dictionary that flows through every node of the LangGraph.
Using a TypedDict makes it clear what fields exist without requiring a heavy ORM.
Keeping state serializable (JSON-compatible) allows DB persistence and resumption.
"""
from typing import Any, TypedDict, Optional


class AgentState(TypedDict):
    # Identification
    task_id: str
    request: str
    workflow: str          # "invoice" or "po_reconciliation"

    # Parsed goal from LLM understanding phase
    goal: dict             # task_type, entity, required_fields, success_conditions, etc.

    # Execution
    steps: list[dict]      # list of {tool, args, result, status, attempt}
    current_step: int
    retry_counts: dict[str, int]  # tool_name -> retry count
    errors: list[str]

    # Discovered data
    documents: list[dict]        # files found
    extracted: dict              # fields extracted from documents
    vendor_info: Optional[dict]  # resolved vendor
    invoice_id: Optional[int]    # created/found invoice DB id
    po_id: Optional[int]         # relevant purchase order id
    candidate_invoices: list[dict] # candidate invoices returned by search
    selected_invoice: Optional[dict] # selected invoice dictionary
    matched_po: Optional[dict]   # matched purchase order dictionary
    reconciliation: Optional[dict] # reconciliation comparison details
    discrepancies: list[str]     # list of discrepancy reasons
    comparisons: dict            # field-level comparison breakdown

    # Control flow
    status: str                  # running / completed / failed / needs_input / waiting_approval
    needs_input_question: Optional[str]
    approval_requested: bool
    approval_id: Optional[int]

    # Verification
    verification: dict           # per-field PASS/FAIL/NOT_CHECKED

    # Evidence (references to EvidenceEntry IDs)
    evidence_ids: list[int]

    # Final output
    summary: str


def initial_state(task_id: str, request: str, workflow: str) -> AgentState:
    return AgentState(
        task_id=task_id,
        request=request,
        workflow=workflow,
        goal={},
        steps=[],
        current_step=0,
        retry_counts={},
        errors=[],
        documents=[],
        extracted={},
        vendor_info=None,
        invoice_id=None,
        po_id=None,
        candidate_invoices=[],
        selected_invoice=None,
        matched_po=None,
        reconciliation=None,
        discrepancies=[],
        comparisons={},
        status="running",
        needs_input_question=None,
        approval_requested=False,
        approval_id=None,
        verification={},
        evidence_ids=[],
        summary="",
    )
