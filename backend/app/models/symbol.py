from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin

if TYPE_CHECKING:
    from app.models.file import RepositoryFile
    from app.models.repository import Repository


class RepositorySymbol(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "repository_symbols"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repository_files.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_symbol_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repository_symbols.id", ondelete="CASCADE"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    symbol_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    """function | method | class | interface | variable | route"""
    language: Mapped[str] = mapped_column(String(64), nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    docstring: Mapped[str | None] = mapped_column(Text, nullable=True)
    route_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    """Populated only for symbol_type == 'route' (e.g. '/api/users/{id}')."""
    http_method: Mapped[str | None] = mapped_column(String(16), nullable=True)

    repository: Mapped["Repository"] = relationship(back_populates="symbols")
    file: Mapped["RepositoryFile"] = relationship(back_populates="symbols")
    parent: Mapped["RepositorySymbol | None"] = relationship(
        remote_side="RepositorySymbol.id", back_populates="children"
    )
    children: Mapped[list["RepositorySymbol"]] = relationship(back_populates="parent")
