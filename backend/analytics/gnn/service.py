"""Service entry point for gnn-style graph analysis flows."""

from __future__ import annotations

from collections.abc import Callable
from math import sqrt
from typing import TYPE_CHECKING, cast

from analytics.gnn.adapters.protocols import GraphSnapshotSourceProtocol
from analytics.gnn.exceptions import (
    GnnConfigurationError,
    GnnDisabledError,
    GnnInsufficientGraphError,
    GnnSnapshotUnavailableError,
    GnnSourceError,
)
from analytics.gnn.models import (
    GnnAnalysisResult,
    GnnCommunity,
    GraphEdgeSignal,
    GraphNodeSignal,
    PredictedLink,
    ScoredNode,
)
from analytics.gnn.service_models import (
    ClusterResult,
    GnnAnalysisRequest,
    GnnAnalysisResponse,
    GnnClusterRequest,
    GnnClusterResponse,
    GnnCommunityResult,
    GnnLinkPrediction,
    GnnNodeScore,
)
from events.protocols import EventBus
from events.types import GnnAnalyzedEvent, GnnAnalyzedReference
from shared.utils import generate_id

if TYPE_CHECKING:
    from numpy.typing import NDArray


class GnnService:
    """Coordinate graph snapshot loading, scoring, link prediction, and event publication."""

    # TODO(production): Replace heuristic scoring with real GNN inference:
    # - Integrate PyTorch Geometric or DGL for node classification / link prediction
    # - Support configurable GNN architectures (GCN, GAT, GraphSAGE)
    # Current _score_nodes() uses simple degree centrality and _predict_links()
    # uses Jaccard similarity — both need ML-backed replacements.

    def __init__(
        self,
        snapshot_source: GraphSnapshotSourceProtocol,
        *,
        event_bus: EventBus,
        gnn_enabled: Callable[[], bool] | None = None,
    ) -> None:
        self._snapshot_source = snapshot_source
        self._event_bus = event_bus
        self._gnn_enabled = gnn_enabled if gnn_enabled is not None else _always_enabled

    def analyze(self, request: GnnAnalysisRequest) -> GnnAnalysisResponse:
        if not self._gnn_enabled():
            raise GnnDisabledError("GNN analysis is disabled by domain configuration.")

        try:
            snapshot = self._snapshot_source.load_snapshot(knowledge_base_id=request.knowledge_base_id)
        except GnnSnapshotUnavailableError:
            raise
        except ValueError as exc:
            raise GnnConfigurationError(str(exc)) from exc
        except Exception as exc:
            raise GnnSourceError("Failed to load graph snapshot.") from exc

        if len(snapshot.nodes) < 2:
            raise GnnInsufficientGraphError("Graph snapshot requires at least two nodes for analysis.")

        scored_nodes = _score_nodes(snapshot.nodes, snapshot.edges)
        communities = _detect_communities(snapshot.nodes, snapshot.edges)
        scored_nodes = _assign_community_ids(scored_nodes, communities)
        node_embeddings = _compute_embeddings(
            snapshot.nodes,
            snapshot.edges,
            dimension=request.embedding_dimension,
        )
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
            communities=communities,
            node_embeddings=node_embeddings,
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
            communities=[
                GnnCommunityResult(
                    community_id=community.community_id,
                    member_entity_ids=list(community.member_entity_ids),
                    density=community.density,
                )
                for community in result.communities
            ],
            node_embeddings={
                entity_id: list(values) for entity_id, values in result.node_embeddings.items()
            },
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


    def list_clusters(self, request: GnnClusterRequest) -> GnnClusterResponse:
        if not self._gnn_enabled():
            return GnnClusterResponse(knowledge_base_id=request.knowledge_base_id, clusters=[])

        try:
            summaries = self._snapshot_source.load_clusters(knowledge_base_id=request.knowledge_base_id)
        except ValueError as exc:
            raise GnnConfigurationError(str(exc)) from exc
        except Exception as exc:
            raise GnnSourceError("Failed to load gnn cluster summaries.") from exc

        clusters = [
            ClusterResult(
                cluster_id=summary.cluster_id,
                entity_ids=list(summary.entity_ids),
                anomaly_score=summary.anomaly_score,
                label=summary.label,
            )
            for summary in summaries
        ]
        return GnnClusterResponse(knowledge_base_id=request.knowledge_base_id, clusters=clusters)


def _always_enabled() -> bool:
    return True


def create_gnn_service(
    snapshot_source: GraphSnapshotSourceProtocol,
    *,
    event_bus: EventBus,
    gnn_enabled: Callable[[], bool] | None = None,
) -> GnnService:
    """Create the default gnn service."""

    return GnnService(snapshot_source, event_bus=event_bus, gnn_enabled=gnn_enabled)


