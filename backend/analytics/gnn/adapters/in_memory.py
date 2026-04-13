"""In-memory graph snapshot source for tests and local development."""

from __future__ import annotations

from analytics.gnn.models import GraphSnapshot


class InMemoryGraphSnapshotSource:
    """A seeded source of graph snapshots keyed by knowledge base."""

    def __init__(self, snapshots: list[GraphSnapshot] | None = None) -> None:
        self._snapshots: dict[str, GraphSnapshot] = {}
        for snapshot in snapshots or []:
            self.put_snapshot(snapshot)

    def put_snapshot(self, snapshot: GraphSnapshot) -> None:
        self._snapshots[snapshot.knowledge_base_id] = snapshot

    def load_snapshot(self, *, knowledge_base_id: str) -> GraphSnapshot:
        snapshot = self._snapshots.get(knowledge_base_id)
        if snapshot is None:
            raise ValueError(f"No graph snapshot registered for knowledge_base_id='{knowledge_base_id}'.")
        return snapshot