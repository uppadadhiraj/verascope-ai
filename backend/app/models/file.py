from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin

if TYPE_CHECKING:
    from app.models.repository import Repository
    from app.models.symbol import RepositorySymbol


class RepositoryFile(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "repository_files"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    path: Mapped[str] = mapped_column(String(1024), nullable=False, index=True)
    """Repository-relative path, forward-slash separated."""
    language: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    line_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    is_test: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_config: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_documentation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_binary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    skipped_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    """Set when the file was intentionally excluded from parsing/embedding
    (too large, binary, generated, etc.) so ingestion can report why."""

    parse_error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    """Non-null if AST/regex parsing failed for this file. Per spec section
    11, a parse failure must not abort the whole repository ingestion."""

    repository: Mapped["Repository"] = relationship(back_populates="files")
    symbols: Mapped[list["RepositorySymbol"]] = relationship(
        back_populates="file", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("repository_id", "path", name="uq_repo_file_path"),)
