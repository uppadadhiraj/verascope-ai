from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict

from app.models.enums import ChangeLifecycleState, ChangeType


class CodeChangeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    change_type: ChangeType
    lifecycle_state: ChangeLifecycleState
    file_path: str
    diff: str | None
    reason: str
    agent_name: str
    applied_to_main: bool
    created_at: dt.datetime


class CodeChangeDetailRead(CodeChangeRead):
    old_content: str | None
    new_content: str | None


class DiffSummary(BaseModel):
    task_id: uuid.UUID
    files_created: list[str] = []
    files_modified: list[str] = []
    files_deleted: list[str] = []
    changes: list[CodeChangeRead] = []
    unified_diff: str
