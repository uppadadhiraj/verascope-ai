"""Shared parse-result types every language parser produces (section 11, 12).

A parser failure for one file must never abort ingestion for the rest of the
repository -- callers catch exceptions and record `ParsedFile.error` instead
of propagating.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExtractedSymbol:
    name: str
    symbol_type: str  # function | method | class | interface | variable | route
    start_line: int
    end_line: int
    signature: str | None = None
    docstring: str | None = None
    parent_name: str | None = None
    route_path: str | None = None
    http_method: str | None = None


@dataclass
class ExtractedImport:
    raw: str
    """The literal import target as written, e.g. 'app.core.config' or
    './utils/auth'. Resolution to an actual file happens later, in
    dependency.py, once every file in the repo has been parsed."""
    imported_names: list[str] = field(default_factory=list)
    line: int = 0


@dataclass
class ParsedFile:
    symbols: list[ExtractedSymbol] = field(default_factory=list)
    imports: list[ExtractedImport] = field(default_factory=list)
    error: str | None = None


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def match_brace_end(lines: list[str], start_line: int, max_lines: int = 2000) -> int:
    """Balance braces starting from `start_line` (1-indexed) to find the
    closing line. Best-effort: does not tokenize strings/comments, so a
    literal '{' inside a string can throw it off on pathological input --
    an accepted limitation of the regex-based (non-AST) parsers."""
    depth = 0
    started = False
    end_idx = start_line - 1
    limit = min(len(lines), start_line - 1 + max_lines)
    for i in range(start_line - 1, limit):
        line = lines[i]
        for ch in line:
            if ch == "{":
                depth += 1
                started = True
            elif ch == "}":
                depth -= 1
        end_idx = i
        if started and depth <= 0:
            break
    return end_idx + 1
