"""Human approval gate (section 32). This is the ONLY place an Approval's
status can move from PENDING -- every downstream action (Fix Agent writing
to a workspace, a git branch/commit, a PR) checks the resulting status
before proceeding.
"""
from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_repository
from app.db.session import get_db
from app.models.approval import Approval
from app.models.enums import ApprovalStatus
from app.models.repository import Repository
from app.models.user import User
from app.schemas.approval import ApprovalDecision, ApprovalRead

router = APIRouter(prefix="/repositories/{repository_id}/approvals", tags=["approvals"])


@router.get("", response_model=list[ApprovalRead])
def list_approvals(
    repository: Repository = Depends(get_owned_repository),
    db: Session = Depends(get_db),
    task_id: uuid.UUID | None = None,
) -> list[ApprovalRead]:
    query = db.query(Approval).filter(Approval.repository_id == repository.id)
    if task_id:
        query = query.filter(Approval.task_id == task_id)
    rows = query.order_by(Approval.created_at.desc()).all()
    return [ApprovalRead.model_validate(r) for r in rows]


@router.get("/{approval_id}", response_model=ApprovalRead)
def get_approval(
    approval_id: uuid.UUID, repository: Repository = Depends(get_owned_repository), db: Session = Depends(get_db)
) -> ApprovalRead:
    approval = db.get(Approval, approval_id)
    if approval is None or approval.repository_id != repository.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found.")
    return ApprovalRead.model_validate(approval)


@router.patch("/{approval_id}", response_model=ApprovalRead)
def decide_approval(
    approval_id: uuid.UUID,
    payload: ApprovalDecision,
    repository: Repository = Depends(get_owned_repository),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApprovalRead:
    approval = db.get(Approval, approval_id)
    if approval is None or approval.repository_id != repository.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found.")
    if approval.status != ApprovalStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This approval has already been decided (status={approval.status.value}).",
        )
    if payload.status == ApprovalStatus.PENDING:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="status must be APPROVED, REJECTED, or CHANGES_REQUESTED.")

    approval.status = payload.status
    approval.comment = payload.comment
    approval.decided_at = dt.datetime.now(dt.timezone.utc)
    db.commit()
    db.refresh(approval)
    return ApprovalRead.model_validate(approval)
