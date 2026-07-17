"""Tests for the graph-repository-backed GNN snapshot source."""

from __future__ import annotations

import logging

import pytest

from analytics.gnn.adapters.cluster_store import InMemoryClusterSummaryStore
from analytics.gnn.adapters.graph_repository_source import GraphRepositorySnapshotSource
from analytics.gnn.exceptions import GnnSnapshotUnavailableError
from analytics.gnn.models import ClusterSummary
from graph.adapters.in_memory import InMemoryGraphRepository
from shared.types import Entity, Relationship


def _source(
    repository: InMemoryGraphRepository, *, max_nodes: int = 5000
) -> GraphRepositorySnapshotSource:
    return GraphRepositorySnapshotSource(
        repository, InMemoryClusterSummaryStore(), max_nodes=max_nodes
    )


def _seed_triangle(repository: InMemoryGraphRepository, kb: str) -> None:
    repository.upsert_entities(
        kb,
        [
            Entity(id="e-1", type="provider", properties={"amount": 100, "npi": "x"}),
            Entity(id="e-2", type="claim", properties={"amount": 25.5}),
            Entity(id="e-3", type="claim", properties={}),
        ],
    )
    repository.upsert_relationships(
        kb,
        [
            Relationship(id="r-1", type="billed", source_id="e-2", target_id="e-1", weight=2.0),
            Relationship(id="r-2", type="billed", source_id="e-3", target_id="e-1"),
        ],
    )


def test_load_snapshot_builds_features_and_edges() -> None:
    repository = InMemoryGraphRepository()
    _seed_triangle(repository, "kb-1")

    snapshot = _source(repository).load_snapshot(knowledge_base_id="kb-1")

    assert snapshot.knowledge_base_id == "kb-1"
    nodes = {node.entity_id: node for node in snapshot.nodes}
    assert set(nodes) == {"e-1", "e-2", "e-3"}
    # degree first, then numeric properties sorted by name; non-numeric skipped
    assert nodes["e-1"].feature_values == [2.0, 100.0]
    assert nodes["e-2"].feature_values == [1.0, 25.5]
    assert nodes["e-3"].feature_values == [1.0, 0.0]  # degree + padded 0.0 (no "amount" property)
    edges = {(edge.source_id, edge.target_id): edge.weight for edge in snapshot.edges}
    assert edges[("e-2", "e-1")] == 2.0
    assert edges[("e-3", "e-1")] == 1.0  # default weight when relationship weight is None


def test_load_snapshot_pads_features_over_union_of_numeric_properties() -> None:
    """Heterogeneous entity types (disjoint numeric property sets) must still produce
    uniform-length feature vectors — every kept entity's vector spans the sorted union
    of numeric property names, padded with 0.0 where an entity lacks a given property."""
    repository = InMemoryGraphRepository()
    repository.upsert_entities(
        "kb-1",
        [
            Entity(id="e-a", type="provider", properties={"a": 1.5}),
            Entity(id="e-b", type="claim", properties={"b": 2.0, "c": 3.0}),
            Entity(id="e-none", type="beneficiary", properties={}),
        ],
    )
    repository.upsert_relationships(
        "kb-1",
        [
            Relationship(id="r-1", type="rel", source_id="e-a", target_id="e-b"),
            Relationship(id="r-2", type="rel", source_id="e-b", target_id="e-none"),
        ],
    )

    snapshot = _source(repository).load_snapshot(knowledge_base_id="kb-1")

    nodes = {node.entity_id: node for node in snapshot.nodes}
    lengths = {len(node.feature_values) for node in nodes.values()}
    assert lengths == {4}  # 1 (degree) + 3 (union of property names: a, b, c)
    # sorted union order is a, b, c; missing properties pad with 0.0
    assert nodes["e-a"].feature_values == [1.0, 1.5, 0.0, 0.0]
    assert nodes["e-b"].feature_values == [2.0, 0.0, 2.0, 3.0]
    assert nodes["e-none"].feature_values == [1.0, 0.0, 0.0, 0.0]


def test_load_snapshot_empty_kb_raises_unavailable() -> None:
    with pytest.raises(GnnSnapshotUnavailableError):
        _source(InMemoryGraphRepository()).load_snapshot(knowledge_base_id="kb-empty")


