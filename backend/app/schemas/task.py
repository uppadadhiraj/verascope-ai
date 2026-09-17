from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict

from app.models.enums import EvidenceStatus, StepStatus, TaskType


class DebugRequest(BaseModel):
    """Input to kick off a Debugger Agent investigation (section 23)."""

    description: str
    error_message: str | None = None
    stack_trace: str | None = None
    logs: str | None = None
    failing_test: str | None = None
    conversation_id: uuid.UUID | None = None


class TaskCreate(BaseModel):
    title: str
    description: str | None = None
    task_type: TaskType = TaskType.GENERAL


class TaskStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    step_number: int
    description: str
    status: StepStatus
    evidence: str | None
    started_at: dt.datetime | None
    completed_at: dt.datetime | None


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    repository_id: uuid.UUID
    title: str
    description: str | None
    task_type: TaskType
    status: StepStatus
    root_cause: str | None
    evidence: list | None
    evidence_status: EvidenceStatus | None
    confidence_notes: str | None
    started_at: dt.datetime | None
    completed_at: dt.datetime | None
    created_at: dt.datetime
    updated_at: dt.datetime


class TaskDetailRead(TaskRead):
    steps: list[TaskStepRead] = []
