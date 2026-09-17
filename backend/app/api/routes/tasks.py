from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_repository
from app.db.session import get_db
from app.models.approval import Approval
from app.models.enums import ApprovalStatus, ApprovalType, RepositoryStatus, StepStatus, TaskType
from app.models.repository import Repository
from app.models.task import Task
from app.models.user import User
from app.schemas.task import DebugRequest, TaskCreate, TaskDetailRead, TaskRead, TaskStepRead
from app.workers.jobs import run_fix_loop_job, run_investigation_job

router = APIRouter(tags=["tasks"])


def _latest_approval(db: Session, task_id: uuid.UUID, approval_type: ApprovalType) -> Approval | None:
    return (
        db.query(Approval)
        .filter(Approval.task_id == task_id, Approval.approval_type == approval_type)
        .order_by(Approval.created_at.desc())
        .first()
    )


@router.post("/repositories/{repository_id}/debug", response_model=TaskRead, status_code=status.HTTP_202_ACCEPTED)
def start_debug_investigation(
    payload: DebugRequest,
    background_tasks: BackgroundTasks,
    repository: Repository = Depends(get_owned_repository),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskRead:
    if repository.status != RepositoryStatus.READY:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Repository is not ready for debugging yet (status={repository.status.value}).",
        )

    task = Task(
        repository_id=repository.id,
        user_id=current_user.id,
        conversation_id=payload.conversation_id,
        title=payload.description[:200],
        description=payload.description,
        task_type=TaskType.DEBUG,
        status=StepStatus.PENDING,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    background_tasks.add_task(
        run_investigation_job,
        str(task.id),
        payload.description,
        payload.error_message,
        payload.stack_trace,
        payload.logs,
        payload.failing_test,
    )
    return TaskRead.model_validate(task)


@router.post("/repositories/{repository_id}/tasks", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    repository: Repository = Depends(get_owned_repository),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskRead:
    task = Task(
        repository_id=repository.id,
        user_id=current_user.id,
        title=payload.title,
        description=payload.description,
        task_type=payload.task_type,
        status=StepStatus.PENDING,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return TaskRead.model_validate(task)


@router.get("/repositories/{repository_id}/tasks", response_model=list[TaskRead])
def list_tasks(repository: Repository = Depends(get_owned_repository), db: Session = Depends(get_db)) -> list[TaskRead]:
    rows = db.query(Task).filter(Task.repository_id == repository.id).order_by(Task.created_at.desc()).all()
    return [TaskRead.model_validate(r) for r in rows]


def _get_task_or_404(task_id: uuid.UUID, repository: Repository, db: Session) -> Task:
    task = db.get(Task, task_id)
    if task is None or task.repository_id != repository.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task {task_id} not found.")
    return task


@router.get("/repositories/{repository_id}/tasks/{task_id}", response_model=TaskDetailRead)
def get_task(
    task_id: uuid.UUID, repository: Repository = Depends(get_owned_repository), db: Session = Depends(get_db)
) -> TaskDetailRead:
    task = _get_task_or_404(task_id, repository, db)
    detail = TaskDetailRead.model_validate(task)
    detail.steps = [TaskStepRead.model_validate(s) for s in task.steps]
    return detail


@router.post(
    "/repositories/{repository_id}/tasks/{task_id}/fix",
    response_model=TaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_fix_loop(
    task_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    repository: Repository = Depends(get_owned_repository),
    db: Session = Depends(get_db),
) -> TaskRead:
    """Requires a CODE_CHANGE approval for this task to already be APPROVED
    (section 32, 51) -- the Fix Agent will not write a single file otherwise."""
    task = _get_task_or_404(task_id, repository, db)

    approval = _latest_approval(db, task.id, ApprovalType.CODE_CHANGE)
    if approval is None or approval.status != ApprovalStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A CODE_CHANGE approval must be APPROVED before the Fix Agent can modify anything.",
        )

    snapshot = approval.summary_snapshot or {}
    instructions = (
        f"Problem: {snapshot.get('problem', task.description or task.title)}\n"
        f"Root cause: {snapshot.get('root_cause', task.root_cause) or 'unknown'}\n"
        f"Proposed fix: {snapshot.get('proposed_fix') or 'Use your judgement based on the root cause.'}\n"
        f"Regression test to write: {snapshot.get('regression_test_description') or 'Write a test that reproduces the original bug and passes once fixed.'}\n"
        f"Affected files (as predicted during investigation, verify before editing): {snapshot.get('affected_files', [])}\n"
    )

    task.status = StepStatus.IN_PROGRESS
    db.commit()

    background_tasks.add_task(run_fix_loop_job, str(task.id), instructions)
    return TaskRead.model_validate(task)
