"""
ledger.py - Evidence Ledger.

Records every tool invocation and verification check to a persistent DB table.
The verifier reads from this ledger to build the final task report.
Keeping this separate from the agent logic enforces the principle that
"no evidence, no success claim."
"""
from datetime import datetime
from typing import Any

import app.database as _db
from app.models import EvidenceEntry


def record(
    task_id: str,
    step: int,
    action: str,
    tool_name: str = None,
    inputs: dict = None,
    outputs: dict = None,
    status: str = "ok",
    source_ref: str = None,
    notes: str = None,
) -> int:
    """
    Write one evidence entry to the DB and return its ID.
    Called after every tool execution and verification check.
    """
    db = _db.SessionLocal()
    try:
        entry = EvidenceEntry(
            task_id=task_id,
            step=step,
            action=action,
            tool_name=tool_name,
            inputs=inputs or {},
            outputs=_sanitize(outputs) or {},
            status=status,
            source_ref=source_ref,
            notes=notes,
            timestamp=datetime.utcnow(),
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry.id
    finally:
        db.close()


def _sanitize(data: Any) -> Any:
    """Remove sensitive keys from evidence before storing."""
    if not isinstance(data, dict):
        return data
    blocked = {"api_key", "password", "secret", "token", "authorization"}
    return {k: v for k, v in data.items() if k.lower() not in blocked}


def get_entries(task_id: str) -> list[dict]:
    """Return all evidence entries for a task as plain dicts."""
    db = _db.SessionLocal()
    try:
        rows = db.query(EvidenceEntry).filter_by(task_id=task_id).order_by(EvidenceEntry.id).all()
        return [
            {
                "id": r.id,
                "step": r.step,
                "action": r.action,
                "tool_name": r.tool_name,
                "inputs": r.inputs,
                "outputs": r.outputs,
                "status": r.status,
                "source_ref": r.source_ref,
                "notes": r.notes,
                "timestamp": r.timestamp.isoformat(),
            }
            for r in rows
        ]
    finally:
        db.close()
