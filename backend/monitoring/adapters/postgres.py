"""Postgres-backed observation writer (write side of the observations table).

Depends only on the psycopg-free ``database.ConnectionProvider`` protocol. The
read-side ``ObservationSourceProtocol`` adapter against the same table is
added in Plan C.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, cast

from database.protocols import ConnectionProvider, Row
from monitoring.exceptions import AlertLifecycleError, MonitoringSourceError
from monitoring.lifecycle import validate_alert_transition
from monitoring.models import (
    AlertHistoryRecord,
    AlertTriageEvent,
    MonitoringBatch,
    MonitoringObservation,
)

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
        title, reasoning, metric_name, evidence_pack_id, created_at, updated_at,
        entity_label, confidence, tags, assignee, generation_metadata, triage_history
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb, %s::jsonb)
    ON CONFLICT (knowledge_base_id, alert_id) DO NOTHING
"""

_ALERT_COUNT_OPEN_SQL = """
    SELECT count(*) FROM alert_history
    WHERE knowledge_base_id = %s AND entity_id = %s AND status = 'open'
"""

_ALERT_COLUMNS = (
    "knowledge_base_id, alert_id, entity_id, entity_type, severity, status, "
    "title, reasoning, metric_name, evidence_pack_id, created_at, updated_at, "
    "entity_label, confidence, tags, assignee, generation_metadata, triage_history"
)


# Both queries below match on alert_id alone even though the table's PK is
# the composite (knowledge_base_id, alert_id): alert_id is a UUID minted
# upstream and globally unique in practice, so an alert_id-only lookup never
# ambiguously spans knowledge bases. The composite PK exists solely for the
# writer's per-kb idempotency (ON CONFLICT DO NOTHING), not for uniqueness.
_ALERT_GET_SQL = f"""
    SELECT {_ALERT_COLUMNS} FROM alert_history WHERE alert_id = %s
"""

_ALERT_GET_SCOPED_SQL = f"""
    SELECT {_ALERT_COLUMNS} FROM alert_history
    WHERE knowledge_base_id = %s AND alert_id = %s
"""

_ALERT_ACK_SQL = f"""
    UPDATE alert_history
    SET status = 'acknowledged', updated_at = %s, triage_history = triage_history || %s::jsonb
    WHERE alert_id = %s
    RETURNING {_ALERT_COLUMNS}
"""

_ALERT_ACK_SCOPED_SQL = f"""
    UPDATE alert_history
    SET status = 'acknowledged', updated_at = %s, triage_history = triage_history || %s::jsonb
    WHERE knowledge_base_id = %s AND alert_id = %s
    RETURNING {_ALERT_COLUMNS}
"""

_ALERT_ASSIGN_SQL = f"""
    UPDATE alert_history
    SET assignee = %s, updated_at = %s, triage_history = triage_history || %s::jsonb
    WHERE knowledge_base_id = %s AND alert_id = %s
    RETURNING {_ALERT_COLUMNS}
"""

_ALERT_STATUS_SQL = f"""
    UPDATE alert_history
    SET status = %s, updated_at = %s, triage_history = triage_history || %s::jsonb
    WHERE knowledge_base_id = %s AND alert_id = %s
    RETURNING {_ALERT_COLUMNS}
"""

_ALERT_COUNT_BY_STATUSES_SQL = "SELECT count(*) FROM alert_history WHERE status = ANY(%s)"

_DELETE_OBSERVATIONS_BY_KB_SQL = "DELETE FROM observations WHERE knowledge_base_id = %s"

