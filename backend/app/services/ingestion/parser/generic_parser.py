"""Regex + brace-matching parser for Java, C and C++.

Same tradeoff as js_ts_parser.py: no real AST, but real (not fabricated)
symbol extraction for the common declaration shapes, with start/end lines
recovered via brace balancing.
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

_JAVA_IMPORT = re.compile(r'^\s*import\s+(?:static\s+)?([\w.]+)\s*;', re.MULTILINE)
_C_INCLUDE = re.compile(r'^\s*#include\s*[<"]([^>"]+)[>"]', re.MULTILINE)

_JAVA_CLASS = re.compile(
    r'^\s*(?:public|private|protected)?\s*(?:static\s+|final\s+|abstract\s+)*'
    r'(?:class|interface|enum)\s+([A-Za-z_]\w*)',
    re.MULTILINE,
)
_JAVA_METHOD = re.compile(
    r'^\s*(?:public|private|protected)\s+(?:static\s+|final\s+|synchronized\s+|abstract\s+)*'
    r'[\w<>\[\],\s]+?\s+([A-Za-z_]\w*)\s*\(([^)]*)\)\s*(?:throws\s+[\w,\s]+)?\s*\{',
    re.MULTILINE,
)

# C / C++: a return-type + name + (...) + '{' on (roughly) one declaration.
# Deliberately conservative to avoid matching control-flow statements.
_C_FUNCTION = re.compile(
    r'^(?![\s]*(?:if|for|while|switch|catch|return)\b)'
    r'^[A-Za-z_][\w:<>\*&,\s]*[\s\*&]([A-Za-z_]\w*)\s*\(([^;{)]*)\)\s*(?:const\s*)?\{',
    re.MULTILINE,
)
_CPP_CLASS = re.compile(
    r'^\s*class\s+([A-Za-z_]\w*)',
    re.MULTILINE,
)


def parse_java(content: str) -> ParsedFile:
    result = ParsedFile()
    lines = content.splitlines()
    try:
        for m in _JAVA_IMPORT.finditer(content):
            result.imports.append(ExtractedImport(raw=m.group(1), line=line_of(content, m.start())))

        for m in _JAVA_CLASS.finditer(content):
            start_line = line_of(content, m.start())
            end_line = match_brace_end(lines, start_line)
            result.symbols.append(
                ExtractedSymbol(name=m.group(1), symbol_type="class", start_line=start_line, end_line=end_line)
            )
            _extract_java_methods(lines, start_line, end_line, m.group(1), result)
    except Exception as exc:
        result.error = f"{type(exc).__name__}: {exc}"
    return result


def _extract_java_methods(
    lines: list[str], class_start: int, class_end: int, class_name: str, result: ParsedFile
) -> None:
    class_body = "\n".join(lines[class_start:class_end])
    for m in _JAVA_METHOD.finditer(class_body):
        start_line = class_start + line_of(class_body, m.start())
        end_line = match_brace_end(lines, start_line)
        result.symbols.append(
            ExtractedSymbol(
                name=m.group(1),
                symbol_type="method",
                start_line=start_line,
                end_line=end_line,
                parent_name=class_name,
                signature=lines[start_line - 1].strip() if start_line - 1 < len(lines) else None,
            )
        )


def parse_c_cpp(content: str, is_cpp: bool) -> ParsedFile:
    result = ParsedFile()
    lines = content.splitlines()
    try:
        for m in _C_INCLUDE.finditer(content):
            result.imports.append(ExtractedImport(raw=m.group(1), line=line_of(content, m.start())))

        if is_cpp:
            for m in _CPP_CLASS.finditer(content):
                start_line = line_of(content, m.start())
                end_line = match_brace_end(lines, start_line)
                result.symbols.append(
                    ExtractedSymbol(
                        name=m.group(1), symbol_type="class", start_line=start_line, end_line=end_line
                    )
                )

        for m in _C_FUNCTION.finditer(content):
            name = m.group(1)
            if name in {"if", "for", "while", "switch", "catch", "return"}:
                continue
            start_line = line_of(content, m.start())
            end_line = match_brace_end(lines, start_line)
            result.symbols.append(
                ExtractedSymbol(
                    name=name,
                    symbol_type="function",
                    start_line=start_line,
                    end_line=end_line,
                    signature=lines[start_line - 1].strip() if start_line - 1 < len(lines) else None,
                )
            )
    except Exception as exc:
        result.error = f"{type(exc).__name__}: {exc}"
    return result
