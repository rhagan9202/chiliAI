"""Tests for the in-memory rag adapters."""

from __future__ import annotations

from rag.adapters.in_memory import InMemoryContextRetriever, InMemoryQueryEmbedder
from rag.models import ContextRecord


def test_in_memory_query_embedder_is_deterministic() -> None:
    embedder = InMemoryQueryEmbedder()

    left = embedder.embed_query(knowledge_base_id="kb-1", question="Claim 42")
    right = embedder.embed_query(knowledge_base_id="kb-1", question="Claim 42")

    assert left == right


def test_in_memory_context_retriever_returns_best_match_first() -> None:
    retriever = InMemoryContextRetriever(
        records=[
            ContextRecord(
                record_id="record-1",
                content_id="content-1",
                embedding=[8.0, 5.0, 3.0, 2.0],
                content="Claim 42 duplicate billing",
            ),
            ContextRecord(
                record_id="record-2",
                content_id="content-2",
                embedding=[30.0, 24.0, 0.0, 5.0],
                content="Unrelated provider enrollment guidance",
            ),
        ]
    )

    results = retriever.retrieve(
        knowledge_base_id="kb-1",
        query_vector=[8.0, 5.0, 3.0, 2.0],
        limit=2,
        filters={},
    )

    assert [item.record_id for item in results] == ["record-1", "record-2"]