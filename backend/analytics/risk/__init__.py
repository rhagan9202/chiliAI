"""Public exports for the risk analytics module."""

from __future__ import annotations

from analytics.risk.adapters.in_memory import InMemoryRiskSignalSource
from analytics.risk.adapters.protocols import RiskSignalSourceProtocol
from analytics.risk.exceptions import (
    RiskConfigurationError,
    RiskError,
    RiskInsufficientSignalsError,
    RiskSourceError,
)
from analytics.risk.models import RiskAssessmentResult, RiskFactor, RiskProfile, RiskSignal
from analytics.risk.protocols import RiskServiceProtocol
from analytics.risk.service import RiskService, create_risk_service
from analytics.risk.service_models import (
    RiskAssessmentRequest,
    RiskAssessmentResponse,
    RiskFactorScore,
)

__all__ = [
    "InMemoryRiskSignalSource",
    "RiskAssessmentRequest",
    "RiskAssessmentResponse",
    "RiskAssessmentResult",
    "RiskConfigurationError",
    "RiskError",
    "RiskFactor",
    "RiskFactorScore",
    "RiskInsufficientSignalsError",
    "RiskProfile",
    "RiskService",
    "RiskServiceProtocol",
    "RiskSignal",
    "RiskSignalSourceProtocol",
    "RiskSourceError",
    "create_risk_service",
]