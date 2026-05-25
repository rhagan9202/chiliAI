"""Postgres-backed observation writer (write side of the observations table).

Depends only on the psycopg-free ``database.ConnectionProvider`` protocol. The
read-side ``ObservationSourceProtocol`` adapter against the same table is
added in Plan C.
"""

from __future__ import annotations

from datetime import datetime
from typing import cast

from database.protocols import ConnectionProvider, Row
from monitoring.exceptions import MonitoringSourceError
from monitoring.models import AlertHistoryRecord, MonitoringBatch, MonitoringObservation

_INSERT_SQL = """
    INSERT INTO observations (
        knowledge_base_id, entity_id, entity_type, metric_name,
        score, observed_at, rationale, evidence_pack_id, batch_id, correlation_id
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (knowledge_base_id, entity_id, metric_name, observed_at) DO NOTHING
"""

_SELECT_BATCH_SQL = """
    SELECT entity_id, entity_type, metric_name, score, observed_at,
           rationale, evidence_pack_id
    FROM observations
    WHERE knowledge_base_id = %s AND batch_id = %s
    ORDER BY observed_at, entity_id, metric_name
"""

_ALERT_INSERT_SQL = """
    INSERT INTO alert_history (
        knowledge_base_id, alert_id, entity_id, entity_type, severity, status,
        title, reasoning, metric_name, evidence_pack_id, created_at, updated_at
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (knowledge_base_id, alert_id) DO NOTHING
"""

_ALERT_COUNT_OPEN_SQL = """
    SELECT count(*) FROM alert_history
    WHERE knowledge_base_id = %s AND entity_id = %s AND status = 'open'
"""


class PostgresObservationStore:
    """An ``ObservationWriter`` backed by the ``observations`` hypertable."""

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def write_observations(
        self, batch: MonitoringBatch, *, correlation_id: str
    ) -> int:
        written = 0
        try:
            with self._provider.connection() as conn:
                for observation in batch.observations:
                    cursor = conn.execute(
                        _INSERT_SQL,
                        (
                            batch.knowledge_base_id,
                            observation.entity_id,
                            observation.entity_type,
                            observation.metric_name,
                            observation.score,
                            observation.observed_at,
                            observation.rationale,
                            observation.evidence_pack_id,
                            batch.batch_id,
                            correlation_id,
                        ),
                    )
                    written += cursor.rowcount
                conn.commit()
        except Exception as exc:
            raise MonitoringSourceError("Failed to write observations.") from exc
        return written


class PostgresObservationSource:
    """An ``ObservationSourceProtocol`` backed by the ``observations`` table.

    ``load_batch`` resolves the run by ``batch_id`` (the ingest correlation
    id), using the existing ``ix_observations_batch`` index.
    """

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def load_batch(self, *, knowledge_base_id: str, batch_id: str) -> MonitoringBatch:
        try:
            with self._provider.connection() as conn:
                rows = conn.execute(
                    _SELECT_BATCH_SQL, (knowledge_base_id, batch_id)
                ).fetchall()
        except Exception as exc:
            raise MonitoringSourceError("Failed to load monitoring batch.") from exc
        if not rows:
            raise ValueError(
                f"No monitoring batch registered for "
                f"knowledge_base_id='{knowledge_base_id}' and batch_id='{batch_id}'."
            )
        return MonitoringBatch(
            knowledge_base_id=knowledge_base_id,
            batch_id=batch_id,
            observations=[_row_to_observation(row) for row in rows],
        )


def _row_to_observation(row: Row) -> MonitoringObservation:
    return MonitoringObservation(
        entity_id=str(row[0]),
        entity_type=str(row[1]),
        metric_name=str(row[2]),
        score=float(cast(float, row[3])),
        observed_at=cast(datetime, row[4]),
        rationale=str(row[5]),
        evidence_pack_id=None if row[6] is None else str(row[6]),
    )


class PostgresAlertHistoryStore:
    """An ``AlertHistoryWriter`` backed by the ``alert_history`` table."""

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def write_alerts(self, records: list[AlertHistoryRecord]) -> int:
        if not records:
            return 0
        written = 0
        try:
            with self._provider.connection() as conn:
                for record in records:
                    cursor = conn.execute(
                        _ALERT_INSERT_SQL,
                        (
                            record.knowledge_base_id,
                            record.alert_id,
                            record.entity_id,
                            record.entity_type,
                            record.severity,
                            record.status,
                            record.title,
                            record.reasoning,
                            record.metric_name,
                            record.evidence_pack_id,
                            record.created_at,
                            record.updated_at,
                        ),
                    )
                    written += cursor.rowcount
                conn.commit()
        except Exception as exc:
            raise MonitoringSourceError("Failed to write alert history.") from exc
        return written

    def count_open_alerts(
        self, *, knowledge_base_id: str, entity_id: str
    ) -> int:
        try:
            with self._provider.connection() as conn:
                row = conn.execute(
                    _ALERT_COUNT_OPEN_SQL, (knowledge_base_id, entity_id)
                ).fetchone()
        except Exception as exc:
            raise MonitoringSourceError("Failed to count open alerts.") from exc
        return 0 if row is None else int(cast(int, row[0]))


__all__ = [
    "PostgresAlertHistoryStore",
    "PostgresObservationSource",
    "PostgresObservationStore",
]
