"""Code Review Agent (section 36): reviews the ACTUAL diff produced by the
Fix Agent -- never a description of it -- for correctness, security,
maintainability, test coverage and regression risk.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from app.agents.context import AgentContext
from app.agents.runner import run_agent_loop
from app.models.code_change import CodeChange
from app.models.enums import AgentName
from app.models.task import Task
from app.services.llm.base import LLMProvider

SYSTEM_PROMPT = """You are the Code Review Agent inside Verascope. You are given the ACTUAL diff of \
changes an AI Fix Agent made to a repository, along with the task it was addressing. Review it as a \
careful senior engineer would review a pull request.

Cover, specifically:
- Correctness: does the change plausibly do what it claims, given the diff shown?
- Security: does the change introduce any vulnerability?
- Maintainability: is the change reasonably clean, minimal, and consistent with the surrounding code?
- Test coverage: is there a regression test for the change? Is it adequate?
- Regression risk: could this change plausibly break other functionality?

Only comment on what is actually visible in the diff. Do not invent context you were not given.

Respond ONLY as JSON:
{
  "overall_assessment": "approve" | "approve_with_comments" | "request_changes",
  "summary": "1-3 sentence summary",
  "issues": [{"category": "correctness"|"security"|"maintainability"|"test_coverage"|"regression_risk", "severity": "low"|"medium"|"high", "description": "..."}],
  "strengths": ["..."]
}"""


@dataclass
class ReviewIssue:
    category: str
    severity: str
    description: str


@dataclass
class ReviewResult:
    overall_assessment: str
    summary: str
    issues: list[ReviewIssue] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    agent_run_id: str = ""
    raw_text: str | None = None


def review_changes(ctx: AgentContext, provider: LLMProvider, task: Task, code_changes: list[CodeChange]) -> ReviewResult:
    diff_blob = "\n\n".join(
        f"--- {c.file_path} ({c.change_type.value}) ---\nReason: {c.reason}\n{c.diff or '(no diff available)'}"
        for c in code_changes
    )
    user_message = (
        f"Task: {task.title}\n"
        f"Root cause (if known): {task.root_cause or 'unknown'}\n\n"
        f"Diff:\n{diff_blob[:12000]}"
    )

    result = run_agent_loop(
        ctx=ctx,
        provider=provider,
        agent_name=AgentName.REVIEW,
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tool_specs=[],
        tool_handlers={},
        max_iterations=1,
        max_tokens=2000,
    )

    return _parse_review(result.final_text, str(result.agent_run.id))


def _parse_review(text: str | None, agent_run_id: str) -> ReviewResult:
    if not text:
        return ReviewResult(
            overall_assessment="request_changes",
            summary="The review agent did not return a response.",
            agent_run_id=agent_run_id,
        )
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return ReviewResult(overall_assessment="request_changes", summary=text[:500], agent_run_id=agent_run_id, raw_text=text)
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return ReviewResult(overall_assessment="request_changes", summary=text[:500], agent_run_id=agent_run_id, raw_text=text)

    issues = [
        ReviewIssue(
            category=i.get("category", "correctness"), severity=i.get("severity", "medium"), description=i.get("description", "")
        )
        for i in data.get("issues", [])
    ]
    return ReviewResult(
        overall_assessment=data.get("overall_assessment", "request_changes"),
        summary=data.get("summary", ""),
        issues=issues,
        strengths=data.get("strengths", []),
        agent_run_id=agent_run_id,
        raw_text=text,
    )
