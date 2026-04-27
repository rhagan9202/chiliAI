"""Internal transport and workflow models for gnn analysis."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


MetadataValue = str | int | float | bool


class GraphNodeSignal(BaseModel):
    """A graph node with numeric features for lightweight scoring."""

    entity_id: str
    feature_values: list[float] = Field(default_factory=list)
    metadata: dict[str, MetadataValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_features(self) -> GraphNodeSignal:
        if not self.feature_values:
            raise ValueError("GraphNodeSignal requires at least one feature value.")
        return self


class GraphEdgeSignal(BaseModel):
    """A weighted edge between two graph nodes."""

    source_id: str
    target_id: str
    weight: float = Field(default=1.0, ge=0.0)


class GraphSnapshot(BaseModel):
    """A graph snapshot loaded for gnn-style analysis."""

    knowledge_base_id: str
    nodes: list[GraphNodeSignal] = Field(default_factory=list)
    edges: list[GraphEdgeSignal] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_nodes(self) -> GraphSnapshot:
        if not self.nodes:
            raise ValueError("GraphSnapshot requires at least one node.")
        return self


class ScoredNode(BaseModel):
    """A node score and inferred cluster assignment."""

    entity_id: str
    score: float = Field(ge=0.0)
    cluster_id: str


class PredictedLink(BaseModel):
    """A predicted relationship between two graph nodes."""

    source_id: str
    target_id: str
    confidence: float = Field(ge=0.0, le=1.0)


class GnnCommunity(BaseModel):
    """A detected community of related entities."""

    community_id: str
    member_entity_ids: list[str] = Field(default_factory=list[str])
    density: float = Field(ge=0.0, le=1.0)


class GnnAnalysisResult(BaseModel):
    """Internal result returned after analyzing a graph snapshot."""

    request_id: str
    knowledge_base_id: str
    node_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    scored_nodes: list[ScoredNode] = Field(default_factory=list)
    predicted_links: list[PredictedLink] = Field(default_factory=list)
    communities: list[GnnCommunity] = Field(default_factory=list[GnnCommunity])
    node_embeddings: dict[str, list[float]] = Field(default_factory=dict[str, list[float]])


class ClusterSummary(BaseModel):
    """An internal pre-computed cluster summary loaded from a snapshot source."""

    cluster_id: str
    entity_ids: list[str] = Field(default_factory=list[str])
    anomaly_score: float = Field(ge=0.0, le=1.0)
    label: str | None = None


__all__ = [
    "ClusterSummary",
    "GnnAnalysisResult",
    "GnnCommunity",
    "GraphEdgeSignal",
    "GraphNodeSignal",
    "GraphSnapshot",
    "MetadataValue",
    "PredictedLink",
    "ScoredNode",
]