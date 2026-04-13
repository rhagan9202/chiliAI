"""Adapter-level protocols for gnn analysis."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from analytics.gnn.models import GraphSnapshot


@runtime_checkable
class GraphSnapshotSourceProtocol(Protocol):
    """Load a graph snapshot for analysis."""

    # TODO(production): Extend with incremental/streaming graph loading:
    # - load_snapshot(kb_id, entity_types, max_nodes) -> GraphSnapshot  (filtered)
    # - load_incremental(kb_id, since: datetime) -> GraphSnapshot  (delta only)
    # Implement production adapter sourcing from Neo4j/graph module.

    def load_snapshot(self, *, knowledge_base_id: str) -> GraphSnapshot: ...


__all__ = [
    "GraphSnapshotSourceProtocol",
]