def _score_nodes(nodes: list[GraphNodeSignal], edges: list[GraphEdgeSignal]) -> list[ScoredNode]:
    weights_by_node: dict[str, float] = {node.entity_id: 0.0 for node in nodes}
    for edge in edges:
        weights_by_node[edge.source_id] = weights_by_node.get(edge.source_id, 0.0) + edge.weight
        weights_by_node[edge.target_id] = weights_by_node.get(edge.target_id, 0.0) + edge.weight
    return [
        ScoredNode(
            entity_id=node.entity_id,
            score=_feature_magnitude(node.feature_values) + weights_by_node.get(node.entity_id, 0.0),
            cluster_id=_fallback_cluster_id(node),
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


def _detect_communities(
    nodes: list[GraphNodeSignal],
    edges: list[GraphEdgeSignal],
) -> list[GnnCommunity]:
    nx_module = _import_networkx()
    graph = _build_networkx_graph(nx_module, nodes, edges)
    community_module = getattr(nx_module, "community")
    louvain = cast(
        Callable[..., list[set[str]]],
        getattr(community_module, "louvain_communities"),
    )
    partitions = louvain(graph, seed=42)
    density_fn = cast(Callable[..., float], getattr(nx_module, "density"))
    communities: list[GnnCommunity] = []
    for index, partition in enumerate(sorted(partitions, key=lambda members: sorted(members))):
        members = sorted(partition)
        subgraph = cast(Callable[[list[str]], object], getattr(graph, "subgraph"))
        subgraph_obj = subgraph(members)
        density = float(density_fn(subgraph_obj))
        communities.append(
            GnnCommunity(
                community_id=f"community-{index}",
                member_entity_ids=members,
                density=max(0.0, min(1.0, density)),
            )
        )
    return communities


def _assign_community_ids(
    scored_nodes: list[ScoredNode],
    communities: list[GnnCommunity],
) -> list[ScoredNode]:
    assignments: dict[str, str] = {}
    for community in communities:
        for member_id in community.member_entity_ids:
            assignments[member_id] = community.community_id
    return [
        ScoredNode(
            entity_id=node.entity_id,
            score=node.score,
            cluster_id=assignments.get(node.entity_id, node.cluster_id),
        )
        for node in scored_nodes
    ]


def _compute_embeddings(
    nodes: list[GraphNodeSignal],
    edges: list[GraphEdgeSignal],
    *,
    dimension: int,
) -> dict[str, list[float]]:
    import numpy as np

    nx_module = _import_networkx()
    graph = _build_networkx_graph(nx_module, nodes, edges)
    ordered_ids = [node.entity_id for node in nodes]
    node_count = len(ordered_ids)
    if node_count == 0:
        return {}

    to_numpy = cast(
        Callable[..., object],
        getattr(nx_module, "to_numpy_array"),
    )
    adjacency_raw = to_numpy(graph, nodelist=ordered_ids, weight="weight", dtype=float)
    adjacency: NDArray[np.float64] = np.asarray(adjacency_raw, dtype=np.float64)
    degree_vector: NDArray[np.float64] = adjacency.sum(axis=1)
    laplacian: NDArray[np.float64] = np.diag(degree_vector) - adjacency
    eigh_result = np.linalg.eigh(laplacian)
    eigenvalues: NDArray[np.float64] = eigh_result.eigenvalues
    eigenvectors: NDArray[np.float64] = eigh_result.eigenvectors

    sort_index = np.argsort(eigenvalues)
    sorted_vectors: NDArray[np.float64] = eigenvectors[:, sort_index]

    target_dim = min(dimension, max(node_count - 1, 1))
    selected_columns: NDArray[np.float64] = sorted_vectors[:, 1 : target_dim + 1]
    if selected_columns.shape[1] == 0:
        selected_columns = sorted_vectors[:, :1]

    if selected_columns.shape[1] < dimension:
        padding: NDArray[np.float64] = np.zeros(
            (node_count, dimension - selected_columns.shape[1]), dtype=np.float64
        )
        embedding_matrix: NDArray[np.float64] = np.hstack((selected_columns, padding))
    else:
        embedding_matrix = selected_columns

    norms: NDArray[np.float64] = np.linalg.norm(embedding_matrix, axis=1, keepdims=True)
    safe_norms: NDArray[np.float64] = np.where(norms > 0.0, norms, 1.0)
    normalized: NDArray[np.float64] = embedding_matrix / safe_norms
    fallback: NDArray[np.float64] = np.zeros(dimension, dtype=np.float64)
    if dimension > 0:
        fallback[0] = 1.0

    embeddings: dict[str, list[float]] = {}
    for index, entity_id in enumerate(ordered_ids):
        row: NDArray[np.float64] = normalized[index]
        row_norm = float(np.linalg.norm(row))
        if row_norm == 0.0:
            embeddings[entity_id] = [float(value) for value in fallback]
        else:
            embeddings[entity_id] = [float(value) for value in row]
    return embeddings


def _build_networkx_graph(
    nx_module: object,
    nodes: list[GraphNodeSignal],
    edges: list[GraphEdgeSignal],
) -> object:
    graph_factory = cast(
        Callable[[], object],
        getattr(nx_module, "Graph"),
    )
    graph = graph_factory()
    add_node = cast(Callable[..., None], getattr(graph, "add_node"))
    add_edge = cast(Callable[..., None], getattr(graph, "add_edge"))
    for node in nodes:
        add_node(node.entity_id)
    for edge in edges:
        add_edge(edge.source_id, edge.target_id, weight=float(edge.weight))
    return graph


def _import_networkx() -> object:
    try:
        import networkx as nx_module
    except ImportError as exc:  # pragma: no cover - exercised via missing extra
        raise GnnConfigurationError(
            "networkx is required for gnn analysis; install the 'analytics' extra."
        ) from exc
    return nx_module


def _fallback_cluster_id(node: GraphNodeSignal) -> str:
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
