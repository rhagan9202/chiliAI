"""Service entry point for embedding generation flows."""

from __future__ import annotations

from embeddings.adapters.protocols import (
    EmbedderProtocol,
    GraphEmbeddingProviderProtocol,
)
from embeddings.exceptions import EmbeddingConfigurationError, EmbeddingProviderError
from embeddings.models import EmbeddingItem, EmbeddingRequest, GraphEmbeddingStatus
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

    def __init__(
        self,
        embedder: EmbedderProtocol,
        *,
        event_bus: EventBus,
        graph_embedding_provider: GraphEmbeddingProviderProtocol | None = None,
    ) -> None:
        self._embedder = embedder
        self._event_bus = event_bus
        self._graph_embedding_provider = graph_embedding_provider

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

        expected_ids = {item.id for item in embedding_request.items}
        actual_ids = set(result.vectors)
        missing_ids = sorted(expected_ids - actual_ids)
        extra_ids = sorted(actual_ids - expected_ids)
        if missing_ids or extra_ids:
            details: list[str] = []
            if missing_ids:
                details.append(f"missing vectors for: {', '.join(missing_ids)}")
            if extra_ids:
                details.append(f"unexpected vectors for: {', '.join(extra_ids)}")
            raise EmbeddingProviderError(
                "Embedding provider returned incomplete batch results: "
                + "; ".join(details)
            )

        text_items = [
            EmbeddedItem(
                content_id=item.id,
                vector=result.vectors[item.id],
                channel="text",
                model_name=result.metadata.model_name,
                provider=result.metadata.provider,
                dimensions=result.metadata.dimensions,
            )
            for item in embedding_request.items
        ]
        graph_items, graph_status = self._embed_graph_channel(
            request,
            embedding_request,
        )
        response = EmbedResponse(
            request_id=result.request_id,
            model_name=result.metadata.model_name,
            dimensions=result.metadata.dimensions,
            items=[*text_items, *graph_items],
            graph_status=graph_status,
        )
        self._event_bus.publish(
            EmbeddingsGeneratedEvent(
                batches=[
                    EmbeddingGeneratedReference(
                        knowledge_base_id=request.knowledge_base_id,
                        request_id=response.request_id,
                        item_count=len(embedding_request.items),
                        dimensions=response.dimensions,
                        model_name=response.model_name,
                    )
                ]
            )
        )
        return response

    def _embed_graph_channel(
        self,
        request: EmbedRequest,
        embedding_request: EmbeddingRequest,
    ) -> tuple[list[EmbeddedItem], GraphEmbeddingStatus | None]:
        if not request.include_graph_embeddings:
            return [], None

        content_ids = [item.id for item in embedding_request.items]
        if request.knowledge_base_id is None:
            if request.require_graph_embeddings:
                raise EmbeddingProviderError(
                    "Graph embeddings require knowledge_base_id."
                )
            return [], GraphEmbeddingStatus(
                requested=True,
                provider_configured=self._graph_embedding_provider is not None,
                missing_content_ids=content_ids,
                failure_message="knowledge_base_id is required for graph embeddings.",
            )

        if self._graph_embedding_provider is None:
            if request.require_graph_embeddings:
                raise EmbeddingProviderError(
                    "Graph embeddings require a graph provider."
                )
            return [], GraphEmbeddingStatus(
                requested=True,
                provider_configured=False,
                missing_content_ids=content_ids,
            )

        try:
            batch = self._graph_embedding_provider.get_node_embeddings(
                knowledge_base_id=request.knowledge_base_id,
                content_ids=content_ids,
                dimensions=request.graph_embedding_dimension,
            )
        except Exception as exc:
            if request.require_graph_embeddings:
                raise EmbeddingProviderError(
                    "Failed to generate graph embeddings."
                ) from exc
            return [], GraphEmbeddingStatus(
                requested=True,
                provider_configured=True,
                missing_content_ids=content_ids,
                failure_message=str(exc),
            )

        graph_items: list[EmbeddedItem] = []
        missing_content_ids: list[str] = []
        for content_id in content_ids:
            vector = batch.vectors.get(content_id)
            if vector is None:
                missing_content_ids.append(content_id)
                continue
            if (
                batch.dimensions != request.graph_embedding_dimension
                or len(vector) != request.graph_embedding_dimension
            ):
                if request.require_graph_embeddings:
                    raise EmbeddingProviderError(
                        "Graph embedding dimension does not match requested "
                        "graph embedding dimension."
                    )
                missing_content_ids.append(content_id)
                continue
            graph_items.append(
                EmbeddedItem(
                    content_id=content_id,
                    vector=list(vector),
                    channel="graph",
                    model_name=batch.model_name,
                    provider=batch.provider,
                    dimensions=batch.dimensions,
                )
            )

        if request.require_graph_embeddings and missing_content_ids:
            raise EmbeddingProviderError(
                "Provider returned missing graph embeddings for: "
                + ", ".join(missing_content_ids)
            )

        return graph_items, GraphEmbeddingStatus(
            requested=True,
            provider_configured=True,
            missing_content_ids=missing_content_ids,
        )


def create_embeddings_service(
    embedder: EmbedderProtocol,
    *,
    event_bus: EventBus,
    graph_embedding_provider: GraphEmbeddingProviderProtocol | None = None,
) -> EmbeddingsService:
    """Create the default embeddings service."""

    return EmbeddingsService(
        embedder,
        event_bus=event_bus,
        graph_embedding_provider=graph_embedding_provider,
    )


__all__ = ["EmbeddingsService", "create_embeddings_service"]
