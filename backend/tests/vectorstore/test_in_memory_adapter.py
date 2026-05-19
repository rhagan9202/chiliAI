"""Tests for the in-memory vectorstore adapter."""

from __future__ import annotations

import pytest

from vectorstore.adapters.in_memory import InMemoryVectorStore
from vectorstore.exceptions import VectorDimensionMismatchError
from vectorstore.models import VectorRecord


def test_in_memory_vector_store_searches_by_similarity_and_filters() -> None:
    store = InMemoryVectorStore()
    store.upsert_records(
        "kb-1",
        [
            VectorRecord(
                id="record-1",
                knowledge_base_id="kb-1",
                content_id="content-1",
                embedding=[1.0, 0.0],
                metadata={"source": "policy"},
            ),
            VectorRecord(
                id="record-2",
                knowledge_base_id="kb-1",
                content_id="content-2",
                embedding=[0.0, 1.0],
                metadata={"source": "claim"},
            ),
        ],
    )

    matches = store.search("kb-1", [0.8, 0.2], 2, {"source": "policy"})

    assert [match.content_id for match in matches] == ["content-1"]


def test_in_memory_vector_store_rejects_dimension_mismatch() -> None:
    store = InMemoryVectorStore()
    store.upsert_records(
        "kb-1",
        [
            VectorRecord(
                id="record-1",
                knowledge_base_id="kb-1",
                content_id="content-1",
                embedding=[1.0, 0.0],
            )
        ],
    )

    with pytest.raises(VectorDimensionMismatchError, match="dimension"):
        store.search("kb-1", [1.0, 0.0, 0.0], 1)


def test_in_memory_vector_store_gets_and_counts_records() -> None:
    store = InMemoryVectorStore()
    record = VectorRecord(
        id="record-1",
        knowledge_base_id="kb-1",
        content_id="content-1",
        embedding=[1.0, 0.0],
        content="Alpha",
        metadata={"source": "policy"},
    )
    store.upsert_records("kb-1", [record])

    assert store.get_record("kb-1", "record-1") == record
    assert store.get_record("kb-1", "missing") is None
    assert store.count_records("kb-1") == 1
    assert store.count_records("missing-kb") == 0


def test_in_memory_vector_store_get_record_returns_detached_copy() -> None:
    store = InMemoryVectorStore()
    store.upsert_records(
        "kb-1",
        [
            VectorRecord(
                id="record-1",
                knowledge_base_id="kb-1",
                content_id="content-1",
                embedding=[1.0, 0.0],
                metadata={"source": "policy"},
            )
        ],
    )

    record = store.get_record("kb-1", "record-1")
    assert record is not None
    record.embedding.append(2.0)
    record.metadata["source"] = "claim"

    stored_record = store.get_record("kb-1", "record-1")
    assert stored_record is not None
    assert stored_record.embedding == [1.0, 0.0]
    assert stored_record.metadata == {"source": "policy"}


def test_in_memory_vector_store_upsert_returns_detached_copies() -> None:
    store = InMemoryVectorStore()

    [record] = store.upsert_records(
        "kb-1",
        [
            VectorRecord(
                id="record-1",
                knowledge_base_id="kb-1",
                content_id="content-1",
                embedding=[1.0, 0.0],
                metadata={"source": "policy"},
            )
        ],
    )
    record.embedding.append(2.0)
    record.metadata["source"] = "claim"

    stored_record = store.get_record("kb-1", "record-1")
    assert stored_record is not None
    assert stored_record.embedding == [1.0, 0.0]
    assert stored_record.metadata == {"source": "policy"}


def test_in_memory_vector_store_deletes_record_idempotently() -> None:
    store = InMemoryVectorStore()
    store.upsert_records(
        "kb-1",
        [
            VectorRecord(
                id="record-1",
                knowledge_base_id="kb-1",
                content_id="content-1",
                embedding=[1.0, 0.0],
            )
        ],
    )

    assert store.delete_record("kb-1", "record-1") is True
    assert store.delete_record("kb-1", "record-1") is False
    assert store.get_record("kb-1", "record-1") is None
    assert store.count_records("kb-1") == 0


def test_in_memory_vector_store_delete_record_clears_namespace_dimension() -> None:
    store = InMemoryVectorStore()
    store.upsert_records(
        "kb-1",
        [
            VectorRecord(
                id="record-1",
                knowledge_base_id="kb-1",
                content_id="content-1",
                embedding=[1.0, 0.0],
            )
        ],
    )

    assert store.delete_record("kb-1", "record-1") is True

    store.upsert_records(
        "kb-1",
        [
            VectorRecord(
                id="record-2",
                knowledge_base_id="kb-1",
                content_id="content-2",
                embedding=[1.0, 0.0, 0.0],
            )
        ],
    )
    assert store.count_records("kb-1") == 1


def test_in_memory_vector_store_delete_namespace_returns_count() -> None:
    store = InMemoryVectorStore()
    store.upsert_records(
        "kb-1",
        [
            VectorRecord(
                id="record-1",
                knowledge_base_id="kb-1",
                content_id="content-1",
                embedding=[1.0, 0.0],
            ),
            VectorRecord(
                id="record-2",
                knowledge_base_id="kb-1",
                content_id="content-2",
                embedding=[0.0, 1.0],
            ),
        ],
    )
    store.upsert_records(
        "kb-2",
        [
            VectorRecord(
                id="record-3",
                knowledge_base_id="kb-2",
                content_id="content-3",
                embedding=[1.0, 1.0],
            )
        ],
    )

    assert store.delete_namespace("kb-1") == 2
    assert store.delete_namespace("kb-1") == 0
    assert store.count_records("kb-1") == 0
    assert store.count_records("kb-2") == 1


def test_in_memory_vector_store_delete_namespace_clears_dimension() -> None:
    store = InMemoryVectorStore()
    store.upsert_records(
        "kb-1",
        [
            VectorRecord(
                id="record-1",
                knowledge_base_id="kb-1",
                content_id="content-1",
                embedding=[1.0, 0.0],
            )
        ],
    )

    assert store.delete_namespace("kb-1") == 1

    store.upsert_records(
        "kb-1",
        [
            VectorRecord(
                id="record-2",
                knowledge_base_id="kb-1",
                content_id="content-2",
                embedding=[1.0, 0.0, 0.0],
            )
        ],
    )
    assert store.count_records("kb-1") == 1
