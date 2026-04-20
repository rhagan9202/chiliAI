"""Service-level protocols for the graph module."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from graph.models import GraphMetrics, SubgraphResult
from graph.service_models import GraphBuildReceipt, GraphBuildTask
from shared.types import Entity


@runtime_checkable
class GraphServiceProtocol(Protocol):
    """Service boundary for graph updates consumed by worker orchestration."""

    # TODO(production): Add get_subgraph(kb_id, entity_ids) -> SubgraphResult once
    # repository adapters expose a matching filtered-subgraph query surface.

    def upsert_task(self, task: GraphBuildTask) -> GraphBuildReceipt: ...

    def get_entity(self, knowledge_base_id: str, entity_id: str) -> Entity | None: ...

    def query_neighborhood(
        self,
        knowledge_base_id: str,
        entity_id: str,
        depth: int,
    ) -> SubgraphResult: ...

    def search_entities(
        self,
        knowledge_base_id: str,
        query: str,
        limit: int,
        offset: int,
    ) -> list[Entity]: ...

    def compute_metrics(self, knowledge_base_id: str) -> GraphMetrics: ...


__all__ = [
    "GraphServiceProtocol",
]