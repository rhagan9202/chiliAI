"""Tests for the in-memory LRU embedding cache."""

from __future__ import annotations

import pytest

from config.schema import EmbeddingsConfig
from embeddings.adapters.cache_in_memory import (
    InMemoryLruEmbeddingCache,
    create_embedding_cache,
    embedding_cache_namespace,
)
from embeddings.adapters.protocols import EmbeddingCacheProtocol
from embeddings.models import CachedEmbedding


def _entry(value: float) -> CachedEmbedding:
    return CachedEmbedding(
        vector=[value], model_name="m", provider="local", dimensions=1
    )


def test_cache_returns_none_for_missing_key() -> None:
    cache = InMemoryLruEmbeddingCache(max_entries=2)

    assert cache.get("missing") is None


def test_cache_roundtrips_entries() -> None:
    cache = InMemoryLruEmbeddingCache(max_entries=2)
    cache.set("key-1", _entry(0.1))

    stored = cache.get("key-1")

    assert stored is not None
    assert stored.vector == [0.1]
    assert stored.provider == "local"


def test_cache_evicts_least_recently_used_entry() -> None:
    cache = InMemoryLruEmbeddingCache(max_entries=2)
    cache.set("key-1", _entry(0.1))
    cache.set("key-2", _entry(0.2))
    assert cache.get("key-1") is not None  # refresh key-1 recency
    cache.set("key-3", _entry(0.3))

    assert cache.get("key-2") is None
    assert cache.get("key-1") is not None
    assert cache.get("key-3") is not None


def test_cache_set_overwrites_and_refreshes_recency() -> None:
    cache = InMemoryLruEmbeddingCache(max_entries=2)
    cache.set("key-1", _entry(0.1))
    cache.set("key-2", _entry(0.2))
    cache.set("key-1", _entry(0.9))
    cache.set("key-3", _entry(0.3))

    assert cache.get("key-2") is None
    stored = cache.get("key-1")
    assert stored is not None
    assert stored.vector == [0.9]


def test_cache_rejects_non_positive_max_entries() -> None:
    with pytest.raises(ValueError, match="max_entries"):
        InMemoryLruEmbeddingCache(max_entries=0)


def test_cache_satisfies_protocol() -> None:
    cache = InMemoryLruEmbeddingCache(max_entries=1)

    assert isinstance(cache, EmbeddingCacheProtocol)


def test_create_embedding_cache_respects_disabled_flag() -> None:
    assert create_embedding_cache(EmbeddingsConfig(cache_enabled=False)) is None


def test_create_embedding_cache_uses_configured_max_entries() -> None:
    cache = create_embedding_cache(EmbeddingsConfig(cache_max_entries=1))

    assert cache is not None
    cache.set("key-1", _entry(0.1))
    cache.set("key-2", _entry(0.2))
    assert cache.get("key-1") is None
    assert cache.get("key-2") is not None


def test_embedding_cache_namespace_pins_model_identity() -> None:
    config = EmbeddingsConfig(provider="local", model="mini", dimensions=128)

    assert embedding_cache_namespace(config) == "local:mini:128"
