"""Enforces the PROPOSED -> APPLIED -> TESTED -> VALIDATED state machine for
CodeChange rows (section 37). These states must never be conflated: only
this function may advance one, and only forward (or to REJECTED from
anywhere).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.code_change import CodeChange
from app.models.enums import ChangeLifecycleState

_ORDER = [
    ChangeLifecycleState.PROPOSED,
    ChangeLifecycleState.APPLIED,
    ChangeLifecycleState.TESTED,
    ChangeLifecycleState.VALIDATED,
]


class LifecycleError(Exception):
    pass


def advance(db: Session, change: CodeChange, new_state: ChangeLifecycleState) -> None:
    if new_state == ChangeLifecycleState.REJECTED:
        change.lifecycle_state = new_state
        db.commit()
        return

    current_idx = _ORDER.index(change.lifecycle_state)
    new_idx = _ORDER.index(new_state)
    if new_idx < current_idx:
        raise LifecycleError(
            f"Cannot move CodeChange {change.id} backward from {change.lifecycle_state.value} to {new_state.value}."
        )
    change.lifecycle_state = new_state
    db.commit()
