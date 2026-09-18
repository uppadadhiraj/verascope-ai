import uuid

from app.core.reconcile import _INTERRUPTED_MESSAGE, reconcile_stuck_state
from app.models.enums import RepositoryStatus, StepStatus
from app.models.repository import Repository
from app.models.task import Task


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_args, **_kwargs):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, repos, tasks):
        self._repos = repos
        self._tasks = tasks
        self.committed = False
        self.closed = False

    def query(self, model):
        if model is Repository:
            return _FakeQuery(self._repos)
        if model is Task:
            return _FakeQuery(self._tasks)
        raise AssertionError(f"unexpected model queried: {model}")

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


def _repo(status: RepositoryStatus) -> Repository:
    return Repository(
        owner_id=uuid.uuid4(),
        name="repo",
        source_type="github",
        status=status,
    )


def _task(status: StepStatus, confidence_notes: str | None = None) -> Task:
    return Task(
        repository_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        title="task",
        task_type="debug",
        status=status,
        confidence_notes=confidence_notes,
    )


def test_reconcile_marks_stuck_repository_failed(monkeypatch):
    stuck = _repo(RepositoryStatus.EMBEDDING)
    done = _repo(RepositoryStatus.READY)
    session = _FakeSession(repos=[stuck], tasks=[])
    monkeypatch.setattr("app.core.reconcile.SessionLocal", lambda: session)

    reconcile_stuck_state()

    assert stuck.status == RepositoryStatus.FAILED
    assert stuck.error_message == _INTERRUPTED_MESSAGE
    assert done.status == RepositoryStatus.READY  # untouched, never queried
    assert session.committed
    assert session.closed


def test_reconcile_marks_stuck_task_failed_and_appends_note(monkeypatch):
    stuck = _task(StepStatus.IN_PROGRESS, confidence_notes="earlier note")
    session = _FakeSession(repos=[], tasks=[stuck])
    monkeypatch.setattr("app.core.reconcile.SessionLocal", lambda: session)

    reconcile_stuck_state()

    assert stuck.status == StepStatus.FAILED
    assert "earlier note" in stuck.confidence_notes
    assert _INTERRUPTED_MESSAGE in stuck.confidence_notes
    assert session.committed


def test_reconcile_skips_commit_when_nothing_stuck(monkeypatch):
    session = _FakeSession(repos=[], tasks=[])
    monkeypatch.setattr("app.core.reconcile.SessionLocal", lambda: session)

    reconcile_stuck_state()

    assert not session.committed
    assert session.closed
