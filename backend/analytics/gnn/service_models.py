"""Service-boundary models for gnn analysis."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GnnAnalysisRequest(BaseModel):
    """A caller-supplied graph analysis request."""

    knowledge_base_id: str
    similarity_threshold: float = Field(default=0.9, ge=0.0, le=1.0)
    top_k_predictions: int = Field(default=5, gt=0)
    embedding_dimension: int = Field(default=8, gt=0, le=256)


class GnnNodeScore(BaseModel):
    """A service-boundary node score result."""

    entity_id: str
    score: float = Field(ge=0.0)
    cluster_id: str


class GnnLinkPrediction(BaseModel):
    """A service-boundary predicted link."""

    source_id: str
    target_id: str
    confidence: float = Field(ge=0.0, le=1.0)


class GnnCommunityResult(BaseModel):
    """A service-boundary detected community."""

    community_id: str
    member_entity_ids: list[str] = Field(default_factory=list[str])
    density: float = Field(ge=0.0, le=1.0)


class GnnAnalysisResponse(BaseModel):
    """A summary of graph analysis output."""

    request_id: str
    knowledge_base_id: str
    node_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    scored_nodes: list[GnnNodeScore] = Field(default_factory=list[GnnNodeScore])
    predicted_links: list[GnnLinkPrediction] = Field(default_factory=list[GnnLinkPrediction])
    communities: list[GnnCommunityResult] = Field(default_factory=list[GnnCommunityResult])
    node_embeddings: dict[str, list[float]] = Field(default_factory=dict[str, list[float]])


class GnnClusterRequest(BaseModel):
    """A caller-supplied request for clustered analysis output."""

    knowledge_base_id: str


class ClusterResult(BaseModel):
    """A single cluster summary returned from GNN analysis."""

    cluster_id: str
    entity_ids: list[str] = Field(default_factory=list[str])
    anomaly_score: float = Field(ge=0.0, le=1.0)
    label: str | None = None


class GnnClusterResponse(BaseModel):
    """A list of clusters discovered for one knowledge base."""

    knowledge_base_id: str
    clusters: list[ClusterResult] = Field(default_factory=list[ClusterResult])


__all__ = [
    "ClusterResult",
    "GnnAnalysisRequest",
    "GnnAnalysisResponse",
    "GnnClusterRequest",
    "GnnClusterResponse",
    "GnnCommunityResult",
    "GnnLinkPrediction",
    "GnnNodeScore",
]