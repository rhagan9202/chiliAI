"""Analyst-facing peer comparison read models for SAFE-CMS-011."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, cast

from pydantic import BaseModel, Field

from analytics.peerstats.adapters.protocols import PeerSignalReaderProtocol
from analytics.peerstats.models import DerivedRiskSignal

PeerAnalysisConfidence = Literal["normal", "low"]


class PeerMetricComparison(BaseModel):
    """Context for one entity metric relative to its peer group."""

    metric_name: str
    entity_type: str
    interval_start: datetime
    peer_group_key: str
    entity_value: float
    peer_mean: float
    peer_std: float = Field(ge=0.0)
    z_score: float
    signal_value: float = Field(ge=0.0, le=1.0)
    cohort_size: int = Field(ge=0)
    percentile: float = Field(ge=0.0, le=100.0)
    rationale: str
    confidence: PeerAnalysisConfidence = "normal"
    confidence_reason: str | None = None


class PeerAnalysisResponse(BaseModel):
    """Peer-analysis context for one entity."""

    knowledge_base_id: str
    entity_id: str
    metrics: list[PeerMetricComparison] = Field(
        default_factory=lambda: cast(list[PeerMetricComparison], [])
    )


class PeerAnalysisService:
    """Build peer comparisons from persisted derived peer signals."""

    def __init__(
        self,
        reader: PeerSignalReaderProtocol,
        *,
        min_cohort_size: int = 5,
    ) -> None:
        self._reader = reader
        self._min_cohort_size = min_cohort_size

    def compare_entity(
        self,
        *,
        knowledge_base_id: str,
        entity_id: str,
        metric_name: str | None = None,
    ) -> PeerAnalysisResponse:
        """Return latest peer context per metric for an entity."""

        signals = self._reader.latest_signals(
            knowledge_base_id=knowledge_base_id,
            entity_id=entity_id,
            metric_name=metric_name,
        )
        metrics = [
            self._comparison_from_signal(
                signal,
                self._reader.peer_group_signals(
                    knowledge_base_id=knowledge_base_id,
                    metric_name=signal.metric_name,
                    interval_start=signal.interval_start,
                    peer_group_key=signal.peer_group_key,
                ),
            )
            for signal in signals
        ]
        return PeerAnalysisResponse(
            knowledge_base_id=knowledge_base_id,
            entity_id=entity_id,
            metrics=metrics,
        )

    def _comparison_from_signal(
        self,
        signal: DerivedRiskSignal,
        cohort_signals: list[DerivedRiskSignal],
    ) -> PeerMetricComparison:
        cohort_values = [item.aggregate_value for item in cohort_signals]
        cohort_size = len(cohort_values)
        percentile = _percentile_rank(signal.aggregate_value, cohort_values)
        confidence: PeerAnalysisConfidence = "normal"
        confidence_reason: str | None = None
        if cohort_size < self._min_cohort_size or signal.peer_std == 0.0:
            confidence = "low"
            confidence_reason = "small_or_degenerate_cohort"
        return PeerMetricComparison(
            metric_name=signal.metric_name,
            entity_type=signal.entity_type,
            interval_start=signal.interval_start,
            peer_group_key=signal.peer_group_key,
            entity_value=signal.aggregate_value,
            peer_mean=signal.peer_mean,
            peer_std=signal.peer_std,
            z_score=signal.z_score,
            signal_value=signal.signal_value,
            cohort_size=cohort_size,
            percentile=percentile,
            rationale=signal.rationale,
            confidence=confidence,
            confidence_reason=confidence_reason,
        )


def _percentile_rank(value: float, cohort_values: list[float]) -> float:
    if not cohort_values:
        return 0.0
    less_or_equal = sum(1 for cohort_value in cohort_values if cohort_value <= value)
    return round((less_or_equal / len(cohort_values)) * 100.0, 2)


__all__ = [
    "PeerAnalysisConfidence",
    "PeerAnalysisResponse",
    "PeerAnalysisService",
    "PeerMetricComparison",
]
