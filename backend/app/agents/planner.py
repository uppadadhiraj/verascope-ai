"""Planner Agent (section 21): turns a task into explicit, trackable steps.

A step's status must never move to COMPLETED without `evidence` backing it
-- `mark_step` below is the only place step status changes, and it enforces
that for every terminal status except PENDING/IN_PROGRESS/BLOCKED.
"""
from __future__ import annotations

import datetime as dt
import json
import re

from app.agents.context import AgentContext
from app.models.enums import StepStatus
from app.models.task import Task, TaskStep
from app.services.llm.base import ChatMessage, LLMProvider

SYSTEM_PROMPT = """You are the Planner Agent inside Verascope. Given a task description (often a bug \
report or feature request) and repository context, break it into a short, explicit, actionable sequence \
of investigation/implementation steps -- the kind a careful senior engineer would actually follow.

Rules:
- 4 to 10 steps. Concrete and verifiable, not vague ("investigate the bug" is too vague; \
"Locate the JWT validation function via search_code" is good).
- For a debugging task, the sequence should generally look like: locate relevant code -> trace \
execution/exception handling -> identify root cause -> propose fix -> write a regression test -> \
implement fix in sandbox -> run tests -> review diff -> request approval.
- For a general task, adapt accordingly but keep the same investigate-before-modify discipline.
- Respond ONLY as JSON: {"steps": ["step 1 text", "step 2 text", ...]}"""


def generate_plan(ctx: AgentContext, provider: LLMProvider, task: Task) -> list[TaskStep]:
    repo_summary = ctx.repository.summary or {}
    user_content = (
        f"Task title: {task.title}\n"
        f"Task description: {task.description or '(none provided)'}\n"
        f"Task type: {task.task_type.value}\n\n"
        f"Repository purpose (if known): {repo_summary.get('purpose', 'unknown')}\n"
        f"Languages: {repo_summary.get('languages', [])}\n"
        f"Frameworks: {repo_summary.get('frameworks', [])}\n"
    )

    response = provider.complete(
        messages=[ChatMessage(role="user", content=user_content)],
        system=SYSTEM_PROMPT,
        max_tokens=1200,
        temperature=0.1,
    )

    steps_text = _parse_steps(response.content or "")
    if not steps_text:
        steps_text = _fallback_plan(task)

    rows: list[TaskStep] = []
    for i, description in enumerate(steps_text, start=1):
        row = TaskStep(task_id=task.id, step_number=i, description=description, status=StepStatus.PENDING)
        ctx.db.add(row)
        rows.append(row)
    ctx.db.flush()
    ctx.db.commit()
    return rows


def _parse_steps(text: str) -> list[str]:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    steps = data.get("steps")
    if not isinstance(steps, list):
        return []
    return [str(s).strip() for s in steps if str(s).strip()]


def _fallback_plan(task: Task) -> list[str]:
    """Used only if the LLM call fails or returns something unparseable --
    ingestion of a plan must not hard-fail the whole debugging flow."""
    if task.task_type.value == "DEBUG":
        return [
            "Search the repository for code relevant to the reported problem.",
            "Trace the relevant execution path and exception handling.",
            "Identify the root cause with supporting evidence.",
            "Propose a fix.",
            "Generate a regression test that reproduces the bug before the fix.",
            "Implement the fix inside an isolated workspace.",
            "Run the regression test and existing tests.",
            "Review the resulting diff.",
            "Request human approval before any Git operation.",
        ]
    return [
        "Search the repository for code relevant to this task.",
        "Determine the scope of files affected.",
        "Propose changes.",
        "Implement changes inside an isolated workspace.",
        "Run relevant tests.",
        "Review the resulting diff.",
        "Request human approval before any Git operation.",
    ]


def mark_step(ctx: AgentContext, step: TaskStep, status: StepStatus, evidence: str | None = None) -> None:
    """The only sanctioned way to change a TaskStep's status. COMPLETED and
    FAILED both require `evidence` -- a step cannot be silently marked done."""
    if status in (StepStatus.COMPLETED, StepStatus.FAILED) and not evidence:
        raise ValueError(f"Cannot mark step {step.step_number} as {status.value} without evidence.")
    now = dt.datetime.now(dt.timezone.utc)
    if status == StepStatus.IN_PROGRESS and step.started_at is None:
        step.started_at = now
    if status in (StepStatus.COMPLETED, StepStatus.FAILED):
        step.completed_at = now
    step.status = status
    if evidence:
        step.evidence = evidence
    ctx.db.commit()
