"""Tests for GNN cluster summary stores."""

from __future__ import annotations

from analytics.gnn.adapters.cluster_store import (
    InMemoryClusterSummaryStore,
    ObjectStoreClusterSummaryStore,
)
from analytics.gnn.models import ClusterSummary
from storage.adapters.in_memory import InMemoryObjectStore


def _summary(cluster_id: str, *, score: float = 0.5) -> ClusterSummary:
    return ClusterSummary(
        cluster_id=cluster_id,
        entity_ids=[f"{cluster_id}-a", f"{cluster_id}-b"],
        anomaly_score=score,
    )


def test_in_memory_store_round_trips_and_replaces() -> None:
    store = InMemoryClusterSummaryStore()
    assert store.load_clusters(knowledge_base_id="kb-1") == []
    store.put_clusters("kb-1", [_summary("c-1")])
    store.put_clusters("kb-1", [_summary("c-2"), _summary("c-3")])
    loaded = store.load_clusters(knowledge_base_id="kb-1")
    assert [s.cluster_id for s in loaded] == ["c-2", "c-3"]  # replace, not append
    assert store.load_clusters(knowledge_base_id="kb-other") == []


def test_in_memory_store_delete_by_kb() -> None:
    store = InMemoryClusterSummaryStore()
    store.put_clusters("kb-1", [_summary("c-1")])
    store.put_clusters("kb-2", [_summary("c-9")])
    store.delete_by_kb("kb-1")
    assert store.load_clusters(knowledge_base_id="kb-1") == []
    assert [s.cluster_id for s in store.load_clusters(knowledge_base_id="kb-2")] == ["c-9"]
    store.delete_by_kb("kb-missing")  # idempotent no-op


def test_object_store_round_trips_across_instances() -> None:
    object_store = InMemoryObjectStore()
    ObjectStoreClusterSummaryStore(object_store).put_clusters("kb-1", [_summary("c-1", score=0.9)])
    reloaded = ObjectStoreClusterSummaryStore(object_store).load_clusters(knowledge_base_id="kb-1")
    assert len(reloaded) == 1
    assert reloaded[0].cluster_id == "c-1"
    assert reloaded[0].anomaly_score == 0.9


def test_object_store_delete_by_kb_removes_key() -> None:
    object_store = InMemoryObjectStore()
    store = ObjectStoreClusterSummaryStore(object_store)
    store.put_clusters("kb-1", [_summary("c-1")])
    store.delete_by_kb("kb-1")
    assert store.load_clusters(knowledge_base_id="kb-1") == []
    assert not object_store.exists("system/analytics/gnn_clusters/kb-1.json")
    store.delete_by_kb("kb-1")  # idempotent no-op
