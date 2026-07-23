"""Postgres-backed time-series history source.

Reads the ``entity_metric_history`` hypertable that Flow 2 populates with
graph metrics over time. Depends only on the psycopg-free
``database.ConnectionProvider`` protocol.
"""

from __future__ import annotations

from datetime import datetime
from typing import cast

from analytics.timeseries.exceptions import TimeseriesSourceError
from analytics.timeseries.models import (
    TimeSeriesObservation,
    TimeSeriesSeries,
    TimeseriesAnomalyRecord,
)
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


_ANOMALY_UPSERT_SQL = """
    INSERT INTO timeseries_anomalies (
        knowledge_base_id, entity_id, metric_name, observed_at,
        observed_value, expected_value, z_score, severity,
        detection_strategy, correlation_id
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (knowledge_base_id, entity_id, metric_name, observed_at)
    DO UPDATE SET
        observed_value = EXCLUDED.observed_value,
        expected_value = EXCLUDED.expected_value,
        z_score = EXCLUDED.z_score,
        severity = EXCLUDED.severity,
        detection_strategy = EXCLUDED.detection_strategy,
        correlation_id = EXCLUDED.correlation_id,
        detected_at = now()
"""

_ANOMALY_SELECT_SQL = """
    SELECT observed_at, observed_value, expected_value, z_score, severity,
           detection_strategy, correlation_id
    FROM timeseries_anomalies
    WHERE knowledge_base_id = %s AND entity_id = %s AND metric_name = %s
    ORDER BY observed_at
"""

_ANOMALY_DELETE_BY_KB_SQL = (
    "DELETE FROM timeseries_anomalies WHERE knowledge_base_id = %s"
)


class PostgresTimeseriesAnomalyStore:
    """A ``TimeseriesAnomalyStoreProtocol`` backed by ``timeseries_anomalies``."""

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def write_anomalies(self, records: list[TimeseriesAnomalyRecord]) -> int:
        if not records:
            return 0
        try:
            with self._provider.connection() as conn:
                for record in records:
                    conn.execute(
                        _ANOMALY_UPSERT_SQL,
                        (
                            record.knowledge_base_id,
                            record.entity_id,
                            record.metric_name,
                            record.observed_at,
                            record.observed_value,
                            record.expected_value,
                            record.z_score,
                            record.severity,
                            record.detection_strategy,
                            record.correlation_id,
                        ),
                    )
                conn.commit()
        except Exception as exc:
            raise TimeseriesSourceError("Failed to write timeseries anomalies.") from exc
        return len(records)

    def load_anomalies(
        self, *, knowledge_base_id: str, entity_id: str, metric_name: str
    ) -> list[TimeseriesAnomalyRecord]:
        try:
            with self._provider.connection() as conn:
                rows = conn.execute(
                    _ANOMALY_SELECT_SQL, (knowledge_base_id, entity_id, metric_name)
                ).fetchall()
        except Exception as exc:
            raise TimeseriesSourceError("Failed to load timeseries anomalies.") from exc
        return [
            TimeseriesAnomalyRecord(
                knowledge_base_id=knowledge_base_id,
                entity_id=entity_id,
                metric_name=metric_name,
                observed_at=cast(datetime, row[0]),
                observed_value=float(cast(float, row[1])),
                expected_value=float(cast(float, row[2])),
                z_score=float(cast(float, row[3])),
                severity=float(cast(float, row[4])),
                detection_strategy=cast(str, row[5]),
                correlation_id=cast(str, row[6]),
            )
            for row in rows
        ]

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        try:
            with self._provider.connection() as conn:
                cursor = conn.execute(_ANOMALY_DELETE_BY_KB_SQL, (knowledge_base_id,))
                conn.commit()
                return cursor.rowcount
        except Exception as exc:
            raise TimeseriesSourceError("Failed to delete timeseries anomalies.") from exc


__all__ = [
    "PostgresTimeSeriesHistorySource",
    "PostgresTimeseriesAnomalyStore",
]
