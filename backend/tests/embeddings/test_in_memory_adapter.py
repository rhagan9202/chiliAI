"""Tests for the in-memory embedding adapter."""

from __future__ import annotations

from embeddings.adapters.in_memory import InMemoryEmbedder
from embeddings.models import EmbeddingItem, EmbeddingRequest


def test_in_memory_embedder_returns_fixed_dimension_vectors() -> None:
    embedder = InMemoryEmbedder()

    result = embedder.embed(
        EmbeddingRequest(
            request_id="request-1",
            model_name="test-model",
            items=[EmbeddingItem(id="item-1", content="Alpha 123")],
        )
    )

    assert result.metadata.dimensions == 4
    assert len(result.vectors["item-1"]) == 4


def test_in_memory_embedder_differs_for_distinct_content() -> None:
    embedder = InMemoryEmbedder()

    result = embedder.embed(
        EmbeddingRequest(
            request_id="request-1",
            model_name="test-model",
            items=[
                EmbeddingItem(id="item-1", content="Alpha"),
                EmbeddingItem(id="item-2", content="Alpha 123"),
            ],
        )
    )

    assert result.vectors["item-1"] != result.vectors["item-2"]