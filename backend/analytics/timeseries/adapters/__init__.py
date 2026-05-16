"""Timeseries adapters."""

from __future__ import annotations

from analytics.timeseries.adapters.in_memory import InMemoryTimeSeriesHistorySource
from analytics.timeseries.adapters.postgres import PostgresTimeSeriesHistorySource
from analytics.timeseries.adapters.protocols import TimeSeriesHistorySourceProtocol

__all__ = [
    "InMemoryTimeSeriesHistorySource",
    "PostgresTimeSeriesHistorySource",
    "TimeSeriesHistorySourceProtocol",
]
