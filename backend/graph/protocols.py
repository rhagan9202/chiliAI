"""Service-level protocols for the graph module."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from graph.service_models import GraphBuildReceipt, GraphBuildTask


@runtime_checkable
class GraphServiceProtocol(Protocol):
    """Service boundary for graph updates consumed by worker orchestration."""

    def upsert_task(self, task: GraphBuildTask) -> GraphBuildReceipt: ...