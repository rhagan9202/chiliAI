"""Public exports for the risk analytics module."""

from __future__ import annotations

from analytics.risk.adapters.in_memory import InMemoryRiskSignalSource
from analytics.risk.adapters.linear_strategy import LinearScoringStrategy
from analytics.risk.adapters.postgres import PostgresRiskHistoryStore
from analytics.risk.adapters.protocols import RiskSignalSourceProtocol
from analytics.risk.exceptions import (
    RiskConfigurationError,
    RiskError,
    RiskHistoryError,
    RiskInsufficientSignalsError,
    RiskSourceError,
)
from analytics.risk.models import (
    RankedRiskEntry,
    RiskAssessmentResult,
    RiskFactor,
    RiskProfile,
    RiskSignal,
)
from analytics.risk.protocols import RiskScoringStrategyProtocol, RiskServiceProtocol
from analytics.risk.service import (
    DEFAULT_TREND_DELTA_THRESHOLD,
    RiskService,
    create_risk_service,
)
from analytics.risk.service_models import (
    RiskAssessmentRequest,
    RiskAssessmentResponse,
    RiskFactorScore,
    RiskScore,
    RiskScoreListRequest,
    RiskScoreListResponse,
    RiskTrend,
)

__all__ = [
    "DEFAULT_TREND_DELTA_THRESHOLD",
    "InMemoryRiskSignalSource",
    "LinearScoringStrategy",
    "PostgresRiskHistoryStore",
    "RankedRiskEntry",
    "RiskAssessmentRequest",
    "RiskAssessmentResponse",
    "RiskAssessmentResult",
    "RiskConfigurationError",
    "RiskError",
    "RiskHistoryError",
    "RiskFactor",
    "RiskFactorScore",
    "RiskInsufficientSignalsError",
    "RiskProfile",
    "RiskScore",
    "RiskScoreListRequest",
    "RiskScoreListResponse",
    "RiskScoringStrategyProtocol",
    "RiskService",
    "RiskServiceProtocol",
    "RiskSignal",
    "RiskSignalSourceProtocol",
    "RiskSourceError",
    "RiskTrend",
    "create_risk_service",
]