"""The shared agent tool-calling loop (section 19, 20, 28, 42).

Every specialized agent (Repository, Debugger, Fix, Test, Security-via-LLM,
Review) drives the same loop: call the LLM with the current message history
and a fixed tool set, execute any requested tool calls against real
repository/workspace state, feed results back, repeat until the model stops
asking for tools or `max_iterations` is hit. Every run and every tool call
is persisted (AgentRun/ToolCall) as it happens -- this is the observability
backbone from section 42, not an afterthought bolted on at the end.
"""
from __future__ import annotations

import datetime as dt
import json
import time
from dataclasses import dataclass, field
from typing import Callable

from app.agents.context import AgentContext
from app.core.logging import get_logger
from app.models.agent_run import AgentRun, ToolCall
from app.models.enums import AgentName, AgentRunStatus
from app.services.llm.base import ChatMessage, LLMProvider, ToolSpec

logger = get_logger(__name__)

ToolHandler = Callable[[AgentContext, dict], dict]


class AgentExecutionError(Exception):
    def __init__(self, message: str, agent_run_id: str | None = None):
        super().__init__(message)
        self.agent_run_id = agent_run_id


@dataclass
class AgentLoopResult:
    final_text: str | None
    agent_run: AgentRun
    messages: list[ChatMessage] = field(default_factory=list)
    iterations_used: int = 0
    hit_max_iterations: bool = False


# Tool names whose `path`/`content` args represent a file being read vs.
# written -- used only to populate AgentRun.files_accessed/files_modified
# for observability, not for access control (each tool handler enforces
# its own boundaries).
_READ_TOOLS = {"read_file", "search_code", "get_file_summary", "get_dependencies", "get_callers"}
_WRITE_TOOLS = {"create_file", "modify_file", "delete_file"}

# Appended to every agent's system prompt. Smaller/local models (this
# project supports Ollama, not just Anthropic/OpenAI) are noticeably more
# prone to two failure modes without this reminder: writing a tool call out
# as prose JSON instead of issuing it as an actual structured tool call
# (especially right after a tool error, when they're "explaining" the fix
# instead of just doing it), and treating that prose as a final answer,
# which silently ends the loop. Observed directly while testing against
# Ollama/llama3.1:8b -- this reinforcement measurably fixed it.
_TOOL_USE_REMINDER = """

IMPORTANT: When you need to use a tool, you MUST issue it as an actual tool call \
(function call), never as JSON text inside your written response. If a tool call \
returns an error, fix the arguments and immediately issue a new, real tool call -- \
do not just describe in words what you would call next."""


