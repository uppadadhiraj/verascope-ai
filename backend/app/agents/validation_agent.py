"""Validation Agent (section 37): the only agent allowed to say a change is
VALIDATED. Deliberately rule-based against actual DB state (TestRun status,
CodeChange lifecycle) rather than trusting any agent's self-report --
"the bug is fixed" is a claim this codebase only lets you make after this
function agrees.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.agents.context import AgentContext
from app.agents.lifecycle import advance
from app.models.code_change import CodeChange
from app.models.enums import ChangeLifecycleState, TestRunStatus
from app.models.task import Task
from app.models.test_run import TestRun


@dataclass
class ValidationResult:
    validated: bool
    reasons: list[str] = field(default_factory=list)
    validated_change_ids: list[str] = field(default_factory=list)


def validate_task(ctx: AgentContext, task: Task, latest_test_run: TestRun | None) -> ValidationResult:
    """Scoped to ctx.workspace_id, not just task_id.

    A task can accumulate CodeChange rows across many separate fix-loop
    invocations (each with its own workspace_id), including abandoned,
    failed attempts. Querying by task_id alone has two real failure modes,
    both found live during testing:
      1. A stale PROPOSED/APPLIED row from an old, abandoned workspace can
         block validation ("N changes not tested yet") even when the
         CURRENT workspace's changes are all genuinely TESTED.
      2. Worse, TESTED rows from old, failed workspaces get swept into
         VALIDATED here too -- and from there into a real git commit
         (git.py), even though they were never part of the test run that
         actually passed.
    """
    query = ctx.db.query(CodeChange).filter(CodeChange.task_id == task.id)
    if ctx.workspace_id:
        query = query.filter(CodeChange.workspace_id == ctx.workspace_id)
    code_changes = query.all()
    if not code_changes:
        return ValidationResult(validated=False, reasons=["No code changes exist for this task yet."])

    not_tested = [c for c in code_changes if c.lifecycle_state == ChangeLifecycleState.PROPOSED or c.lifecycle_state == ChangeLifecycleState.APPLIED]
    if not_tested:
        reasons.append(f"{len(not_tested)} change(s) have not been tested yet.")

    if latest_test_run is None:
        reasons.append("No test run is associated with this task.")
    elif latest_test_run.status != TestRunStatus.PASSED:
        reasons.append(
            f"Latest test run status is {latest_test_run.status.value}, not PASSED "
            f"({latest_test_run.failed_count or 0} failing)."
        )

    if reasons:
        return ValidationResult(validated=False, reasons=reasons)

    validated_ids: list[str] = []
    for change in code_changes:
        if change.lifecycle_state == ChangeLifecycleState.TESTED:
            advance(ctx.db, change, ChangeLifecycleState.VALIDATED)
            validated_ids.append(str(change.id))

    return ValidationResult(
        validated=True,
        reasons=["All code changes tested; latest test run passed."],
        validated_change_ids=validated_ids,
    )
