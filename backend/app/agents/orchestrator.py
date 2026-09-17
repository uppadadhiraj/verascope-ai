"""Orchestrator (section 20, 30): coordinates the multi-agent debugging
workflow end to end (section 51):

  Planner -> Debugger -> [human approval] -> Fix <-> Test (bounded loop)
  -> Review -> Validation -> [human approval] -> Git -> [human approval] -> PR

Everything up to and including Debugger investigation requires no approval
(it's read-only). Nothing that writes to a workspace runs before a
CODE_CHANGE approval exists and is APPROVED -- that check lives in the API
route (api/routes/debug.py), not here, but this module is written assuming
it's only ever invoked after that gate has already passed.

The autonomous fix loop (section 30) hard-caps at
settings.sandbox_max_iterations (default 5) and always terminates: on
tests passing, on max iterations, or on an unrecoverable sandbox/tool error.
It never loops indefinitely.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from app.agents import fix_agent, planner, test_agent, validation_agent
from app.agents.context import AgentContext
from app.agents.debugger_agent import DebuggerFinding, investigate
from app.agents.review_agent import ReviewResult, review_changes
from app.core.logging import get_logger
from app.models.code_change import CodeChange
from app.models.enums import EvidenceStatus, StepStatus
from app.models.task import Task, TaskStep
from app.models.test_run import TestRun
from app.services.git.workspace import create_workspace, new_workspace_id
from app.services.llm.base import LLMProvider

logger = get_logger(__name__)


@dataclass
class InvestigationResult:
    task: Task
    steps: list[TaskStep]
    finding: DebuggerFinding


def run_investigation(
    ctx: AgentContext,
    provider: LLMProvider,
    task: Task,
    description: str,
    error_message: str | None = None,
    stack_trace: str | None = None,
    logs: str | None = None,
    failing_test: str | None = None,
) -> InvestigationResult:
    """Planner + Debugger only -- entirely read-only, no approval required."""
    task.status = StepStatus.IN_PROGRESS
    task.started_at = task.started_at or dt.datetime.now(dt.timezone.utc)
    ctx.db.commit()

    steps = planner.generate_plan(ctx, provider, task)

    investigation_steps = [s for s in steps if s.step_number <= max(1, len(steps) // 2)]
    if investigation_steps:
        planner.mark_step(ctx, investigation_steps[0], StepStatus.IN_PROGRESS)

    finding = investigate(
        ctx, provider, task, description, error_message, stack_trace, logs, failing_test
    )

    if investigation_steps:
        evidence_text = finding.root_cause or finding.confidence_notes or "Investigation completed."
        status = StepStatus.COMPLETED if finding.evidence_status != EvidenceStatus.INSUFFICIENT else StepStatus.BLOCKED
        try:
            planner.mark_step(ctx, investigation_steps[0], status, evidence=evidence_text)
        except ValueError:
            planner.mark_step(ctx, investigation_steps[0], StepStatus.BLOCKED, evidence=evidence_text)

    if finding.evidence_status == EvidenceStatus.INSUFFICIENT:
        task.status = StepStatus.BLOCKED
    ctx.db.commit()

    return InvestigationResult(task=task, steps=steps, finding=finding)


@dataclass
class FixLoopResult:
    passed: bool
    iterations_used: int
    hit_max_iterations: bool
    stopped_reason: str
    code_changes: list[CodeChange] = field(default_factory=list)
    test_runs: list[TestRun] = field(default_factory=list)
    review: ReviewResult | None = None
    workspace_id: str | None = None


def run_autonomous_fix_loop(
    ctx: AgentContext,
    provider: LLMProvider,
    task: Task,
    initial_instructions: str,
    max_iterations: int | None = None,
) -> FixLoopResult:
    """Requires ctx.repository to be set; attaches its own workspace. Caller
    (API route) must have already verified the CODE_CHANGE approval for this
    task is APPROVED before calling this."""
    settings = ctx.settings
    max_iterations = max_iterations or settings.sandbox_max_iterations

    workspace_id = new_workspace_id()
    workspace_dir = create_workspace(str(ctx.repository.id), settings, workspace_id=workspace_id)
    ctx.workspace_dir = workspace_dir
    ctx.workspace_id = workspace_id

    all_changes: list[CodeChange] = []
    all_test_runs: list[TestRun] = []
    instructions = initial_instructions
    passed = False
    stopped_reason = ""

    for iteration in range(1, max_iterations + 1):
        try:
            changes, _summary, _run_id = fix_agent.apply_fix(ctx, provider, task, instructions)
        except Exception as exc:  # noqa: BLE001
            logger.error("fix_loop_fix_agent_failed", task_id=str(task.id), iteration=iteration, error=str(exc))
            stopped_reason = f"Fix Agent failed on iteration {iteration}: {exc}"
            break
        all_changes.extend(changes)

        if not changes:
            stopped_reason = f"Fix Agent made no changes on iteration {iteration}; stopping to avoid an empty loop."
            break

        try:
            test_run = test_agent.execute_tests(ctx, task, workspace_dir, settings, iteration=iteration)
        except Exception as exc:  # noqa: BLE001
            logger.error("fix_loop_test_agent_failed", task_id=str(task.id), iteration=iteration, error=str(exc))
            stopped_reason = f"Test execution failed on iteration {iteration}: {exc}"
            break
        all_test_runs.append(test_run)

        if test_run.status.value == "PASSED":
            passed = True
            stopped_reason = f"Tests passed on iteration {iteration}."
            break

        instructions = (
            f"{initial_instructions}\n\n"
            f"--- Previous attempt (iteration {iteration}) failed tests ---\n"
            f"Command: {test_run.command}\n"
            f"Exit code: {test_run.exit_code}\n"
            f"Output (tail):\n{(test_run.output or '')[-3000:]}\n\n"
            f"Analyze this failure and adjust your fix accordingly. Do not repeat the exact same change."
        )
    else:
        stopped_reason = f"Reached the maximum of {max_iterations} fix/test iterations without passing tests."

    review = None
    if passed:
        try:
            review = review_changes(ctx, provider, task, all_changes)
        except Exception as exc:  # noqa: BLE001
            logger.error("fix_loop_review_failed", task_id=str(task.id), error=str(exc))

        latest_run = all_test_runs[-1] if all_test_runs else None
        validation_agent.validate_task(ctx, task, latest_run)
        task.status = StepStatus.COMPLETED
        task.completed_at = dt.datetime.now(dt.timezone.utc)
    else:
        task.status = StepStatus.BLOCKED

    # Surface WHY the loop stopped -- previously computed but discarded,
    # leaving a user looking at status=BLOCKED with no explanation (found
    # during live testing: the loop stopped after a single iteration
    # because the Fix Agent made no further tool calls on iteration 2, and
    # there was no way to tell that from the API/UI). confidence_notes
    # already exists on Task for exactly this kind of "here's what happened
    # and why" note; append rather than overwrite so the Debugger Agent's
    # own notes aren't lost.
    fix_loop_note = f"Fix loop: {stopped_reason}"
    task.confidence_notes = f"{task.confidence_notes}\n\n{fix_loop_note}" if task.confidence_notes else fix_loop_note

    ctx.db.commit()

    return FixLoopResult(
        passed=passed,
        iterations_used=len(all_test_runs),
        hit_max_iterations=(len(all_test_runs) >= max_iterations and not passed),
        stopped_reason=stopped_reason,
        code_changes=all_changes,
        test_runs=all_test_runs,
        review=review,
        workspace_id=workspace_id,
    )
