from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_owned_repository
from app.db.session import get_db
from app.models.agent_run import AgentRun
from app.models.repository import Repository
from app.schemas.agent_run import AgentRunDetailRead, AgentRunRead, ToolCallRead

router = APIRouter(prefix="/repositories/{repository_id}/agent-runs", tags=["observability"])


@router.get("", response_model=list[AgentRunRead])
def list_agent_runs(
    repository: Repository = Depends(get_owned_repository),
    db: Session = Depends(get_db),
    task_id: uuid.UUID | None = None,
) -> list[AgentRunRead]:
    query = db.query(AgentRun).filter(AgentRun.repository_id == repository.id)
    if task_id:
        query = query.filter(AgentRun.task_id == task_id)
    rows = query.order_by(AgentRun.started_at.desc()).limit(200).all()
    return [AgentRunRead.model_validate(r) for r in rows]


@router.get("/{agent_run_id}", response_model=AgentRunDetailRead)
def get_agent_run(
    agent_run_id: uuid.UUID, repository: Repository = Depends(get_owned_repository), db: Session = Depends(get_db)
) -> AgentRunDetailRead:
    run = db.get(AgentRun, agent_run_id)
    if run is None or run.repository_id != repository.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found.")
    detail = AgentRunDetailRead.model_validate(run)
    detail.tool_calls = [ToolCallRead.model_validate(tc) for tc in run.tool_calls]
    return detail
