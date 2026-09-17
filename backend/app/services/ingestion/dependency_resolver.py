"""Resolves raw import strings to actual repository files, building the
IMPORTS edges of the dependency graph (section 13).

An import that can't be resolved to a file in this repository (a
third-party package, or a construct we don't handle) is not an error -- it
just stays unresolved and the raw text is preserved on the edge so it's
still visible as evidence, per RepositoryDependency.raw_reference.
"""
from __future__ import annotations

from dataclasses import dataclass
from posixpath import dirname, normpath

from app.services.ingestion.parser.base import ExtractedImport

_JS_EXTENSIONS = [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"]


@dataclass
class ResolvedImport:
    source_file: str
    target_file: str | None
    raw: str


def resolve_imports(
    imports_by_file: dict[str, list[ExtractedImport]],
    language_by_file: dict[str, str | None],
) -> list[ResolvedImport]:
    file_set = set(language_by_file.keys())
    resolved: list[ResolvedImport] = []

    for source_file, imports in imports_by_file.items():
        language = language_by_file.get(source_file)
        for imp in imports:
            target = None
            if language == "python":
                target = _resolve_python(source_file, imp.raw, file_set)
            elif language in ("javascript", "typescript"):
                target = _resolve_js(source_file, imp.raw, file_set)
            elif language == "java":
                target = _resolve_java(imp.raw, file_set)
            elif language in ("c", "cpp"):
                target = _resolve_c(source_file, imp.raw, file_set)
            resolved.append(ResolvedImport(source_file=source_file, target_file=target, raw=imp.raw))

    return resolved


def _resolve_python(source_file: str, raw: str, file_set: set[str]) -> str | None:
    if raw.startswith("."):
        # relative import: leading dots count directory levels up from the
        # source file's package.
        level = len(raw) - len(raw.lstrip("."))
        remainder = raw[level:]
        base_dir = dirname(source_file)
        for _ in range(level - 1):
            base_dir = dirname(base_dir)
        parts = remainder.split(".") if remainder else []
        candidate_base = normpath("/".join([base_dir, *parts])) if parts else base_dir
    else:
        candidate_base = raw.replace(".", "/")

    for suffix in ("", "/__init__"):
        candidate = f"{candidate_base}{suffix}.py".lstrip("/")
        if candidate in file_set:
            return candidate
    return None


def _resolve_js(source_file: str, raw: str, file_set: set[str]) -> str | None:
    if not (raw.startswith(".") or raw.startswith("/")):
        return None  # bare specifier -> npm package, not in this repo
    base_dir = dirname(source_file)
    candidate_base = normpath("/".join([base_dir, raw])).lstrip("/")

    for ext in _JS_EXTENSIONS:
        candidate = f"{candidate_base}{ext}"
        if candidate in file_set:
            return candidate
    for ext in _JS_EXTENSIONS:
        candidate = f"{candidate_base}/index{ext}"
        if candidate in file_set:
            return candidate
    if candidate_base in file_set:
        return candidate_base
    return None


def _resolve_java(raw: str, file_set: set[str]) -> str | None:
    suffix = raw.replace(".", "/") + ".java"
    for f in file_set:
        if f.endswith(suffix):
            return f
    return None


def _resolve_c(source_file: str, raw: str, file_set: set[str]) -> str | None:
    base_dir = dirname(source_file)
    candidate = normpath("/".join([base_dir, raw])).lstrip("/")
    if candidate in file_set:
        return candidate
    for f in file_set:
        if f.endswith("/" + raw) or f == raw:
            return f
    return None
