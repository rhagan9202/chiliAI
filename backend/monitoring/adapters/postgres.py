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
from monitoring.models import MonitoringBatch, MonitoringObservation

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


__all__ = [
    "PostgresObservationSource",
    "PostgresObservationStore",
]
