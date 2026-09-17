"""Background job entry points (section 40: long-running operations must
not block ordinary HTTP requests).

For this MVP, "background" means FastAPI's BackgroundTasks -- simple,
in-process, and honest about what it is (no Celery/Redis claimed that isn't
there). Each job opens its OWN DB session because the request-scoped
session from api/deps.py is already closed by the time these run. Progress
is communicated to the frontend via polling the resource's status field
(Repository.status, Task.status) rather than websockets -- documented as a
V2 upgrade path (section 54), not implemented here.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from app.agents import orchestrator, security_agent
from app.agents.context import AgentContext
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.enums import ApprovalStatus, ApprovalType, RepositoryStatus, StepStatus
from app.models.repository import Repository
from app.models.task import Task
from app.services.ingestion.pipeline import run_ingestion_pipeline
from app.services.ingestion.source import IngestionSourceError, clone_github_repository, extract_zip_archive
from app.services.llm.factory import get_llm_provider
from app.services.vectorstore.chroma_store import get_vector_store
from app.db.session import SessionLocal

logger = get_logger(__name__)


def _mark_repository_failed(db, repository_id: str, message: str) -> None:
    # db.rollback() FIRST: if we got here because a flush/commit failed
    # (e.g. a UniqueViolation), the session's transaction is left in a
    # "pending rollback" state where any further statement -- including the
    # `db.get()` below and the eventual commit -- raises PendingRollbackError
    # until it's explicitly rolled back. Found live: every one of this
    # module's exception handlers had this gap, which meant a mid-transaction
    # DB error could silently prevent status=FAILED from ever being recorded,
    # leaving a repository/task stuck at whatever status it last reached
    # (e.g. SCANNING) forever with no error surfaced to the user.
    db.rollback()
    repository = db.get(Repository, uuid.UUID(repository_id))
    if repository:
        repository.status = RepositoryStatus.FAILED
        repository.error_message = message
        db.commit()


def _mark_task_failed(db, task_id: str) -> None:
    db.rollback()
    task = db.get(Task, uuid.UUID(task_id))
    if task:
        task.status = StepStatus.FAILED
        db.commit()


def run_github_ingestion_job(repository_id: str, repo_url: str, branch: str | None) -> None:
    db = SessionLocal()
    settings = get_settings()
    try:
        repository = db.get(Repository, uuid.UUID(repository_id))
        if repository is None:
            return
        repository.status = RepositoryStatus.CLONING
        repository.status_detail = "Cloning repository from GitHub"
        db.commit()

        dest = settings.repo_path(repository_id)
        try:
            active_branch = clone_github_repository(repo_url, dest, branch=branch, github_token=settings.github_token)
        except IngestionSourceError as exc:
            repository.status = RepositoryStatus.FAILED
            repository.error_message = str(exc)
            db.commit()
            return

        repository.default_branch = active_branch
        repository.local_path = str(dest)
        db.commit()

        run_ingestion_pipeline(db, repository, settings)
    except Exception as exc:  # noqa: BLE001
        logger.error("github_ingestion_job_failed", repository_id=repository_id, error=str(exc))
        _mark_repository_failed(db, repository_id, f"Unexpected error: {exc}")
    finally:
        db.close()


def run_zip_ingestion_job(repository_id: str, zip_path: str) -> None:
    db = SessionLocal()
    settings = get_settings()
    try:
        repository = db.get(Repository, uuid.UUID(repository_id))
        if repository is None:
            return
        repository.status = RepositoryStatus.CLONING
        repository.status_detail = "Extracting uploaded archive"
        db.commit()

        dest = settings.repo_path(repository_id)
        try:
            extract_zip_archive(Path(zip_path), dest)
        except IngestionSourceError as exc:
            repository.status = RepositoryStatus.FAILED
            repository.error_message = str(exc)
            db.commit()
            return
        finally:
            Path(zip_path).unlink(missing_ok=True)

        repository.local_path = str(dest)
        db.commit()

        run_ingestion_pipeline(db, repository, settings)
    except Exception as exc:  # noqa: BLE001
        logger.error("zip_ingestion_job_failed", repository_id=repository_id, error=str(exc))
        _mark_repository_failed(db, repository_id, f"Unexpected error: {exc}")
    finally:
        db.close()


def run_rescan_job(repository_id: str) -> None:
    """Re-runs the ingestion pipeline against the already-present on-disk
    repository copy (used for ZIP-sourced repositories, and as the shared
    tail end of the GitHub rescan path)."""
    db = SessionLocal()
    settings = get_settings()
    try:
        repository = db.get(Repository, uuid.UUID(repository_id))
        if repository is None:
            return
        run_ingestion_pipeline(db, repository, settings)
    except Exception as exc:  # noqa: BLE001
        logger.error("rescan_job_failed", repository_id=repository_id, error=str(exc))
        _mark_repository_failed(db, repository_id, f"Unexpected error: {exc}")
    finally:
        db.close()


def run_investigation_job(
    task_id: str,
    description: str,
    error_message: str | None,
    stack_trace: str | None,
    logs: str | None,
    failing_test: str | None,
) -> None:
    db = SessionLocal()
    try:
        task = db.get(Task, uuid.UUID(task_id))
        if task is None:
            return
        repository = task.repository
        settings = get_settings()
        ctx = AgentContext(db=db, settings=settings, repository=repository, vector_store=get_vector_store(), task=task)
        provider = get_llm_provider()

        result = orchestrator.run_investigation(
            ctx, provider, task, description, error_message, stack_trace, logs, failing_test
        )

        if result.finding.evidence_status.value != "INSUFFICIENT":
            from app.models.approval import Approval

            approval = Approval(
                repository_id=repository.id,
                task_id=task.id,
                user_id=task.user_id,
                approval_type=ApprovalType.CODE_CHANGE,
                status=ApprovalStatus.PENDING,
                summary_snapshot={
                    "problem": description,
                    "root_cause": result.finding.root_cause,
                    "evidence": result.finding.evidence,
                    "evidence_status": result.finding.evidence_status.value,
                    "proposed_fix": result.finding.proposed_fix,
                    "regression_test_description": result.finding.regression_test_description,
                    "affected_files": result.finding.affected_files,
                    "impact": result.finding.impact,
                },
            )
            db.add(approval)
            task.status = StepStatus.BLOCKED
            db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.error("investigation_job_failed", task_id=task_id, error=str(exc))
        _mark_task_failed(db, task_id)
    finally:
        db.close()


def run_fix_loop_job(task_id: str, initial_instructions: str) -> None:
    db = SessionLocal()
    try:
        task = db.get(Task, uuid.UUID(task_id))
        if task is None:
            return
        repository = task.repository
        settings = get_settings()
        ctx = AgentContext(db=db, settings=settings, repository=repository, vector_store=get_vector_store(), task=task)
        provider = get_llm_provider()

        fix_result = orchestrator.run_autonomous_fix_loop(ctx, provider, task, initial_instructions)

        if fix_result.passed:
            from app.models.approval import Approval
            from app.services.git.workspace import unified_diff

            diff_blob = "\n\n".join(
                unified_diff(c.old_content, c.new_content, c.file_path) for c in fix_result.code_changes
            )
            approval = Approval(
                repository_id=repository.id,
                task_id=task.id,
                user_id=task.user_id,
                approval_type=ApprovalType.GIT_OPERATION,
                status=ApprovalStatus.PENDING,
                summary_snapshot={
                    "files_changed": [c.file_path for c in fix_result.code_changes],
                    "diff": diff_blob[:20000],
                    "iterations_used": fix_result.iterations_used,
                    "review": {
                        "overall_assessment": fix_result.review.overall_assessment if fix_result.review else None,
                        "summary": fix_result.review.summary if fix_result.review else None,
                        "issues": [i.__dict__ for i in fix_result.review.issues] if fix_result.review else [],
                    },
                },
            )
            db.add(approval)
            db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.error("fix_loop_job_failed", task_id=task_id, error=str(exc))
        _mark_task_failed(db, task_id)
    finally:
        db.close()


def run_security_scan_job(repository_id: str, task_id: str | None = None) -> None:
    db = SessionLocal()
    try:
        repository = db.get(Repository, uuid.UUID(repository_id))
        if repository is None:
            return
        settings = get_settings()
        security_agent.scan_repository(db, repository, settings.repo_path)
        # Set regardless of whether any findings were produced -- a clean
        # scan result (0 findings) is a real, useful outcome and must be
        # distinguishable from "never scanned yet" (see the field's
        # docstring on the model).
        import datetime as dt

        repository.last_security_scan_at = dt.datetime.now(dt.timezone.utc)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.error("security_scan_job_failed", repository_id=repository_id, error=str(exc))
        db.rollback()
    finally:
        db.close()
