"""Startup reconciliation: recovers from a backend crash/restart that
happened mid-job.

This project's background jobs (app/workers/jobs.py) run in-process via
FastAPI's BackgroundTasks -- deliberately simple, no external queue (see
README's "Known limitations"). The real cost of that simplicity: if the
process dies while a job is running (a crash, a `docker compose down`, a
deploy, Ctrl-C), whatever row that job was updating is left sitting in a
non-terminal status (SCANNING, EMBEDDING, IN_PROGRESS, ...) forever, with no
error message and no way for a user to tell anything is wrong -- observed
directly during development, and confirmed to require manual DB
intervention to recover from.

This is not a substitute for a real job queue with heartbeats/retries (the
correct V2 fix, per the README) -- it's the honest, minimal thing that
closes the "stuck forever, silently" failure mode for this MVP's simpler
architecture: on every startup, anything left mid-job by whatever process
existed before this one is definitionally NOT still running (this process
hasn't dispatched anything yet), so it's safe to mark it failed with a
clear, specific reason and let the user retry.
"""
from __future__ import annotations

from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.models.enums import RepositoryStatus, StepStatus
from app.models.repository import Repository
from app.models.task import Task

logger = get_logger(__name__)

_INTERRUPTED_MESSAGE = (
    "Interrupted by a server restart while this was in progress. No data was corrupted, "
    "but the job did not finish -- please retry."
)

_STUCK_REPOSITORY_STATUSES = [
    RepositoryStatus.PENDING,
    RepositoryStatus.CLONING,
    RepositoryStatus.SCANNING,
    RepositoryStatus.PARSING,
    RepositoryStatus.EMBEDDING,
    RepositoryStatus.SUMMARIZING,
]


def reconcile_stuck_state() -> None:
    db = SessionLocal()
    try:
        stuck_repos = (
            db.query(Repository).filter(Repository.status.in_(_STUCK_REPOSITORY_STATUSES)).all()
        )
        for repo in stuck_repos:
            logger.warning(
                "reconcile_stuck_repository", repository_id=str(repo.id), previous_status=repo.status.value
            )
            repo.status = RepositoryStatus.FAILED
            repo.error_message = _INTERRUPTED_MESSAGE
            repo.status_detail = "Ingestion interrupted"

        stuck_tasks = db.query(Task).filter(Task.status == StepStatus.IN_PROGRESS).all()
        for task in stuck_tasks:
            logger.warning("reconcile_stuck_task", task_id=str(task.id))
            task.status = StepStatus.FAILED
            note = f"Interrupted: {_INTERRUPTED_MESSAGE}"
            task.confidence_notes = f"{task.confidence_notes}\n\n{note}" if task.confidence_notes else note

        if stuck_repos or stuck_tasks:
            db.commit()
            logger.info(
                "reconcile_complete", repositories_recovered=len(stuck_repos), tasks_recovered=len(stuck_tasks)
            )
    finally:
        db.close()
