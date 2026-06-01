"""Service-level protocols for the graph module."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from graph.models import GraphDeleteByProvenance, GraphMetrics, SubgraphResult
from graph.service_models import GraphBuildReceipt, GraphBuildTask
from shared.types import Entity


@runtime_checkable
class GraphServiceProtocol(Protocol):
    """Service boundary for graph updates consumed by worker orchestration."""

    def upsert_task(self, task: GraphBuildTask) -> GraphBuildReceipt: ...

    def get_entity(self, knowledge_base_ids: list[str], entity_id: str) -> Entity | None: ...

    def update_entity_properties(
        self,
        knowledge_base_id: str,
        entity_id: str,
        properties: dict[str, object],
    ) -> Entity: ...

    def query_neighborhood(
        self,
        knowledge_base_id: str,
        entity_id: str,
        depth: int,
    ) -> SubgraphResult: ...

    def get_subgraph(
        self,
        knowledge_base_id: str,
        seed_entity_ids: list[str],
        depth: int = 1,
    ) -> SubgraphResult: ...

    def search_entities(
        self,
        knowledge_base_ids: list[str],
        query: str,
        limit: int,
        offset: int,
    ) -> list[Entity]: ...

    def compute_metrics(self, knowledge_base_id: str) -> GraphMetrics: ...

    def delete_knowledge_base(self, knowledge_base_id: str) -> None: ...

    def delete_by_source_document(
        self,
        knowledge_base_id: str,
        source_document_id: str,
    ) -> GraphDeleteByProvenance: ...


__all__ = [
    "GraphServiceProtocol",
]