from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict

from app.models.enums import RepositorySourceType, RepositoryStatus


class RepositoryCreateFromGitHub(BaseModel):
    repo_url: str
    name: str | None = None
    branch: str | None = None


class RepositoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    source_type: RepositorySourceType
    source_url: str | None
    default_branch: str
    status: RepositoryStatus
    status_detail: str | None
    error_message: str | None
    languages: dict | None
    frameworks: list | None
    file_count: int
    total_size_bytes: int
    last_indexed_at: dt.datetime | None
    last_security_scan_at: dt.datetime | None
    created_at: dt.datetime
    updated_at: dt.datetime


class RepositorySummaryRead(BaseModel):
    """Facts/inferences/uncertain-tagged summary (section 16)."""

    purpose: str | None = None
    languages: list[str] = []
    frameworks: list[str] = []
    important_directories: list[str] = []
    entry_points: list[str] = []
    api_entry_points: list[str] = []
    database: str | None = None
    authentication: str | None = None
    major_components: list[str] = []
    test_framework: str | None = None
    build_instructions: str | None = None
    important_config_files: list[str] = []
    facts: list[str] = []
    inferences: list[str] = []
    uncertain: list[str] = []


class IngestionProgress(BaseModel):
    repository_id: uuid.UUID
    status: RepositoryStatus
    status_detail: str | None
    error_message: str | None
