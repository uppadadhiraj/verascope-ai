"""Regex + brace-matching parser for JavaScript/TypeScript.

Not a full AST. A real JS/TS parser would mean shipping a tree-sitter
grammar and a Node/V8 (or tree-sitter Python bindings) dependency; for this
MVP we extract the common declaration shapes with regex and recover
start/end lines by balancing braces from the declaration site. This covers
the vast majority of real-world function/class/route declarations and,
per section 11 of the spec, a parser failure (or an unrecognized construct)
degrades gracefully -- it's simply not added to the symbol table, it never
aborts ingestion.
"""
from __future__ import annotations

import re

from app.services.ingestion.parser.base import (
    ExtractedImport,
    ExtractedSymbol,
    ParsedFile,
    line_of,
    match_brace_end,
)

_IMPORT_FROM = re.compile(r'^\s*import\s+.*?\sfrom\s+[\'"]([^\'"]+)[\'"]', re.MULTILINE)
_IMPORT_BARE = re.compile(r'^\s*import\s+[\'"]([^\'"]+)[\'"]', re.MULTILINE)
_REQUIRE = re.compile(r'require\(\s*[\'"]([^\'"]+)[\'"]\s*\)')

_FUNCTION_DECL = re.compile(
    r'^\s*(?:export\s+(?:default\s+)?)?(?:async\s+)?function\s*\*?\s+([A-Za-z_$][\w$]*)\s*\(',
    re.MULTILINE,
)
_ARROW_CONST = re.compile(
    r'^\s*(?:export\s+(?:default\s+)?)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>\s*\{',
    re.MULTILINE,
)
# `obj.prop = function name() {}` / `A.prototype.m = function () {}` / a
# property assigned an arrow function. Extremely common in non-class,
# prototypal-style JS (this is how most of Express's own lib/*.js defines
# its methods, for instance) -- missing this pattern meant a 632-line real
# file yielded only 2 extracted symbols instead of dozens, found live while
# testing against expressjs/express.
_PROPERTY_ASSIGNMENT_FUNCTION = re.compile(
    r'^\s*(?:module\.exports\.|exports\.)?[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*\.([A-Za-z_$][\w$]*)'
    r'\s*=\s*(?:async\s+)?function\s*[A-Za-z_$]*\s*\(',
    re.MULTILINE,
)
_PROPERTY_ASSIGNMENT_ARROW = re.compile(
    r'^\s*(?:module\.exports\.|exports\.)?[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*\.([A-Za-z_$][\w$]*)'
    r'\s*=\s*(?:async\s*)?\([^)]*\)\s*=>\s*\{',
    re.MULTILINE,
)
_CLASS_DECL = re.compile(
    r'^\s*(?:export\s+(?:default\s+)?)?class\s+([A-Za-z_$][\w$]*)',
    re.MULTILINE,
)
_METHOD_DECL = re.compile(
    r'^\s{2,}(?:public\s+|private\s+|protected\s+|static\s+|async\s+)*([A-Za-z_$][\w$]*)\s*\(([^)]*)\)\s*(?::\s*[\w<>\[\].,\s|]+)?\s*\{',
    re.MULTILINE,
)
_INTERFACE_DECL = re.compile(
    r'^\s*(?:export\s+)?interface\s+([A-Za-z_$][\w$]*)',
    re.MULTILINE,
)

_ROUTE_CALL = re.compile(
    r'\b(?:router|app)\.(get|post|put|delete|patch)\s*\(\s*[\'"]([^\'"]+)[\'"]',
    re.IGNORECASE,
)

_RESERVED_METHOD_NAMES = {"if", "for", "while", "switch", "catch", "function"}


