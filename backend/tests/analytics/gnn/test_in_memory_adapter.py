"""Tests for the in-memory gnn adapter."""

from __future__ import annotations

import pytest

from analytics.gnn.adapters.in_memory import InMemoryGraphSnapshotSource
from analytics.gnn.models import ClusterSummary, GraphNodeSignal, GraphSnapshot


def test_in_memory_snapshot_source_returns_seeded_snapshot() -> None:
    snapshot = GraphSnapshot(
        knowledge_base_id="kb-1",
        nodes=[GraphNodeSignal(entity_id="provider-1", feature_values=[1.0, 0.0])],
    )
    source = InMemoryGraphSnapshotSource(snapshots=[snapshot])

    loaded = source.load_snapshot(knowledge_base_id="kb-1")

    assert loaded == snapshot


def test_in_memory_snapshot_source_raises_for_unknown_snapshot() -> None:
    source = InMemoryGraphSnapshotSource()

    with pytest.raises(ValueError, match="No graph snapshot registered"):
        source.load_snapshot(knowledge_base_id="kb-missing")


def test_in_memory_snapshot_source_returns_seeded_clusters() -> None:
    source = InMemoryGraphSnapshotSource(
        clusters={
            "kb-1": [
                ClusterSummary(cluster_id="c-1", entity_ids=["a"], anomaly_score=0.4)
            ]
        }
    )

    clusters = source.load_clusters(knowledge_base_id="kb-1")

    assert len(clusters) == 1
    assert clusters[0].cluster_id == "c-1"


def test_in_memory_snapshot_source_returns_empty_clusters_for_unseeded_kb() -> None:
    source = InMemoryGraphSnapshotSource()

    clusters = source.load_clusters(knowledge_base_id="kb-missing")

    assert clusters == []