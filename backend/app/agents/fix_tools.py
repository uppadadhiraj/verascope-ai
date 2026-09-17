"""Workspace-mutating tools for the Fix Agent (section 26, 28).

Every call here operates ONLY inside `ctx.workspace_dir` -- an isolated copy
created by services/git/workspace.py, never the indexed repository clone
and never the user's real repository. The caller (fix_agent.py) turns each
result into a CodeChange row with lifecycle_state=PROPOSED so the change is
tracked before it's ever eligible for approval.
"""
from __future__ import annotations

import re

from app.agents.context import AgentContext
from app.agents.tool_args import path_arg as _path_arg
from app.models.enums import ChangeType
from app.services.git.workspace import (
    delete_workspace_file,
    read_workspace_file,
    unified_diff,
    write_workspace_file,
)
from app.services.llm.base import ToolSpec


def _require_workspace(ctx: AgentContext) -> None:
    if ctx.workspace_dir is None:
        raise ValueError("No workspace is attached to this agent context -- cannot modify files.")


# create_file/modify_file both require COMPLETE file content, not a patch --
# but models (any provider, not just local/small ones; this is a common
# failure mode across the board) sometimes elide unchanged parts with a
# placeholder comment as if writing a diff. Observed directly during
# testing: llama3.1:8b replaced an entire file with a few lines plus
# "# ... rest of the function remains the same ...", producing a file that
# doesn't even parse. Rather than silently write garbage and let it surface
# three steps later as a confusing test failure, reject the call immediately
# with a message that tells the model exactly what it did wrong.
_PLACEHOLDER_PATTERNS = [
    re.compile(r"(rest|remainder)\s+of\s+the\s+(function|file|code|class|method)\s+(remains?|stays?|is)\s+(the\s+same|unchanged)", re.IGNORECASE),
    re.compile(r"\.\.\.\s*(rest|remaining|existing)\s+(of\s+the\s+)?(code|file|function|method|class|logic)", re.IGNORECASE),
    re.compile(r"^\s*(//|#)\s*\.\.\.\s*$", re.MULTILINE),
    re.compile(r"[<\[]\s*(rest of|remaining|existing)\s+code\s*[>\]]", re.IGNORECASE),
]


def _placeholder_content_error(content: str) -> str | None:
    for pattern in _PLACEHOLDER_PATTERNS:
        if pattern.search(content):
            return (
                "This content looks like a partial patch, not a complete file: it appears to "
                "contain a placeholder comment (e.g. 'rest of the function remains the same') "
                "instead of actual code. modify_file/create_file require the FULL file content, "
                "with nothing elided. Read the current file, then write out the complete file "
                "with your change applied, and call the tool again."
            )
    return None


def tool_create_file(ctx: AgentContext, args: dict) -> dict:
    _require_workspace(ctx)
    path, content = _path_arg(args), args["content"]
    reason = args.get("reason", "")
    placeholder_error = _placeholder_content_error(content)
    if placeholder_error:
        return {"error": placeholder_error}
    existing = read_workspace_file(ctx.workspace_dir, path)
    if existing is not None:
        return {"error": f"'{path}' already exists. Use modify_file to change an existing file."}
    write_workspace_file(ctx.workspace_dir, path, content)
    return {
        "path": path,
        "change_type": ChangeType.CREATE.value,
        "old_content": None,
        "new_content": content,
        "diff": unified_diff(None, content, path),
        "reason": reason,
    }


def tool_modify_file(ctx: AgentContext, args: dict) -> dict:
    _require_workspace(ctx)
    path, content = _path_arg(args), args["content"]
    reason = args.get("reason", "")
    placeholder_error = _placeholder_content_error(content)
    if placeholder_error:
        return {"error": placeholder_error}
    old_content = read_workspace_file(ctx.workspace_dir, path)
    if old_content is None:
        return {"error": f"'{path}' does not exist in the workspace. Use create_file for new files."}
    write_workspace_file(ctx.workspace_dir, path, content)
    return {
        "path": path,
        "change_type": ChangeType.MODIFY.value,
        "old_content": old_content,
        "new_content": content,
        "diff": unified_diff(old_content, content, path),
        "reason": reason,
    }


def tool_delete_file(ctx: AgentContext, args: dict) -> dict:
    _require_workspace(ctx)
    path = _path_arg(args)
    reason = args.get("reason", "")
    old_content = read_workspace_file(ctx.workspace_dir, path)
    if old_content is None:
        return {"error": f"'{path}' does not exist in the workspace."}
    delete_workspace_file(ctx.workspace_dir, path)
    return {
        "path": path,
        "change_type": ChangeType.DELETE.value,
        "old_content": old_content,
        "new_content": None,
        "diff": unified_diff(old_content, None, path),
        "reason": reason,
    }


FIX_TOOL_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="create_file",
        description="Create a new file in the workspace with the given content.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "reason": {"type": "string", "description": "Why this file is being created."},
            },
            "required": ["path", "content", "reason"],
        },
    ),
    ToolSpec(
        name="modify_file",
        description="Replace the full contents of an existing workspace file. Always read the file first so you write a complete, correct replacement -- this is not a patch/diff apply, it overwrites the whole file.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "reason": {"type": "string", "description": "Why this file is being modified."},
            },
            "required": ["path", "content", "reason"],
        },
    ),
    ToolSpec(
        name="delete_file",
        description="Delete a file from the workspace.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "reason": {"type": "string", "description": "Why this file is being deleted."},
            },
            "required": ["path", "reason"],
        },
    ),
]

FIX_TOOL_HANDLERS = {
    "create_file": tool_create_file,
    "modify_file": tool_modify_file,
    "delete_file": tool_delete_file,
}
