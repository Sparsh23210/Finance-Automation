"""
tasks.py - REST API for agent task management.
Handles task submission, status polling, evidence retrieval, and approvals.
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import datetime

from app.database import get_db
from app.models import Task, EvidenceEntry, ApprovalRequest
from app.schemas import TaskCreate, TaskOut, EvidenceOut, ApprovalDecision, ApprovalOut

router = APIRouter(prefix="/tasks", tags=["tasks"])


# Import here to avoid circular import; agent runner is in agent/graph.py
def _get_runner():
    from app.agent.graph import run_task
    return run_task


@router.post("", response_model=TaskOut, status_code=202)
def submit_task(body: TaskCreate, background: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Submit a natural-language task. The agent runs asynchronously in the background.
    Poll GET /tasks/{id} to check progress.
    """
    task_id = str(uuid.uuid4())
    task = Task(id=task_id, request=body.request, workflow=body.workflow, status="running")
    db.add(task)
    db.commit()
    db.refresh(task)

    run_task = _get_runner()
    background.add_task(run_task, task_id, body.request, body.workflow)

    return task


@router.get("", response_model=list[TaskOut])
def list_tasks(db: Session = Depends(get_db)):
    return db.query(Task).order_by(Task.created_at.desc()).limit(50).all()


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: str, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return task


@router.get("/{task_id}/evidence", response_model=list[EvidenceOut])
def get_evidence(task_id: str, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return db.query(EvidenceEntry).filter_by(task_id=task_id).order_by(EvidenceEntry.id).all()


@router.get("/{task_id}/approval", response_model=ApprovalOut)
def get_approval(task_id: str, db: Session = Depends(get_db)):
    ap = db.query(ApprovalRequest).filter_by(task_id=task_id).order_by(ApprovalRequest.id.desc()).first()
    if not ap:
        raise HTTPException(404, "No approval request for this task")
    return ap


@router.post("/{task_id}/approval/decide", response_model=ApprovalOut)
def decide_approval(task_id: str, body: ApprovalDecision, background: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Approve or reject a pending action.
    After approval, the agent is resumed in the background.
    NOTE: In a real system, this endpoint would require authentication.
    For the prototype, 'decided_by' is a plain string (local dev identity).
    """
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status != "waiting_approval":
        raise HTTPException(400, f"Task is not waiting for approval (current status: {task.status})")

    ap = db.query(ApprovalRequest).filter_by(task_id=task_id, decision="pending").first()
    if not ap:
        raise HTTPException(404, "No pending approval request")

    ap.decision = body.decision
    ap.decided_by = body.decided_by
    ap.decided_at = datetime.utcnow()

    if body.decision == "rejected":
        task.status = "failed"
        db.commit()
        return ap

    # Approved — resume the agent
    task.status = "running"
    db.commit()

    run_task = _get_runner()
    background.add_task(run_task, task_id, task.request, task.workflow, resume=True)
    return ap
