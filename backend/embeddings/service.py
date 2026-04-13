"""Service entry point for embedding generation flows."""

from __future__ import annotations

from embeddings.adapters.protocols import EmbedderProtocol
from embeddings.exceptions import EmbeddingConfigurationError, EmbeddingProviderError
from embeddings.models import EmbeddingItem, EmbeddingRequest
from embeddings.service_models import EmbedRequest, EmbedResponse, EmbeddedItem
from events.protocols import EventBus
from events.types import EmbeddingGeneratedReference, EmbeddingsGeneratedEvent
from shared.utils import generate_id


class EmbeddingsService:
    """Coordinate request normalization, embedding generation, and event publication."""

    # TODO(production): Implement graph-metric embedding flow (architecture specifies
    # hybrid text + graph-metric embeddings). Add model routing: select embedder by
    # model_name when multiple providers are configured. Add embedding caching to
    # avoid re-embedding identical content. Add batch chunking to respect provider
    # token-per-batch and rate limits. Add retry with backoff for provider failures.
    # Add object store persistence of embedding results for reproducibility.

    def __init__(self, embedder: EmbedderProtocol, *, event_bus: EventBus) -> None:
        self._embedder = embedder
        self._event_bus = event_bus

    def embed(self, request: EmbedRequest) -> EmbedResponse:
        embedding_request = EmbeddingRequest(
            request_id=generate_id(),
            knowledge_base_id=request.knowledge_base_id,
            model_name=request.model_name,
            items=[
                EmbeddingItem(id=submission.content_id, content=submission.content)
                for submission in request.submissions
            ],
        )
        try:
            result = self._embedder.embed(embedding_request)
        except ValueError as exc:
            raise EmbeddingConfigurationError(str(exc)) from exc
        except Exception as exc:
            raise EmbeddingProviderError("Failed to generate embeddings.") from exc

        response = EmbedResponse(
            request_id=result.request_id,
            model_name=result.metadata.model_name,
            dimensions=result.metadata.dimensions,
            items=[
                EmbeddedItem(content_id=item.id, vector=result.vectors[item.id])
                for item in embedding_request.items
            ],
        )
        self._event_bus.publish(
            EmbeddingsGeneratedEvent(
                batches=[
                    EmbeddingGeneratedReference(
                        knowledge_base_id=request.knowledge_base_id,
                        request_id=response.request_id,
                        item_count=len(response.items),
                        dimensions=response.dimensions,
                        model_name=response.model_name,
                    )
                ]
            )
        )
        return response


def create_embeddings_service(
    embedder: EmbedderProtocol,
    *,
    event_bus: EventBus,
) -> EmbeddingsService:
    """Create the default embeddings service."""

    return EmbeddingsService(embedder, event_bus=event_bus)


__all__ = ["EmbeddingsService", "create_embeddings_service"]