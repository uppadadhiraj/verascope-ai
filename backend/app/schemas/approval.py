from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict

from app.models.enums import ApprovalStatus, ApprovalType


class ApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    approval_type: ApprovalType
    status: ApprovalStatus
    summary_snapshot: dict
    comment: str | None
    decided_at: dt.datetime | None
    created_at: dt.datetime


class ApprovalDecision(BaseModel):
    status: ApprovalStatus
    comment: str | None = None
