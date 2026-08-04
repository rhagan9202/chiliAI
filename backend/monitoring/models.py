"""Internal transport and workflow models for active monitoring."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Literal, cast

from pydantic import BaseModel, Field, field_validator, model_validator

# MonitoringObservation now lives in shared/types.py so producers
# (records/) and consumers (monitoring/) can both depend on it without
# crossing module boundaries. Re-exported here for backward compatibility
# with code that still imports it from monitoring.models.
from shared.types import MonitoringObservation
from shared.utils import utc_now


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
    generation_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("generation_metadata")
    @classmethod
    def _generation_metadata_must_be_json_safe(
        cls, value: dict[str, Any]
    ) -> dict[str, Any]:
        return normalize_generation_metadata(value)


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


class AlertTriageEvent(BaseModel):
    """Auditable event appended when an alert's queue state changes."""

    event_type: Literal["assigned", "status_changed"]
    actor: str
    occurred_at: datetime = Field(default_factory=utc_now)
    assignee: str | None = None
    from_status: str | None = None
    to_status: str | None = None
    reason: str | None = None


class AlertHistoryRecord(BaseModel):
    """A row in ``alert_history`` — the sole backing store for ``/alerts`` (alerts.36)."""

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
    entity_label: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=lambda: list[str]())
    assignee: str | None = None
    generation_metadata: dict[str, Any] = Field(default_factory=dict)
    triage_history: list[AlertTriageEvent] = Field(
        default_factory=lambda: list[AlertTriageEvent]()
    )

    @field_validator("generation_metadata")
    @classmethod
    def _generation_metadata_must_be_json_safe(
        cls, value: dict[str, Any]
    ) -> dict[str, Any]:
        return normalize_generation_metadata(value)


def normalize_generation_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON-safe metadata copy, expanding Pydantic values."""

    normalized = _json_safe_value(metadata)
    if not isinstance(normalized, dict):
        raise ValueError("generation_metadata must decode to a JSON object.")
    return cast(dict[str, Any], normalized)


def _json_safe_value(value: Any) -> object:
    if isinstance(value, BaseModel):
        return _json_safe_value(value.model_dump(mode="json"))
    if value is None or isinstance(value, str | int | bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("generation_metadata floats must be finite.")
        return value
    if isinstance(value, list):
        return [_json_safe_value(item) for item in cast(list[Any], value)]
    if isinstance(value, dict):
        normalized: dict[str, object] = {}
        for key, item in cast(dict[Any, Any], value).items():
            if not isinstance(key, str):
                raise ValueError("generation_metadata keys must be strings.")
            normalized[key] = _json_safe_value(item)
        return normalized
    raise ValueError("generation_metadata must contain only JSON-safe values.")


__all__ = [
    "AlertCandidate",
    "AlertGroup",
    "AlertHistoryRecord",
    "AlertTriageEvent",
    "MonitoringBatch",
    "MonitoringObservation",
    "normalize_generation_metadata",
    "SuppressionRule",
]
