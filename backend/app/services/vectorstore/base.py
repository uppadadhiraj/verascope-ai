"""VectorStore interface. ChromaVectorStore is the only implementation for
now, but every call site depends on this ABC (not on chromadb directly) so
swapping vector databases later (section 6, 55) doesn't ripple through the
ingestion pipeline, the chat service, or the agents.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class VectorRecord:
    id: str
    repository_id: str
    file_path: str
    language: str | None
    chunk_type: str
    start_line: int
    end_line: int
    content: str
    symbol: str | None = None


@dataclass
class VectorSearchResult:
    record: VectorRecord
    score: float


@dataclass
class SearchFilters:
    language: str | None = None
    file_path: str | None = None
    chunk_type: str | None = None
    file_paths: list[str] = field(default_factory=list)


class VectorStoreTimeoutError(Exception):
    """Raised when a vector store call doesn't return within its timeout.

    Observed directly: ChromaDB's SQLite-backed PersistentClient can hang
    indefinitely on a write (and, by the same mechanism, presumably a read)
    with no exception -- left unhandled, this silently wedges a repository
    at status=EMBEDDING forever, or hangs a live chat/search HTTP request
    with no feedback to the user. Callers should treat this as a normal,
    expected-to-happen failure mode (report it, don't crash), not a bug in
    their own code."""


class VectorStore(ABC):
    @abstractmethod
    def upsert(self, records: list[VectorRecord]) -> None: ...

    @abstractmethod
    def delete_repository(self, repository_id: str) -> None: ...

    @abstractmethod
    def delete_file(self, repository_id: str, file_path: str) -> None: ...

    @abstractmethod
    def search(
        self, repository_id: str, query: str, top_k: int = 8, filters: SearchFilters | None = None
    ) -> list[VectorSearchResult]: ...
