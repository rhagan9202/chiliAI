"""Service-boundary models for timeseries analysis."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class TimeseriesAnalysisRequest(BaseModel):
    """A caller-supplied time-series anomaly analysis request."""

    knowledge_base_id: str
    entity_id: str
    metric_name: str
    baseline_window: int = Field(default=5, gt=1)
    min_history: int = Field(default=6, gt=2)
    z_threshold: float = Field(default=2.0, gt=0.0)

    @model_validator(mode="after")
    def _validate_history_requirements(self) -> TimeseriesAnalysisRequest:
        if self.min_history <= self.baseline_window:
            raise ValueError("TimeseriesAnalysisRequest min_history must exceed baseline_window.")
        return self


class TimeseriesAnomaly(BaseModel):
    """A service-boundary anomaly record."""

    observed_at: datetime
    observed_value: float
    expected_value: float
    deviation: float = Field(ge=0.0)
    z_score: float = Field(ge=0.0)


class TimeseriesAnalysisResponse(BaseModel):
    """A summary of time-series anomaly analysis."""

    request_id: str
    knowledge_base_id: str
    entity_id: str
    metric_name: str
    observation_count: int = Field(ge=0)
    anomaly_count: int = Field(ge=0)
    anomalies: list[TimeseriesAnomaly] = Field(default_factory=list)


__all__ = [
    "TimeseriesAnalysisRequest",
    "TimeseriesAnalysisResponse",
    "TimeseriesAnomaly",
]