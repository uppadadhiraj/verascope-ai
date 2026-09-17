"""Fix Agent (section 26): implements an approved plan/root-cause finding
as concrete file changes, but ONLY inside the isolated workspace created for
this task. It never touches the indexed repository clone or the user's real
repository -- that only happens later, through services/git/git_ops.py,
after a human approves.

Every successful create_file/modify_file/delete_file tool call becomes a
CodeChange row with lifecycle_state=PROPOSED. Nothing here sets
lifecycle_state to APPLIED/TESTED/VALIDATED -- those transitions belong to
the Test Agent and Validation Agent respectively (section 37).
"""
from __future__ import annotations

import json

from app.agents.context import AgentContext
from app.agents.fix_tools import FIX_TOOL_HANDLERS, FIX_TOOL_SPECS
from app.agents.lifecycle import advance
from app.agents.repository_tools import REPOSITORY_TOOL_HANDLERS, REPOSITORY_TOOL_SPECS
from app.agents.runner import run_agent_loop
from app.models.agent_run import ToolCall
from app.models.code_change import CodeChange
from app.models.enums import AgentName, ChangeLifecycleState, ChangeType
from app.models.task import Task
from app.services.llm.base import LLMProvider, ToolSpec

SYSTEM_PROMPT = """You are the Fix Agent inside Verascope. You implement a specific, approved-in-\
principle change inside an isolated workspace copy of the repository.

You have read-only investigation tools (read_file, search_code, find_symbol, get_dependencies, \
get_callers, get_file_summary) AND file-modification tools (create_file, modify_file, delete_file) that \
operate on the workspace.

Rules:
1. Read the relevant file(s) with read_file BEFORE modifying them, so your replacement content is \
complete and correct -- modify_file replaces the entire file.
2. Make the MINIMAL change that addresses the described problem. Do not refactor unrelated code, \
rename things, or "clean up" code that isn't part of the task.
3. Every create_file/modify_file/delete_file call requires a clear `reason` explaining why.
4. If the task calls for a regression test, write one using the repository's existing test framework \
and conventions (check existing test files first with search_code/read_file).
5. Do not attempt to run tests yourself or make git commits -- that is handled by other agents after you.
6. When you are done making changes, respond with a short plain-text summary of what you changed and why."""


def apply_fix(
    ctx: AgentContext,
    provider: LLMProvider,
    task: Task,
    instructions: str,
    max_iterations: int = 12,
) -> tuple[list[CodeChange], str | None, str]:
    """Returns (code_changes, summary_text, agent_run_id)."""
    if ctx.workspace_dir is None or ctx.workspace_id is None:
        raise ValueError("apply_fix requires an AgentContext with a workspace attached.")

    combined_specs: list[ToolSpec] = [*REPOSITORY_TOOL_SPECS, *FIX_TOOL_SPECS]
    combined_handlers = {**REPOSITORY_TOOL_HANDLERS, **FIX_TOOL_HANDLERS}

    result = run_agent_loop(
        ctx=ctx,
        provider=provider,
        agent_name=AgentName.FIX,
        system_prompt=SYSTEM_PROMPT,
        user_message=instructions,
        tool_specs=combined_specs,
        tool_handlers=combined_handlers,
        max_iterations=max_iterations,
        max_tokens=4096,
    )

    code_changes = _persist_code_changes(ctx, task, str(result.agent_run.id))
    return code_changes, result.final_text, str(result.agent_run.id)


def _persist_code_changes(ctx: AgentContext, task: Task, agent_run_id: str) -> list[CodeChange]:
    import uuid as _uuid

    tool_calls = (
        ctx.db.query(ToolCall)
        .filter(
            ToolCall.agent_run_id == _uuid.UUID(agent_run_id),
            ToolCall.tool_name.in_(["create_file", "modify_file", "delete_file"]),
            ToolCall.status == "success",
        )
        .all()
    )

    changes: list[CodeChange] = []
    for tc in tool_calls:
        try:
            data = json.loads(tc.result_summary or "{}")
        except json.JSONDecodeError:
            continue
        if "path" not in data:
            continue

        change = CodeChange(
            repository_id=ctx.repository.id,
            task_id=task.id,
            agent_run_id=_uuid.UUID(agent_run_id),
            change_type=ChangeType(data["change_type"]),
            lifecycle_state=ChangeLifecycleState.PROPOSED,
            file_path=data["path"],
            old_content=data.get("old_content"),
            new_content=data.get("new_content"),
            diff=data.get("diff"),
            reason=data.get("reason") or "No reason provided by the Fix Agent.",
            agent_name="fix",
            workspace_id=ctx.workspace_id,
            applied_to_main=False,
        )
        ctx.db.add(change)
        ctx.db.flush()
        # The file is already written to the workspace at this point (the
        # tool handler wrote it synchronously) -- so PROPOSED immediately
        # advances to APPLIED. TESTED/VALIDATED are set later, by the Test
        # and Validation agents respectively.
        advance(ctx.db, change, ChangeLifecycleState.APPLIED)
        changes.append(change)

    ctx.db.commit()
    return changes
