"""Turns a parsed file into embeddable chunks (section 14).

Where symbols were extracted, each top-level symbol (function/class/route)
becomes its own chunk -- that gives the vector store line-accurate,
semantically coherent units instead of arbitrary line windows. Files with no
extracted symbols (unsupported language, docs, config) fall back to a
sliding line-window so they're still searchable.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.ingestion.parser.base import ExtractedSymbol

WINDOW_LINES = 60
WINDOW_OVERLAP = 10
MAX_CHUNK_CHARS = 4000


@dataclass
class Chunk:
    content: str
    chunk_type: str  # symbol | window | document
    start_line: int
    end_line: int
    symbol: str | None = None


def chunk_file(content: str, language: str | None, symbols: list[ExtractedSymbol]) -> list[Chunk]:
    lines = content.splitlines()
    if not lines:
        return []

    # Prefer top-level symbols (no parent, or class-level) -- nested methods
    # are already covered by their enclosing class chunk, and chunking both
    # would duplicate content in the vector store for no retrieval benefit.
    top_level = [s for s in symbols if s.symbol_type in ("function", "class") and s.parent_name is None]

    if top_level:
        chunks = []
        for sym in sorted(top_level, key=lambda s: s.start_line):
            start = max(1, sym.start_line)
            end = min(len(lines), sym.end_line or sym.start_line)
            text = "\n".join(lines[start - 1 : end])
            if not text.strip():
                continue
            chunks.append(
                Chunk(
                    content=text[:MAX_CHUNK_CHARS],
                    chunk_type="symbol",
                    start_line=start,
                    end_line=end,
                    symbol=sym.name,
                )
            )
        # Cover any gaps (module-level code between/around symbols) with a
        # single window so imports/constants remain searchable too.
        covered = {ln for c in chunks for ln in range(c.start_line, c.end_line + 1)}
        gap_lines = [i + 1 for i in range(len(lines)) if (i + 1) not in covered]
        if gap_lines:
            chunks.extend(_window_chunks(lines, only_lines=set(gap_lines)))
        return chunks

    chunk_type = "document" if language in (None, "markdown", "json", "yaml", "toml") else "window"
    return _window_chunks(lines, chunk_type=chunk_type)


def _window_chunks(
    lines: list[str], only_lines: set[int] | None = None, chunk_type: str = "window"
) -> list[Chunk]:
    chunks: list[Chunk] = []
    step = WINDOW_LINES - WINDOW_OVERLAP
    i = 0
    while i < len(lines):
        start = i + 1
        end = min(len(lines), i + WINDOW_LINES)
        window_line_nums = range(start, end + 1)
        if only_lines is None or any(n in only_lines for n in window_line_nums):
            text = "\n".join(lines[start - 1 : end])
            if text.strip():
                chunks.append(
                    Chunk(content=text[:MAX_CHUNK_CHARS], chunk_type=chunk_type, start_line=start, end_line=end)
                )
        i += step
        if end >= len(lines):
            break
    return chunks
