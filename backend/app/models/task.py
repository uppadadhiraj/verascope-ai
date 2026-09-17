from __future__ import annotations

import datetime as dt
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import EvidenceStatus, StepStatus, TaskType

if TYPE_CHECKING:
    from app.models.agent_run import AgentRun
    from app.models.approval import Approval
    from app.models.code_change import CodeChange
    from app.models.pull_request import PullRequest
    from app.models.repository import Repository
    from app.models.test_run import TestRun
    from app.models.user import User


class Task(UUIDPKMixin, TimestampMixin, Base):
    """A unit of work the Planner has broken into steps -- a debugging
    investigation, a feature request, a security scan, etc. (section 21)."""

    __tablename__ = "tasks"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    task_type: Mapped[TaskType] = mapped_column(Enum(TaskType, name="task_type"), nullable=False)
    status: Mapped[StepStatus] = mapped_column(
        Enum(StepStatus, name="task_status"), default=StepStatus.PENDING, nullable=False, index=True
    )

    # --- Debugging-specific evidence trail (section 23, 37) ---
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    """List of {file_path, start_line, end_line, note}."""
    evidence_status: Mapped[EvidenceStatus | None] = mapped_column(
        Enum(EvidenceStatus, name="evidence_status"), nullable=True
    )
    confidence_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    repository: Mapped["Repository"] = relationship(back_populates="tasks")
    steps: Mapped[list["TaskStep"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="TaskStep.step_number"
    )
    agent_runs: Mapped[list["AgentRun"]] = relationship(back_populates="task")
    code_changes: Mapped[list["CodeChange"]] = relationship(back_populates="task")
    test_runs: Mapped[list["TestRun"]] = relationship(back_populates="task")
    approvals: Mapped[list["Approval"]] = relationship(back_populates="task")
    pull_requests: Mapped[list["PullRequest"]] = relationship(back_populates="task")


class TaskStep(UUIDPKMixin, Base):
    """A single Planner step. Statuses are PENDING/IN_PROGRESS/COMPLETED/
    FAILED/BLOCKED -- a step must never be marked COMPLETED without
    `evidence` backing it (enforced in the Planner agent, not here)."""

    __tablename__ = "task_steps"

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[StepStatus] = mapped_column(
        Enum(StepStatus, name="task_step_status"), default=StepStatus.PENDING, nullable=False
    )
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Free-text proof the step actually completed (a file read, a tool
    result, a test outcome) -- required before status can move to
    COMPLETED."""

    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    task: Mapped["Task"] = relationship(back_populates="steps")
