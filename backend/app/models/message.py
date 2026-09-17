from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPKMixin
from app.models.enums import MessageRole

if TYPE_CHECKING:
    from app.models.conversation import Conversation


class Message(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole, name="message_role"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    """List of {file_path, start_line, end_line, symbol} the answer is
    grounded in. Empty/omitted means the assistant explicitly had
    insufficient evidence -- never fabricated citations."""
    token_usage: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    """{model, input_tokens, output_tokens, total_tokens, latency_ms}"""

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
