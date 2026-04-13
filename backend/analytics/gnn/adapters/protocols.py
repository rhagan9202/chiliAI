"""Adapter-level protocols for gnn analysis."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from analytics.gnn.models import GraphSnapshot


@runtime_checkable
class GraphSnapshotSourceProtocol(Protocol):
    """Load a graph snapshot for analysis."""

    def load_snapshot(self, *, knowledge_base_id: str) -> GraphSnapshot: ...


__all__ = [
    "GraphSnapshotSourceProtocol",
]