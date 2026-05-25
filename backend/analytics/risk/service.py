"""Service entry point for composite risk scoring flows."""

from __future__ import annotations

from analytics.risk.adapters.linear_strategy import LinearScoringStrategy
from analytics.risk.adapters.protocols import RiskSignalSourceProtocol
from analytics.risk.exceptions import (
    RiskConfigurationError,
    RiskInsufficientSignalsError,
    RiskSourceError,
)
from analytics.risk.models import RiskAssessmentResult
from analytics.risk.protocols import RiskScoringStrategyProtocol
from analytics.risk.service_models import (
    RiskAssessmentRequest,
    RiskAssessmentResponse,
    RiskFactorScore,
    RiskScore,
    RiskScoreListRequest,
    RiskScoreListResponse,
    RiskTrend,
)
from events.protocols import EventBus
from events.types import RiskFactorReference, RiskScoredEvent, RiskScoredReference
from shared.utils import generate_id

DEFAULT_TREND_DELTA_THRESHOLD = 0.05


class RiskService:
    """Coordinate signal loading, weighted scoring, and event publication."""

    def __init__(
        self,
        signal_source: RiskSignalSourceProtocol,
        *,
        event_bus: EventBus,
        scoring_strategy: RiskScoringStrategyProtocol | None = None,
        delta_threshold: float = DEFAULT_TREND_DELTA_THRESHOLD,
    ) -> None:
        self._signal_source = signal_source
        self._event_bus = event_bus
        self._scoring_strategy: RiskScoringStrategyProtocol = (
            scoring_strategy if scoring_strategy is not None else LinearScoringStrategy()
        )
        self._delta_threshold = delta_threshold

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

        factors = self._scoring_strategy.score(profile.signals)
        overall_score = min(1.0, sum(factor.contribution for factor in factors))
        risk_level = _risk_level(
            overall_score,
            medium_risk_threshold=request.medium_risk_threshold,
            high_risk_threshold=request.high_risk_threshold,
        )

        previous_score = self._load_previous_score(
            knowledge_base_id=request.knowledge_base_id,
            entity_id=request.entity_id,
        )
        trend = _compute_trend(
            current_score=overall_score,
            previous_score=previous_score,
            delta_threshold=self._delta_threshold,
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
            trend=trend,
            previous_score=previous_score,
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
                        factors=[
                            RiskFactorReference(
                                factor_name=factor.factor_name,
                                raw_value=factor.raw_value,
                                weight=factor.weight,
                                contribution=factor.contribution,
                                rationale=factor.rationale,
                            )
                            for factor in response.factors
                        ],
                    )
                ]
            )
        )
        return response

    def list_scores(self, request: RiskScoreListRequest) -> RiskScoreListResponse:
        try:
            entries = self._signal_source.list_ranked_entries(
                knowledge_base_id=request.knowledge_base_id,
                entity_type=request.entity_type,
                limit=request.limit,
            )
        except ValueError as exc:
            raise RiskConfigurationError(str(exc)) from exc
        except Exception as exc:
            raise RiskSourceError("Failed to load ranked risk scores.") from exc

        items = [
            RiskScore(
                entity_id=entry.entity_id,
                entity_type=entry.entity_type,
                overall_score=entry.overall_score,
                risk_level=entry.risk_level,
            )
            for entry in entries
        ]
        return RiskScoreListResponse(
            knowledge_base_id=request.knowledge_base_id,
            items=items,
            total=len(items),
        )

    def _load_previous_score(
        self, *, knowledge_base_id: str, entity_id: str
    ) -> float | None:
        try:
            return self._signal_source.load_historical_score(
                knowledge_base_id=knowledge_base_id,
                entity_id=entity_id,
            )
        except Exception:
            return None


def create_risk_service(
    signal_source: RiskSignalSourceProtocol,
    *,
    event_bus: EventBus,
    scoring_strategy: RiskScoringStrategyProtocol | None = None,
    delta_threshold: float = DEFAULT_TREND_DELTA_THRESHOLD,
) -> RiskService:
    """Create the default risk service."""

    return RiskService(
        signal_source,
        event_bus=event_bus,
        scoring_strategy=scoring_strategy,
        delta_threshold=delta_threshold,
    )


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


def _compute_trend(
    *,
    current_score: float,
    previous_score: float | None,
    delta_threshold: float,
) -> RiskTrend | None:
    if previous_score is None:
        return None
    delta = current_score - previous_score
    if delta > delta_threshold:
        return "increasing"
    if -delta > delta_threshold:
        return "decreasing"
    return "stable"


__all__ = ["DEFAULT_TREND_DELTA_THRESHOLD", "RiskService", "create_risk_service"]
