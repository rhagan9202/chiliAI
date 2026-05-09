"""Service-level protocols for the timeseries analytics module."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from analytics.timeseries.service_models import (
    TimeseriesAnalysisRequest,
    TimeseriesAnalysisResponse,
    TimeseriesQueryRequest,
    TimeseriesResponse,
)


@runtime_checkable
class TimeseriesServiceProtocol(Protocol):
    """Service boundary for time-series anomaly detection."""

    def analyze(self, request: TimeseriesAnalysisRequest) -> TimeseriesAnalysisResponse: ...

    def query_metric(self, request: TimeseriesQueryRequest) -> TimeseriesResponse: ...


__all__ = [
    "TimeseriesServiceProtocol",
]