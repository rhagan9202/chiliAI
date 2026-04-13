"""Public exports for the gnn analytics module."""

from __future__ import annotations

from analytics.gnn.adapters.in_memory import InMemoryGraphSnapshotSource
from analytics.gnn.adapters.protocols import GraphSnapshotSourceProtocol
from analytics.gnn.exceptions import GnnConfigurationError, GnnError, GnnInsufficientGraphError, GnnSourceError
from analytics.gnn.models import (
    GnnAnalysisResult,
    GraphEdgeSignal,
    GraphNodeSignal,
    GraphSnapshot,
    PredictedLink,
    ScoredNode,
)
from analytics.gnn.protocols import GnnServiceProtocol
from analytics.gnn.service import GnnService, create_gnn_service
from analytics.gnn.service_models import GnnAnalysisRequest, GnnAnalysisResponse, GnnLinkPrediction, GnnNodeScore

__all__ = [
    "GnnAnalysisRequest",
    "GnnAnalysisResponse",
    "GnnAnalysisResult",
    "GnnConfigurationError",
    "GnnError",
    "GnnInsufficientGraphError",
    "GnnLinkPrediction",
    "GnnNodeScore",
    "GnnService",
    "GnnServiceProtocol",
    "GnnSourceError",
    "GraphEdgeSignal",
    "GraphNodeSignal",
    "GraphSnapshot",
    "GraphSnapshotSourceProtocol",
    "InMemoryGraphSnapshotSource",
    "PredictedLink",
    "ScoredNode",
    "create_gnn_service",
]