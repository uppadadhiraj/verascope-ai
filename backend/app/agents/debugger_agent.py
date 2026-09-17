"""Debugger Agent (section 23): investigates a reported bug using the
read-only repository tools and produces a root-cause finding that is always
graded by an evidence status -- OBSERVED / INFERRED / HYPOTHESIZED /
VERIFIED / INSUFFICIENT (section 46). It never claims "the bug is fixed" --
that claim can only ever come from the Validation Agent, after a fix has
actually been applied and tested (section 23, 37).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from app.agents.context import AgentContext
from app.agents.repository_tools import REPOSITORY_TOOL_HANDLERS, REPOSITORY_TOOL_SPECS
from app.agents.runner import run_agent_loop
from app.models.enums import AgentName, EvidenceStatus
from app.models.task import Task
from app.services.llm.base import LLMProvider

SYSTEM_PROMPT = """You are the Debugger Agent inside Verascope. You investigate a reported bug in a \
real software repository using ONLY the tools provided (list_files, read_file, search_code, find_symbol, \
get_dependencies, get_callers, get_file_summary, get_repository_summary, git_history).

Investigation process to follow:
1. Understand the reported error/behavior.
2. Search the repository for relevant code (search_code, find_symbol).
3. Read the actual implicated files (read_file) -- never reason about code you have not read.
4. Trace the execution path: what calls what, what depends on what (get_dependencies, get_callers).
5. Form a hypothesis about the root cause and verify it against the code you've read.
6. Only conclude a root cause when you have directly observed the code that causes the behavior.

You MUST distinguish, in your own reasoning and in the final answer:
- OBSERVED: something you directly read in the code that explains the behavior.
- INFERRED: a reasonable conclusion from observed code, not directly stated.
- HYPOTHESIZED: a plausible but unconfirmed explanation.
- VERIFIED: only applicable after an actual fix has been tested -- you will never have this status \
yourself, since you do not apply or test fixes.
- INSUFFICIENT: the available evidence does not support a confident root cause.

Never claim a bug "is fixed" -- you only investigate and propose, you do not validate.

When you have finished investigating (or if you determine the evidence is insufficient), respond with \
ONLY a JSON object, no other text, in this exact shape:
{
  "summary": "one paragraph summary of the problem",
  "root_cause": "the root cause, or null if insufficient evidence",
  "evidence_status": "OBSERVED" | "INFERRED" | "HYPOTHESIZED" | "INSUFFICIENT",
  "evidence": [{"file_path": "...", "start_line": 1, "end_line": 10, "note": "why this is relevant"}],
  "affected_files": ["..."],
  "impact": "what this bug affects, or null",
  "proposed_fix": "a specific description of the proposed code fix, or null if insufficient evidence",
  "regression_test_description": "what a regression test for this should verify, or null",
  "confidence_notes": "brief note on your confidence and any gaps in evidence"
}"""


@dataclass
class DebuggerFinding:
    summary: str | None
    root_cause: str | None
    evidence_status: EvidenceStatus
    evidence: list[dict] = field(default_factory=list)
    affected_files: list[str] = field(default_factory=list)
    impact: str | None = None
    proposed_fix: str | None = None
    regression_test_description: str | None = None
    confidence_notes: str | None = None
    agent_run_id: str = ""
    raw_text: str | None = None


def investigate(
    ctx: AgentContext,
    provider: LLMProvider,
    task: Task,
    description: str,
    error_message: str | None = None,
    stack_trace: str | None = None,
    logs: str | None = None,
    failing_test: str | None = None,
    max_iterations: int = 12,
) -> DebuggerFinding:
    parts = [f"Bug report: {description}"]
    if error_message:
        parts.append(f"Error message:\n{error_message}")
    if stack_trace:
        parts.append(f"Stack trace:\n{stack_trace}")
    if logs:
        parts.append(f"Relevant logs:\n{logs}")
    if failing_test:
        parts.append(f"Failing test:\n{failing_test}")
    user_message = "\n\n".join(parts)

    result = run_agent_loop(
        ctx=ctx,
        provider=provider,
        agent_name=AgentName.DEBUGGER,
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        tool_specs=REPOSITORY_TOOL_SPECS,
        tool_handlers=REPOSITORY_TOOL_HANDLERS,
        max_iterations=max_iterations,
        max_tokens=3000,
    )

    finding = _parse_finding(result.final_text)
    finding.agent_run_id = str(result.agent_run.id)

    task.root_cause = finding.root_cause
    task.evidence = finding.evidence
    task.evidence_status = finding.evidence_status
    task.confidence_notes = finding.confidence_notes
    ctx.db.commit()

    return finding


def _parse_finding(text: str | None) -> DebuggerFinding:
    if not text:
        return DebuggerFinding(
            summary=None,
            root_cause=None,
            evidence_status=EvidenceStatus.INSUFFICIENT,
            confidence_notes="The agent did not produce a final answer within its tool-call budget.",
            raw_text=text,
        )

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return DebuggerFinding(
            summary=text[:500],
            root_cause=None,
            evidence_status=EvidenceStatus.INSUFFICIENT,
            confidence_notes="The agent's response was not in the expected structured format.",
            raw_text=text,
        )

    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return DebuggerFinding(
            summary=text[:500],
            root_cause=None,
            evidence_status=EvidenceStatus.INSUFFICIENT,
            confidence_notes="The agent's structured response could not be parsed as JSON.",
            raw_text=text,
        )

    try:
        evidence_status = EvidenceStatus(data.get("evidence_status", "INSUFFICIENT"))
    except ValueError:
        evidence_status = EvidenceStatus.INSUFFICIENT

    root_cause = data.get("root_cause")
    if isinstance(root_cause, str) and root_cause.strip().upper() in {s.value for s in EvidenceStatus}:
        # Smaller models occasionally put a status-like sentinel (e.g. the
        # literal string "INSUFFICIENT") directly in root_cause instead of
        # `null`, contradicting evidence_status -- observed directly with
        # Ollama/llama3.1:8b. Trust the model's own uncertainty signal over
        # a nonsensical "root cause" value; never surface a fake root cause.
        root_cause = None
        evidence_status = EvidenceStatus.INSUFFICIENT

    return DebuggerFinding(
        summary=data.get("summary"),
        root_cause=root_cause,
        evidence_status=evidence_status,
        evidence=data.get("evidence") or [],
        affected_files=data.get("affected_files") or [],
        impact=data.get("impact"),
        proposed_fix=data.get("proposed_fix"),
        regression_test_description=data.get("regression_test_description"),
        confidence_notes=data.get("confidence_notes"),
        raw_text=text,
    )
