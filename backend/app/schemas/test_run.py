from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict

from app.models.enums import TestRunStatus


class TestRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID | None
    framework: str | None
    command: str
    exit_code: int | None
    duration_ms: int | None
    passed_count: int | None
    failed_count: int | None
    output: str | None
    error_output: str | None
    status: TestRunStatus
    iteration: int
    created_at: dt.datetime


class RunTestsRequest(BaseModel):
    workspace_id: str | None = None
    """If omitted, tests run against the read-only indexed repository copy."""
    test_path: str | None = None
