"""Durable cluster-summary stores for GNN pipeline results."""

from __future__ import annotations

from pydantic import BaseModel, Field

from analytics.gnn.models import ClusterSummary
from storage.protocols import ObjectStore

__all__ = ["InMemoryClusterSummaryStore", "ObjectStoreClusterSummaryStore"]


class _ClusterSnapshot(BaseModel):
    """Serialized per-KB cluster list for object-store persistence."""

    clusters: list[ClusterSummary] = Field(default_factory=list[ClusterSummary])


class InMemoryClusterSummaryStore:
    """Process-local cluster summary store for tests and in-memory stacks."""

    def __init__(self) -> None:
        self._clusters: dict[str, list[ClusterSummary]] = {}

    def put_clusters(self, knowledge_base_id: str, clusters: list[ClusterSummary]) -> None:
        self._clusters[knowledge_base_id] = list(clusters)

    def load_clusters(self, *, knowledge_base_id: str) -> list[ClusterSummary]:
        return list(self._clusters.get(knowledge_base_id, []))

    def delete_by_kb(self, knowledge_base_id: str) -> None:
        self._clusters.pop(knowledge_base_id, None)


class ObjectStoreClusterSummaryStore:
    """Cluster summaries persisted per-KB in the configured object store."""

    _KEY_PREFIX = "system/analytics/gnn_clusters/"

    def __init__(self, object_store: ObjectStore) -> None:
        self._object_store = object_store

    def _key(self, knowledge_base_id: str) -> str:
        return f"{self._KEY_PREFIX}{knowledge_base_id}.json"

    def put_clusters(self, knowledge_base_id: str, clusters: list[ClusterSummary]) -> None:
        snapshot = _ClusterSnapshot(clusters=list(clusters))
        self._object_store.put_bytes(
            self._key(knowledge_base_id),
            snapshot.model_dump_json().encode("utf-8"),
            media_type="application/json",
            metadata={"record_type": "gnn_cluster_summaries"},
        )

    def load_clusters(self, *, knowledge_base_id: str) -> list[ClusterSummary]:
        key = self._key(knowledge_base_id)
        if not self._object_store.exists(key):
            return []
        stored = self._object_store.get_bytes(key)
        return list(_ClusterSnapshot.model_validate_json(stored.content).clusters)

    def delete_by_kb(self, knowledge_base_id: str) -> None:
        self._object_store.delete(self._key(knowledge_base_id))
