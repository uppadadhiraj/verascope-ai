"""Language dispatcher. `parse_file` never raises -- any exception from a
language-specific parser is caught and reported as `ParsedFile.error` so one
bad file cannot abort ingestion for the rest of the repository (section 11)."""
from __future__ import annotations

from app.services.ingestion.parser.base import ExtractedImport, ExtractedSymbol, ParsedFile
from app.services.ingestion.parser.generic_parser import parse_c_cpp, parse_java
from app.services.ingestion.parser.js_ts_parser import parse_js_ts
from app.services.ingestion.parser.python_parser import parse_python

__all__ = ["ExtractedImport", "ExtractedSymbol", "ParsedFile", "parse_file"]


def parse_file(language: str | None, content: str) -> ParsedFile:
    if language is None:
        return ParsedFile()
    try:
        if language == "python":
            return parse_python(content)
        if language in ("javascript", "typescript"):
            return parse_js_ts(content)
        if language == "java":
            return parse_java(content)
        if language == "c":
            return parse_c_cpp(content, is_cpp=False)
        if language == "cpp":
            return parse_c_cpp(content, is_cpp=True)
        return ParsedFile()
    except Exception as exc:  # last-resort guard: ingestion must continue
        return ParsedFile(error=f"{type(exc).__name__}: {exc}")
