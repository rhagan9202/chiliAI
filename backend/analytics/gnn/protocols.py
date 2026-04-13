"""Service-level protocols for the gnn analytics module."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from analytics.gnn.service_models import GnnAnalysisRequest, GnnAnalysisResponse


@runtime_checkable
class GnnServiceProtocol(Protocol):
    """Service boundary for graph neural network style analysis."""

    def analyze(self, request: GnnAnalysisRequest) -> GnnAnalysisResponse: ...