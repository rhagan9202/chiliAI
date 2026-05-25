"""Tests for Flow 2 — graph-metric persistence.

Flow 2 runs at the end of ``handle_graph_updated_for_analytics`` regardless of
whether any entity-level analytics are executed.  We drive it via the PUBLIC
handler with an EMPTY object store so that ``_resolve_upserted_entity_ids``
returns an empty list for every document (skipping GNN/risk/explainability),
while ``_persist_graph_metrics_for_event`` still executes unconditionally.
"""

from __future__ import annotations

from agent.coordinator import handle_graph_updated_for_analytics
from analytics.explainability.adapters.in_memory import (
    InMemoryExplainabilityContextSource,
)
from analytics.explainability.service import ExplainabilityService, create_explainability_service
from analytics.gnn.adapters.in_memory import InMemoryGraphSnapshotSource
from analytics.gnn.service import GnnService, create_gnn_service
from analytics.metrics.adapters.in_memory import InMemoryEntityMetricRepository
from analytics.metrics.models import EntityMetricSample, EntityMetricValue
from analytics.metrics.throttle import MetricsRecomputeThrottle
from analytics.risk.adapters.in_memory import InMemoryRiskSignalSource
from analytics.risk.service import RiskService, create_risk_service
from events.adapters.in_memory import InMemoryEventBus
from events.types import GraphUpdatedDocumentReference, GraphUpdatedEvent
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.service import GraphService, create_graph_service
from shared.types import Entity
from storage.adapters.in_memory import InMemoryObjectStore


class _CountingMetricRepository:
    """An EntityMetricRepository spy that counts record_metrics calls."""

    def __init__(self) -> None:
        self._inner = InMemoryEntityMetricRepository()
        self.record_calls = 0

    def record_metrics(self, samples: list[EntityMetricSample]) -> int:
        self.record_calls += 1
        return self._inner.record_metrics(samples)

    def load_current_metrics(
        self, *, knowledge_base_id: str, entity_id: str
    ) -> list[EntityMetricValue]:
        return self._inner.load_current_metrics(
            knowledge_base_id=knowledge_base_id, entity_id=entity_id
        )


def _build_graph_service(event_bus: InMemoryEventBus, entity_count: int) -> GraphService:
    service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=InMemoryObjectStore(),
        event_bus=event_bus,
    )
    service.upsert_records_graph(
        "kb-1",
        [
            Entity(id=f"claim:{index}", type="claim", properties={})
            for index in range(entity_count)
        ],
        [],
    )
    return service


def _build_gnn_service(event_bus: InMemoryEventBus) -> GnnService:
    return create_gnn_service(InMemoryGraphSnapshotSource(), event_bus=event_bus)


def _build_risk_service(event_bus: InMemoryEventBus) -> RiskService:
    return create_risk_service(InMemoryRiskSignalSource(), event_bus=event_bus)


def _build_explainability_service(event_bus: InMemoryEventBus) -> ExplainabilityService:
    return create_explainability_service(
        InMemoryExplainabilityContextSource(), event_bus=event_bus
    )


def _event() -> GraphUpdatedEvent:
    return GraphUpdatedEvent(
        correlation_id="corr-metrics",
        documents=[
            GraphUpdatedDocumentReference(
                knowledge_base_id="kb-1",
                source_document_id="src-1",
                parsed_document_id="parsed-1",
                extraction_result_id="extract-1",
                validation_report_id="valid-1",
                upserted_entity_count=3,
                upserted_relationship_count=0,
            )
        ],
    )


def test_flow2_persists_graph_metrics() -> None:
    event_bus = InMemoryEventBus()
    graph_service = _build_graph_service(event_bus, entity_count=3)
    gnn_service = _build_gnn_service(event_bus)
    risk_service = _build_risk_service(event_bus)
    explainability_service = _build_explainability_service(event_bus)
    repo = InMemoryEntityMetricRepository()
    throttle = MetricsRecomputeThrottle(min_interval_seconds=300)

    # Empty object store => _resolve_upserted_entity_ids returns [] for each
    # document so the GNN/risk/explainability path is skipped via `continue`.
    # _persist_graph_metrics_for_event still runs unconditionally at end of handler.
    handle_graph_updated_for_analytics(
        _event(),
        gnn_service=gnn_service,
        risk_service=risk_service,
        explainability_service=explainability_service,
        graph_service=graph_service,
        event_bus=event_bus,
        object_store=InMemoryObjectStore(),
        entity_metric_repository=repo,
        metrics_throttle=throttle,
    )

    current = repo.load_current_metrics(
        knowledge_base_id="kb-1", entity_id="__graph__"
    )
    by_metric = {value.metric_name: value.value for value in current}
    assert by_metric["entity_count"] == 3.0
    assert "relationship_count" in by_metric
    assert "avg_degree" in by_metric


def test_flow2_is_throttled_per_kb() -> None:
    event_bus = InMemoryEventBus()
    graph_service = _build_graph_service(event_bus, entity_count=3)
    gnn_service = _build_gnn_service(event_bus)
    risk_service = _build_risk_service(event_bus)
    explainability_service = _build_explainability_service(event_bus)
    repo = _CountingMetricRepository()
    throttle = MetricsRecomputeThrottle(min_interval_seconds=300)

    # First call populates the repo; second call is throttled (same throttle
    # instance tracks the last-recompute timestamp for "kb-1", so should_recompute
    # returns False and record_metrics is never called a second time).
    handle_graph_updated_for_analytics(
        _event(),
        gnn_service=gnn_service,
        risk_service=risk_service,
        explainability_service=explainability_service,
        graph_service=graph_service,
        event_bus=event_bus,
        object_store=InMemoryObjectStore(),
        entity_metric_repository=repo,
        metrics_throttle=throttle,
    )
    handle_graph_updated_for_analytics(
        _event(),
        gnn_service=gnn_service,
        risk_service=risk_service,
        explainability_service=explainability_service,
        graph_service=graph_service,
        event_bus=event_bus,
        object_store=InMemoryObjectStore(),
        entity_metric_repository=repo,
        metrics_throttle=throttle,
    )

    # The spy must show exactly one persist call: the throttle suppressed the second.
    assert repo.record_calls == 1

    # Snapshot still contains all three metrics from the first (un-throttled) call.
    current = repo.load_current_metrics(
        knowledge_base_id="kb-1", entity_id="__graph__"
    )
    assert len(current) == 3  # one row per metric
