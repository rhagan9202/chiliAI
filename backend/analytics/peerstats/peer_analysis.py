"""Analyst-facing peer comparison read models for SAFE-CMS-011."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, cast

from pydantic import BaseModel, Field

from analytics.peerstats.adapters.protocols import PeerSignalReaderProtocol
from analytics.peerstats.models import DerivedRiskSignal
from config.schema import PeerCohortDefinitionConfig, PeerCohortExclusionConfig

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
    distribution: "PeerDistributionSummary | None" = None
    cohort: "PeerCohortContext | None" = None


class PeerDistributionSummary(BaseModel):
    """Metric distribution for the matching peer group."""

    count: int = Field(ge=0)
    minimum: float
    p50: float
    p90: float
    maximum: float


class PeerCohortExclusionSummary(BaseModel):
    """Configured exclusion rule exposed with the cohort definition."""

    field: str
    operator: str
    values: list[str] = Field(default_factory=lambda: cast(list[str], []))
    reason: str


class PeerCohortContext(BaseModel):
    """Cohort definition and membership context for one metric comparison."""

    id: str
    label: str
    version: str
    entity_type: str
    peer_metric: str
    group_by: list[str] = Field(default_factory=lambda: cast(list[str], []))
    group_values: dict[str, str] = Field(default_factory=dict[str, str])
    exclusions: list[PeerCohortExclusionSummary] = Field(
        default_factory=lambda: cast(list[PeerCohortExclusionSummary], [])
    )
    member_entity_ids: list[str] = Field(default_factory=lambda: cast(list[str], []))
    member_count: int = Field(ge=0)


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
        cohort_definitions: list[PeerCohortDefinitionConfig] | None = None,
    ) -> None:
        self._reader = reader
        self._min_cohort_size = min_cohort_size
        self._cohort_definitions = list(cohort_definitions or [])

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
            distribution=_distribution_summary(cohort_values),
            cohort=self._cohort_context(signal, cohort_signals),
        )

    def _cohort_context(
        self,
        signal: DerivedRiskSignal,
        cohort_signals: list[DerivedRiskSignal],
    ) -> PeerCohortContext | None:
        definition = self._cohort_definition_for(signal)
        if definition is None:
            return None
        return PeerCohortContext(
            id=definition.id,
            label=definition.label,
            version=definition.version,
            entity_type=definition.entity_type,
            peer_metric=definition.peer_metric,
            group_by=list(definition.group_by),
            group_values=_group_values(
                signal.peer_group_key,
                entity_type=signal.entity_type,
                group_by=definition.group_by,
            ),
            exclusions=[
                _exclusion_summary(exclusion)
                for exclusion in definition.exclusions
            ],
            member_entity_ids=sorted(item.entity_id for item in cohort_signals),
            member_count=len(cohort_signals),
        )

    def _cohort_definition_for(
        self,
        signal: DerivedRiskSignal,
    ) -> PeerCohortDefinitionConfig | None:
        for definition in self._cohort_definitions:
            if (
                definition.peer_metric == signal.metric_name
                and definition.entity_type == signal.entity_type
            ):
                return definition
        return None


def _percentile_rank(value: float, cohort_values: list[float]) -> float:
    if not cohort_values:
        return 0.0
    less_or_equal = sum(1 for cohort_value in cohort_values if cohort_value <= value)
    return round((less_or_equal / len(cohort_values)) * 100.0, 2)


def _distribution_summary(cohort_values: list[float]) -> PeerDistributionSummary | None:
    if not cohort_values:
        return None
    sorted_values = sorted(cohort_values)
    return PeerDistributionSummary(
        count=len(sorted_values),
        minimum=sorted_values[0],
        p50=_quantile(sorted_values, 0.5),
        p90=_quantile(sorted_values, 0.9),
        maximum=sorted_values[-1],
    )


def _quantile(sorted_values: list[float], q: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * q
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    fraction = position - lower_index
    lower = sorted_values[lower_index]
    upper = sorted_values[upper_index]
    return round(lower + (upper - lower) * fraction, 2)


def _group_values(
    peer_group_key: str,
    *,
    entity_type: str,
    group_by: list[str],
) -> dict[str, str]:
    parts = peer_group_key.split("|")
    if parts and parts[0] == entity_type:
        parts = parts[1:]
    return {
        field_name: parts[index]
        for index, field_name in enumerate(group_by)
        if index < len(parts)
    }


def _exclusion_summary(
    exclusion: PeerCohortExclusionConfig,
) -> PeerCohortExclusionSummary:
    return PeerCohortExclusionSummary(
        field=exclusion.field,
        operator=exclusion.operator,
        values=list(exclusion.values),
        reason=exclusion.reason,
    )


__all__ = [
    "PeerAnalysisConfidence",
    "PeerCohortContext",
    "PeerCohortExclusionSummary",
    "PeerAnalysisResponse",
    "PeerDistributionSummary",
    "PeerAnalysisService",
    "PeerMetricComparison",
]
