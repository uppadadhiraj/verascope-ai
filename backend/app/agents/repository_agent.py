"""Repository Agent (section 22): answers questions about the codebase
using the read-only investigation tools, grounded in actual retrieved
evidence rather than the model's prior knowledge (section 17, 46).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.agents.context import AgentContext
from app.agents.repository_tools import REPOSITORY_TOOL_HANDLERS, REPOSITORY_TOOL_SPECS
from app.agents.runner import AgentLoopResult, run_agent_loop
from app.models.agent_run import ToolCall
from app.models.enums import AgentName
from app.services.llm.base import LLMProvider

SYSTEM_PROMPT = """You are the Repository Agent inside Verascope, an AI software engineering platform.

Your job is to answer questions about a specific software repository using ONLY the tools provided \
(list_files, read_file, search_code, find_symbol, get_dependencies, get_callers, get_file_summary, \
get_repository_summary, git_history). These tools return real evidence from the actual repository.

Rules you must follow:
1. Investigate before answering. Use search_code and find_symbol to locate relevant code, then \
read_file to confirm before citing it. Do not answer from assumptions.
2. Every file or function you reference MUST have actually been returned by a tool call in this \
conversation. Never invent file names, function names, or line numbers.
3. If the tools do not surface enough evidence to answer confidently, say so explicitly: \
"Insufficient evidence to determine X" -- do not guess.
4. Distinguish facts (directly observed in retrieved code) from inferences (reasonable conclusions \
you're drawing beyond what was directly read).
5. Keep answers concise and reference concrete file paths and line numbers.
6. Stop calling tools once you have enough evidence to answer -- do not over-investigate simple questions."""


@dataclass
class Citation:
    file_path: str
    start_line: int | None
    end_line: int | None
    symbol: str | None = None


@dataclass
class RepositoryAnswer:
    text: str | None
    citations: list[Citation]
    agent_run_id: str
    token_usage: dict


def answer_repository_question(
    ctx: AgentContext, provider: LLMProvider, question: str, max_iterations: int = 8
) -> RepositoryAnswer:
    result: AgentLoopResult = run_agent_loop(
        ctx=ctx,
        provider=provider,
        agent_name=AgentName.REPOSITORY,
        system_prompt=SYSTEM_PROMPT,
        user_message=question,
        tool_specs=REPOSITORY_TOOL_SPECS,
        tool_handlers=REPOSITORY_TOOL_HANDLERS,
        max_iterations=max_iterations,
    )

    citations = _extract_citations(ctx, str(result.agent_run.id))

    answer_text = result.final_text
    if answer_text is None:
        answer_text = (
            "I was unable to reach a final answer within the tool-call budget for this question. "
            "Try narrowing the question, or ask again -- partial investigation results were still logged."
        )

    return RepositoryAnswer(
        text=answer_text,
        citations=citations,
        agent_run_id=str(result.agent_run.id),
        token_usage={
            "model": result.agent_run.model,
            "input_tokens": result.agent_run.input_tokens,
            "output_tokens": result.agent_run.output_tokens,
            "total_tokens": result.agent_run.total_tokens,
            "latency_ms": result.agent_run.latency_ms,
        },
    )


def _extract_citations(ctx: AgentContext, agent_run_id: str) -> list[Citation]:
    """Citations are derived from what the tools actually returned during
    this run -- not from asking the model to self-report them -- so a
    citation can never point at a file/line the agent didn't really see."""
    import uuid as _uuid

    tool_calls = ctx.db.query(ToolCall).filter(ToolCall.agent_run_id == _uuid.UUID(agent_run_id)).all()
    seen: set[tuple] = set()
    citations: list[Citation] = []

    for tc in tool_calls:
        if tc.status != "success" or not tc.result_summary:
            continue
        import json

        try:
            data = json.loads(tc.result_summary)
        except json.JSONDecodeError:
            continue

        if tc.tool_name == "read_file" and isinstance(data, dict) and data.get("path"):
            key = (data["path"], data.get("start_line"), data.get("end_line"))
            if key not in seen:
                seen.add(key)
                citations.append(Citation(data["path"], data.get("start_line"), data.get("end_line")))
        elif tc.tool_name == "search_code" and isinstance(data, dict):
            for r in data.get("results", [])[:5]:
                key = (r.get("file_path"), r.get("start_line"), r.get("end_line"))
                if key not in seen and r.get("file_path"):
                    seen.add(key)
                    citations.append(
                        Citation(r["file_path"], r.get("start_line"), r.get("end_line"), r.get("symbol"))
                    )
        elif tc.tool_name == "find_symbol" and isinstance(data, dict):
            for s in data.get("symbols", [])[:5]:
                key = (s.get("file_path"), s.get("start_line"), s.get("end_line"))
                if key not in seen and s.get("file_path"):
                    seen.add(key)
                    citations.append(
                        Citation(s["file_path"], s.get("start_line"), s.get("end_line"), s.get("name"))
                    )
        elif tc.tool_name == "get_file_summary" and isinstance(data, dict) and data.get("path"):
            for s in data.get("symbols", [])[:5]:
                key = (data["path"], s.get("start_line"), s.get("end_line"))
                if key not in seen:
                    seen.add(key)
                    citations.append(Citation(data["path"], s.get("start_line"), s.get("end_line"), s.get("name")))

    return citations
