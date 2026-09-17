from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict

from app.models.enums import MessageRole


class ChatRequest(BaseModel):
    conversation_id: uuid.UUID | None = None
    message: str


class Citation(BaseModel):
    file_path: str
    start_line: int | None = None
    end_line: int | None = None
    symbol: str | None = None


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: MessageRole
    content: str
    citations: list[Citation] | None
    token_usage: dict | None
    created_at: dt.datetime


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    repository_id: uuid.UUID
    title: str
    created_at: dt.datetime
    updated_at: dt.datetime


class ConversationDetailRead(ConversationRead):
    messages: list[MessageRead] = []
