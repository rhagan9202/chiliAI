"""Tests for the embeddings service."""

from __future__ import annotations

import logging
from collections.abc import Sequence

import pytest
from prometheus_client import REGISTRY

from embeddings.adapters.protocols import (
    EmbedderProtocol,
    GraphEmbeddingProviderProtocol,
)
from embeddings.adapters.cache_in_memory import InMemoryLruEmbeddingCache
from embeddings.adapters.in_memory import InMemoryEmbedder
from embeddings.exceptions import EmbeddingConfigurationError, EmbeddingProviderError
from embeddings.models import (
    EmbeddingMetadata,
    EmbeddingRequest,
    EmbeddingResult,
    GraphEmbeddingBatch,
)
from embeddings.service import EmbeddingsService, create_embeddings_service
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


class _ExplodingEmbedder(EmbedderProtocol):
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        del request
        raise self._exc


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


def test_embeddings_service_maps_provider_value_error_to_configuration_error() -> None:
    event_bus = InMemoryEventBus()
    service = create_embeddings_service(
        _ExplodingEmbedder(ValueError("bad config")),
        event_bus=event_bus,
    )

    with pytest.raises(EmbeddingConfigurationError, match="bad config"):
        service.embed(
            EmbedRequest(
                submissions=[EmbedSubmission(content_id="content-1", content="Alpha")]
            )
        )

    assert event_bus.published_events == []


