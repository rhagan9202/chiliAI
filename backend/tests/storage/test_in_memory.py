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


def test_in_memory_object_store_delete_removes_existing_key() -> None:
    store = InMemoryObjectStore()
    store.put_bytes("documents/doc-1.txt", b"delete me")

    store.delete("documents/doc-1.txt")

    assert not store.exists("documents/doc-1.txt")
    with pytest.raises(KeyError):
        store.get_bytes("documents/doc-1.txt")


def test_in_memory_object_store_delete_missing_key_is_no_op() -> None:
    store = InMemoryObjectStore()
    store.put_bytes("documents/doc-1.txt", b"keep me")

    store.delete("missing")

    stored = store.get_bytes("documents/doc-1.txt")

    assert stored.content == b"keep me"


def test_in_memory_object_store_exists_tracks_key_lifecycle() -> None:
    store = InMemoryObjectStore()

    assert not store.exists("documents/doc-1.txt")

    store.put_bytes("documents/doc-1.txt", b"hello")

    assert store.exists("documents/doc-1.txt")

    store.delete("documents/doc-1.txt")

    assert not store.exists("documents/doc-1.txt")


def test_in_memory_object_store_list_keys_filters_by_prefix() -> None:
    store = InMemoryObjectStore()
    store.put_bytes("documents/doc-2.txt", b"two")
    store.put_bytes("documents/doc-1.txt", b"one")
    store.put_bytes("artifacts/doc-1.json", b"metadata")

    keys = store.list_keys("documents/")

    assert keys == ["documents/doc-1.txt", "documents/doc-2.txt"]


def test_in_memory_object_store_list_keys_empty_prefix_returns_all_keys() -> None:
    store = InMemoryObjectStore()
    store.put_bytes("documents/doc-2.txt", b"two")
    store.put_bytes("artifacts/doc-1.json", b"metadata")
    store.put_bytes("documents/doc-1.txt", b"one")

    keys = store.list_keys("")

    assert keys == [
        "artifacts/doc-1.json",
        "documents/doc-1.txt",
        "documents/doc-2.txt",
    ]


def test_in_memory_object_store_list_keys_returns_deterministic_sorted_order() -> None:
    store = InMemoryObjectStore()
    store.put_bytes("prefix/c.txt", b"c")
    store.put_bytes("prefix/a.txt", b"a")
    store.put_bytes("prefix/b.txt", b"b")

    first_listing = store.list_keys("prefix/")
    second_listing = store.list_keys("prefix/")

    assert first_listing == ["prefix/a.txt", "prefix/b.txt", "prefix/c.txt"]
    assert second_listing == first_listing
