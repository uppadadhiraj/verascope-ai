"""Pluggable text -> vector embedding.

Default is a local sentence-transformers model (no API key, no network call,
works offline) so repository indexing never hard-depends on an LLM provider
key being present. Swapping to OpenAI embeddings is a config change
(EMBEDDING_PROVIDER=openai), not a code change.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from functools import lru_cache

from app.core.config import Settings, get_settings


class Embedder(ABC):
    @property
    @abstractmethod
    def dimensions(self) -> int: ...

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]: ...

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


class LocalEmbedder(Embedder):
    """sentence-transformers, loaded once and reused (loading the model is
    the expensive part -- inference on short code chunks is fast)."""

    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        # get_sentence_embedding_dimension() was renamed to
        # get_embedding_dimension() in sentence-transformers 5.x; requirements.txt
        # allows >=3.3, so support both instead of pinning a higher floor just
        # for this one call.
        if hasattr(self._model, "get_embedding_dimension"):
            self._dimensions = self._model.get_embedding_dimension()
        else:
            self._dimensions = self._model.get_sentence_embedding_dimension()

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        return [v.tolist() for v in vectors]


class OpenAIEmbedder(Embedder):
    _DIMENSIONS = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
    }

    def __init__(self, api_key: str, model: str):
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._model = model

    @property
    def dimensions(self) -> int:
        return self._DIMENSIONS.get(self._model, 1536)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self._client.embeddings.create(model=self._model, input=texts)
        return [item.embedding for item in response.data]


def build_embedder(settings: Settings) -> Embedder:
    if settings.embedding_provider == "openai":
        if not settings.openai_api_key:
            raise RuntimeError("EMBEDDING_PROVIDER=openai requires OPENAI_API_KEY to be set")
        return OpenAIEmbedder(settings.openai_api_key, settings.openai_embedding_model)
    return LocalEmbedder(settings.local_embedding_model)


@lru_cache
def get_embedder() -> Embedder:
    return build_embedder(get_settings())
