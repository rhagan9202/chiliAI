"""In-memory graph snapshot source for tests and local development."""

from __future__ import annotations

from analytics.gnn.exceptions import GnnSnapshotUnavailableError
from analytics.gnn.models import ClusterSummary, GraphSnapshot

__all__ = ["InMemoryGraphSnapshotSource"]


class InMemoryGraphSnapshotSource:
    """A seeded source of graph snapshots keyed by knowledge base."""

    def __init__(
        self,
        snapshots: list[GraphSnapshot] | None = None,
        *,
        clusters: dict[str, list[ClusterSummary]] | None = None,
    ) -> None:
        self._snapshots: dict[str, GraphSnapshot] = {}
        self._clusters: dict[str, list[ClusterSummary]] = {
            knowledge_base_id: list(summaries)
            for knowledge_base_id, summaries in (clusters or {}).items()
        }
        for snapshot in snapshots or []:
            self.put_snapshot(snapshot)

    def put_snapshot(self, snapshot: GraphSnapshot) -> None:
        self._snapshots[snapshot.knowledge_base_id] = snapshot

    def put_clusters(self, knowledge_base_id: str, clusters: list[ClusterSummary]) -> None:
        self._clusters[knowledge_base_id] = list(clusters)

    def load_snapshot(self, *, knowledge_base_id: str) -> GraphSnapshot:
        snapshot = self._snapshots.get(knowledge_base_id)
        if snapshot is None:
            raise GnnSnapshotUnavailableError(
                "No graph snapshot registered for "
                f"knowledge_base_id='{knowledge_base_id}'."
            )
        return snapshot

    def load_clusters(self, *, knowledge_base_id: str) -> list[ClusterSummary]:
        return list(self._clusters.get(knowledge_base_id, []))