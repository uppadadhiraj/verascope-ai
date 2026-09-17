from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPKMixin
from app.models.enums import RelationshipType

if TYPE_CHECKING:
    from app.models.repository import Repository


class RepositoryDependency(UUIDPKMixin, CreatedAtMixin, Base):
    """An edge in the repository relationship graph (section 13).

    Targets are nullable because a reference may point outside the
    repository (a third-party import) or to a symbol the parser could not
    resolve -- in that case `raw_reference` retains the textual reference so
    the edge is still useful evidence instead of being silently dropped.
    """

    __tablename__ = "repository_dependencies"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relationship_type: Mapped[RelationshipType] = mapped_column(
        Enum(RelationshipType, name="dependency_relationship_type"), nullable=False, index=True
    )

    source_file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repository_files.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_symbol_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repository_symbols.id", ondelete="CASCADE"), nullable=True
    )

    target_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repository_files.id", ondelete="CASCADE"), nullable=True, index=True
    )
    target_symbol_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repository_symbols.id", ondelete="CASCADE"), nullable=True
    )
    raw_reference: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    """e.g. the raw import string ('from ..utils import foo') when the
    target could not be resolved to a file in this repository."""

    repository: Mapped["Repository"] = relationship(back_populates="dependencies")
