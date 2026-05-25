"""Postgres-backed entity-metric repository.

Depends only on the psycopg-free ``database.ConnectionProvider`` protocol.
Writes the time-series ``entity_metric_history`` hypertable and upserts the
``entity_metrics_current`` snapshot table in a single transaction.
"""

from __future__ import annotations

from datetime import datetime
from typing import cast

from analytics.metrics.exceptions import MetricsRepositoryError
from analytics.metrics.models import EntityMetricSample, EntityMetricValue
from database.protocols import ConnectionProvider, Row

_HISTORY_INSERT_SQL = """
    INSERT INTO entity_metric_history (
        knowledge_base_id, entity_id, metric_name, value, observed_at, correlation_id
    ) VALUES (%s, %s, %s, %s, %s, %s)
    ON CONFLICT (knowledge_base_id, entity_id, metric_name, observed_at) DO NOTHING
"""

_CURRENT_UPSERT_SQL = """
    INSERT INTO entity_metrics_current (
        knowledge_base_id, entity_id, metric_name, value, updated_at
    ) VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT (knowledge_base_id, entity_id, metric_name)
    DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at
"""

_CURRENT_SELECT_SQL = """
    SELECT knowledge_base_id, entity_id, metric_name, value, updated_at
    FROM entity_metrics_current
    WHERE knowledge_base_id = %s AND entity_id = %s
    ORDER BY metric_name
"""


class PostgresEntityMetricRepository:
    """An ``EntityMetricRepository`` backed by the two metric tables."""

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def record_metrics(self, samples: list[EntityMetricSample]) -> int:
        if not samples:
            return 0
        written = 0
        try:
            with self._provider.connection() as conn:
                for sample in samples:
                    cursor = conn.execute(
                        _HISTORY_INSERT_SQL,
                        (
                            sample.knowledge_base_id,
                            sample.entity_id,
                            sample.metric_name,
                            sample.value,
                            sample.observed_at,
                            sample.correlation_id,
                        ),
                    )
                    written += cursor.rowcount
                    conn.execute(
                        _CURRENT_UPSERT_SQL,
                        (
                            sample.knowledge_base_id,
                            sample.entity_id,
                            sample.metric_name,
                            sample.value,
                            sample.observed_at,
                        ),
                    )
                conn.commit()
        except Exception as exc:
            raise MetricsRepositoryError("Failed to record entity metrics.") from exc
        return written

    def load_current_metrics(
        self, *, knowledge_base_id: str, entity_id: str
    ) -> list[EntityMetricValue]:
        try:
            with self._provider.connection() as conn:
                rows = conn.execute(
                    _CURRENT_SELECT_SQL, (knowledge_base_id, entity_id)
                ).fetchall()
        except Exception as exc:
            raise MetricsRepositoryError("Failed to load current metrics.") from exc
        return [_row_to_value(row) for row in rows]


def _row_to_value(row: Row) -> EntityMetricValue:
    return EntityMetricValue(
        knowledge_base_id=str(row[0]),
        entity_id=str(row[1]),
        metric_name=str(row[2]),
        value=float(cast(float, row[3])),
        updated_at=cast(datetime, row[4]),
    )


__all__ = [
    "PostgresEntityMetricRepository",
]
