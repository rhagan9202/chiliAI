"""Service-boundary models for monitoring evaluation."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from monitoring.models import AlertGroup
from shared.types import Alert


class MonitoringEvaluationRequest(BaseModel):
    """A caller-supplied monitoring evaluation request."""

    knowledge_base_id: str
    batch_id: str
    medium_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    high_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    window_minutes: int = Field(default=60, gt=0)
    min_observations_in_window: int = Field(default=1, gt=0)

    @model_validator(mode="after")
    def _validate_thresholds(self) -> MonitoringEvaluationRequest:
        if self.high_threshold <= self.medium_threshold:
            raise ValueError("MonitoringEvaluationRequest high_threshold must exceed medium_threshold.")
        return self


class MonitoringEvaluationResponse(BaseModel):
    """Summary returned after generating alerts from a monitoring batch."""

    knowledge_base_id: str
    batch_id: str
    processed_observation_count: int = Field(ge=0)
    alert_count: int = Field(ge=0)
    alerts: list[Alert] = Field(default_factory=lambda: list[Alert]())
    suppressed_count: int = 0
    suppressed_by_rule_count: int = 0
    rate_limited_count: int = 0
    alert_groups: list[AlertGroup] = Field(default_factory=lambda: list[AlertGroup]())


class AlertListRequest(BaseModel):
    """Filters and pagination for listing alerts."""

    severity: str | None = None
    entity_type: str | None = None
    status: str | None = None
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class AlertListResponse(BaseModel):
    """A page of alerts with the total matching count."""

    items: list[Alert] = Field(default_factory=lambda: list[Alert]())
    total: int = Field(ge=0)


class ResolutionRequest(BaseModel):
    """Resolution payload supplied with `POST /alerts/{id}/resolve`."""

    resolved_by: str = Field(min_length=1)
    notes: str | None = None


class AlertActionResponse(BaseModel):
    """Response wrapper returned by alert lifecycle actions."""

    alert: Alert


__all__ = [
    "AlertActionResponse",
    "AlertListRequest",
    "AlertListResponse",
    "MonitoringEvaluationRequest",
    "MonitoringEvaluationResponse",
    "ResolutionRequest",
]
