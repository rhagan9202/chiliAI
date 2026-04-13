"""Tests for the gnn service."""

from __future__ import annotations

import pytest

from analytics.gnn.adapters.in_memory import InMemoryGraphSnapshotSource
from analytics.gnn.exceptions import GnnInsufficientGraphError
from analytics.gnn.models import GraphEdgeSignal, GraphNodeSignal, GraphSnapshot
from analytics.gnn.service import create_gnn_service
from analytics.gnn.service_models import GnnAnalysisRequest
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