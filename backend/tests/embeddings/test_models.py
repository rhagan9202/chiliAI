"""Tests for embeddings module models."""

from __future__ import annotations

import pytest

from embeddings.models import (
    CachedEmbedding,
    EmbeddingItem,
    EmbeddingMetadata,
    EmbeddingRequest,
    EmbeddingResult,
    EmbeddingVector,
    GraphEmbeddingBatch,
    GraphEmbeddingStatus,
    build_embedding_cache_key,
)
from embeddings.service_models import EmbedRequest, EmbedSubmission, EmbeddedItem


def test_embedding_item_rejects_empty_content() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        EmbeddingItem(id="item-1", content=" ")


def test_embedding_request_requires_items() -> None:
    with pytest.raises(ValueError, match="at least one item"):
        EmbeddingRequest(request_id="request-1", model_name="test-model", items=[])


def test_embed_request_requires_submissions() -> None:
    with pytest.raises(ValueError, match="at least one submission"):
        EmbedRequest(submissions=[])


def test_embed_submission_accepts_valid_content() -> None:
    submission = EmbedSubmission(content_id="content-1", content="Policy paragraph")

    assert submission.content_id == "content-1"


def test_embedding_vector_requires_non_empty_vector() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        EmbeddingVector(
            content_id="entity-1",
            channel="text",
            vector=[],
            model_name="model",
            provider="local",
            dimensions=3,
        )


def test_embedding_vector_requires_matching_dimensions() -> None:
    with pytest.raises(ValueError, match="length must match"):
        EmbeddingVector(
            content_id="entity-1",
            channel="text",
            vector=[0.1, 0.2],
            model_name="model",
            provider="local",
            dimensions=3,
        )


def test_embedding_result_exposes_text_vectors_for_compatibility() -> None:
    result = EmbeddingResult(
        request_id="request-1",
        vectors={"entity-1": [0.1, 0.2]},
        metadata=EmbeddingMetadata(model_name="text-model", dimensions=2, provider="local"),
    )

    assert result.vectors == {"entity-1": [0.1, 0.2]}
    assert [(item.content_id, item.channel) for item in result.items] == [
        ("entity-1", "text")
    ]


def test_embedding_result_preserves_graph_channel_items() -> None:
    result = EmbeddingResult(
        request_id="request-1",
        vectors={"entity-1": [0.1, 0.2]},
        metadata=EmbeddingMetadata(model_name="text-model", dimensions=2, provider="local"),
        items=[
            EmbeddingVector(
                content_id="entity-1",
                channel="text",
                vector=[0.1, 0.2],
                model_name="text-model",
                provider="local",
                dimensions=2,
            ),
            EmbeddingVector(
                content_id="entity-1",
                channel="graph",
                vector=[0.7, 0.3, 0.0],
                model_name="gnn-spectral",
                provider="gnn",
                dimensions=3,
            ),
        ],
        graph_status=GraphEmbeddingStatus(
            requested=True,
            provider_configured=True,
            missing_content_ids=[],
            failure_message=None,
        ),
    )

    assert result.vectors == {"entity-1": [0.1, 0.2]}
    assert [item.channel for item in result.items] == ["text", "graph"]
    assert result.graph_status is not None
    assert result.graph_status.requested is True


def test_embedding_result_requires_text_vector() -> None:
    with pytest.raises(ValueError, match="at least one text vector"):
        EmbeddingResult(
            request_id="request-1",
            vectors={},
            metadata=EmbeddingMetadata(
                model_name="graph-model",
                dimensions=2,
                provider="gnn",
            ),
            items=[
                EmbeddingVector(
                    content_id="entity-1",
                    channel="graph",
                    vector=[0.1, 0.2],
                    model_name="graph-model",
                    provider="gnn",
                    dimensions=2,
                )
            ],
        )


def test_graph_embedding_batch_requires_positive_dimensions() -> None:
    with pytest.raises(ValueError, match="greater than 0"):
        GraphEmbeddingBatch(
            vectors={"entity-1": [1.0]},
            model_name="gnn",
            provider="gnn",
            dimensions=0,
        )


def test_graph_embedding_batch_requires_vectors_match_dimensions() -> None:
    with pytest.raises(ValueError, match="must match dimensions"):
        GraphEmbeddingBatch(
            vectors={"entity-1": [1.0, 2.0]},
            model_name="gnn",
            provider="gnn",
            dimensions=3,
        )


def test_embed_request_graph_flags_default_to_text_only() -> None:
    request = EmbedRequest(
        submissions=[EmbedSubmission(content_id="entity-1", content="Alpha")]
    )

    assert request.include_graph_embeddings is False
    assert request.require_graph_embeddings is False
    assert request.graph_embedding_dimension == 8


def test_embedded_item_defaults_to_text_channel() -> None:
    item = EmbeddedItem(content_id="entity-1", vector=[0.1])

    assert item.channel == "text"
    assert item.dimensions == 1


def test_build_embedding_cache_key_is_deterministic() -> None:
    first = build_embedding_cache_key(
        namespace="local:model-a:4", model_name="m", content="Alpha"
    )
    second = build_embedding_cache_key(
        namespace="local:model-a:4", model_name="m", content="Alpha"
    )

    assert first == second
    assert len(first) == 64  # sha256 hex digest


def test_build_embedding_cache_key_varies_by_all_parts() -> None:
    base = build_embedding_cache_key(
        namespace="local:model-a:4", model_name="m", content="Alpha"
    )

    assert base != build_embedding_cache_key(
        namespace="local:model-a:8", model_name="m", content="Alpha"
    )
    assert base != build_embedding_cache_key(
        namespace="local:model-a:4", model_name="other", content="Alpha"
    )
    assert base != build_embedding_cache_key(
        namespace="local:model-a:4", model_name="m", content="Beta"
    )


def test_cached_embedding_requires_matching_dimensions() -> None:
    entry = CachedEmbedding(
        vector=[0.1, 0.2], model_name="m", provider="local", dimensions=2
    )
    assert entry.dimensions == 2

    with pytest.raises(ValueError, match="dimensions"):
        CachedEmbedding(
            vector=[0.1, 0.2], model_name="m", provider="local", dimensions=3
        )


def test_cached_embedding_rejects_empty_vector() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        CachedEmbedding(vector=[], model_name="m", provider="local", dimensions=1)
