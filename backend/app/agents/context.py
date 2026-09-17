"""Everything a tool handler needs to act -- and nothing more. Handlers
receive an AgentContext instead of reaching for globals, so every
filesystem/DB/vector-store access an agent makes is scoped to one
repository (and, where relevant, one workspace) by construction.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.repository import Repository
from app.models.task import Task
from app.services.vectorstore.base import VectorStore


@dataclass
class AgentContext:
    db: Session
    settings: Settings
    repository: Repository
    vector_store: VectorStore
    task: Task | None = None
    workspace_dir: Path | None = None
    workspace_id: str | None = None

    @property
    def repo_dir(self) -> Path:
        return self.settings.repo_path(str(self.repository.id))
