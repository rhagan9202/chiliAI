"""Tests for the embeddings service."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from embeddings.adapters.protocols import (
    EmbedderProtocol,
    GraphEmbeddingProviderProtocol,
)
from embeddings.adapters.in_memory import InMemoryEmbedder
from embeddings.exceptions import EmbeddingProviderError
from embeddings.models import (
    EmbeddingMetadata,
    EmbeddingRequest,
    EmbeddingResult,
    GraphEmbeddingBatch,
)
from embeddings.service import create_embeddings_service
from embeddings.service_models import EmbedRequest, EmbedSubmission
from events.adapters.in_memory import InMemoryEventBus
from events.types import EmbeddingsGeneratedEvent


class _PartialEmbedder(EmbedderProtocol):
    def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        return EmbeddingResult(
            request_id=request.request_id,
            vectors={request.items[0].id: [0.1, 0.2]},
            metadata=EmbeddingMetadata(
                model_name=request.model_name,
                dimensions=2,
                provider="partial",
            ),
        )


class _GraphProvider(GraphEmbeddingProviderProtocol):
    def __init__(
        self,
        *,
        vectors: dict[str, list[float]],
        dimensions: int = 3,
        exc: Exception | None = None,
    ) -> None:
        self._vectors = vectors
        self._dimensions = dimensions
        self._exc = exc
        self.calls: list[tuple[str, list[str], int]] = []

    def get_node_embeddings(
        self,
        *,
        knowledge_base_id: str,
        content_ids: Sequence[str],
        dimensions: int,
    ) -> GraphEmbeddingBatch:
        self.calls.append((knowledge_base_id, list(content_ids), dimensions))
        if self._exc is not None:
            raise self._exc
        return GraphEmbeddingBatch(
            vectors={key: list(value) for key, value in self._vectors.items()},
            model_name="gnn-spectral",
            provider="gnn",
            dimensions=self._dimensions,
        )


def test_embeddings_service_generates_vectors_and_publishes_event() -> None:
    event_bus = InMemoryEventBus()
    service = create_embeddings_service(InMemoryEmbedder(), event_bus=event_bus)

    response = service.embed(
        EmbedRequest(
            knowledge_base_id="kb-1",
            submissions=[
                EmbedSubmission(content_id="content-1", content="Claim 42 amount 100")
            ],
        )
    )

    assert response.model_name == "in-memory-embedder"
    assert response.dimensions == 384
    assert len(response.items) == 1
    assert isinstance(event_bus.published_events[-1], EmbeddingsGeneratedEvent)


def test_embeddings_service_rejects_partial_provider_results() -> None:
    event_bus = InMemoryEventBus()
    service = create_embeddings_service(_PartialEmbedder(), event_bus=event_bus)

    with pytest.raises(EmbeddingProviderError, match="missing vectors"):
        service.embed(
            EmbedRequest(
                knowledge_base_id="kb-1",
                submissions=[
                    EmbedSubmission(content_id="content-1", content="Alpha"),
                    EmbedSubmission(content_id="content-2", content="Beta"),
                ],
            )
        )

    assert event_bus.published_events == []


def test_embeddings_service_preserves_submission_order() -> None:
    event_bus = InMemoryEventBus()
    service = create_embeddings_service(InMemoryEmbedder(), event_bus=event_bus)

    response = service.embed(
        EmbedRequest(
            submissions=[
                EmbedSubmission(content_id="content-1", content="Alpha"),
                EmbedSubmission(content_id="content-2", content="Beta 123"),
            ]
        )
    )

    assert [item.content_id for item in response.items] == ["content-1", "content-2"]


def test_embeddings_service_adds_graph_channel_when_requested() -> None:
    event_bus = InMemoryEventBus()
    graph_provider = _GraphProvider(vectors={"content-1": [0.3, 0.4, 0.5]})
    service = create_embeddings_service(
        InMemoryEmbedder(dimensions=4),
        event_bus=event_bus,
        graph_embedding_provider=graph_provider,
    )

    response = service.embed(
        EmbedRequest(
            knowledge_base_id="kb-1",
            include_graph_embeddings=True,
            graph_embedding_dimension=3,
            submissions=[EmbedSubmission(content_id="content-1", content="Alpha")],
        )
    )

    assert [(item.content_id, item.channel) for item in response.items] == [
        ("content-1", "text"),
        ("content-1", "graph"),
    ]
    assert response.items[0].dimensions == 4
    assert response.items[1].dimensions == 3
    assert graph_provider.calls == [("kb-1", ["content-1"], 3)]
    assert response.graph_status is not None
    assert response.graph_status.missing_content_ids == []


def test_embeddings_service_omits_missing_graph_vectors_by_default() -> None:
    event_bus = InMemoryEventBus()
    service = create_embeddings_service(
        InMemoryEmbedder(dimensions=4),
        event_bus=event_bus,
        graph_embedding_provider=_GraphProvider(vectors={}),
    )

    response = service.embed(
        EmbedRequest(
            knowledge_base_id="kb-1",
            include_graph_embeddings=True,
            submissions=[EmbedSubmission(content_id="content-1", content="Alpha")],
        )
    )

    assert [item.channel for item in response.items] == ["text"]
    assert response.graph_status is not None
    assert response.graph_status.missing_content_ids == ["content-1"]


def test_embeddings_service_requires_graph_vectors_when_requested() -> None:
    event_bus = InMemoryEventBus()
    service = create_embeddings_service(
        InMemoryEmbedder(dimensions=4),
        event_bus=event_bus,
        graph_embedding_provider=_GraphProvider(vectors={}),
    )

    with pytest.raises(EmbeddingProviderError, match="missing graph embeddings"):
        service.embed(
            EmbedRequest(
                knowledge_base_id="kb-1",
                include_graph_embeddings=True,
                require_graph_embeddings=True,
                submissions=[EmbedSubmission(content_id="content-1", content="Alpha")],
            )
        )


def test_embeddings_service_requires_graph_channel_even_when_not_included() -> None:
    event_bus = InMemoryEventBus()
    graph_provider = _GraphProvider(vectors={"content-1": [0.3, 0.4, 0.5]})
    service = create_embeddings_service(
        InMemoryEmbedder(dimensions=4),
        event_bus=event_bus,
        graph_embedding_provider=graph_provider,
    )

    response = service.embed(
        EmbedRequest(
            knowledge_base_id="kb-1",
            include_graph_embeddings=False,
            require_graph_embeddings=True,
            graph_embedding_dimension=3,
            submissions=[EmbedSubmission(content_id="content-1", content="Alpha")],
        )
    )

    assert [(item.content_id, item.channel) for item in response.items] == [
        ("content-1", "text"),
        ("content-1", "graph"),
    ]
    assert graph_provider.calls == [("kb-1", ["content-1"], 3)]
    assert response.graph_status is not None
    assert response.graph_status.missing_content_ids == []


def test_embeddings_service_records_graph_provider_failure_when_not_required() -> None:
    event_bus = InMemoryEventBus()
    service = create_embeddings_service(
        InMemoryEmbedder(dimensions=4),
        event_bus=event_bus,
        graph_embedding_provider=_GraphProvider(
            vectors={},
            exc=RuntimeError("gnn unavailable"),
        ),
    )

    response = service.embed(
        EmbedRequest(
            knowledge_base_id="kb-1",
            include_graph_embeddings=True,
            submissions=[EmbedSubmission(content_id="content-1", content="Alpha")],
        )
    )

    assert [item.channel for item in response.items] == ["text"]
    assert response.graph_status is not None
    assert response.graph_status.failure_message == "gnn unavailable"


def test_embeddings_service_rejects_graph_dimension_mismatch_when_required() -> None:
    event_bus = InMemoryEventBus()
    service = create_embeddings_service(
        InMemoryEmbedder(dimensions=4),
        event_bus=event_bus,
        graph_embedding_provider=_GraphProvider(
            vectors={"content-1": [0.1, 0.2]},
            dimensions=2,
        ),
    )

    with pytest.raises(EmbeddingProviderError, match="graph embedding dimension"):
        service.embed(
            EmbedRequest(
                knowledge_base_id="kb-1",
                include_graph_embeddings=True,
                require_graph_embeddings=True,
                graph_embedding_dimension=3,
                submissions=[EmbedSubmission(content_id="content-1", content="Alpha")],
            )
        )
