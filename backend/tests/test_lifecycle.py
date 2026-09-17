import pytest

from app.agents.lifecycle import LifecycleError, advance
from app.models.code_change import CodeChange
from app.models.enums import ChangeLifecycleState, ChangeType


class _FakeSession:
    def commit(self):
        pass


def _change(state: ChangeLifecycleState) -> CodeChange:
    return CodeChange(
        change_type=ChangeType.MODIFY,
        lifecycle_state=state,
        file_path="app/main.py",
        reason="test",
        agent_name="fix",
        workspace_id="ws-1",
    )


def test_advance_moves_forward():
    db = _FakeSession()
    change = _change(ChangeLifecycleState.PROPOSED)
    advance(db, change, ChangeLifecycleState.APPLIED)
    assert change.lifecycle_state == ChangeLifecycleState.APPLIED
    advance(db, change, ChangeLifecycleState.TESTED)
    assert change.lifecycle_state == ChangeLifecycleState.TESTED


def test_advance_rejects_moving_backward():
    db = _FakeSession()
    change = _change(ChangeLifecycleState.TESTED)
    with pytest.raises(LifecycleError):
        advance(db, change, ChangeLifecycleState.PROPOSED)
    assert change.lifecycle_state == ChangeLifecycleState.TESTED


def test_advance_allows_reject_from_any_state():
    db = _FakeSession()
    change = _change(ChangeLifecycleState.TESTED)
    advance(db, change, ChangeLifecycleState.REJECTED)
    assert change.lifecycle_state == ChangeLifecycleState.REJECTED
