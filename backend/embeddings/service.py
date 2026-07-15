"""Service entry point for embedding generation flows."""

from __future__ import annotations

import logging

from embeddings.adapters.protocols import (
    EmbedderProtocol,
    EmbeddingCacheProtocol,
    GraphEmbeddingProviderProtocol,
)
from embeddings.exceptions import EmbeddingConfigurationError, EmbeddingProviderError
from embeddings.metrics import TokenSource, estimate_tokens, record_embedding_usage
from embeddings.models import (
    CachedEmbedding,
    EmbeddingItem,
    EmbeddingMetadata,
    EmbeddingRequest,
    GraphEmbeddingStatus,
    build_embedding_cache_key,
)
from embeddings.service_models import (
    EmbedRequest,
    EmbedResponse,
    EmbedSubmission,
    EmbeddedItem,
)
from events.protocols import EventBus
from events.types import EmbeddingGeneratedReference, EmbeddingsGeneratedEvent
from shared.utils import generate_id

logger = logging.getLogger(__name__)


class EmbeddingsService:
    """Coordinate request normalization, caching, generation, and events."""

    # Roadmap (BL-045): object-store persistence of embedding results, model
    # routing across multiple configured providers, and a durable per-request
    # usage ledger. Batch chunking and provider retry live in the adapters.

    def __init__(
        self,
        embedder: EmbedderProtocol,
        *,
        event_bus: EventBus,
        graph_embedding_provider: GraphEmbeddingProviderProtocol | None = None,
        cache: EmbeddingCacheProtocol | None = None,
        cache_namespace: str = "",
    ) -> None:
        self._embedder = embedder
        self._event_bus = event_bus
        self._graph_embedding_provider = graph_embedding_provider
        self._cache = cache
        self._cache_namespace = cache_namespace

    def embed(self, request: EmbedRequest) -> EmbedResponse:
        request_id = generate_id()
        cached_items, miss_submissions = self._partition_cached(request)

        fresh_items: dict[str, EmbeddedItem] = {}
        result_metadata: EmbeddingMetadata | None = None
        if miss_submissions:
            result_metadata, fresh_items = self._embed_misses(
                request, request_id, miss_submissions
            )

        text_items = [
            fresh_items[submission.content_id]
            if submission.content_id in fresh_items
            else cached_items[submission.content_id]
            for submission in request.submissions
        ]
        model_name, dimensions = _response_identity(
            request, result_metadata, text_items
        )
        graph_items, graph_status = self._embed_graph_channel(
            request,
            [submission.content_id for submission in request.submissions],
        )
        response = EmbedResponse(
            request_id=request_id,
            model_name=model_name,
            dimensions=dimensions,
            items=[*text_items, *graph_items],
            graph_status=graph_status,
        )
        self._event_bus.publish(
            EmbeddingsGeneratedEvent(
                batches=[
                    EmbeddingGeneratedReference(
                        knowledge_base_id=request.knowledge_base_id,
                        request_id=response.request_id,
                        item_count=len(request.submissions),
                        dimensions=response.dimensions,
                        model_name=response.model_name,
                    )
                ]
            )
        )
        self._record_usage(
            request,
            result_metadata,
            provider=_usage_provider(result_metadata, text_items),
            model_name=model_name,
            cache_hits=len(cached_items),
            miss_submissions=miss_submissions,
        )
        return response

    def _cache_key(self, model_name: str, content: str) -> str:
        return build_embedding_cache_key(
            namespace=self._cache_namespace,
            model_name=model_name,
            content=content,
        )

    def _partition_cached(
        self, request: EmbedRequest
    ) -> tuple[dict[str, EmbeddedItem], list[EmbedSubmission]]:
        """Split submissions into cached text items and cache misses."""

        if self._cache is None:
            return {}, list(request.submissions)

        cached: dict[str, EmbeddedItem] = {}
        misses: list[EmbedSubmission] = []
        for submission in request.submissions:
            entry = self._cache.get(
                self._cache_key(request.model_name, submission.content)
            )
            if entry is None:
                misses.append(submission)
                continue
            cached[submission.content_id] = EmbeddedItem(
                content_id=submission.content_id,
                vector=list(entry.vector),
                channel="text",
                model_name=entry.model_name,
                provider=entry.provider,
                dimensions=entry.dimensions,
            )
        return cached, misses

    def _embed_misses(
        self,
        request: EmbedRequest,
        request_id: str,
        miss_submissions: list[EmbedSubmission],
    ) -> tuple[EmbeddingMetadata, dict[str, EmbeddedItem]]:
        """Embed cache misses, validate completeness, and back-fill the cache."""

        embedding_request = EmbeddingRequest(
            request_id=request_id,
            knowledge_base_id=request.knowledge_base_id,
            model_name=request.model_name,
            items=[
                EmbeddingItem(id=submission.content_id, content=submission.content)
                for submission in miss_submissions
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

        fresh_items: dict[str, EmbeddedItem] = {}
        for submission in miss_submissions:
            vector = result.vectors[submission.content_id]
            fresh_items[submission.content_id] = EmbeddedItem(
                content_id=submission.content_id,
                vector=vector,
                channel="text",
                model_name=result.metadata.model_name,
                provider=result.metadata.provider,
                dimensions=result.metadata.dimensions,
            )
            if self._cache is not None:
                self._cache.set(
                    self._cache_key(request.model_name, submission.content),
                    CachedEmbedding(
                        vector=list(vector),
                        model_name=result.metadata.model_name,
                        provider=result.metadata.provider,
                        dimensions=result.metadata.dimensions,
                    ),
                )
        return result.metadata, fresh_items

    def _embed_graph_channel(
        self,
        request: EmbedRequest,
        content_ids: list[str],
    ) -> tuple[list[EmbeddedItem], GraphEmbeddingStatus | None]:
        if not request.include_graph_embeddings and not request.require_graph_embeddings:
            return [], None

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

    def _record_usage(
        self,
        request: EmbedRequest,
        result_metadata: EmbeddingMetadata | None,
        *,
        provider: str,
        model_name: str,
        cache_hits: int,
        miss_submissions: list[EmbedSubmission],
    ) -> None:
        """Record counters and a structured log line for one embed() call."""

        token_source: TokenSource
        if result_metadata is not None and result_metadata.total_tokens is not None:
            tokens = result_metadata.total_tokens
            token_source = "reported"
        elif miss_submissions:
            tokens = sum(
                estimate_tokens(submission.content)
                for submission in miss_submissions
            )
            token_source = "estimated"
        else:
            tokens = 0
            token_source = "cached"
        record_embedding_usage(
            provider=provider,
            model_name=model_name,
            knowledge_base_id=request.knowledge_base_id,
            cache_hits=cache_hits,
            cache_misses=len(miss_submissions),
            tokens=tokens,
            token_source=token_source,
        )
        logger.info(
            "embedding usage: provider=%s model=%s knowledge_base_id=%s "
            "texts=%d cache_hits=%d cache_misses=%d tokens=%d token_source=%s",
            provider,
            model_name,
            request.knowledge_base_id or "none",
            len(request.submissions),
            cache_hits,
            len(miss_submissions),
            tokens,
            token_source,
        )


def _response_identity(
    request: EmbedRequest,
    result_metadata: EmbeddingMetadata | None,
    text_items: list[EmbeddedItem],
) -> tuple[str, int]:
    """Resolve the response model name and dimensions for hit/miss mixes."""

    if result_metadata is not None:
        return result_metadata.model_name, result_metadata.dimensions
    first = text_items[0]
    return (
        first.model_name or request.model_name,
        first.dimensions or len(first.vector),
    )


def _usage_provider(
    result_metadata: EmbeddingMetadata | None,
    text_items: list[EmbeddedItem],
) -> str:
    """Resolve the provider label for usage recording."""

    if result_metadata is not None:
        return result_metadata.provider
    return text_items[0].provider or "unknown"


def create_embeddings_service(
    embedder: EmbedderProtocol,
    *,
    event_bus: EventBus,
    graph_embedding_provider: GraphEmbeddingProviderProtocol | None = None,
    cache: EmbeddingCacheProtocol | None = None,
    cache_namespace: str = "",
) -> EmbeddingsService:
    """Create the default embeddings service."""

    return EmbeddingsService(
        embedder,
        event_bus=event_bus,
        graph_embedding_provider=graph_embedding_provider,
        cache=cache,
        cache_namespace=cache_namespace,
    )


__all__ = ["EmbeddingsService", "create_embeddings_service"]
