"""Tests for the sentence-transformers embedding adapter."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import cast

import pytest

from config.schema import EmbeddingsConfig
from embeddings.adapters.sentence_transformers_adapter import (
    SentenceTransformerModelProtocol,
    SentenceTransformersEmbedder,
)
from embeddings.exceptions import EmbeddingProviderError
from embeddings.models import EmbeddingItem, EmbeddingRequest


class FakeSentenceTransformer:
    """Deterministic fake model for offline adapter tests."""

    def __init__(
        self,
        vector_size: int,
        *,
        zero_texts: set[str] | None = None,
    ) -> None:
        self._vector_size = vector_size
        self._zero_texts = zero_texts or set()
        self.calls: list[tuple[list[str], int]] = []

    def encode(
        self,
        sentences: Sequence[str],
        *,
        batch_size: int,
        show_progress_bar: bool,
        normalize_embeddings: bool,
    ) -> list[list[float]]:
        del show_progress_bar
        del normalize_embeddings

        materialized_sentences = list(sentences)
        self.calls.append((materialized_sentences, batch_size))
        return [self._vector_for(text) for text in materialized_sentences]

    def _vector_for(self, text: str) -> list[float]:
        if text in self._zero_texts:
            return [0.0] * self._vector_size

        base_vector = [
            float(len(text) + 1),
            float(sum(1 for char in text if char.isalpha()) + 1),
            float(sum(1 for char in text if char.isdigit()) + len(text.split()) + 1),
            float((sum(ord(char) for char in text) % 17) + 1),
        ]
        return base_vector[: self._vector_size]


def test_sentence_transformers_embedder_batches_and_normalizes_vectors() -> None:
    config = EmbeddingsConfig(
        provider="sentence_transformers",
        model="all-MiniLM-L6-v2",
        dimensions=3,
        batch_size=2,
    )
    model = FakeSentenceTransformer(vector_size=3)
    embedder = SentenceTransformersEmbedder(config, model=model)

    result = embedder.embed(
        EmbeddingRequest(
            request_id="request-1",
            model_name="ignored-at-runtime",
            items=[
                EmbeddingItem(id="item-1", content="Alpha"),
                EmbeddingItem(id="item-2", content="Beta 123"),
                EmbeddingItem(id="item-3", content="Gamma"),
                EmbeddingItem(id="item-4", content="Delta 456"),
                EmbeddingItem(id="item-5", content="Epsilon"),
            ],
        )
    )

    assert result.metadata.provider == "sentence-transformers"
    assert result.metadata.model_name == config.model
    assert result.metadata.dimensions == config.dimensions
    assert list(result.vectors) == [
        "item-1",
        "item-2",
        "item-3",
        "item-4",
        "item-5",
    ]
    assert [len(call[0]) for call in model.calls] == [2, 2, 1]
    assert [call[1] for call in model.calls] == [2, 2, 2]

    for vector in result.vectors.values():
        assert len(vector) == config.dimensions
        assert any(component != 0.0 for component in vector)
        assert math.isclose(
            math.sqrt(sum(component * component for component in vector)),
            1.0,
            rel_tol=1e-9,
        )


def test_sentence_transformers_embedder_loads_model_once() -> None:
    config = EmbeddingsConfig(
        provider="sentence_transformers",
        model="all-MiniLM-L6-v2",
        dimensions=3,
        batch_size=4,
    )
    model = FakeSentenceTransformer(vector_size=3)
    loader_calls: list[str] = []

    def load_model(model_name: str) -> SentenceTransformerModelProtocol:
        loader_calls.append(model_name)
        return cast(SentenceTransformerModelProtocol, model)

    embedder = SentenceTransformersEmbedder(config, model_loader=load_model)

    first_request = EmbeddingRequest(
        request_id="request-1",
        model_name="client-requested-model",
        items=[EmbeddingItem(id="item-1", content="Alpha")],
    )
    second_request = EmbeddingRequest(
        request_id="request-2",
        model_name="client-requested-model",
        items=[EmbeddingItem(id="item-2", content="Beta")],
    )

    embedder.embed(first_request)
    embedder.embed(second_request)

    assert loader_calls == [config.model]
    assert len(model.calls) == 2


def test_sentence_transformers_embedder_rejects_dimension_mismatch() -> None:
    config = EmbeddingsConfig(
        provider="sentence_transformers",
        model="all-MiniLM-L6-v2",
        dimensions=3,
        batch_size=2,
    )
    embedder = SentenceTransformersEmbedder(
        config,
        model=FakeSentenceTransformer(vector_size=2),
    )

    with pytest.raises(EmbeddingProviderError, match="Expected 3, received 2"):
        embedder.embed(
            EmbeddingRequest(
                request_id="request-1",
                model_name="ignored",
                items=[EmbeddingItem(id="item-1", content="Alpha")],
            )
        )


def test_sentence_transformers_embedder_rejects_zero_vectors() -> None:
    config = EmbeddingsConfig(
        provider="sentence_transformers",
        model="all-MiniLM-L6-v2",
        dimensions=3,
        batch_size=2,
    )
    embedder = SentenceTransformersEmbedder(
        config,
        model=FakeSentenceTransformer(vector_size=3, zero_texts={"zero"}),
    )

    with pytest.raises(EmbeddingProviderError, match="zero vector"):
        embedder.embed(
            EmbeddingRequest(
                request_id="request-1",
                model_name="ignored",
                items=[EmbeddingItem(id="item-1", content="zero")],
            )
        )