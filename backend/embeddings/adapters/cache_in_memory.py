"""In-process LRU cache adapter for text embeddings."""

from __future__ import annotations

import threading
from collections import OrderedDict

from config.schema import EmbeddingsConfig
from embeddings.models import CachedEmbedding

__all__ = [
    "InMemoryLruEmbeddingCache",
    "create_embedding_cache",
    "embedding_cache_namespace",
]


class InMemoryLruEmbeddingCache:
    """Thread-safe LRU cache bounded by entry count.

    Per-process only by design: the embedder is a per-process singleton, so
    hits accrue exactly where repeat embeds happen. A shared/durable cache is
    BL-045 roadmap tier and would arrive as another EmbeddingCacheProtocol
    adapter.
    """

    def __init__(self, *, max_entries: int) -> None:
        if max_entries <= 0:
            raise ValueError(
                "InMemoryLruEmbeddingCache max_entries must be positive."
            )
        self._max_entries = max_entries
        self._entries: OrderedDict[str, CachedEmbedding] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> CachedEmbedding | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            self._entries.move_to_end(key)
            return entry

    def set(self, key: str, value: CachedEmbedding) -> None:
        with self._lock:
            self._entries[key] = value
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)


def embedding_cache_namespace(config: EmbeddingsConfig) -> str:
    """Derive the cache namespace pinning provider, model, and dimensions."""

    return f"{config.provider}:{config.model}:{config.dimensions}"


def create_embedding_cache(
    config: EmbeddingsConfig,
) -> InMemoryLruEmbeddingCache | None:
    """Build the config-selected embedding cache; None when disabled."""

    if not config.cache_enabled:
        return None
    return InMemoryLruEmbeddingCache(max_entries=config.cache_max_entries)
