"""Adapter-level protocols for gnn analysis."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from analytics.gnn.models import ClusterSummary, GraphSnapshot


@runtime_checkable
class GraphSnapshotSourceProtocol(Protocol):
    """Load a graph snapshot for analysis."""

    # TODO(production): Extend with incremental/streaming graph loading:
    # - load_snapshot(kb_id, entity_types, max_nodes) -> GraphSnapshot  (filtered)
    # - load_incremental(kb_id, since: datetime) -> GraphSnapshot  (delta only)
    # Implement production adapter sourcing from Neo4j/graph module.

    def load_snapshot(self, *, knowledge_base_id: str) -> GraphSnapshot: ...

    def load_clusters(self, *, knowledge_base_id: str) -> list[ClusterSummary]: ...


@runtime_checkable
class ClusterSummaryStoreProtocol(Protocol):
    """Store and retrieve cluster summaries by knowledge base."""

    def put_clusters(self, knowledge_base_id: str, clusters: list[ClusterSummary]) -> None: ...

    def load_clusters(self, *, knowledge_base_id: str) -> list[ClusterSummary]: ...

    def delete_by_kb(self, knowledge_base_id: str) -> None: ...


__all__ = [
    "ClusterSummaryStoreProtocol",
    "GraphSnapshotSourceProtocol",
]