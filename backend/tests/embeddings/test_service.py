"""Tests for the embeddings service."""

from __future__ import annotations

import pytest

from embeddings.adapters.protocols import EmbedderProtocol
from embeddings.adapters.in_memory import InMemoryEmbedder
from embeddings.exceptions import EmbeddingProviderError
from embeddings.models import EmbeddingMetadata, EmbeddingRequest, EmbeddingResult
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
