from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict


class FileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    path: str
    language: str | None
    size_bytes: int
    line_count: int
    is_test: bool
    is_config: bool
    is_documentation: bool
    is_binary: bool
    skipped_reason: str | None
    parse_error: str | None


class FileTreeNode(BaseModel):
    name: str
    path: str
    type: str  # "file" | "directory"
    language: str | None = None
    children: list["FileTreeNode"] = []


FileTreeNode.model_rebuild()


class FileContentRead(BaseModel):
    path: str
    language: str | None
    content: str
    line_count: int


class SymbolRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    file_id: uuid.UUID
    name: str
    symbol_type: str
    language: str
    start_line: int
    end_line: int
    signature: str | None
    docstring: str | None
    route_path: str | None
    http_method: str | None


class CodeSearchResult(BaseModel):
    file_path: str
    start_line: int
    end_line: int
    symbol: str | None
    chunk_type: str
    content: str
    score: float


class DependencyGraphNode(BaseModel):
    id: str  # file path, used as the node key
    language: str | None
    is_test: bool
    in_degree: int
    out_degree: int


class DependencyGraphEdge(BaseModel):
    source: str  # file path
    target: str  # file path
    relationship: str


class DependencyGraph(BaseModel):
    """Structural (import-level) dependency graph -- see repository_tools.py
    module docstring for the same "not a call graph" caveat. Only edges
    resolved to another file IN this repository are included; external
    package imports are real evidence too but would just clutter a graph
    of "which of my own files depend on which"."""

    nodes: list[DependencyGraphNode]
    edges: list[DependencyGraphEdge]
    truncated: bool
