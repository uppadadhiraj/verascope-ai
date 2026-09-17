from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_owned_repository
from app.db.session import get_db
from app.models.code_change import CodeChange
from app.models.enums import ChangeType
from app.models.repository import Repository
from app.schemas.code_change import CodeChangeRead, DiffSummary

router = APIRouter(prefix="/repositories/{repository_id}/tasks/{task_id}", tags=["changes"])


@router.get("/changes", response_model=list[CodeChangeRead])
def list_changes(
    task_id: uuid.UUID, repository: Repository = Depends(get_owned_repository), db: Session = Depends(get_db)
) -> list[CodeChangeRead]:
    rows = (
        db.query(CodeChange)
        .filter(CodeChange.task_id == task_id, CodeChange.repository_id == repository.id)
        .order_by(CodeChange.created_at)
        .all()
    )
    return [CodeChangeRead.model_validate(r) for r in rows]


@router.get("/diff", response_model=DiffSummary)
def get_diff(
    task_id: uuid.UUID, repository: Repository = Depends(get_owned_repository), db: Session = Depends(get_db)
) -> DiffSummary:
    rows = (
        db.query(CodeChange)
        .filter(CodeChange.task_id == task_id, CodeChange.repository_id == repository.id)
        .order_by(CodeChange.created_at)
        .all()
    )
    return DiffSummary(
        task_id=task_id,
        files_created=[r.file_path for r in rows if r.change_type == ChangeType.CREATE],
        files_modified=[r.file_path for r in rows if r.change_type == ChangeType.MODIFY],
        files_deleted=[r.file_path for r in rows if r.change_type == ChangeType.DELETE],
        changes=[CodeChangeRead.model_validate(r) for r in rows],
        unified_diff="\n\n".join(r.diff or "" for r in rows),
    )
