"""Postgres-backed time-series history source.

Reads the ``entity_metric_history`` hypertable that Flow 2 populates with
graph metrics over time. Depends only on the psycopg-free
``database.ConnectionProvider`` protocol.
"""

from __future__ import annotations

from datetime import datetime
from typing import cast

from analytics.timeseries.exceptions import TimeseriesSourceError
from analytics.timeseries.models import TimeSeriesObservation, TimeSeriesSeries
from database.protocols import ConnectionProvider, Row

_SERIES_SQL = """
    SELECT observed_at, value
    FROM entity_metric_history
    WHERE knowledge_base_id = %s AND entity_id = %s AND metric_name = %s
    ORDER BY observed_at
"""

_RANGE_SQL = """
    SELECT observed_at, value
    FROM entity_metric_history
    WHERE knowledge_base_id = %s AND metric_name = %s
      AND observed_at >= %s AND observed_at <= %s
    ORDER BY observed_at
"""


class PostgresTimeSeriesHistorySource:
    """A ``TimeSeriesHistorySourceProtocol`` backed by ``entity_metric_history``."""

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def load_series(
        self,
        *,
        knowledge_base_id: str,
        entity_id: str,
        metric_name: str,
    ) -> TimeSeriesSeries:
        try:
            with self._provider.connection() as conn:
                rows = conn.execute(
                    _SERIES_SQL, (knowledge_base_id, entity_id, metric_name)
                ).fetchall()
        except Exception as exc:
            raise TimeseriesSourceError("Failed to load time-series history.") from exc
        if not rows:
            raise ValueError(
                "No time series registered for "
                f"knowledge_base_id='{knowledge_base_id}', "
                f"entity_id='{entity_id}', metric_name='{metric_name}'."
            )
        return TimeSeriesSeries(
            knowledge_base_id=knowledge_base_id,
            entity_id=entity_id,
            metric_name=metric_name,
            observations=[_row_to_observation(row) for row in rows],
        )

    def load_metric_range(
        self,
        *,
        knowledge_base_id: str,
        metric_name: str,
        start: datetime,
        end: datetime,
    ) -> list[TimeSeriesObservation]:
        try:
            with self._provider.connection() as conn:
                rows = conn.execute(
                    _RANGE_SQL, (knowledge_base_id, metric_name, start, end)
                ).fetchall()
        except Exception as exc:
            raise TimeseriesSourceError("Failed to load metric range.") from exc
        return [_row_to_observation(row) for row in rows]


def _row_to_observation(row: Row) -> TimeSeriesObservation:
    return TimeSeriesObservation(
        observed_at=cast(datetime, row[0]),
        value=float(cast(float, row[1])),
    )


__all__ = [
    "PostgresTimeSeriesHistorySource",
]
