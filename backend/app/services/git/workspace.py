"""Isolated fix workspaces (section 26, 27).

The Fix Agent never touches the indexed repository clone directly. It
always works inside a throwaway copy under WORKSPACE_STORAGE_DIR, keyed by
a workspace id (one per Task). Only after human approval does anything from
here get copied onto a real git branch of the actual repository (see
git_ops.py).
"""
from __future__ import annotations

import difflib
import shutil
import uuid
from pathlib import Path

from app.core.config import Settings


def new_workspace_id() -> str:
    return uuid.uuid4().hex


def create_workspace(repository_id: str, settings: Settings, workspace_id: str | None = None) -> Path:
    workspace_id = workspace_id or new_workspace_id()
    src = settings.repo_path(repository_id)
    dest = settings.workspace_path(workspace_id)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns(".git"))
    return dest


def read_workspace_file(workspace_dir: Path, relative_path: str) -> str | None:
    target = _safe_join(workspace_dir, relative_path)
    if not target.exists():
        return None
    return target.read_text(encoding="utf-8", errors="replace")


def write_workspace_file(workspace_dir: Path, relative_path: str, content: str) -> None:
    target = _safe_join(workspace_dir, relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def delete_workspace_file(workspace_dir: Path, relative_path: str) -> None:
    target = _safe_join(workspace_dir, relative_path)
    if target.exists():
        target.unlink()


def unified_diff(old_content: str | None, new_content: str | None, path: str) -> str:
    old_lines = (old_content or "").splitlines(keepends=True)
    new_lines = (new_content or "").splitlines(keepends=True)
    diff = difflib.unified_diff(
        old_lines, new_lines, fromfile=f"a/{path}", tofile=f"b/{path}", lineterm=""
    )
    return "\n".join(diff)


def _safe_join(workspace_dir: Path, relative_path: str) -> Path:
    """Refuses any relative_path that would escape workspace_dir -- the Fix
    Agent's file arguments come from an LLM tool call and must be treated as
    untrusted input."""
    candidate = (workspace_dir / relative_path).resolve()
    workspace_resolved = workspace_dir.resolve()
    if not str(candidate).startswith(str(workspace_resolved)):
        raise ValueError(f"Path '{relative_path}' escapes the workspace.")
    return candidate


def cleanup_workspace(workspace_dir: Path) -> None:
    if workspace_dir.exists():
        shutil.rmtree(workspace_dir, ignore_errors=True)