def test_load_snapshot_caps_to_top_degree_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repository = InMemoryGraphRepository()
    # hub e-hub connects to e-1..e-4; e-iso is isolated (degree 0)
    repository.upsert_entities(
        "kb-1",
        [Entity(id=f"e-{i}", type="claim", properties={}) for i in (1, 2, 3, 4)]
        + [Entity(id="e-hub", type="provider", properties={}), Entity(id="e-iso", type="claim", properties={})],
    )
    repository.upsert_relationships(
        "kb-1",
        [
            Relationship(id=f"r-{i}", type="billed", source_id=f"e-{i}", target_id="e-hub")
            for i in (1, 2, 3, 4)
        ],
    )

    with caplog.at_level(logging.WARNING):
        snapshot = _source(repository, max_nodes=5).load_snapshot(knowledge_base_id="kb-1")

    kept = {node.entity_id for node in snapshot.nodes}
    assert len(kept) == 5
    assert "e-hub" in kept and "e-iso" not in kept  # lowest degree dropped
    assert len(snapshot.edges) == 4  # no edge touches a dropped node
    assert any("truncat" in record.message.lower() for record in caplog.records)


def test_bool_properties_are_not_numeric_features() -> None:
    repository = InMemoryGraphRepository()
    repository.upsert_entities(
        "kb-1",
        [
            Entity(id="e-1", type="claim", properties={"flagged": True, "amount": 10}),
            Entity(id="e-2", type="claim", properties={}),
        ],
    )
    repository.upsert_relationships(
        "kb-1",
        [Relationship(id="r-1", type="rel", source_id="e-1", target_id="e-2")],
    )
    snapshot = _source(repository).load_snapshot(knowledge_base_id="kb-1")
    node = next(n for n in snapshot.nodes if n.entity_id == "e-1")
    assert node.feature_values == [1.0, 10.0]  # bool excluded


def test_load_clusters_delegates_to_store() -> None:
    repository = InMemoryGraphRepository()
    store = InMemoryClusterSummaryStore()
    store.put_clusters("kb-1", [ClusterSummary(cluster_id="c-1", entity_ids=["e-1"], anomaly_score=0.4)])
    source = GraphRepositorySnapshotSource(repository, store)
    assert [c.cluster_id for c in source.load_clusters(knowledge_base_id="kb-1")] == ["c-1"]


def test_load_snapshot_clamps_negative_weights_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repository = InMemoryGraphRepository()
    repository.upsert_entities(
        "kb-1",
        [
            Entity(id="e-1", type="claim", properties={}),
            Entity(id="e-2", type="claim", properties={}),
        ],
    )
    repository.upsert_relationships(
        "kb-1",
        [
            Relationship(id="r-1", type="rel", source_id="e-1", target_id="e-2", weight=-2.0),
        ],
    )

    with caplog.at_level(logging.WARNING):
        snapshot = _source(repository).load_snapshot(knowledge_base_id="kb-1")

    # Snapshot should build despite negative weight
    assert len(snapshot.nodes) == 2
    assert len(snapshot.edges) == 1
    # Negative weight clamped to 0.0
    edge = snapshot.edges[0]
    assert edge.weight == 0.0
    # Warning logged with KB and count
    assert any("kb-1" in record.message and "1" in record.message for record in caplog.records
               if "clamp" in record.message.lower())


def test_non_finite_float_strings_excluded_from_features() -> None:
    repository = InMemoryGraphRepository()
    repository.upsert_entities(
        "kb-1",
        [
            Entity(id="e-1", type="claim", properties={"a": "nan", "b": 2.5}),
            Entity(id="e-2", type="claim", properties={}),
        ],
    )
    repository.upsert_relationships(
        "kb-1",
        [Relationship(id="r-1", type="rel", source_id="e-1", target_id="e-2")],
    )
    snapshot = _source(repository).load_snapshot(knowledge_base_id="kb-1")
    node = next(n for n in snapshot.nodes if n.entity_id == "e-1")
    # Degree (1.0) + numeric properties; "nan" string parsed but excluded, 2.5 included
    assert node.feature_values == [1.0, 2.5]
