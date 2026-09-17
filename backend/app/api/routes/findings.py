from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_owned_repository
from app.db.session import get_db
from app.models.enums import RepositoryStatus
from app.models.finding import Finding
from app.models.repository import Repository
from app.schemas.finding import FindingRead, FindingStatusUpdate
from app.workers.jobs import run_security_scan_job

router = APIRouter(prefix="/repositories/{repository_id}/findings", tags=["security"])


@router.post("/scan", status_code=status.HTTP_202_ACCEPTED)
def trigger_security_scan(
    background_tasks: BackgroundTasks,
    repository: Repository = Depends(get_owned_repository),
    db: Session = Depends(get_db),
) -> dict:
    if repository.status != RepositoryStatus.READY:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Repository is not ready for scanning yet (status={repository.status.value}).",
        )
    db.query(Finding).filter(Finding.repository_id == repository.id).delete()
    db.commit()
    background_tasks.add_task(run_security_scan_job, str(repository.id))
    return {"status": "scan_started"}


@router.get("", response_model=list[FindingRead])
def list_findings(
    repository: Repository = Depends(get_owned_repository), db: Session = Depends(get_db)
) -> list[FindingRead]:
    rows = (
        db.query(Finding)
        .filter(Finding.repository_id == repository.id)
        .order_by(Finding.severity.desc(), Finding.created_at.desc())
        .all()
    )
    return [FindingRead.model_validate(r) for r in rows]


@router.patch("/{finding_id}", response_model=FindingRead)
def update_finding_status(
    finding_id: uuid.UUID,
    payload: FindingStatusUpdate,
    repository: Repository = Depends(get_owned_repository),
    db: Session = Depends(get_db),
) -> FindingRead:
    finding = db.get(Finding, finding_id)
    if finding is None or finding.repository_id != repository.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found.")
    finding.status = payload.status
    db.commit()
    db.refresh(finding)
    return FindingRead.model_validate(finding)
