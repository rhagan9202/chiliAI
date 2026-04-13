"""Tests for the in-memory gnn adapter."""

from __future__ import annotations

from analytics.gnn.adapters.in_memory import InMemoryGraphSnapshotSource
from analytics.gnn.models import GraphNodeSignal, GraphSnapshot


def test_in_memory_snapshot_source_returns_seeded_snapshot() -> None:
    snapshot = GraphSnapshot(
        knowledge_base_id="kb-1",
        nodes=[GraphNodeSignal(entity_id="provider-1", feature_values=[1.0, 0.0])],
    )
    source = InMemoryGraphSnapshotSource(snapshots=[snapshot])

    loaded = source.load_snapshot(knowledge_base_id="kb-1")

    assert loaded == snapshot