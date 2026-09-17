from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_owned_repository
from app.db.session import get_db
from app.models.repository import Repository
from app.models.test_run import TestRun
from app.schemas.test_run import TestRunRead

router = APIRouter(prefix="/repositories/{repository_id}", tags=["tests"])


@router.get("/tasks/{task_id}/test-runs", response_model=list[TestRunRead])
def list_task_test_runs(
    task_id: uuid.UUID, repository: Repository = Depends(get_owned_repository), db: Session = Depends(get_db)
) -> list[TestRunRead]:
    rows = (
        db.query(TestRun)
        .filter(TestRun.task_id == task_id, TestRun.repository_id == repository.id)
        .order_by(TestRun.created_at)
        .all()
    )
    return [TestRunRead.model_validate(r) for r in rows]


@router.get("/test-runs", response_model=list[TestRunRead])
def list_repository_test_runs(
    repository: Repository = Depends(get_owned_repository), db: Session = Depends(get_db)
) -> list[TestRunRead]:
    rows = (
        db.query(TestRun)
        .filter(TestRun.repository_id == repository.id)
        .order_by(TestRun.created_at.desc())
        .limit(100)
        .all()
    )
    return [TestRunRead.model_validate(r) for r in rows]