def run_agent_loop(
    ctx: AgentContext,
    provider: LLMProvider,
    agent_name: AgentName,
    system_prompt: str,
    user_message: str,
    tool_specs: list[ToolSpec],
    tool_handlers: dict[str, ToolHandler],
    max_iterations: int = 8,
    max_tokens: int = 4096,
) -> AgentLoopResult:
    agent_run = AgentRun(
        repository_id=ctx.repository.id,
        task_id=ctx.task.id if ctx.task else None,
        agent_name=agent_name,
        status=AgentRunStatus.RUNNING,
        started_at=dt.datetime.now(dt.timezone.utc),
        input_summary=user_message[:2000],
        model=provider.model_name,
        files_accessed=[],
        files_modified=[],
    )
    ctx.db.add(agent_run)
    ctx.db.flush()

    effective_system_prompt = system_prompt + (_TOOL_USE_REMINDER if tool_specs else "")

    messages: list[ChatMessage] = [ChatMessage(role="user", content=user_message)]
    files_accessed: set[str] = set()
    files_modified: set[str] = set()
    total_latency = 0

    try:
        iteration = 0
        hit_max = False
        while True:
            iteration += 1
            if iteration > max_iterations:
                hit_max = True
                break

            response = provider.complete(
                messages=messages, system=effective_system_prompt, tools=tool_specs, max_tokens=max_tokens
            )
            agent_run.input_tokens += response.usage.input_tokens
            agent_run.output_tokens += response.usage.output_tokens
            agent_run.total_tokens += response.usage.total_tokens
            total_latency += response.latency_ms

            if not response.tool_calls:
                agent_run.status = AgentRunStatus.COMPLETED
                agent_run.output_summary = (response.content or "")[:2000]
                agent_run.ended_at = dt.datetime.now(dt.timezone.utc)
                agent_run.latency_ms = total_latency
                agent_run.files_accessed = sorted(files_accessed)
                agent_run.files_modified = sorted(files_modified)
                ctx.db.commit()
                return AgentLoopResult(
                    final_text=response.content, agent_run=agent_run, messages=messages, iterations_used=iteration
                )

            messages.append(ChatMessage(role="assistant", content=response.content or "", tool_calls=response.tool_calls))

            for tool_call in response.tool_calls:
                result, status, error_message, duration_ms = _execute_tool(ctx, tool_handlers, tool_call.name, tool_call.arguments)

                path = tool_call.arguments.get("path") if isinstance(tool_call.arguments, dict) else None
                if path and tool_call.name in _READ_TOOLS:
                    files_accessed.add(path)
                if path and tool_call.name in _WRITE_TOOLS:
                    files_modified.add(path)

                ctx.db.add(
                    ToolCall(
                        agent_run_id=agent_run.id,
                        tool_name=tool_call.name,
                        arguments=_json_safe(tool_call.arguments),
                        # NOT truncated: this field is a Postgres TEXT column
                        # (no real size limit) and is JSON-parsed back later
                        # -- by repository_agent.py to build chat citations,
                        # and critically by fix_agent.py to reconstruct
                        # CodeChange rows (old/new content + diff). A
                        # mid-string truncation here previously produced
                        # invalid JSON that failed silently, dropping
                        # citations and, worse, could have silently dropped
                        # real Fix Agent file changes.
                        result_summary=json.dumps(result),
                        status=status,
                        error_message=error_message,
                        duration_ms=duration_ms,
                    )
                )
                messages.append(
                    ChatMessage(role="tool", content=json.dumps(result), tool_call_id=tool_call.id, name=tool_call.name)
                )
            ctx.db.flush()

        # Loop exited via max_iterations
        agent_run.status = AgentRunStatus.COMPLETED
        agent_run.output_summary = "Reached max tool-calling iterations without a final answer."
        agent_run.ended_at = dt.datetime.now(dt.timezone.utc)
        agent_run.latency_ms = total_latency
        agent_run.files_accessed = sorted(files_accessed)
        agent_run.files_modified = sorted(files_modified)
        ctx.db.commit()
        return AgentLoopResult(
            final_text=None, agent_run=agent_run, messages=messages, iterations_used=iteration, hit_max_iterations=hit_max
        )

    except Exception as exc:  # noqa: BLE001 -- must record failure, never leave a run stuck RUNNING
        logger.error("agent_run_failed", agent=agent_name.value, error=str(exc))
        agent_run.status = AgentRunStatus.FAILED
        agent_run.error_message = str(exc)
        agent_run.ended_at = dt.datetime.now(dt.timezone.utc)
        agent_run.latency_ms = total_latency
        ctx.db.commit()
        raise AgentExecutionError(str(exc), agent_run_id=str(agent_run.id)) from exc


def _execute_tool(
    ctx: AgentContext, handlers: dict[str, ToolHandler], name: str, arguments: dict
) -> tuple[dict, str, str | None, int]:
    handler = handlers.get(name)
    start = time.monotonic()
    if handler is None:
        return {"error": f"Unknown tool '{name}'."}, "error", f"Unknown tool '{name}'", 0
    try:
        result = handler(ctx, arguments or {})
        duration_ms = int((time.monotonic() - start) * 1000)
        status = "error" if isinstance(result, dict) and result.get("error") else "success"
        return result, status, result.get("error") if status == "error" else None, duration_ms
    except KeyError as exc:
        # Handlers do plain `args["x"]` lookups for required parameters; a
        # bare KeyError renders as just "'x'", which tells the model
        # nothing. Smaller/local models in particular sometimes drift on
        # exact argument names (e.g. 'file_path' instead of the schema's
        # 'path') -- a clear message here gives them a real chance to
        # self-correct on the next tool call instead of giving up.
        duration_ms = int((time.monotonic() - start) * 1000)
        message = f"Missing required argument: {exc}. Check the tool's parameter names and try again."
        return {"error": message}, "error", message, duration_ms
    except Exception as exc:  # noqa: BLE001 -- one bad tool call must not kill the agent run
        duration_ms = int((time.monotonic() - start) * 1000)
        return {"error": str(exc)}, "error", str(exc), duration_ms


def _json_safe(value):
    try:
        json.dumps(value)
        return value
    except TypeError:
        return {"repr": repr(value)}
