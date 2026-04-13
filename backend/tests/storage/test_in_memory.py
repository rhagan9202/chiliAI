"""Tests for the in-memory object store adapter."""

from __future__ import annotations

import pytest

from storage.adapters.in_memory import InMemoryObjectStore
from storage.protocols import ObjectStore


def test_in_memory_object_store_satisfies_protocol() -> None:
    store = InMemoryObjectStore()

    assert isinstance(store, ObjectStore)


def test_in_memory_object_store_round_trip() -> None:
    store = InMemoryObjectStore()

    written = store.put_bytes(
        "documents/doc-1.txt",
        b"hello world",
        media_type="text/plain",
        metadata={"source": "unit-test"},
    )
    stored = store.get_bytes("documents/doc-1.txt")

    assert written.key == stored.key
    assert written.size_bytes == stored.size_bytes
    assert stored.content == b"hello world"
    assert stored.media_type == "text/plain"
    assert stored.metadata == {"source": "unit-test"}


def test_in_memory_object_store_raises_for_missing_key() -> None:
    store = InMemoryObjectStore()

    with pytest.raises(KeyError):
        store.get_bytes("missing")