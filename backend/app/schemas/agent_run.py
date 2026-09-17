from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict

from app.models.enums import AgentName, AgentRunStatus


class ToolCallRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tool_name: str
    arguments: dict | None
    result_summary: str | None
    status: str
    error_message: str | None
    duration_ms: int | None
    created_at: dt.datetime


class AgentRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    repository_id: uuid.UUID
    task_id: uuid.UUID | None
    agent_name: AgentName
    status: AgentRunStatus
    started_at: dt.datetime
    ended_at: dt.datetime | None
    input_summary: str | None
    output_summary: str | None
    error_message: str | None
    files_accessed: list | None
    files_modified: list | None
    model: str | None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_ms: int | None


class AgentRunDetailRead(AgentRunRead):
    tool_calls: list[ToolCallRead] = []
