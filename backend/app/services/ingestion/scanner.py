"""Recursive repository scanner (section 9).

Walks a cloned/extracted repository on disk and produces a flat list of
`ScannedFile` records: path, size, language, and the test/config/doc/binary
classification flags. Ignore rules (directories + extensions + size cap) are
applied here so nothing huge, generated, or binary ever reaches the parser,
embedder, or LLM context.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import Settings
from app.services.ingestion.language_detect import (
    detect_language,
    is_config_file,
    is_documentation_file,
    is_test_file,
)

# A quick binary sniff: if these bytes show up in the first chunk, treat the
# file as binary regardless of extension.
_NULL_BYTE = b"\x00"


@dataclass
class ScannedFile:
    path: str  # repository-relative, forward-slash separated
    absolute_path: Path
    size_bytes: int
    language: str | None
    is_test: bool
    is_config: bool
    is_documentation: bool
    is_binary: bool
    skipped_reason: str | None = None
    content_hash: str | None = None
    line_count: int = 0


@dataclass
class ScanResult:
    files: list[ScannedFile] = field(default_factory=list)
    skipped_dirs: list[str] = field(default_factory=list)
    total_files_seen: int = 0
    truncated: bool = False
    """True if max_repo_files was hit and the scan stopped early."""


def _looks_binary(sample: bytes) -> bool:
    return _NULL_BYTE in sample


def _to_posix(rel_path: Path) -> str:
    return rel_path.as_posix()


def scan_repository(root: Path, settings: Settings) -> ScanResult:
    result = ScanResult()
    ignored_dirs = settings.ignored_dir_set
    ignored_exts = settings.ignored_extension_set

    for dirpath, dirnames, filenames in _walk(root):
        # Prune ignored directories in-place so os.walk doesn't descend into them.
        pruned = [d for d in dirnames if d in ignored_dirs or d.startswith(".") and d not in (".",)]
        for d in pruned:
            result.skipped_dirs.append(_to_posix((dirpath / d).relative_to(root)))
        dirnames[:] = [d for d in dirnames if d not in ignored_dirs and not (d.startswith(".") and d != ".")]

        for filename in filenames:
            result.total_files_seen += 1
            if len(result.files) >= settings.max_repo_files:
                result.truncated = True
                return result

            abs_path = dirpath / filename
            rel_path = _to_posix(abs_path.relative_to(root))
            ext = abs_path.suffix.lower()

            language = detect_language(rel_path)
            is_test = is_test_file(rel_path)
            is_config = is_config_file(rel_path)
            is_doc = is_documentation_file(rel_path)

            try:
                size_bytes = abs_path.stat().st_size
            except OSError:
                continue

            skipped_reason = None
            is_binary = False

            if ext in ignored_exts:
                skipped_reason = f"ignored extension {ext}"
                is_binary = True
            elif size_bytes > settings.max_file_size_bytes:
                skipped_reason = f"file too large ({size_bytes} bytes)"
            else:
                try:
                    with open(abs_path, "rb") as fh:
                        sample = fh.read(4096)
                    if _looks_binary(sample):
                        skipped_reason = "binary content detected"
                        is_binary = True
                except OSError as exc:
                    skipped_reason = f"unreadable: {exc}"

            scanned = ScannedFile(
                path=rel_path,
                absolute_path=abs_path,
                size_bytes=size_bytes,
                language=language,
                is_test=is_test,
                is_config=is_config,
                is_documentation=is_doc,
                is_binary=is_binary,
                skipped_reason=skipped_reason,
            )

            if not skipped_reason:
                _hydrate_content_metadata(scanned)

            result.files.append(scanned)

    return result


def _hydrate_content_metadata(scanned: ScannedFile) -> None:
    try:
        text = scanned.absolute_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        scanned.skipped_reason = f"unreadable: {exc}"
        return
    scanned.content_hash = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
    scanned.line_count = text.count("\n") + 1 if text else 0


def _walk(root: Path):
    """Thin wrapper over os.walk using pathlib, top-down so dirnames pruning
    takes effect."""
    import os

    for dirpath, dirnames, filenames in os.walk(root):
        yield Path(dirpath), dirnames, filenames
