"""Service entry point for composite risk scoring flows."""

from __future__ import annotations

from analytics.risk.adapters.protocols import RiskSignalSourceProtocol
from analytics.risk.exceptions import (
    RiskConfigurationError,
    RiskInsufficientSignalsError,
    RiskSourceError,
)
from analytics.risk.models import RiskAssessmentResult, RiskFactor, RiskSignal
from analytics.risk.service_models import (
    RiskAssessmentRequest,
    RiskAssessmentResponse,
    RiskFactorScore,
)
from events.protocols import EventBus
from events.types import RiskScoredEvent, RiskScoredReference
from shared.utils import generate_id


class RiskService:
    """Coordinate signal loading, weighted scoring, and event publication."""

    # TODO(production): Replace simple weighted-sum scoring with pluggable risk
    # models (logistic regression, gradient boosting, ensemble). Add temporal risk
    # trending (compare current score to historical baseline). Add risk explanation
    # generation linking scores to specific evidence. Add batch assessment for
    # evaluating all entities in a knowledge base. Add caching for repeated
    # assessments of the same entity. Current _score_factors() is a basic linear
    # weighting — needs ML-backed alternatives as configurable strategies.

    def __init__(self, signal_source: RiskSignalSourceProtocol, *, event_bus: EventBus) -> None:
        self._signal_source = signal_source
        self._event_bus = event_bus

    def assess(self, request: RiskAssessmentRequest) -> RiskAssessmentResponse:
        try:
            profile = self._signal_source.load_profile(
                knowledge_base_id=request.knowledge_base_id,
                entity_id=request.entity_id,
            )
        except ValueError as exc:
            raise RiskConfigurationError(str(exc)) from exc
        except Exception as exc:
            raise RiskSourceError("Failed to load risk signals.") from exc

        if len(profile.signals) < 2:
            raise RiskInsufficientSignalsError(
                "Risk profile requires at least two signals for assessment."
            )

        factors = _score_factors(profile.signals)
        overall_score = min(1.0, sum(factor.contribution for factor in factors))
        risk_level = _risk_level(
            overall_score,
            medium_risk_threshold=request.medium_risk_threshold,
            high_risk_threshold=request.high_risk_threshold,
        )
        result = RiskAssessmentResult(
            request_id=generate_id(),
            knowledge_base_id=request.knowledge_base_id,
            entity_id=request.entity_id,
            overall_score=overall_score,
            risk_level=risk_level,
            factor_count=len(factors),
            factors=factors,
        )
        response = RiskAssessmentResponse(
            request_id=result.request_id,
            knowledge_base_id=result.knowledge_base_id,
            entity_id=result.entity_id,
            overall_score=result.overall_score,
            risk_level=result.risk_level,
            factor_count=result.factor_count,
            factors=[
                RiskFactorScore(
                    factor_name=factor.factor_name,
                    raw_value=factor.raw_value,
                    weight=factor.weight,
                    contribution=factor.contribution,
                    rationale=factor.rationale,
                )
                for factor in result.factors
            ],
        )
        self._event_bus.publish(
            RiskScoredEvent(
                assessments=[
                    RiskScoredReference(
                        knowledge_base_id=response.knowledge_base_id,
                        request_id=response.request_id,
                        entity_id=response.entity_id,
                        overall_score=response.overall_score,
                        risk_level=response.risk_level,
                        factor_count=response.factor_count,
                    )
                ]
            )
        )
        return response


def create_risk_service(
    signal_source: RiskSignalSourceProtocol,
    *,
    event_bus: EventBus,
) -> RiskService:
    """Create the default risk service."""

    return RiskService(signal_source, event_bus=event_bus)


def _score_factors(signals: list[RiskSignal]) -> list[RiskFactor]:
    total_weight = sum(signal.weight for signal in signals)
    return [
        RiskFactor(
            factor_name=signal.signal_name,
            raw_value=signal.value,
            weight=signal.weight,
            contribution=min(1.0, (signal.value * signal.weight) / total_weight),
            rationale=signal.rationale,
        )
        for signal in signals
    ]


def _risk_level(
    overall_score: float,
    *,
    medium_risk_threshold: float,
    high_risk_threshold: float,
) -> str:
    if overall_score >= high_risk_threshold:
        return "high"
    if overall_score >= medium_risk_threshold:
        return "medium"
    return "low"


__all__ = ["RiskService", "create_risk_service"]