"""Service-boundary models for timeseries analysis."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

DetectionStrategy = Literal["z_score", "stl_decomposition", "isolation_forest"]


class TimeseriesAnalysisRequest(BaseModel):
    """A caller-supplied time-series anomaly analysis request."""

    knowledge_base_id: str
    entity_id: str
    metric_name: str
    baseline_window: int = Field(default=5, gt=1)
    min_history: int = Field(default=6, gt=2)
    z_threshold: float = Field(default=2.0, gt=0.0)
    detection_strategy: DetectionStrategy = "z_score"
    contamination: float = Field(default=0.05, gt=0.0, le=0.5)
    window_size: int | None = None

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
    anomalies: list[TimeseriesAnomaly] = Field(
        default_factory=list[TimeseriesAnomaly]
    )


class TimeseriesQueryRequest(BaseModel):
    """A caller-supplied range query for a metric series."""

    knowledge_base_id: str
    metric_name: str
    start: datetime
    end: datetime

    @model_validator(mode="after")
    def _validate_range(self) -> TimeseriesQueryRequest:
        if self.end <= self.start:
            raise ValueError("TimeseriesQueryRequest end must be after start.")
        return self


class TimeseriesPoint(BaseModel):
    """A single data point in a returned time-series."""

    observed_at: datetime
    value: float


class MetricTimeseriesResponse(BaseModel):
    """A range-bounded list of timeseries data points."""

    knowledge_base_id: str
    metric_name: str
    start: datetime
    end: datetime
    points: list[TimeseriesPoint] = Field(default_factory=list[TimeseriesPoint])


__all__ = [
    "DetectionStrategy",
    "MetricTimeseriesResponse",
    "TimeseriesAnalysisRequest",
    "TimeseriesAnalysisResponse",
    "TimeseriesAnomaly",
    "TimeseriesPoint",
    "TimeseriesQueryRequest",
]
