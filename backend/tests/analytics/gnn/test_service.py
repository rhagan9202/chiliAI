"""Tests for the gnn service."""

from __future__ import annotations

import pytest

from analytics.gnn.adapters.in_memory import InMemoryGraphSnapshotSource
from analytics.gnn.adapters.protocols import GraphSnapshotSourceProtocol
from analytics.gnn.exceptions import GnnConfigurationError, GnnInsufficientGraphError, GnnSourceError
from analytics.gnn.models import (
    ClusterSummary,
    GraphEdgeSignal,
    GraphNodeSignal,
    GraphSnapshot,
)
from analytics.gnn.service import create_gnn_service
from analytics.gnn.service_models import GnnAnalysisRequest, GnnClusterRequest
from events.adapters.in_memory import InMemoryEventBus
from events.types import GnnAnalyzedEvent


def test_gnn_service_scores_nodes_predicts_links_and_publishes_event() -> None:
    event_bus = InMemoryEventBus()
    service = create_gnn_service(
        InMemoryGraphSnapshotSource(
            snapshots=[
                GraphSnapshot(
                    knowledge_base_id="kb-1",
                    nodes=[
                        GraphNodeSignal(entity_id="provider-1", feature_values=[1.0, 0.0, 1.0]),
                        GraphNodeSignal(entity_id="provider-2", feature_values=[1.0, 0.0, 0.9]),
                        GraphNodeSignal(entity_id="provider-3", feature_values=[0.0, 1.0, 0.0]),
                    ],
                    edges=[GraphEdgeSignal(source_id="provider-1", target_id="provider-3", weight=1.0)],
                )
            ]
        ),
        event_bus=event_bus,
    )

    response = service.analyze(GnnAnalysisRequest(knowledge_base_id="kb-1", similarity_threshold=0.95))

    assert response.node_count == 3
    assert len(response.predicted_links) == 1
    assert response.predicted_links[0].source_id == "provider-1"
    assert isinstance(event_bus.published_events[-1], GnnAnalyzedEvent)


def test_gnn_service_requires_at_least_two_nodes() -> None:
    event_bus = InMemoryEventBus()
    service = create_gnn_service(
        InMemoryGraphSnapshotSource(
            snapshots=[
                GraphSnapshot(
                    knowledge_base_id="kb-1",
                    nodes=[GraphNodeSignal(entity_id="provider-1", feature_values=[1.0, 0.0])],
                )
            ]
        ),
        event_bus=event_bus,
    )

    with pytest.raises(GnnInsufficientGraphError, match="at least two nodes"):
        service.analyze(GnnAnalysisRequest(knowledge_base_id="kb-1"))


def test_gnn_service_list_clusters_returns_summaries_when_enabled() -> None:
    snapshot_source = InMemoryGraphSnapshotSource()
    snapshot_source.put_clusters(
        "kb-1",
        [
            ClusterSummary(
                cluster_id="c-1",
                entity_ids=["a", "b"],
                anomaly_score=0.7,
                label="hot",
            ),
            ClusterSummary(
                cluster_id="c-2",
                entity_ids=["c"],
                anomaly_score=0.2,
            ),
        ],
    )
    service = create_gnn_service(
        snapshot_source,
        event_bus=InMemoryEventBus(),
        gnn_enabled=lambda: True,
    )

    response = service.list_clusters(GnnClusterRequest(knowledge_base_id="kb-1"))

    assert len(response.clusters) == 2
    assert response.clusters[0].cluster_id == "c-1"
    assert response.clusters[0].label == "hot"
    assert response.clusters[1].label is None


def test_gnn_service_list_clusters_returns_empty_when_disabled() -> None:
    snapshot_source = InMemoryGraphSnapshotSource()
    snapshot_source.put_clusters(
        "kb-1",
        [
            ClusterSummary(cluster_id="c-1", entity_ids=["a"], anomaly_score=0.9),
        ],
    )
    service = create_gnn_service(
        snapshot_source,
        event_bus=InMemoryEventBus(),
        gnn_enabled=lambda: False,
    )

    response = service.list_clusters(GnnClusterRequest(knowledge_base_id="kb-1"))

    assert response.clusters == []


def test_gnn_service_list_clusters_defaults_to_enabled() -> None:
    snapshot_source = InMemoryGraphSnapshotSource()
    snapshot_source.put_clusters(
        "kb-1",
        [ClusterSummary(cluster_id="c-1", entity_ids=["a"], anomaly_score=0.5)],
    )
    service = create_gnn_service(snapshot_source, event_bus=InMemoryEventBus())

    response = service.list_clusters(GnnClusterRequest(knowledge_base_id="kb-1"))

    assert len(response.clusters) == 1


class _ValueErrorSnapshotSource:
    def load_snapshot(self, *, knowledge_base_id: str) -> GraphSnapshot:
        raise NotImplementedError

    def load_clusters(self, *, knowledge_base_id: str) -> list[ClusterSummary]:
        del knowledge_base_id
        raise ValueError("missing kb")


class _RuntimeErrorSnapshotSource:
    def load_snapshot(self, *, knowledge_base_id: str) -> GraphSnapshot:
        raise NotImplementedError

    def load_clusters(self, *, knowledge_base_id: str) -> list[ClusterSummary]:
        del knowledge_base_id
        raise RuntimeError("source down")


def test_gnn_service_list_clusters_translates_value_error() -> None:
    source: GraphSnapshotSourceProtocol = _ValueErrorSnapshotSource()
    service = create_gnn_service(source, event_bus=InMemoryEventBus(), gnn_enabled=lambda: True)

    with pytest.raises(GnnConfigurationError, match="missing kb"):
        service.list_clusters(GnnClusterRequest(knowledge_base_id="kb-1"))


def test_gnn_service_list_clusters_translates_runtime_error() -> None:
    source: GraphSnapshotSourceProtocol = _RuntimeErrorSnapshotSource()
    service = create_gnn_service(source, event_bus=InMemoryEventBus(), gnn_enabled=lambda: True)

    with pytest.raises(GnnSourceError, match="cluster summaries"):
        service.list_clusters(GnnClusterRequest(knowledge_base_id="kb-1"))