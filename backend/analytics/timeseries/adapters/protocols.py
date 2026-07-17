"""Adapter-level protocols for time-series analytics."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from analytics.timeseries.models import (
    TimeSeriesObservation,
    TimeSeriesSeries,
    TimeseriesAnomalyRecord,
)


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

    def load_metric_range(
        self,
        *,
        knowledge_base_id: str,
        metric_name: str,
        start: datetime,
        end: datetime,
    ) -> list[TimeSeriesObservation]: ...


@runtime_checkable
class TimeseriesAnomalyStoreProtocol(Protocol):
    """Persist and read detected series anomalies idempotently."""

    def write_anomalies(self, records: list[TimeseriesAnomalyRecord]) -> int:
        """Upsert each record on its (kb, entity, metric, observed_at) key."""
        ...

    def load_anomalies(
        self, *, knowledge_base_id: str, entity_id: str, metric_name: str
    ) -> list[TimeseriesAnomalyRecord]:
        """Return the entity metric's anomalies ordered by observed_at."""
        ...

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        """Delete all anomalies for a knowledge base; return rows removed."""
        ...


__all__ = [
    "TimeSeriesHistorySourceProtocol",
    "TimeseriesAnomalyStoreProtocol",
]