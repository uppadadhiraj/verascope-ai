from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict

from app.models.enums import FindingSeverity, FindingStatus


class FindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    finding_type: str
    severity: FindingSeverity
    status: FindingStatus
    file_path: str
    start_line: int | None
    end_line: int | None
    evidence: str
    explanation: str
    impact: str | None
    remediation: str | None
    created_at: dt.datetime


class FindingStatusUpdate(BaseModel):
    status: FindingStatus
