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