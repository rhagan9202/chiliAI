"""Service entry point for gnn-style graph analysis flows."""

from __future__ import annotations

from math import sqrt

from analytics.gnn.adapters.protocols import GraphSnapshotSourceProtocol
from analytics.gnn.exceptions import GnnConfigurationError, GnnInsufficientGraphError, GnnSourceError
from analytics.gnn.models import GnnAnalysisResult, GraphEdgeSignal, GraphNodeSignal, PredictedLink, ScoredNode
from analytics.gnn.service_models import GnnAnalysisRequest, GnnAnalysisResponse, GnnLinkPrediction, GnnNodeScore
from events.protocols import EventBus
from events.types import GnnAnalyzedEvent, GnnAnalyzedReference
from shared.utils import generate_id


class GnnService:
    """Coordinate graph snapshot loading, scoring, link prediction, and event publication."""

    def __init__(self, snapshot_source: GraphSnapshotSourceProtocol, *, event_bus: EventBus) -> None:
        self._snapshot_source = snapshot_source
        self._event_bus = event_bus

    def analyze(self, request: GnnAnalysisRequest) -> GnnAnalysisResponse:
        try:
            snapshot = self._snapshot_source.load_snapshot(knowledge_base_id=request.knowledge_base_id)
        except ValueError as exc:
            raise GnnConfigurationError(str(exc)) from exc
        except Exception as exc:
            raise GnnSourceError("Failed to load graph snapshot.") from exc

        if len(snapshot.nodes) < 2:
            raise GnnInsufficientGraphError("Graph snapshot requires at least two nodes for analysis.")

        scored_nodes = _score_nodes(snapshot.nodes, snapshot.edges)
        predicted_links = _predict_links(
            snapshot.nodes,
            snapshot.edges,
            similarity_threshold=request.similarity_threshold,
            top_k=request.top_k_predictions,
        )
        result = GnnAnalysisResult(
            request_id=generate_id(),
            knowledge_base_id=request.knowledge_base_id,
            node_count=len(snapshot.nodes),
            edge_count=len(snapshot.edges),
            scored_nodes=scored_nodes,
            predicted_links=predicted_links,
        )
        response = GnnAnalysisResponse(
            request_id=result.request_id,
            knowledge_base_id=result.knowledge_base_id,
            node_count=result.node_count,
            edge_count=result.edge_count,
            scored_nodes=[
                GnnNodeScore(entity_id=node.entity_id, score=node.score, cluster_id=node.cluster_id)
                for node in result.scored_nodes
            ],
            predicted_links=[
                GnnLinkPrediction(
                    source_id=link.source_id,
                    target_id=link.target_id,
                    confidence=link.confidence,
                )
                for link in result.predicted_links
            ],
        )
        self._event_bus.publish(
            GnnAnalyzedEvent(
                analyses=[
                    GnnAnalyzedReference(
                        knowledge_base_id=response.knowledge_base_id,
                        request_id=response.request_id,
                        node_count=response.node_count,
                        edge_count=response.edge_count,
                        predicted_link_count=len(response.predicted_links),
                        cluster_count=len({node.cluster_id for node in response.scored_nodes}),
                    )
                ]
            )
        )
        return response


def create_gnn_service(
    snapshot_source: GraphSnapshotSourceProtocol,
    *,
    event_bus: EventBus,
) -> GnnService:
    """Create the default gnn service."""

    return GnnService(snapshot_source, event_bus=event_bus)


def _score_nodes(nodes: list[GraphNodeSignal], edges: list[GraphEdgeSignal]) -> list[ScoredNode]:
    weights_by_node: dict[str, float] = {node.entity_id: 0.0 for node in nodes}
    for edge in edges:
        weights_by_node[edge.source_id] = weights_by_node.get(edge.source_id, 0.0) + edge.weight
        weights_by_node[edge.target_id] = weights_by_node.get(edge.target_id, 0.0) + edge.weight
    return [
        ScoredNode(
            entity_id=node.entity_id,
            score=_feature_magnitude(node.feature_values) + weights_by_node.get(node.entity_id, 0.0),
            cluster_id=_cluster_id(node),
        )
        for node in nodes
    ]


def _predict_links(
    nodes: list[GraphNodeSignal],
    edges: list[GraphEdgeSignal],
    *,
    similarity_threshold: float,
    top_k: int,
) -> list[PredictedLink]:
    existing_pairs = {
        tuple(sorted((edge.source_id, edge.target_id)))
        for edge in edges
    }
    predictions: list[PredictedLink] = []
    for index, left in enumerate(nodes):
        for right in nodes[index + 1:]:
            pair = tuple(sorted((left.entity_id, right.entity_id)))
            if pair in existing_pairs:
                continue
            similarity = _cosine_similarity(left.feature_values, right.feature_values)
            if similarity >= similarity_threshold:
                predictions.append(
                    PredictedLink(source_id=left.entity_id, target_id=right.entity_id, confidence=similarity)
                )
    predictions.sort(key=lambda prediction: prediction.confidence, reverse=True)
    return predictions[:top_k]


def _cluster_id(node: GraphNodeSignal) -> str:
    anchor = round(node.feature_values[0]) if node.feature_values else 0
    return f"cluster-{anchor}"


def _feature_magnitude(values: list[float]) -> float:
    return sqrt(sum(value * value for value in values))


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("Feature vectors must share the same dimension.")
    left_norm = _feature_magnitude(left)
    right_norm = _feature_magnitude(right)
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    dot_product = sum(left_value * right_value for left_value, right_value in zip(left, right, strict=False))
    similarity = dot_product / (left_norm * right_norm)
    return max(0.0, min(1.0, similarity))


__all__ = ["GnnService", "create_gnn_service"]