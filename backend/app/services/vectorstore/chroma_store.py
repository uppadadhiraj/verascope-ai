"""ChromaDB-backed VectorStore, run embedded (PersistentClient) -- no
separate server process. Repository-scoping (section 14: "searches are
repository-scoped") is enforced via a `where` filter on `repository_id` on
every query, using one shared collection for all repositories rather than
one collection per repository (simpler re-indexing / cleanup semantics).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from functools import lru_cache
from typing import Callable, TypeVar

import chromadb

from app.core.config import Settings, get_settings
from app.services.vectorstore.base import (
    SearchFilters,
    VectorRecord,
    VectorSearchResult,
    VectorStore,
    VectorStoreTimeoutError,
)
from app.services.vectorstore.embedder import Embedder, get_embedder

_COLLECTION_NAME = "repository_chunks"
_CALL_TIMEOUT_SECONDS = 60

_T = TypeVar("_T")


def _with_timeout(fn: Callable[..., _T], *args, **kwargs) -> _T:
    # Deliberately not a `with ThreadPoolExecutor(...)` block: its __exit__
    # calls shutdown(wait=True), which would block until the stuck worker
    # thread finishes -- exactly what this exists to avoid. Python cannot
    # forcibly kill a thread, so on timeout the call is left to run out its
    # life on a leaked thread (harmless: it either finishes on its own or
    # stays blocked until process exit) while this function returns control
    # immediately.
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(fn, *args, **kwargs)
    try:
        return future.result(timeout=_CALL_TIMEOUT_SECONDS)
    except FutureTimeoutError as exc:
        raise VectorStoreTimeoutError(
            f"ChromaDB call ({fn.__name__}) did not respond within {_CALL_TIMEOUT_SECONDS}s."
        ) from exc
    finally:
        pool.shutdown(wait=False)


class ChromaVectorStore(VectorStore):
    def __init__(self, persist_dir: str, embedder: Embedder):
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collection = self._client.get_or_create_collection(
            name=_COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
        )
        self._embedder = embedder

    def upsert(self, records: list[VectorRecord]) -> None:
        if not records:
            return
        vectors = self._embedder.embed([r.content for r in records])
        _with_timeout(
            self._collection.upsert,
            ids=[r.id for r in records],
            embeddings=vectors,
            documents=[r.content for r in records],
            metadatas=[
                {
                    "repository_id": r.repository_id,
                    "file_path": r.file_path,
                    "language": r.language or "",
                    "chunk_type": r.chunk_type,
                    "start_line": r.start_line,
                    "end_line": r.end_line,
                    "symbol": r.symbol or "",
                }
                for r in records
            ],
        )

    def delete_repository(self, repository_id: str) -> None:
        _with_timeout(self._collection.delete, where={"repository_id": repository_id})

    def delete_file(self, repository_id: str, file_path: str) -> None:
        _with_timeout(
            self._collection.delete,
            where={"$and": [{"repository_id": repository_id}, {"file_path": file_path}]},
        )

    def search(
        self, repository_id: str, query: str, top_k: int = 8, filters: SearchFilters | None = None
    ) -> list[VectorSearchResult]:
        where_clauses: list[dict] = [{"repository_id": repository_id}]
        if filters:
            if filters.language:
                where_clauses.append({"language": filters.language})
            if filters.file_path:
                where_clauses.append({"file_path": filters.file_path})
            if filters.chunk_type:
                where_clauses.append({"chunk_type": filters.chunk_type})
            if filters.file_paths:
                where_clauses.append({"file_path": {"$in": filters.file_paths}})
        where = where_clauses[0] if len(where_clauses) == 1 else {"$and": where_clauses}

        query_vector = self._embedder.embed_one(query)
        result = _with_timeout(
            self._collection.query,
            query_embeddings=[query_vector],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        if not result["ids"] or not result["ids"][0]:
            return []

        out: list[VectorSearchResult] = []
        for idx, chunk_id in enumerate(result["ids"][0]):
            meta = result["metadatas"][0][idx]
            distance = result["distances"][0][idx]
            record = VectorRecord(
                id=chunk_id,
                repository_id=meta["repository_id"],
                file_path=meta["file_path"],
                language=meta.get("language") or None,
                chunk_type=meta["chunk_type"],
                start_line=meta["start_line"],
                end_line=meta["end_line"],
                content=result["documents"][0][idx],
                symbol=meta.get("symbol") or None,
            )
            # cosine distance -> similarity score in [0, 1] (approximately)
            score = max(0.0, 1.0 - distance / 2.0)
            out.append(VectorSearchResult(record=record, score=score))
        return out


@lru_cache
def get_vector_store() -> VectorStore:
    settings: Settings = get_settings()
    return ChromaVectorStore(settings.chroma_persist_dir, get_embedder())
