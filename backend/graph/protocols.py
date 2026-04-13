"""Service-level protocols for the graph module."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from graph.service_models import GraphBuildReceipt, GraphBuildTask


@runtime_checkable
class GraphServiceProtocol(Protocol):
    """Service boundary for graph updates consumed by worker orchestration."""

    # TODO(production): Add read/query service methods:
    # - query_neighborhood(kb_id, entity_id, depth) -> NeighborhoodResult
    # - get_entity(kb_id, entity_id) -> Entity | None
    # - search_entities(kb_id, filters, limit, offset) -> list[Entity]
    # - compute_metrics(kb_id) -> GraphMetrics
    # - get_subgraph(kb_id, entity_ids) -> SubgraphResult
    # The service protocol is currently write-only; all frontend-facing views need reads.

    def upsert_task(self, task: GraphBuildTask) -> GraphBuildReceipt: ...


__all__ = [
    "GraphServiceProtocol",
]