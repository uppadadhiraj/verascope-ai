from __future__ import annotations

import datetime as dt
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import ApprovalStatus, ApprovalType

if TYPE_CHECKING:
    from app.models.repository import Repository
    from app.models.task import Task
    from app.models.user import User


class Approval(UUIDPKMixin, TimestampMixin, Base):
    """A human-in-the-loop gate (section 32). Nothing downstream of a
    CODE_CHANGE/GIT_OPERATION/PR_CREATION approval may proceed until this
    row's status is APPROVED."""

    __tablename__ = "approvals"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    approval_type: Mapped[ApprovalType] = mapped_column(Enum(ApprovalType, name="approval_type"), nullable=False)
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus, name="approval_status"), default=ApprovalStatus.PENDING, nullable=False, index=True
    )
    summary_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    """Frozen snapshot of {problem, root_cause, evidence, proposed_changes,
    files_affected, tests, expected_impact, diff} exactly as shown to the
    user at decision time (section 32) -- so the approval record stays
    meaningful even if the task evolves afterward."""
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    repository: Mapped["Repository"] = relationship(back_populates="approvals")
    task: Mapped["Task"] = relationship(back_populates="approvals")
