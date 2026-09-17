from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_repository
from app.core.config import get_settings
from app.db.session import get_db
from app.models.enums import RepositorySourceType, RepositoryStatus
from app.models.repository import Repository
from app.models.user import User
from app.schemas.repository import (
    IngestionProgress,
    RepositoryCreateFromGitHub,
    RepositoryRead,
    RepositorySummaryRead,
)
from app.services.ingestion.source import IngestionSourceError, validate_github_url
from app.workers.jobs import run_github_ingestion_job, run_rescan_job, run_zip_ingestion_job

router = APIRouter(prefix="/repositories", tags=["repositories"])

_ALLOWED_ZIP_CONTENT_TYPES = {"application/zip", "application/x-zip-compressed", "application/octet-stream"}
_MAX_ZIP_BYTES = 200 * 1024 * 1024


@router.post("/github", response_model=RepositoryRead, status_code=status.HTTP_201_CREATED)
def create_from_github(
    payload: RepositoryCreateFromGitHub,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RepositoryRead:
    try:
        owner, repo_name = validate_github_url(payload.repo_url)
    except IngestionSourceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    repository = Repository(
        owner_id=current_user.id,
        name=payload.name or repo_name,
        source_type=RepositorySourceType.GITHUB,
        source_url=payload.repo_url,
        status=RepositoryStatus.PENDING,
        status_detail="Queued for cloning",
    )
    db.add(repository)
    db.commit()
    db.refresh(repository)

    background_tasks.add_task(run_github_ingestion_job, str(repository.id), payload.repo_url, payload.branch)
    return RepositoryRead.model_validate(repository)


@router.post("/upload", response_model=RepositoryRead, status_code=status.HTTP_201_CREATED)
def create_from_zip(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RepositoryRead:
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only .zip files are accepted.")

    settings = get_settings()
    repository = Repository(
        owner_id=current_user.id,
        name=file.filename.rsplit(".", 1)[0],
        source_type=RepositorySourceType.ZIP,
        status=RepositoryStatus.PENDING,
        status_detail="Queued for extraction",
    )
    db.add(repository)
    db.commit()
    db.refresh(repository)

    upload_dir = Path(settings.workspace_storage_dir).resolve() / "_uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    zip_path = upload_dir / f"{repository.id}.zip"

    size = 0
    with open(zip_path, "wb") as out:
        while chunk := file.file.read(1024 * 1024):
            size += len(chunk)
            if size > _MAX_ZIP_BYTES:
                out.close()
                zip_path.unlink(missing_ok=True)
                db.delete(repository)
                db.commit()
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"ZIP file exceeds the {_MAX_ZIP_BYTES // (1024 * 1024)}MB limit.",
                )
            out.write(chunk)

    background_tasks.add_task(run_zip_ingestion_job, str(repository.id), str(zip_path))
    return RepositoryRead.model_validate(repository)


@router.get("", response_model=list[RepositoryRead])
def list_repositories(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> list[RepositoryRead]:
    rows = (
        db.query(Repository)
        .filter(Repository.owner_id == current_user.id)
        .order_by(Repository.created_at.desc())
        .all()
    )
    return [RepositoryRead.model_validate(r) for r in rows]


@router.get("/{repository_id}", response_model=RepositoryRead)
def get_repository(repository: Repository = Depends(get_owned_repository)) -> RepositoryRead:
    return RepositoryRead.model_validate(repository)


@router.get("/{repository_id}/progress", response_model=IngestionProgress)
def get_ingestion_progress(repository: Repository = Depends(get_owned_repository)) -> IngestionProgress:
    return IngestionProgress(
        repository_id=repository.id,
        status=repository.status,
        status_detail=repository.status_detail,
        error_message=repository.error_message,
    )


@router.get("/{repository_id}/summary", response_model=RepositorySummaryRead)
def get_repository_summary(repository: Repository = Depends(get_owned_repository)) -> RepositorySummaryRead:
    if repository.status != RepositoryStatus.READY or not repository.summary:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Repository is not ready yet (status={repository.status.value}). No summary available.",
        )
    return RepositorySummaryRead(**repository.summary)


@router.post("/{repository_id}/rescan", response_model=RepositoryRead)
def rescan_repository(
    background_tasks: BackgroundTasks,
    repository: Repository = Depends(get_owned_repository),
    db: Session = Depends(get_db),
) -> RepositoryRead:
    """Full re-index (section 48). Incremental change-detection is a
    documented V2 upgrade -- this MVP re-runs the full pipeline, which is
    correct (never stale) if slower than a true incremental rescan."""
    if repository.status in (RepositoryStatus.CLONING, RepositoryStatus.SCANNING, RepositoryStatus.PARSING, RepositoryStatus.EMBEDDING, RepositoryStatus.SUMMARIZING):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Repository is already being indexed.")

    repository.status = RepositoryStatus.PENDING
    repository.status_detail = "Queued for rescan"
    db.commit()

    if repository.source_type == RepositorySourceType.GITHUB:
        background_tasks.add_task(run_github_ingestion_job, str(repository.id), repository.source_url, repository.default_branch)
    else:
        background_tasks.add_task(run_rescan_job, str(repository.id))
    return RepositoryRead.model_validate(repository)


@router.delete("/{repository_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_repository(
    repository: Repository = Depends(get_owned_repository),
    db: Session = Depends(get_db),
) -> None:
    settings = get_settings()
    from app.services.vectorstore.chroma_store import get_vector_store

    get_vector_store().delete_repository(str(repository.id))

    repo_dir = settings.repo_path(str(repository.id))
    if repo_dir.exists():
        shutil.rmtree(repo_dir, ignore_errors=True)

    db.delete(repository)
    db.commit()
