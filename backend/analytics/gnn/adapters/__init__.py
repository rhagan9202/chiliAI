"""Gnn adapters."""

from __future__ import annotations

from analytics.gnn.adapters.in_memory import InMemoryGraphSnapshotSource
from analytics.gnn.adapters.protocols import GraphSnapshotSourceProtocol

__all__ = ["GraphSnapshotSourceProtocol", "InMemoryGraphSnapshotSource"]