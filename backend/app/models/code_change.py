from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base, CreatedAtMixin, UUIDPKMixin
from app.models.enums import ChangeLifecycleState, ChangeType

if TYPE_CHECKING:
    from app.models.repository import Repository
    from app.models.task import Task


class CodeChange(UUIDPKMixin, CreatedAtMixin, Base):
    """A single file-level modification proposed/applied by the Fix Agent,
    always inside an isolated workspace first (section 26).

    `lifecycle_state` must never be conflated: PROPOSED (diff generated,
    nothing on disk yet outside the sandbox workspace) -> APPLIED (written to
    the workspace) -> TESTED (tests ran against it) -> VALIDATED (Validation
    Agent confirmed the requested behavior). Only a VALIDATED + approved set
    of changes may ever be committed to a git branch.
    """

    __tablename__ = "code_changes"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
    )

    change_type: Mapped[ChangeType] = mapped_column(Enum(ChangeType, name="change_type"), nullable=False)
    lifecycle_state: Mapped[ChangeLifecycleState] = mapped_column(
        Enum(ChangeLifecycleState, name="change_lifecycle_state"),
        default=ChangeLifecycleState.PROPOSED,
        nullable=False,
        index=True,
    )

    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    old_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    diff: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    agent_name: Mapped[str] = mapped_column(String(64), nullable=False)

    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False)
    applied_to_main: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    """True only after an approved git commit lands this change on a branch
    off the user's actual repository -- never the default/main branch
    directly (section 27, 33)."""

    repository: Mapped["Repository"] = relationship(back_populates="code_changes")
    task: Mapped["Task"] = relationship(back_populates="code_changes")
