"""Adapter-level protocols for time-series analytics."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from analytics.timeseries.models import TimeSeriesSeries


@runtime_checkable
class TimeSeriesHistorySourceProtocol(Protocol):
    """Load historical observations for one entity metric."""

    # TODO(production): Extend with batch/streaming and date range filtering:
    # - load_series(kb_id, entity_id, metric_name, start, end) -> TimeSeriesSeries
    # - load_multiple(kb_id, entity_ids, metric_name) -> list[TimeSeriesSeries]
    # Implement production adapters sourcing data from the graph or time-series DB.

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