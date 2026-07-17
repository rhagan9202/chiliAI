"""Graph-repository-backed snapshot source: feeds the GNN engine real graph data."""

from __future__ import annotations

import logging

from analytics.gnn.adapters.protocols import ClusterSummaryStoreProtocol
from analytics.gnn.exceptions import GnnSnapshotUnavailableError
from analytics.gnn.models import ClusterSummary, GraphEdgeSignal, GraphNodeSignal, GraphSnapshot
from graph.adapters.protocols import GraphRepository
from shared.types import Entity

logger = logging.getLogger(__name__)

__all__ = ["GraphRepositorySnapshotSource"]

_DEFAULT_MAX_NODES = 5000


def _numeric_features(entity: Entity) -> list[float]:
    """Numeric property values sorted by property name; bools excluded."""
    values: list[tuple[str, float]] = []
    for name, value in entity.properties.items():
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            values.append((name, float(value)))
        elif isinstance(value, str):
            try:
                values.append((name, float(value)))
            except ValueError:
                continue
    return [value for _, value in sorted(values)]


class GraphRepositorySnapshotSource:
    """Build bounded GNN snapshots from the configured graph repository."""

    def __init__(
        self,
        repository: GraphRepository,
        cluster_store: ClusterSummaryStoreProtocol,
        *,
        max_nodes: int = _DEFAULT_MAX_NODES,
    ) -> None:
        self._repository = repository
        self._cluster_store = cluster_store
        self._max_nodes = max_nodes

    def load_snapshot(self, *, knowledge_base_id: str) -> GraphSnapshot:
        entities = self._repository.get_entities(knowledge_base_id)
        if not entities:
            raise GnnSnapshotUnavailableError(
                f"Knowledge base '{knowledge_base_id}' has no graph entities yet."
            )
        relationships = self._repository.get_relationships(knowledge_base_id)

        degree: dict[str, int] = {entity.id: 0 for entity in entities}
        for relationship in relationships:
            if relationship.source_id in degree:
                degree[relationship.source_id] += 1
            if relationship.target_id in degree:
                degree[relationship.target_id] += 1

        if len(entities) > self._max_nodes:
            ranked = sorted(entities, key=lambda e: (-degree[e.id], e.id))
            kept, dropped = ranked[: self._max_nodes], ranked[self._max_nodes :]
            logger.warning(
                "GNN snapshot truncated for kb=%s: kept top-%d of %d nodes by degree "
                "(%d dropped).",
                knowledge_base_id, self._max_nodes, len(entities), len(dropped),
            )
            entities = kept
        kept_ids = {entity.id for entity in entities}

        nodes = [
            GraphNodeSignal(
                entity_id=entity.id,
                feature_values=[float(degree[entity.id])] + _numeric_features(entity),
                metadata={"entity_type": entity.type},
            )
            for entity in entities
        ]
        edges = [
            GraphEdgeSignal(
                source_id=relationship.source_id,
                target_id=relationship.target_id,
                weight=relationship.weight if relationship.weight is not None else 1.0,
            )
            for relationship in relationships
            if relationship.source_id in kept_ids and relationship.target_id in kept_ids
        ]
        return GraphSnapshot(knowledge_base_id=knowledge_base_id, nodes=nodes, edges=edges)

    def load_clusters(self, *, knowledge_base_id: str) -> list[ClusterSummary]:
        return self._cluster_store.load_clusters(knowledge_base_id=knowledge_base_id)
