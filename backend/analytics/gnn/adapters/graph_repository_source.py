"""Graph-repository-backed snapshot source: feeds the GNN engine real graph data."""

from __future__ import annotations

import logging
import math

from analytics.gnn.adapters.protocols import ClusterSummaryStoreProtocol
from analytics.gnn.exceptions import GnnSnapshotUnavailableError
from analytics.gnn.models import ClusterSummary, GraphEdgeSignal, GraphNodeSignal, GraphSnapshot
from graph.adapters.protocols import GraphRepository
from shared.types import Entity

logger = logging.getLogger(__name__)

__all__ = ["GraphRepositorySnapshotSource"]

_DEFAULT_MAX_NODES = 5000


def _numeric_feature_map(entity: Entity) -> dict[str, float]:
    """Entity's numeric properties as name -> value; bools excluded, non-finite skipped,
    float-parseable strings included."""
    values: dict[str, float] = {}
    for name, value in entity.properties.items():
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            float_val = float(value)
            if math.isfinite(float_val):
                values[name] = float_val
        elif isinstance(value, str):
            try:
                float_val = float(value)
            except ValueError:
                continue
            if math.isfinite(float_val):
                values[name] = float_val
    return values


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

        # Heterogeneous entity types carry disjoint numeric property sets; build the sorted
        # union of numeric property names across kept entities so every feature vector has
        # the same dimension, padding with 0.0 where an entity lacks a given property.
        feature_maps = {entity.id: _numeric_feature_map(entity) for entity in entities}
        feature_names = sorted({name for feature_map in feature_maps.values() for name in feature_map})

        nodes = [
            GraphNodeSignal(
                entity_id=entity.id,
                feature_values=[float(degree[entity.id])]
                + [feature_maps[entity.id].get(name, 0.0) for name in feature_names],
                metadata={"entity_type": entity.type},
            )
            for entity in entities
        ]

        # Track negative weights for logging
        clamped_count = 0
        edges: list[GraphEdgeSignal] = []
        for relationship in relationships:
            if relationship.source_id not in kept_ids or relationship.target_id not in kept_ids:
                continue

            weight = relationship.weight if relationship.weight is not None else 1.0
            if weight < 0.0:
                clamped_count += 1
                weight = 0.0

            edges.append(
                GraphEdgeSignal(
                    source_id=relationship.source_id,
                    target_id=relationship.target_id,
                    weight=weight,
                )
            )

        if clamped_count > 0:
            logger.warning(
                "GNN snapshot clamped %d negative edge weights to 0.0 for kb=%s.",
                clamped_count,
                knowledge_base_id,
            )

        return GraphSnapshot(knowledge_base_id=knowledge_base_id, nodes=nodes, edges=edges)

    def load_clusters(self, *, knowledge_base_id: str) -> list[ClusterSummary]:
        return self._cluster_store.load_clusters(knowledge_base_id=knowledge_base_id)
