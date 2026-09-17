from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict

from app.models.enums import PullRequestStatus


class CreateBranchRequest(BaseModel):
    branch_name: str | None = None
    """Auto-generated from the task title if omitted, e.g. verascope/fix-invalid-jwt."""


class CreatePullRequestRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    open_pr: bool = True
    """If False, only branch + commit are created (no GitHub API call)."""


class PullRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    branch_name: str
    base_branch: str
    commit_sha: str | None
    pr_number: int | None
    pr_url: str | None
    title: str
    description: str | None
    status: PullRequestStatus
    error_message: str | None
    created_at: dt.datetime
