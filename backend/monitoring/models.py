"""Internal transport and workflow models for active monitoring."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from shared.utils import utc_now


class MonitoringObservation(BaseModel):
    """A scored observation produced by upstream monitoring inputs."""

    entity_id: str
    entity_type: str
    metric_name: str
    score: float = Field(ge=0.0, le=1.0)
    observed_at: datetime = Field(default_factory=utc_now)
    rationale: str
    evidence_pack_id: str | None = None


class MonitoringBatch(BaseModel):
    """A batch of monitoring observations for one knowledge base."""

    knowledge_base_id: str
    batch_id: str
    observations: list[MonitoringObservation] = Field(
        default_factory=lambda: list[MonitoringObservation]()
    )

    @model_validator(mode="after")
    def _validate_observations(self) -> MonitoringBatch:
        if not self.observations:
            raise ValueError("MonitoringBatch requires at least one observation.")
        return self


class AlertCandidate(BaseModel):
    """An internal candidate ready to become a surfaced alert."""

    entity_id: str
    entity_type: str
    severity: str
    title: str
    reasoning: str
    score: float = Field(ge=0.0, le=1.0)
    metric_name: str
    evidence_pack_id: str | None = None


class SuppressionRule(BaseModel):
    """A rule that suppresses observations matching given dimensions during a time range.

    ``entity_type`` / ``metric_name`` accept ``None`` as a wildcard meaning
    "match any value for that dimension". The rule applies when ``start_time``
    <= "now" <= ``end_time``.
    """

    entity_type: str | None = None
    metric_name: str | None = None
    start_time: datetime
    end_time: datetime
    reason: str

    @model_validator(mode="after")
    def _validate_time_range(self) -> SuppressionRule:
        if self.end_time <= self.start_time:
            raise ValueError("SuppressionRule end_time must be after start_time.")
        return self

    def matches(
        self,
        *,
        entity_type: str,
        metric_name: str,
        now: datetime,
    ) -> bool:
        """Return True when the rule applies to the supplied observation context."""

        if self.entity_type is not None and self.entity_type != entity_type:
            return False
        if self.metric_name is not None and self.metric_name != metric_name:
            return False
        return self.start_time <= now <= self.end_time


class AlertGroup(BaseModel):
    """A correlation cluster of related alerts produced in the same evaluation."""

    group_id: str
    alert_ids: list[str]
    entity_type: str
    created_at: datetime
    correlation_reason: str


class AlertHistoryRecord(BaseModel):
    """A row destined for the analytics-facing ``alert_history`` log."""

    knowledge_base_id: str
    alert_id: str
    entity_id: str
    entity_type: str
    severity: str
    status: str
    title: str
    reasoning: str
    metric_name: str
    evidence_pack_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


__all__ = [
    "AlertCandidate",
    "AlertGroup",
    "AlertHistoryRecord",
    "MonitoringBatch",
    "MonitoringObservation",
    "SuppressionRule",
]
