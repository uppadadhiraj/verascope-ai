"""Git branch/commit/PR endpoints (section 33, 34).

Both actions here require their corresponding Approval to already be
APPROVED -- this module trusts that check and does not re-derive it, but
every endpoint performs it explicitly before touching the repository clone.
Nothing here EVER writes to the repository's default branch.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_repository
from app.core.config import get_settings
from app.db.session import get_db
from app.models.approval import Approval
from app.models.code_change import CodeChange
from app.models.enums import (
    ApprovalStatus,
    ApprovalType,
    ChangeLifecycleState,
    PullRequestStatus,
    RepositorySourceType,
)
from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.models.task import Task
from app.models.user import User
from app.schemas.pull_request import CreateBranchRequest, CreatePullRequestRequest, PullRequestRead
from app.services.git import git_ops
from app.services.git.github_client import GitHubClientError, build_pr_description, create_pull_request
from app.services.git.git_ops import GitOpsError
from app.services.ingestion.source import validate_github_url

router = APIRouter(prefix="/repositories/{repository_id}/tasks/{task_id}", tags=["git"])


def _latest_approval(db: Session, task_id: uuid.UUID, approval_type: ApprovalType) -> Approval | None:
    return (
        db.query(Approval)
        .filter(Approval.task_id == task_id, Approval.approval_type == approval_type)
        .order_by(Approval.created_at.desc())
        .first()
    )


def _get_task_or_404(task_id: uuid.UUID, repository: Repository, db: Session) -> Task:
    task = db.get(Task, task_id)
    if task is None or task.repository_id != repository.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task {task_id} not found.")
    return task


@router.post("/git/branch", response_model=PullRequestRead, status_code=status.HTTP_201_CREATED)
def create_branch_and_commit(
    task_id: uuid.UUID,
    payload: CreateBranchRequest,
    repository: Repository = Depends(get_owned_repository),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PullRequestRead:
    task = _get_task_or_404(task_id, repository, db)

    approval = _latest_approval(db, task.id, ApprovalType.GIT_OPERATION)
    if approval is None or approval.status != ApprovalStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A GIT_OPERATION approval must be APPROVED before committing to a branch.",
        )

    # Scope to the MOST RECENT workspace_id for this task, not just
    # task_id. A task can accumulate CodeChange rows across several
    # separate fix-loop invocations (each its own workspace_id) -- earlier
    # ones from abandoned/failed attempts. Found live during testing:
    # without this scope, a stale or even broken file from an old failed
    # iteration could ride along into a real git commit alongside the
    # actually-validated fix.
    latest_change = (
        db.query(CodeChange).filter(CodeChange.task_id == task.id).order_by(CodeChange.created_at.desc()).first()
    )
    if latest_change is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No code changes exist for this task.")

    changes = (
        db.query(CodeChange)
        .filter(
            CodeChange.task_id == task.id,
            CodeChange.workspace_id == latest_change.workspace_id,
            CodeChange.lifecycle_state == ChangeLifecycleState.VALIDATED,
        )
        .order_by(CodeChange.created_at)
        .all()
    )
    if not changes:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No VALIDATED code changes exist for this task's latest fix attempt -- nothing safe to commit.",
        )

    # Within that one workspace, the same file can still have been written
    # more than once across loop iterations before tests passed -- keep
    # only the last (final) row per path.
    deduped_by_path: dict[str, CodeChange] = {}
    for c in changes:
        deduped_by_path[c.file_path] = c
    changes = list(deduped_by_path.values())

    settings = get_settings()
    repo_dir = settings.repo_path(str(repository.id))
    branch_name = payload.branch_name or git_ops.slugify_branch_name(task.title)

    applied = [
        git_ops.AppliedChange(path=c.file_path, change_type=c.change_type, new_content=c.new_content)
        for c in changes
    ]
    commit_message = f"{task.title}\n\nApplied by Verascope after human approval.\nTask: {task.id}"

    try:
        commit_sha = git_ops.create_branch_commit(
            repo_dir, branch_name, repository.default_branch, applied, commit_message
        )
    except GitOpsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    for c in changes:
        c.applied_to_main = True
    db.commit()

    pr_row = PullRequest(
        repository_id=repository.id,
        task_id=task.id,
        branch_name=branch_name,
        base_branch=repository.default_branch,
        commit_sha=commit_sha,
        title=task.title,
        status=PullRequestStatus.COMMITTED,
    )
    db.add(pr_row)

    if repository.source_type == RepositorySourceType.GITHUB:
        pr_approval = Approval(
            repository_id=repository.id,
            task_id=task.id,
            user_id=current_user.id,
            approval_type=ApprovalType.PR_CREATION,
            status=ApprovalStatus.PENDING,
            summary_snapshot={
                "branch_name": branch_name,
                "base_branch": repository.default_branch,
                "commit_sha": commit_sha,
                "files_changed": [c.file_path for c in changes],
            },
        )
        db.add(pr_approval)

    db.commit()
    db.refresh(pr_row)
    return PullRequestRead.model_validate(pr_row)


@router.get("/pull-requests", response_model=list[PullRequestRead])
def list_pull_requests(
    task_id: uuid.UUID, repository: Repository = Depends(get_owned_repository), db: Session = Depends(get_db)
) -> list[PullRequestRead]:
    rows = (
        db.query(PullRequest)
        .filter(PullRequest.task_id == task_id, PullRequest.repository_id == repository.id)
        .order_by(PullRequest.created_at.desc())
        .all()
    )
    return [PullRequestRead.model_validate(r) for r in rows]


@router.post("/git/pull-request", response_model=PullRequestRead)
def open_pull_request(
    task_id: uuid.UUID,
    payload: CreatePullRequestRequest,
    repository: Repository = Depends(get_owned_repository),
    db: Session = Depends(get_db),
) -> PullRequestRead:
    task = _get_task_or_404(task_id, repository, db)

    if repository.source_type != RepositorySourceType.GITHUB or not repository.source_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This repository has no GitHub remote configured -- cannot open a pull request.",
        )

    approval = _latest_approval(db, task.id, ApprovalType.PR_CREATION)
    if approval is None or approval.status != ApprovalStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A PR_CREATION approval must be APPROVED before opening a pull request.",
        )

    pr_row = (
        db.query(PullRequest)
        .filter(PullRequest.task_id == task.id, PullRequest.repository_id == repository.id)
        .order_by(PullRequest.created_at.desc())
        .first()
    )
    if pr_row is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No branch/commit exists for this task yet.")
    if pr_row.status == PullRequestStatus.PR_CREATED:
        return PullRequestRead.model_validate(pr_row)

    settings = get_settings()
    owner, repo_name = validate_github_url(repository.source_url)

    changes = db.query(CodeChange).filter(CodeChange.task_id == task.id).all()
    description = payload.description or build_pr_description(
        problem=task.description or task.title,
        root_cause=task.root_cause,
        changes_summary="\n".join(f"- {c.file_path}: {c.reason}" for c in changes),
        tests_summary="See the Test Results tab in Verascope for full output.",
        files_affected=[c.file_path for c in changes],
    )

    try:
        created = create_pull_request(
            github_token=settings.github_token,
            owner=owner,
            repo=repo_name,
            branch_name=pr_row.branch_name,
            base_branch=pr_row.base_branch,
            title=payload.title or task.title,
            body=description,
        )
    except GitHubClientError as exc:
        pr_row.status = PullRequestStatus.FAILED
        pr_row.error_message = str(exc)
        db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    pr_row.status = PullRequestStatus.PR_CREATED
    pr_row.pr_number = created.number
    pr_row.pr_url = created.html_url
    pr_row.description = description
    db.commit()
    db.refresh(pr_row)
    return PullRequestRead.model_validate(pr_row)
