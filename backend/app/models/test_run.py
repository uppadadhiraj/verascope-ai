from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPKMixin
from app.models.enums import TestRunStatus

if TYPE_CHECKING:
    from app.models.repository import Repository
    from app.models.task import Task


class TestRun(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "test_runs"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
    )

    framework: Mapped[str | None] = mapped_column(String(64), nullable=True)
    """pytest | unittest | jest | vitest | junit | ctest | unknown"""
    command: Mapped[str] = mapped_column(String(1024), nullable=False)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    passed_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failed_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[TestRunStatus] = mapped_column(
        Enum(TestRunStatus, name="test_run_status"), nullable=False, index=True
    )
    iteration: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    """Which iteration of the autonomous fix loop (section 30) this run
    belongs to; 0 for a one-off/manual test run."""

    repository: Mapped["Repository"] = relationship(back_populates="test_runs")
    task: Mapped["Task | None"] = relationship(back_populates="test_runs")
