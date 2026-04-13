"""Internal transport and workflow models for time-series analysis."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class TimeSeriesObservation(BaseModel):
    """A single timestamped numeric observation."""

    observed_at: datetime
    value: float


class TimeSeriesSeries(BaseModel):
    """A named numeric time series for one entity."""

    knowledge_base_id: str
    entity_id: str
    metric_name: str
    observations: list[TimeSeriesObservation] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_observations(self) -> TimeSeriesSeries:
        if not self.observations:
            raise ValueError("TimeSeriesSeries requires at least one observation.")
        ordered = sorted(self.observations, key=lambda observation: observation.observed_at)
        if ordered != self.observations:
            raise ValueError("TimeSeriesSeries observations must be ordered by observed_at.")
        return self


class AnomalyPoint(BaseModel):
    """An anomalous observation identified by the timeseries service."""

    observed_at: datetime
    observed_value: float
    expected_value: float
    deviation: float = Field(ge=0.0)
    z_score: float = Field(ge=0.0)


class TimeSeriesAnalysisResult(BaseModel):
    """Internal result returned after analyzing a single time series."""

    request_id: str
    knowledge_base_id: str
    entity_id: str
    metric_name: str
    observation_count: int = Field(ge=0)
    anomaly_count: int = Field(ge=0)
    anomalies: list[AnomalyPoint] = Field(default_factory=list)


__all__ = [
    "AnomalyPoint",
    "TimeSeriesAnalysisResult",
    "TimeSeriesObservation",
    "TimeSeriesSeries",
]