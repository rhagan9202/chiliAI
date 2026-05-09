"""Service-level protocols for the risk analytics module."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from analytics.risk.models import RiskFactor, RiskSignal
from analytics.risk.service_models import (
    RiskAssessmentRequest,
    RiskAssessmentResponse,
    RiskScoreListRequest,
    RiskScoreListResponse,
)


@runtime_checkable
class RiskServiceProtocol(Protocol):
    """Service boundary for composite risk scoring."""

    def assess(self, request: RiskAssessmentRequest) -> RiskAssessmentResponse: ...

    def list_scores(self, request: RiskScoreListRequest) -> RiskScoreListResponse: ...


@runtime_checkable
class RiskScoringStrategyProtocol(Protocol):
    """Pluggable strategy that maps risk signals to weighted risk factors."""

    def score(self, signals: list[RiskSignal]) -> list[RiskFactor]: ...


__all__ = [
    "RiskScoringStrategyProtocol",
    "RiskServiceProtocol",
]
