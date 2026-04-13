"""Service-boundary models for monitoring evaluation."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from shared.types import Alert


class MonitoringEvaluationRequest(BaseModel):
    """A caller-supplied monitoring evaluation request."""

    knowledge_base_id: str
    batch_id: str
    medium_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    high_threshold: float = Field(default=0.85, ge=0.0, le=1.0)

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
    alerts: list[Alert] = Field(default_factory=list)


__all__ = ["MonitoringEvaluationRequest", "MonitoringEvaluationResponse"]