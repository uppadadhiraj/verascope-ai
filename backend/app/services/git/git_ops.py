"""Git operations against the ACTUAL indexed repository clone (section 33).

Nothing in this module ever commits to the repository's default branch.
Every write happens on a fresh `verascope/<slug>` branch created off of it,
and only after an Approval row for approval_type=GIT_OPERATION has status
APPROVED (enforced by the caller in api/routes/git.py, not here -- this
module trusts its caller).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings
from app.models.enums import ChangeType


class GitOpsError(Exception):
    pass


@dataclass
class AppliedChange:
    path: str
    change_type: ChangeType
    new_content: str | None


def ensure_git_repo(repo_dir: Path, default_branch: str = "main") -> None:
    """ZIP-uploaded repositories have no .git directory. Initialize one with
    a baseline commit so branch/commit/diff semantics work uniformly
    regardless of source_type (section 8, 33).

    `default_branch` must match Repository.default_branch (what the DB
    thinks the base branch is called) -- found live during testing:
    `git.Repo.init()` with no explicit branch name uses the HOST machine's
    `init.defaultBranch` git config (which is "master" on some machines,
    "main" on others), while the Repository row always defaults to "main"
    regardless of the host. That mismatch made every ZIP-uploaded repo's
    first git operation fail with "Base branch 'main' does not exist" on a
    machine configured for "master". Explicitly naming the branch here
    makes repo creation deterministic and independent of host git config.
    """
    import git

    if (repo_dir / ".git").exists():
        return
    repo = git.Repo.init(repo_dir, initial_branch=default_branch)
    repo.git.add(A=True)
    if repo.is_dirty() or not repo.head.is_valid():
        repo.index.commit("Initial import (ZIP upload)")


def slugify_branch_name(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    slug = slug[:50] or "change"
    return f"verascope/fix-{slug}"


def create_branch_commit(
    repo_dir: Path,
    branch_name: str,
    base_branch: str,
    changes: list[AppliedChange],
    commit_message: str,
) -> str:
    """Creates `branch_name` off `base_branch`, applies `changes` (already
    validated/approved), commits, and returns the commit SHA. Leaves the
    repo checked out on the new branch, never touches `base_branch` itself
    after this point."""
    import git

    ensure_git_repo(repo_dir, default_branch=base_branch)
    repo = git.Repo(repo_dir)

    if base_branch not in [h.name for h in repo.heads]:
        raise GitOpsError(f"Base branch '{base_branch}' does not exist in this repository clone.")
    repo.heads[base_branch].checkout()

    if branch_name in [h.name for h in repo.heads]:
        repo.delete_head(branch_name, force=True)
    new_branch = repo.create_head(branch_name)
    new_branch.checkout()

    for change in changes:
        abs_path = repo_dir / change.path
        if change.change_type == ChangeType.DELETE:
            if abs_path.exists():
                abs_path.unlink()
                repo.index.remove([change.path], working_tree=True)
        else:
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_text(change.new_content or "", encoding="utf-8")
            repo.index.add([change.path])

    if not repo.is_dirty(untracked_files=True) and not repo.index.diff("HEAD"):
        raise GitOpsError("No effective changes to commit (workspace matches the base branch).")

    commit = repo.index.commit(commit_message)
    return commit.hexsha


def get_branch_diff(repo_dir: Path, branch_name: str, base_branch: str) -> str:
    import git

    repo = git.Repo(repo_dir)
    return repo.git.diff(f"{base_branch}...{branch_name}")


def push_branch(repo_dir: Path, branch_name: str, github_token: str, remote_url: str | None = None) -> None:
    import git

    repo = git.Repo(repo_dir)
    if remote_url and github_token:
        auth_url = _inject_token(remote_url, github_token)
        if "verascope-origin" in [r.name for r in repo.remotes]:
            repo.delete_remote("verascope-origin")
        remote = repo.create_remote("verascope-origin", auth_url)
    else:
        if not repo.remotes:
            raise GitOpsError("Repository has no configured remote to push to.")
        remote = repo.remote()

    try:
        remote.push(refspec=f"{branch_name}:{branch_name}")
    except git.GitCommandError as exc:
        raise GitOpsError(f"git push failed: {exc}") from exc


def _inject_token(remote_url: str, token: str) -> str:
    if remote_url.startswith("https://") and "@" not in remote_url:
        return remote_url.replace("https://", f"https://{token}@", 1)
    return remote_url