def parse_js_ts(content: str) -> ParsedFile:
    result = ParsedFile()
    lines = content.splitlines()

    try:
        for m in _IMPORT_FROM.finditer(content):
            result.imports.append(ExtractedImport(raw=m.group(1), line=line_of(content, m.start())))
        for m in _IMPORT_BARE.finditer(content):
            result.imports.append(ExtractedImport(raw=m.group(1), line=line_of(content, m.start())))
        for m in _REQUIRE.finditer(content):
            result.imports.append(ExtractedImport(raw=m.group(1), line=line_of(content, m.start())))

        for m in _CLASS_DECL.finditer(content):
            start_line = line_of(content, m.start())
            end_line = match_brace_end(lines, start_line)
            result.symbols.append(
                ExtractedSymbol(
                    name=m.group(1), symbol_type="class", start_line=start_line, end_line=end_line
                )
            )
            _extract_methods(lines, start_line, end_line, m.group(1), result)

        for m in _INTERFACE_DECL.finditer(content):
            start_line = line_of(content, m.start())
            end_line = match_brace_end(lines, start_line)
            result.symbols.append(
                ExtractedSymbol(
                    name=m.group(1), symbol_type="interface", start_line=start_line, end_line=end_line
                )
            )

        for m in _FUNCTION_DECL.finditer(content):
            start_line = line_of(content, m.start())
            end_line = match_brace_end(lines, start_line)
            result.symbols.append(
                ExtractedSymbol(
                    name=m.group(1),
                    symbol_type="function",
                    start_line=start_line,
                    end_line=end_line,
                    signature=lines[start_line - 1].strip() if start_line - 1 < len(lines) else None,
                )
            )

        for m in _ARROW_CONST.finditer(content):
            start_line = line_of(content, m.start())
            end_line = match_brace_end(lines, start_line)
            result.symbols.append(
                ExtractedSymbol(
                    name=m.group(1),
                    symbol_type="function",
                    start_line=start_line,
                    end_line=end_line,
                    signature=lines[start_line - 1].strip() if start_line - 1 < len(lines) else None,
                )
            )

        seen_start_lines: set[int] = set()
        for pattern in (_PROPERTY_ASSIGNMENT_FUNCTION, _PROPERTY_ASSIGNMENT_ARROW):
            for m in pattern.finditer(content):
                start_line = line_of(content, m.start())
                if start_line in seen_start_lines:
                    continue  # a line can match both patterns' broader alternation in odd cases
                seen_start_lines.add(start_line)
                end_line = match_brace_end(lines, start_line)
                result.symbols.append(
                    ExtractedSymbol(
                        name=m.group(1),
                        symbol_type="method",
                        start_line=start_line,
                        end_line=end_line,
                        signature=lines[start_line - 1].strip() if start_line - 1 < len(lines) else None,
                    )
                )

        for m in _ROUTE_CALL.finditer(content):
            start_line = line_of(content, m.start())
            result.symbols.append(
                ExtractedSymbol(
                    name=f"{m.group(1).upper()} {m.group(2)}",
                    symbol_type="route",
                    start_line=start_line,
                    end_line=start_line,
                    route_path=m.group(2),
                    http_method=m.group(1).upper(),
                )
            )
    except Exception as exc:  # regex parsing must never blow up ingestion
        result.error = f"{type(exc).__name__}: {exc}"

    return result


def _extract_methods(
    lines: list[str], class_start: int, class_end: int, class_name: str, result: ParsedFile
) -> None:
    class_body = "\n".join(lines[class_start:class_end])  # excludes the `class X {` line itself
    for m in _METHOD_DECL.finditer(class_body):
        name = m.group(1)
        if name in _RESERVED_METHOD_NAMES:
            continue
        local_start = line_of(class_body, m.start())
        start_line = class_start + local_start
        end_line = match_brace_end(lines, start_line)
        result.symbols.append(
            ExtractedSymbol(
                name=name,
                symbol_type="method",
                start_line=start_line,
                end_line=end_line,
                parent_name=class_name,
                signature=lines[start_line - 1].strip() if start_line - 1 < len(lines) else None,
            )
        )