def test_embeddings_service_maps_provider_exception_to_provider_error() -> None:
    event_bus = InMemoryEventBus()
    service = create_embeddings_service(
        _ExplodingEmbedder(RuntimeError("backend down")),
        event_bus=event_bus,
    )

    with pytest.raises(EmbeddingProviderError, match="Failed to generate embeddings"):
        service.embed(
            EmbedRequest(
                submissions=[EmbedSubmission(content_id="content-1", content="Alpha")]
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


def test_embeddings_service_reports_missing_knowledge_base_for_optional_graph() -> None:
    event_bus = InMemoryEventBus()
    service = create_embeddings_service(
        InMemoryEmbedder(dimensions=4),
        event_bus=event_bus,
    )

    response = service.embed(
        EmbedRequest(
            include_graph_embeddings=True,
            submissions=[EmbedSubmission(content_id="content-1", content="Alpha")],
        )
    )

    assert [item.channel for item in response.items] == ["text"]
    assert response.graph_status is not None
    assert response.graph_status.provider_configured is False
    assert response.graph_status.missing_content_ids == ["content-1"]
    assert response.graph_status.failure_message is not None


def test_embeddings_service_requires_knowledge_base_for_required_graph() -> None:
    event_bus = InMemoryEventBus()
    service = create_embeddings_service(
        InMemoryEmbedder(dimensions=4),
        event_bus=event_bus,
    )

    with pytest.raises(EmbeddingProviderError, match="knowledge_base_id"):
        service.embed(
            EmbedRequest(
                include_graph_embeddings=True,
                require_graph_embeddings=True,
                submissions=[EmbedSubmission(content_id="content-1", content="Alpha")],
            )
        )


def test_embeddings_service_requires_graph_provider_when_required() -> None:
    event_bus = InMemoryEventBus()
    service = create_embeddings_service(
        InMemoryEmbedder(dimensions=4),
        event_bus=event_bus,
    )

    with pytest.raises(EmbeddingProviderError, match="graph provider"):
        service.embed(
            EmbedRequest(
                knowledge_base_id="kb-1",
                include_graph_embeddings=True,
                require_graph_embeddings=True,
                submissions=[EmbedSubmission(content_id="content-1", content="Alpha")],
            )
        )


def test_embeddings_service_omits_dimension_mismatch_when_graph_not_required() -> None:
    event_bus = InMemoryEventBus()
    service = create_embeddings_service(
        InMemoryEmbedder(dimensions=4),
        event_bus=event_bus,
        graph_embedding_provider=_GraphProvider(
            vectors={"content-1": [0.1, 0.2]},
            dimensions=2,
        ),
    )

    response = service.embed(
        EmbedRequest(
            knowledge_base_id="kb-1",
            include_graph_embeddings=True,
            graph_embedding_dimension=3,
            submissions=[EmbedSubmission(content_id="content-1", content="Alpha")],
        )
    )

    assert [item.channel for item in response.items] == ["text"]
    assert response.graph_status is not None
    assert response.graph_status.missing_content_ids == ["content-1"]


def test_embeddings_service_wraps_required_graph_provider_failure() -> None:
    event_bus = InMemoryEventBus()
    service = create_embeddings_service(
        InMemoryEmbedder(dimensions=4),
        event_bus=event_bus,
        graph_embedding_provider=_GraphProvider(
            vectors={},
            exc=RuntimeError("gnn unavailable"),
        ),
    )

    with pytest.raises(EmbeddingProviderError, match="Failed to generate graph"):
        service.embed(
            EmbedRequest(
                knowledge_base_id="kb-1",
                include_graph_embeddings=True,
                require_graph_embeddings=True,
                submissions=[EmbedSubmission(content_id="content-1", content="Alpha")],
            )
        )


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


class _CountingEmbedder(EmbedderProtocol):
    """Delegate to InMemoryEmbedder while recording every provider call."""

    def __init__(self, *, dimensions: int = 4) -> None:
        self._inner = InMemoryEmbedder(dimensions=dimensions)
        self.requests: list[EmbeddingRequest] = []

    def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        self.requests.append(request)
        return self._inner.embed(request)


def _cached_service(
    embedder: EmbedderProtocol,
    event_bus: InMemoryEventBus,
    *,
    graph_embedding_provider: GraphEmbeddingProviderProtocol | None = None,
) -> EmbeddingsService:
    return create_embeddings_service(
        embedder,
        event_bus=event_bus,
        graph_embedding_provider=graph_embedding_provider,
        cache=InMemoryLruEmbeddingCache(max_entries=16),
        cache_namespace="local:test-model:4",
    )


def test_embeddings_service_serves_repeated_content_from_cache() -> None:
    event_bus = InMemoryEventBus()
    embedder = _CountingEmbedder()
    service = _cached_service(embedder, event_bus)
    request = EmbedRequest(
        knowledge_base_id="kb-1",
        submissions=[EmbedSubmission(content_id="content-1", content="Alpha")],
    )

    first = service.embed(request)
    second = service.embed(request)

    assert len(embedder.requests) == 1
    assert second.items[0].vector == first.items[0].vector
    assert second.items[0].provider == "in-memory"
    assert second.model_name == first.model_name
    assert second.dimensions == first.dimensions
    assert second.request_id != first.request_id


def test_embeddings_service_embeds_only_cache_misses_in_order() -> None:
    event_bus = InMemoryEventBus()
    embedder = _CountingEmbedder()
    service = _cached_service(embedder, event_bus)

    service.embed(
        EmbedRequest(
            submissions=[EmbedSubmission(content_id="content-1", content="Alpha")]
        )
    )
    response = service.embed(
        EmbedRequest(
            submissions=[
                EmbedSubmission(content_id="content-1", content="Alpha"),
                EmbedSubmission(content_id="content-2", content="Beta"),
            ]
        )
    )

    assert [item.id for item in embedder.requests[-1].items] == ["content-2"]
    assert [item.content_id for item in response.items] == [
        "content-1",
        "content-2",
    ]


def test_embeddings_service_cache_key_includes_request_model_name() -> None:
    event_bus = InMemoryEventBus()
    embedder = _CountingEmbedder()
    service = _cached_service(embedder, event_bus)

    service.embed(
        EmbedRequest(
            model_name="model-a",
            submissions=[EmbedSubmission(content_id="content-1", content="Alpha")],
        )
    )
    service.embed(
        EmbedRequest(
            model_name="model-b",
            submissions=[EmbedSubmission(content_id="content-1", content="Alpha")],
        )
    )

    assert len(embedder.requests) == 2


def test_embeddings_service_without_cache_always_embeds() -> None:
    event_bus = InMemoryEventBus()
    embedder = _CountingEmbedder()
    service = create_embeddings_service(embedder, event_bus=event_bus)
    request = EmbedRequest(
        submissions=[EmbedSubmission(content_id="content-1", content="Alpha")]
    )

    service.embed(request)
    service.embed(request)

    assert len(embedder.requests) == 2


def test_embeddings_service_publishes_event_on_full_cache_hit() -> None:
    event_bus = InMemoryEventBus()
    service = _cached_service(_CountingEmbedder(), event_bus)
    request = EmbedRequest(
        knowledge_base_id="kb-1",
        submissions=[EmbedSubmission(content_id="content-1", content="Alpha")],
    )

    service.embed(request)
    service.embed(request)

    assert len(event_bus.published_events) == 2
    event = event_bus.published_events[-1]
    assert isinstance(event, EmbeddingsGeneratedEvent)
    assert event.batches[0].item_count == 1


def test_embeddings_service_graph_channel_covers_cached_submissions() -> None:
    event_bus = InMemoryEventBus()
    graph_provider = _GraphProvider(
        vectors={"content-1": [0.3, 0.4, 0.5], "content-2": [0.6, 0.7, 0.8]}
    )
    service = _cached_service(
        _CountingEmbedder(), event_bus, graph_embedding_provider=graph_provider
    )

    service.embed(
        EmbedRequest(
            knowledge_base_id="kb-1",
            submissions=[EmbedSubmission(content_id="content-1", content="Alpha")],
        )
    )
    service.embed(
        EmbedRequest(
            knowledge_base_id="kb-1",
            include_graph_embeddings=True,
            graph_embedding_dimension=3,
            submissions=[
                EmbedSubmission(content_id="content-1", content="Alpha"),
                EmbedSubmission(content_id="content-2", content="Beta"),
            ],
        )
    )

    assert graph_provider.calls[-1] == ("kb-1", ["content-1", "content-2"], 3)


class _UsageReportingEmbedder(EmbedderProtocol):
    """Embedder whose metadata carries provider-reported token usage."""

    def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        return EmbeddingResult(
            request_id=request.request_id,
            vectors={item.id: [0.1, 0.2] for item in request.items},
            metadata=EmbeddingMetadata(
                model_name="usage-model",
                dimensions=2,
                provider="usage-provider",
                total_tokens=42,
            ),
        )


def _sample_or_zero(name: str, labels: dict[str, str]) -> float:
    value = REGISTRY.get_sample_value(name, labels)
    return 0.0 if value is None else value


def test_embeddings_service_records_reported_token_usage() -> None:
    labels = {
        "provider": "usage-provider",
        "model": "usage-model",
        "knowledge_base_id": "kb-usage",
        "source": "reported",
    }
    before = _sample_or_zero("embedding_tokens_total", labels)
    service = create_embeddings_service(
        _UsageReportingEmbedder(), event_bus=InMemoryEventBus()
    )

    service.embed(
        EmbedRequest(
            knowledge_base_id="kb-usage",
            submissions=[EmbedSubmission(content_id="content-1", content="Alpha")],
        )
    )

    assert _sample_or_zero("embedding_tokens_total", labels) - before == 42.0


def test_embeddings_service_records_estimated_tokens_and_cache_results() -> None:
    hit_labels = {
        "provider": "in-memory",
        "model": "svc-usage-model",
        "cache_result": "hit",
    }
    miss_labels = {**hit_labels, "cache_result": "miss"}
    token_labels = {
        "provider": "in-memory",
        "model": "svc-usage-model",
        "knowledge_base_id": "none",
        "source": "estimated",
    }
    hits_before = _sample_or_zero("embedding_texts_total", hit_labels)
    misses_before = _sample_or_zero("embedding_texts_total", miss_labels)
    tokens_before = _sample_or_zero("embedding_tokens_total", token_labels)
    service = _cached_service(_CountingEmbedder(), InMemoryEventBus())
    request = EmbedRequest(
        model_name="svc-usage-model",
        submissions=[
            EmbedSubmission(content_id="content-1", content="Alpha beta!")
        ],
    )

    service.embed(request)
    service.embed(request)

    assert _sample_or_zero("embedding_texts_total", miss_labels) - misses_before == 1.0
    assert _sample_or_zero("embedding_texts_total", hit_labels) - hits_before == 1.0
    # "Alpha beta!" is 11 chars -> ceil(11 / 4) = 3 estimated tokens, misses only.
    assert _sample_or_zero("embedding_tokens_total", token_labels) - tokens_before == 3.0


def test_embeddings_service_logs_structured_usage_line(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = _cached_service(_CountingEmbedder(), InMemoryEventBus())
    request = EmbedRequest(
        knowledge_base_id="kb-log",
        submissions=[EmbedSubmission(content_id="content-1", content="Alpha")],
    )

    with caplog.at_level(logging.INFO, logger="embeddings.service"):
        service.embed(request)
        service.embed(request)

    usage_lines = [
        record.getMessage()
        for record in caplog.records
        if record.name == "embeddings.service"
        and record.getMessage().startswith("embedding usage:")
    ]
    assert len(usage_lines) == 2
    assert "cache_misses=1" in usage_lines[0]
    assert "token_source=estimated" in usage_lines[0]
    assert "cache_hits=1" in usage_lines[1]
    assert "token_source=cached" in usage_lines[1]
    assert "knowledge_base_id=kb-log" in usage_lines[1]
