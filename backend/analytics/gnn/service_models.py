"""Service-boundary models for gnn analysis."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GnnAnalysisRequest(BaseModel):
    """A caller-supplied graph analysis request."""

    knowledge_base_id: str
    similarity_threshold: float = Field(default=0.9, ge=0.0, le=1.0)
    top_k_predictions: int = Field(default=5, gt=0)


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


class GnnAnalysisResponse(BaseModel):
    """A summary of graph analysis output."""

    request_id: str
    knowledge_base_id: str
    node_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    scored_nodes: list[GnnNodeScore] = Field(default_factory=list)
    predicted_links: list[GnnLinkPrediction] = Field(default_factory=list)


__all__ = [
    "GnnAnalysisRequest",
    "GnnAnalysisResponse",
    "GnnLinkPrediction",
    "GnnNodeScore",
]