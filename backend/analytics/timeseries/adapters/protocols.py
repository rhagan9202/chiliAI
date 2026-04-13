"""Adapter-level protocols for time-series analytics."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from analytics.timeseries.models import TimeSeriesSeries


@runtime_checkable
class TimeSeriesHistorySourceProtocol(Protocol):
    """Load historical observations for one entity metric."""

    def load_series(
        self,
        *,
        knowledge_base_id: str,
        entity_id: str,
        metric_name: str,
    ) -> TimeSeriesSeries: ...


__all__ = [
    "TimeSeriesHistorySourceProtocol",
]