from __future__ import annotations

import datetime as dt
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import RepositorySourceType, RepositoryStatus

if TYPE_CHECKING:
    from app.models.agent_run import AgentRun
    from app.models.approval import Approval
    from app.models.code_change import CodeChange
    from app.models.conversation import Conversation
    from app.models.dependency import RepositoryDependency
    from app.models.file import RepositoryFile
    from app.models.finding import Finding
    from app.models.pull_request import PullRequest
    from app.models.symbol import RepositorySymbol
    from app.models.task import Task
    from app.models.test_run import TestRun
    from app.models.user import User


class Repository(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "repositories"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[RepositorySourceType] = mapped_column(
        Enum(RepositorySourceType, name="repository_source_type"), nullable=False
    )
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    local_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    default_branch: Mapped[str] = mapped_column(String(255), default="main", nullable=False)

    status: Mapped[RepositoryStatus] = mapped_column(
        Enum(RepositoryStatus, name="repository_status"),
        default=RepositoryStatus.PENDING,
        nullable=False,
        index=True,
    )
    status_detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    languages: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    frameworks: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    """Structured summary: purpose, entry_points, frameworks, database, auth,
    tests, facts/inferences/uncertain buckets. See services/ingestion/summary.py"""

    file_count: Mapped[int] = mapped_column(default=0, nullable=False)
    total_size_bytes: Mapped[int] = mapped_column(default=0, nullable=False)

    last_indexed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_security_scan_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    """Lets the frontend distinguish 'never scanned' from 'scanned and found
    nothing' -- both render as zero Finding rows, which looked like a
    silent failure to a real user before this field existed."""

    owner: Mapped["User"] = relationship(back_populates="repositories")
    files: Mapped[list["RepositoryFile"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
    symbols: Mapped[list["RepositorySymbol"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
    dependencies: Mapped[list["RepositoryDependency"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
    tasks: Mapped[list["Task"]] = relationship(back_populates="repository", cascade="all, delete-orphan")
    agent_runs: Mapped[list["AgentRun"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
    findings: Mapped[list["Finding"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
    code_changes: Mapped[list["CodeChange"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
    test_runs: Mapped[list["TestRun"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
    approvals: Mapped[list["Approval"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
    pull_requests: Mapped[list["PullRequest"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
