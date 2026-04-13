"""Service-level protocols for the risk analytics module."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from analytics.risk.service_models import RiskAssessmentRequest, RiskAssessmentResponse


@runtime_checkable
class RiskServiceProtocol(Protocol):
    """Service boundary for composite risk scoring."""

    def assess(self, request: RiskAssessmentRequest) -> RiskAssessmentResponse: ...


__all__ = [
    "RiskServiceProtocol",
]