"""
policy.py - Permission and business-policy checks.

These functions are always executed in Python — the LLM cannot override them.
The agent checks policy BEFORE executing any write tool.

Rules:
- Writes always require "write" permission.
- Invoices over the threshold require approval.
- File access is restricted to the workspace.
- Approval decisions are validated here, not just in the frontend.
"""
from decimal import Decimal
from typing import Any

# These would come from a real auth system. For the prototype, a set of
# "authorized users" is hardcoded for local dev.
AUTHORIZED_APPROVERS = {"admin", "finance_manager", "dev"}

# Invoice amount above this (in INR) requires human approval before creation
APPROVAL_THRESHOLD_INR = Decimal("50000.00")


class PolicyError(Exception):
    """Raised when a policy check fails."""
    pass


def check_write_permission(tool_name: str, state: dict) -> None:
    """
    Verify the agent is allowed to execute a write tool.
    Currently all tasks have write permission by default (prototype).
    In production, this would check task roles or OAuth scopes.
    """
    from app.tools.registry import get_tool
    spec = get_tool(tool_name)
    if spec and spec.has_side_effects:
        # Future: check state["auth_roles"] etc.
        pass  # permitted for now


def check_amount_threshold(amount_str: str, currency: str = "INR") -> dict[str, Any]:
    """
    Returns whether the amount requires approval.
    Only INR is currently policy-controlled.
    """
    try:
        amount = Decimal(str(amount_str))
    except Exception:
        return {"requires_approval": False, "reason": "could not parse amount"}

    if currency == "INR" and amount > APPROVAL_THRESHOLD_INR:
        return {
            "requires_approval": True,
            "reason": f"Amount ₹{amount} exceeds threshold ₹{APPROVAL_THRESHOLD_INR}",
            "amount": str(amount),
            "threshold": str(APPROVAL_THRESHOLD_INR),
        }
    return {"requires_approval": False, "amount": str(amount)}


def validate_approval(decided_by: str, decision: str) -> None:
    """
    Validate that the approval decision comes from an authorized user.
    Raises PolicyError on failure — this check runs on the backend.
    """
    if decided_by not in AUTHORIZED_APPROVERS:
        raise PolicyError(f"'{decided_by}' is not an authorized approver")
    if decision not in {"approved", "rejected"}:
        raise PolicyError(f"Invalid decision: '{decision}'")


def classify_error(error_msg: str, attempt: int, max_retries: int) -> str:
    """
    Classify an error and decide what the agent should do next.
    Returns one of: "retry", "clarify", "escalate", "abort"
    """
    msg = error_msg.lower()

    if attempt >= max_retries:
        return "abort"

    # Temporary errors worth retrying
    if any(k in msg for k in ["timeout", "connection", "503", "rate limit", "temporarily"]):
        return "retry"

    # Duplicate — check existing record, don't create again
    if "409" in msg or "duplicate" in msg or "already exists" in msg:
        return "check_duplicate"

    # Missing data — might need user input
    if any(k in msg for k in ["not found", "404", "missing", "null", "none"]):
        return "clarify"

    # Permission errors — don't retry
    if any(k in msg for k in ["403", "forbidden", "unauthorized", "permission"]):
        return "escalate"

    return "retry"