_DELETE_ALERT_HISTORY_BY_KB_SQL = "DELETE FROM alert_history WHERE knowledge_base_id = %s"


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

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        try:
            with self._provider.connection() as conn:
                cursor = conn.execute(
                    _DELETE_OBSERVATIONS_BY_KB_SQL, (knowledge_base_id,)
                )
                conn.commit()
                return cursor.rowcount
        except Exception as exc:
            raise MonitoringSourceError("Failed to delete observations.") from exc


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
                            record.entity_label,
                            record.confidence,
                            json.dumps(record.tags),
                            record.assignee,
                            _encode_generation_metadata(record.generation_metadata),
                            _encode_triage_history(record.triage_history),
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

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        try:
            with self._provider.connection() as conn:
                cursor = conn.execute(
                    _DELETE_ALERT_HISTORY_BY_KB_SQL, (knowledge_base_id,)
                )
                conn.commit()
                return cursor.rowcount
        except Exception as exc:
            raise MonitoringSourceError("Failed to delete alert history.") from exc

    def list_alerts(
        self,
        *,
        knowledge_base_id: str | None = None,
        statuses: list[str] | None = None,
        severities: list[str] | None = None,
        tags: list[str] | None = None,
        created_from: str | None = None,
        created_to: str | None = None,
        evidence: str | None = None,
        freshness: str | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[AlertHistoryRecord], int]:
        clauses: list[str] = []
        params: list[object] = []
        if statuses:
            clauses.append("status = ANY(%s)")
            params.append(list(statuses))
        if severities:
            clauses.append("severity = ANY(%s)")
            params.append(list(severities))
        if tags:
            clauses.append(
                "EXISTS (SELECT 1 FROM jsonb_array_elements_text(tags) AS tag(value) "
                "WHERE tag.value = ANY(%s))"
            )
            params.append(list(tags))
        if created_from is not None:
            clauses.append("created_at::date >= %s")
            params.append(created_from)
        if created_to is not None:
            clauses.append("created_at::date <= %s")
            params.append(created_to)
        if evidence == "with_evidence":
            clauses.append("evidence_pack_id IS NOT NULL")
        elif evidence == "without_evidence":
            clauses.append("evidence_pack_id IS NULL")
        if freshness == "fresh":
            clauses.append("updated_at >= now() - interval '14 days'")
        elif freshness == "stale":
            clauses.append("updated_at < now() - interval '14 days'")
        if knowledge_base_id is not None:
            clauses.append("knowledge_base_id = %s")
            params.append(knowledge_base_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        try:
            with self._provider.connection() as conn:
                total_row = conn.execute(
                    f"SELECT count(*) FROM alert_history {where}", tuple(params)
                ).fetchone()
                total = 0 if total_row is None else int(cast(int, total_row[0]))
                rows = conn.execute(
                    f"SELECT {_ALERT_COLUMNS} FROM alert_history {where} "
                    "ORDER BY created_at DESC, alert_id DESC LIMIT %s OFFSET %s",
                    (*params, limit, offset),
                ).fetchall()
        except Exception as exc:
            raise MonitoringSourceError("Failed to list alert history.") from exc
        return [_row_to_alert_record(row) for row in rows], total

    def get_alert(self, alert_id: str) -> AlertHistoryRecord | None:
        try:
            with self._provider.connection() as conn:
                row = conn.execute(_ALERT_GET_SQL, (alert_id,)).fetchone()
        except Exception as exc:
            raise MonitoringSourceError("Failed to read alert history.") from exc
        return None if row is None else _row_to_alert_record(row)

    def acknowledge(
        self,
        alert_id: str,
        *,
        knowledge_base_id: str | None = None,
        actor: str = "system",
    ) -> AlertHistoryRecord | None:
        try:
            with self._provider.connection() as conn:
                existing = conn.execute(
                    _ALERT_GET_SCOPED_SQL
                    if knowledge_base_id is not None
                    else _ALERT_GET_SQL,
                    (knowledge_base_id, alert_id)
                    if knowledge_base_id is not None
                    else (alert_id,),
                ).fetchone()
                if existing is None:
                    return None
                record = _row_to_alert_record(existing)
                validate_alert_transition(record.status, "acknowledged")
                event = AlertTriageEvent(
                    event_type="status_changed",
                    actor=actor,
                    from_status=record.status,
                    to_status="acknowledged",
                )
                row = conn.execute(
                    _ALERT_ACK_SCOPED_SQL
                    if knowledge_base_id is not None
                    else _ALERT_ACK_SQL,
                    (
                        event.occurred_at,
                        _encode_triage_history([event]),
                        knowledge_base_id,
                        alert_id,
                    )
                    if knowledge_base_id is not None
                    else (
                        event.occurred_at,
                        _encode_triage_history([event]),
                        alert_id,
                    ),
                ).fetchone()
                conn.commit()
        except AlertLifecycleError:
            raise
        except Exception as exc:
            raise MonitoringSourceError("Failed to acknowledge alert.") from exc
        return None if row is None else _row_to_alert_record(row)

    def assign(
        self,
        alert_id: str,
        *,
        knowledge_base_id: str,
        assignee: str | None,
        actor: str,
    ) -> AlertHistoryRecord | None:
        event = AlertTriageEvent(
            event_type="assigned",
            actor=actor,
            assignee=assignee,
        )
        try:
            with self._provider.connection() as conn:
                row = conn.execute(
                    _ALERT_ASSIGN_SQL,
                    (
                        assignee,
                        event.occurred_at,
                        _encode_triage_history([event]),
                        knowledge_base_id,
                        alert_id,
                    ),
                ).fetchone()
                conn.commit()
        except Exception as exc:
            raise MonitoringSourceError("Failed to assign alert.") from exc
        return None if row is None else _row_to_alert_record(row)

    def transition_status(
        self,
        alert_id: str,
        *,
        knowledge_base_id: str,
        status: str,
        actor: str,
        reason: str | None = None,
    ) -> AlertHistoryRecord | None:
        try:
            with self._provider.connection() as conn:
                existing = conn.execute(
                    _ALERT_GET_SCOPED_SQL, (knowledge_base_id, alert_id)
                ).fetchone()
                if existing is None:
                    return None
                record = _row_to_alert_record(existing)
                validate_alert_transition(record.status, status)
                event = AlertTriageEvent(
                    event_type="status_changed",
                    actor=actor,
                    from_status=record.status,
                    to_status=status,
                    reason=reason,
                )
                row = conn.execute(
                    _ALERT_STATUS_SQL,
                    (
                        status,
                        event.occurred_at,
                        _encode_triage_history([event]),
                        knowledge_base_id,
                        alert_id,
                    ),
                ).fetchone()
                conn.commit()
        except AlertLifecycleError:
            raise
        except Exception as exc:
            raise MonitoringSourceError("Failed to transition alert status.") from exc
        return None if row is None else _row_to_alert_record(row)

    def count_by_statuses(self, statuses: set[str]) -> int:
        try:
            with self._provider.connection() as conn:
                row = conn.execute(
                    _ALERT_COUNT_BY_STATUSES_SQL, (list(statuses),)
                ).fetchone()
        except Exception as exc:
            raise MonitoringSourceError("Failed to count alerts by status.") from exc
        return 0 if row is None else int(cast(int, row[0]))


def _row_to_alert_record(row: Row) -> AlertHistoryRecord:
    return AlertHistoryRecord(
        knowledge_base_id=cast(str, row[0]),
        alert_id=cast(str, row[1]),
        entity_id=cast(str, row[2]),
        entity_type=cast(str, row[3]),
        severity=cast(str, row[4]),
        status=cast(str, row[5]),
        title=cast(str, row[6]),
        reasoning=cast(str, row[7]),
        metric_name=cast(str, row[8]),
        evidence_pack_id=None if row[9] is None else cast(str, row[9]),
        created_at=cast(datetime, row[10]),
        updated_at=cast(datetime, row[11]),
        entity_label=cast(str, row[12]),
        confidence=float(cast(float, row[13])),
        tags=_decode_tags(row[14]),
        assignee=None if row[15] is None else cast(str, row[15]),
        generation_metadata=_decode_generation_metadata(row[16]),
        triage_history=_decode_triage_history(row[17]),
    )


def _decode_tags(value: object) -> list[str]:
    decoded = json.loads(value) if isinstance(value, (str, bytes)) else value
    return cast(list[str], decoded or [])


def _encode_triage_history(events: list[AlertTriageEvent]) -> str:
    return json.dumps([event.model_dump(mode="json") for event in events])


def _encode_generation_metadata(metadata: dict[str, Any]) -> str:
    return json.dumps(metadata)


def _decode_generation_metadata(value: object) -> dict[str, Any]:
    decoded = json.loads(value) if isinstance(value, (str, bytes)) else value
    return cast(dict[str, Any], decoded or {})


def _decode_triage_history(value: object) -> list[AlertTriageEvent]:
    decoded = json.loads(value) if isinstance(value, (str, bytes)) else value
    return [
        AlertTriageEvent.model_validate(item)
        for item in cast(list[object], decoded or [])
    ]


__all__ = [
    "PostgresAlertHistoryStore",
    "PostgresObservationSource",
    "PostgresObservationStore",
]
