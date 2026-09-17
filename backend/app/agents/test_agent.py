"""Test Agent (section 25, 29): detects the workspace's test framework, runs
it inside the Docker sandbox, and persists the result. On success, advances
any CodeChange rows for this task from APPLIED to TESTED -- "tested" here
strictly means "a test run was executed against this change", not "passed";
pass/fail is recorded separately on the TestRun row itself and interpreted
by the Validation Agent / autonomous fix loop.
"""
from __future__ import annotations

from pathlib import Path

from app.agents.context import AgentContext
from app.agents.lifecycle import advance
from app.core.config import Settings
from app.models.code_change import CodeChange
from app.models.enums import ChangeLifecycleState, TestRunStatus
from app.models.task import Task
from app.models.test_run import TestRun
from app.services.sandbox.docker_sandbox import SandboxError
from app.services.sandbox.test_runner import TestExecutionOutcome, detect_test_framework, run_tests


class NoTestFrameworkDetected(Exception):
    pass


def execute_tests(
    ctx: AgentContext, task: Task, workspace_dir: Path, settings: Settings, iteration: int = 0, test_path: str | None = None
) -> TestRun:
    info = detect_test_framework(workspace_dir, settings)
    if info is None:
        run = TestRun(
            repository_id=ctx.repository.id,
            task_id=task.id,
            framework=None,
            command="(no framework detected)",
            status=TestRunStatus.ERROR,
            error_output="No supported test framework was detected in this workspace.",
            iteration=iteration,
        )
        ctx.db.add(run)
        ctx.db.commit()
        return run

    try:
        outcome: TestExecutionOutcome = run_tests(workspace_dir, settings, framework_info=info, test_path=test_path)
    except SandboxError as exc:
        run = TestRun(
            repository_id=ctx.repository.id,
            task_id=task.id,
            framework=info.framework,
            command=info.command,
            status=TestRunStatus.ERROR,
            error_output=str(exc),
            iteration=iteration,
        )
        ctx.db.add(run)
        ctx.db.commit()
        return run

    result = outcome.sandbox_result
    if result.timed_out:
        status = TestRunStatus.TIMEOUT
    elif result.exit_code == 0:
        status = TestRunStatus.PASSED
    else:
        status = TestRunStatus.FAILED

    run = TestRun(
        repository_id=ctx.repository.id,
        task_id=task.id,
        framework=outcome.framework,
        command=outcome.command,
        exit_code=result.exit_code,
        duration_ms=result.duration_ms,
        passed_count=outcome.passed_count,
        failed_count=outcome.failed_count,
        output=result.stdout[-8000:],
        error_output=result.stderr[-2000:] if result.stderr else None,
        status=status,
        iteration=iteration,
    )
    ctx.db.add(run)
    ctx.db.flush()

    _advance_task_changes(ctx, task)
    ctx.db.commit()
    return run


def _advance_task_changes(ctx: AgentContext, task: Task) -> None:
    # Scoped to ctx.workspace_id, NOT just task_id: a task can accumulate
    # CodeChange rows across many separate fix-loop iterations/invocations
    # (each with its own workspace_id) -- some of them from abandoned,
    # failed attempts. Without this scope, a change from an earlier failed
    # iteration could get advanced to TESTED here and later swept into
    # VALIDATED (validate_task) and then a real git commit (git.py), even
    # though it was never part of the test run that actually passed.
    query = ctx.db.query(CodeChange).filter(
        CodeChange.task_id == task.id, CodeChange.lifecycle_state == ChangeLifecycleState.APPLIED
    )
    if ctx.workspace_id:
        query = query.filter(CodeChange.workspace_id == ctx.workspace_id)
    for change in query.all():
        advance(ctx.db, change, ChangeLifecycleState.TESTED)
