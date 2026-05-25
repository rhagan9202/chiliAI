"""Public exports for the timeseries analytics module."""

from __future__ import annotations

from analytics.timeseries.adapters.in_memory import InMemoryTimeSeriesHistorySource
from analytics.timeseries.adapters.postgres import PostgresTimeSeriesHistorySource
from analytics.timeseries.adapters.protocols import TimeSeriesHistorySourceProtocol
from analytics.timeseries.exceptions import (
    TimeseriesConfigurationError,
    TimeseriesError,
    TimeseriesInsufficientHistoryError,
    TimeseriesSourceError,
)
from analytics.timeseries.models import (
    AnomalyPoint,
    TimeSeriesAnalysisResult,
    TimeSeriesObservation,
    TimeSeriesSeries,
)
from analytics.timeseries.protocols import TimeseriesServiceProtocol
from analytics.timeseries.service import TimeseriesService, create_timeseries_service
from analytics.timeseries.service_models import (
    MetricTimeseriesResponse,
    TimeseriesAnalysisRequest,
    TimeseriesAnalysisResponse,
    TimeseriesAnomaly,
    TimeseriesPoint,
    TimeseriesQueryRequest,
)

__all__ = [
    "AnomalyPoint",
    "InMemoryTimeSeriesHistorySource",
    "MetricTimeseriesResponse",
    "PostgresTimeSeriesHistorySource",
    "TimeSeriesAnalysisResult",
    "TimeSeriesHistorySourceProtocol",
    "TimeSeriesObservation",
    "TimeSeriesSeries",
    "TimeseriesAnalysisRequest",
    "TimeseriesAnalysisResponse",
    "TimeseriesAnomaly",
    "TimeseriesConfigurationError",
    "TimeseriesError",
    "TimeseriesInsufficientHistoryError",
    "TimeseriesPoint",
    "TimeseriesQueryRequest",
    "TimeseriesService",
    "TimeseriesServiceProtocol",
    "TimeseriesSourceError",
    "create_timeseries_service",
]
