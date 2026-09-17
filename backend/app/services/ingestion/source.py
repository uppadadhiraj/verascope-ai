"""Repository acquisition: GitHub clone (section 7) and ZIP upload
(section 8), both landing the repository at the same on-disk layout so the
rest of the ingestion pipeline doesn't care which source it came from.
"""
from __future__ import annotations

import os
import re
import shutil
import stat
import time
import zipfile
from pathlib import Path

_GITHUB_URL_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+?)(?:\.git)?/?$"
)


class IngestionSourceError(Exception):
    """Raised for user-facing ingestion failures (bad URL, clone failure,
    zip traversal, etc.) -- always with a specific, actionable message
    (section 45: avoid generic 'something went wrong')."""


def validate_github_url(repo_url: str) -> tuple[str, str]:
    match = _GITHUB_URL_RE.match(repo_url.strip())
    if not match:
        raise IngestionSourceError(
            f"'{repo_url}' does not look like a GitHub repository URL "
            "(expected https://github.com/<owner>/<repo>)."
        )
    return match.group("owner"), match.group("repo")


def _robust_rmtree(path: Path, retries: int = 6, delay: float = 0.5) -> None:
    """shutil.rmtree can fail transiently on Windows with 'Access is denied'
    on git pack files -- a well-known GitPython+Windows interaction (git
    pack files are often written read-only, and file handles from a
    just-closed `git.Repo` aren't always released by the OS immediately).
    Found live while testing a rescan. Clearing the read-only bit and
    retrying with a short backoff is the same workaround pip/tox/conda use
    for the same underlying Windows behavior; on Linux (this project's
    Docker image) the first attempt always succeeds and this is a no-op.
    """

    def _on_rm_error(func, path_str, exc_info):  # noqa: ANN001 -- shutil's required onerror signature
        try:
            os.chmod(path_str, stat.S_IWRITE)
            func(path_str)
        except OSError:
            pass

    last_exc: OSError | None = None
    for _ in range(retries):
        try:
            shutil.rmtree(path, onerror=_on_rm_error)
            return
        except OSError as exc:
            last_exc = exc
            time.sleep(delay)

    raise IngestionSourceError(
        f"Could not remove the existing repository directory at '{path}' after {retries} attempts "
        f"(last error: {last_exc}). It may be locked by another process (an editor, antivirus scan, "
        "or a lingering git process) -- close anything that might have it open and try again."
    ) from last_exc


def clone_github_repository(
    repo_url: str, dest: Path, branch: str | None = None, github_token: str = ""
) -> str:
    """Clones into `dest` (which must not already exist) and returns the
    default branch name that was actually checked out."""
    import git

    owner, repo = validate_github_url(repo_url)
    if dest.exists():
        _robust_rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    clone_url = repo_url
    if github_token:
        clone_url = f"https://{github_token}@github.com/{owner}/{repo}.git"

    try:
        kwargs = {"depth": 1}
        if branch:
            kwargs["branch"] = branch
        cloned = git.Repo.clone_from(clone_url, dest, **kwargs)
    except git.GitCommandError as exc:
        stderr = (exc.stderr or "").lower()
        if "could not read username" in stderr or "authentication failed" in stderr or "403" in stderr:
            raise IngestionSourceError(
                f"'{owner}/{repo}' could not be cloned -- it may be private. "
                "Set GITHUB_TOKEN with access to this repository and try again."
            ) from exc
        if "not found" in stderr or "repository not found" in stderr:
            raise IngestionSourceError(f"GitHub repository '{owner}/{repo}' was not found.") from exc
        raise IngestionSourceError(f"git clone failed for '{owner}/{repo}': {exc}") from exc

    active_branch = cloned.active_branch.name if not cloned.head.is_detached else (branch or "main")
    return active_branch


def extract_zip_archive(zip_path: Path, dest: Path) -> None:
    """Extracts `zip_path` into `dest`, refusing any entry that would
    escape `dest` (zip-slip / path traversal protection, section 8)."""
    dest.mkdir(parents=True, exist_ok=True)
    resolved_dest = dest.resolve()

    with zipfile.ZipFile(zip_path) as zf:
        members = zf.infolist()
        if len(members) > 200_000:
            raise IngestionSourceError("ZIP archive contains an unreasonable number of entries.")

        for member in members:
            member_path = (dest / member.filename).resolve()
            if not str(member_path).startswith(str(resolved_dest)):
                raise IngestionSourceError(
                    f"Refusing to extract '{member.filename}': path traversal outside the workspace."
                )

        zf.extractall(dest)

    _flatten_single_root_dir(dest)


def _flatten_single_root_dir(dest: Path) -> None:
    """GitHub-style zip downloads wrap everything in a single
    '<repo>-<branch>/' directory -- unwrap it so file paths in the DB match
    what a `git clone` of the same repo would produce."""
    entries = list(dest.iterdir())
    if len(entries) == 1 and entries[0].is_dir():
        root = entries[0]
        for item in root.iterdir():
            shutil.move(str(item), str(dest / item.name))
        root.rmdir()
