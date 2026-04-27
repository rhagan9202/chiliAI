"""Graph-context bridge adapter that delegates expansion to the graph service."""

from __future__ import annotations

from graph.protocols import GraphServiceProtocol
from rag.models import (
    GraphContext,
    GraphContextEdge,
    GraphContextNode,
    RetrievedContextItem,
)


_ENTITY_ID_KEYS: tuple[str, ...] = ("entity_id", "entityId", "entity")


class ServiceGraphContextExpander:
    """Expand retrieved context into a graph neighborhood via `GraphServiceProtocol`."""

    def __init__(
        self,
        graph_service: GraphServiceProtocol,
        *,
        depth: int = 1,
    ) -> None:
        if depth < 0:
            raise ValueError("ServiceGraphContextExpander depth must be non-negative.")
        self._graph_service = graph_service
        self._depth = depth

    def expand(
        self,
        *,
        knowledge_base_id: str,
        context_items: list[RetrievedContextItem],
    ) -> GraphContext:
        seen_entity_ids: set[str] = set()
        ordered_entity_ids: list[str] = []
        for item in context_items:
            entity_id = _extract_entity_id(item)
            if entity_id is None or entity_id in seen_entity_ids:
                continue
            seen_entity_ids.add(entity_id)
            ordered_entity_ids.append(entity_id)

        nodes: list[GraphContextNode] = []
        edges: list[GraphContextEdge] = []
        seen_node_ids: set[str] = set()
        seen_edge_ids: set[str] = set()

        for entity_id in ordered_entity_ids:
            subgraph = self._graph_service.query_neighborhood(
                knowledge_base_id,
                entity_id,
                self._depth,
            )
            for entity in subgraph.entities:
                if entity.id in seen_node_ids:
                    continue
                seen_node_ids.add(entity.id)
                nodes.append(
                    GraphContextNode(
                        entity_id=entity.id,
                        entity_type=entity.type,
                        summary=_node_summary(entity.id, entity.type),
                    )
                )
            for relationship in subgraph.relationships:
                if relationship.id in seen_edge_ids:
                    continue
                seen_edge_ids.add(relationship.id)
                edges.append(
                    GraphContextEdge(
                        relationship_id=relationship.id,
                        relationship_type=relationship.type,
                        source_id=relationship.source_id,
                        target_id=relationship.target_id,
                        summary=None,
                    )
                )

        summary = _summary_for(nodes, edges)
        return GraphContext(nodes=nodes, edges=edges, summary=summary)


def _extract_entity_id(item: RetrievedContextItem) -> str | None:
    for key in _ENTITY_ID_KEYS:
        raw = item.metadata.get(key)
        if isinstance(raw, str) and raw.strip() != "":
            return raw
    return None


def _node_summary(entity_id: str, entity_type: str) -> str:
    return f"{entity_type}:{entity_id}"


def _summary_for(
    nodes: list[GraphContextNode],
    edges: list[GraphContextEdge],
) -> str:
    if not nodes and not edges:
        return ""
    return f"Expanded {len(nodes)} graph nodes and {len(edges)} relationships."


__all__ = ["ServiceGraphContextExpander"]
