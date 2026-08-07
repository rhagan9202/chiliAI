"""Postgres-backed connector repository.

Durable state for connector definitions, their sync runs, and quarantined
source rows. The in-memory adapter is process-lifetime, so every registered
connector and every sync run vanished on API restart — and a sync run that
survives a restart is the whole point of `source_cursor`.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import cast

from connectors.models import (
    ConnectorConfigValue,
    ConnectorDefinition,
    ConnectorDefinitionCreate,
    ConnectorDefinitionPage,
    ConnectorMappingRef,
    ConnectorQuarantinePage,
    ConnectorQuarantineRecord,
    ConnectorQuarantineRecordCreate,
    ConnectorSchedule,
    ConnectorScheduleMode,
    ConnectorSourceType,
    ConnectorStatus,
    ConnectorSyncCounters,
    ConnectorSyncRun,
    ConnectorSyncRunCreate,
    ConnectorSyncRunPage,
    ConnectorSyncRunUpdate,
    ConnectorSyncStatus,
)
from database.protocols import ConnectionProvider, Row
from shared.utils import generate_id, utc_now

__all__ = ["PostgresConnectorRepository"]

_DEFINITION_COLUMNS = (
    "connector_id, knowledge_base_id, name, source_type, domain_name, status, "
    "schedule_mode, schedule_expression, credentials_ref, config, mapping, "
    "created_at, updated_at"
)

_RUN_COLUMNS = (
    "run_id, connector_id, knowledge_base_id, requested_by, status, counters, "
    "idempotency_key, ingest_correlation_id, source_cursor, error_message, "
    "started_at, completed_at, updated_at"
)

_QUARANTINE_COLUMNS = (
    "quarantine_id, run_id, connector_id, knowledge_base_id, source_record_id, "
    "reason, raw_ref, created_at"
)

_TERMINAL_STATUSES: frozenset[str] = frozenset({"completed", "failed", "canceled"})


class PostgresConnectorRepository:
    """Persist connector definitions, sync runs, and quarantine in Postgres."""

    def __init__(self, connection_provider: ConnectionProvider) -> None:
        self._provider = connection_provider

    # --- definitions --------------------------------------------------------

    def save_definition(
        self, payload: ConnectorDefinitionCreate
    ) -> ConnectorDefinition:
        definition = ConnectorDefinition(**payload.model_dump())
        with self._provider.connection() as conn:
            # DO NOTHING, not DO UPDATE: the in-memory adapter returns the
            # existing definition untouched on re-save, and the two backends
            # must not disagree about whether a re-register overwrites.
            conn.execute(
                f"""
                INSERT INTO connectors ({_DEFINITION_COLUMNS})
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (knowledge_base_id, connector_id) DO NOTHING
                """,
                (
                    definition.connector_id,
                    definition.knowledge_base_id,
                    definition.name,
                    definition.source_type,
                    definition.domain_name,
                    definition.status,
                    definition.schedule.mode,
                    definition.schedule.expression,
                    definition.credentials_ref,
                    json.dumps(definition.config),
                    json.dumps(definition.mapping.model_dump()),
                    definition.created_at,
                    definition.updated_at,
                ),
            )
            conn.commit()
        stored = self.get_definition(
            knowledge_base_id=definition.knowledge_base_id,
            connector_id=definition.connector_id,
        )
        if stored is None:
            raise ValueError(
                f"Connector '{definition.connector_id}' was not stored."
            )
        return stored

    def get_definition(
        self,
        *,
        knowledge_base_id: str,
        connector_id: str,
    ) -> ConnectorDefinition | None:
        with self._provider.connection() as conn:
            row = conn.execute(
                f"""
                SELECT {_DEFINITION_COLUMNS} FROM connectors
                 WHERE knowledge_base_id = %s AND connector_id = %s
                """,
                (knowledge_base_id, connector_id),
            ).fetchone()
        return None if row is None else _definition_from_row(row)

    def list_definitions(
        self,
        *,
        knowledge_base_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ConnectorDefinitionPage:
        normalized_limit, normalized_offset = _page_bounds(limit, offset)
        clauses: list[str] = []
        params: list[object] = []
        if knowledge_base_id is not None:
            clauses.append("knowledge_base_id = %s")
            params.append(knowledge_base_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._provider.connection() as conn:
            total_row = conn.execute(
                f"SELECT count(*) FROM connectors {where}", tuple(params)
            ).fetchone()
            rows = conn.execute(
                f"""
                SELECT {_DEFINITION_COLUMNS} FROM connectors {where}
                 ORDER BY knowledge_base_id ASC, connector_id ASC
                 LIMIT %s OFFSET %s
                """,
                (*params, normalized_limit, normalized_offset),
            ).fetchall()
        return ConnectorDefinitionPage(
            items=[_definition_from_row(row) for row in rows],
            total_items=_count(total_row),
            limit=normalized_limit,
            offset=normalized_offset,
        )

    # --- sync runs ----------------------------------------------------------

    def create_run(self, payload: ConnectorSyncRunCreate) -> ConnectorSyncRun:
        run = ConnectorSyncRun(**payload.model_dump())
        with self._provider.connection() as conn:
            try:
                conn.execute(
                    f"""
                    INSERT INTO connector_sync_runs ({_RUN_COLUMNS})
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        run.run_id,
                        run.connector_id,
                        run.knowledge_base_id,
                        run.requested_by,
                        run.status,
                        json.dumps(run.counters.model_dump()),
                        run.idempotency_key,
                        run.ingest_correlation_id,
                        run.source_cursor,
                        run.error_message,
                        run.started_at,
                        run.completed_at,
                        run.updated_at,
                    ),
                )
                conn.commit()
            except Exception as exc:
                conn.rollback()
                # The partial unique index on (connector_id, idempotency_key)
                # is what makes concurrent sync requests safe; surface it as a
                # ValueError so the service sees one behaviour per backend.
                if _is_unique_violation(exc):
                    raise ValueError(
                        "ConnectorSyncRun idempotency_key already exists for this connector."
                    ) from exc
                raise
        stored = self.get_run(run.run_id)
        if stored is None:
            raise ValueError(f"ConnectorSyncRun '{run.run_id}' was not stored.")
        return stored

    def get_run(self, run_id: str) -> ConnectorSyncRun | None:
        with self._provider.connection() as conn:
            row = conn.execute(
                f"SELECT {_RUN_COLUMNS} FROM connector_sync_runs WHERE run_id = %s",
                (run_id,),
            ).fetchone()
        return None if row is None else _run_from_row(row)

    def claim_sync_run(
        self,
        run_id: str,
        *,
        now: datetime,
    ) -> ConnectorSyncRun | None:
        with self._provider.connection() as conn:
            row = conn.execute(
                f"""
                UPDATE connector_sync_runs
                   SET status = 'running', updated_at = %s
                 WHERE run_id = %s AND status = 'queued'
                RETURNING {_RUN_COLUMNS}
                """,
                (now, run_id),
            ).fetchone()
            conn.commit()
        return None if row is None else _run_from_row(row)

    def update_run(
        self,
        run_id: str,
        update: ConnectorSyncRunUpdate,
    ) -> ConnectorSyncRun:
        assignments: list[str] = []
        params: list[object] = []
        if update.status is not None:
            assignments.append("status = %s")
            params.append(update.status)
        if update.counters is not None:
            assignments.append("counters = %s")
            params.append(json.dumps(update.counters.model_dump()))
        if update.ingest_correlation_id is not None:
            assignments.append("ingest_correlation_id = %s")
            params.append(update.ingest_correlation_id)
        if update.source_cursor is not None:
            assignments.append("source_cursor = %s")
            params.append(update.source_cursor)
        if update.error_message is not None:
            assignments.append("error_message = %s")
            params.append(update.error_message)
        now = utc_now()
        if update.status is not None and update.status in _TERMINAL_STATUSES:
            assignments.append("completed_at = %s")
            params.append(now)
        assignments.append("updated_at = %s")
        params.append(now)

        with self._provider.connection() as conn:
            row = conn.execute(
                f"""
                UPDATE connector_sync_runs SET {", ".join(assignments)}
                 WHERE run_id = %s
                RETURNING {_RUN_COLUMNS}
                """,
                (*params, run_id),
            ).fetchone()
            conn.commit()
        if row is None:
            # Matches the in-memory adapter, which raises KeyError.
            raise KeyError(run_id)
        return _run_from_row(row)

    def list_runs(
        self,
        *,
        connector_id: str | None = None,
        knowledge_base_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ConnectorSyncRunPage:
        normalized_limit, normalized_offset = _page_bounds(limit, offset)
        clauses: list[str] = []
        params: list[object] = []
        if connector_id is not None:
            clauses.append("connector_id = %s")
            params.append(connector_id)
        if knowledge_base_id is not None:
            clauses.append("knowledge_base_id = %s")
            params.append(knowledge_base_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._provider.connection() as conn:
            total_row = conn.execute(
                f"SELECT count(*) FROM connector_sync_runs {where}", tuple(params)
            ).fetchone()
            rows = conn.execute(
                f"""
                SELECT {_RUN_COLUMNS} FROM connector_sync_runs {where}
                 ORDER BY started_at DESC, run_id ASC
                 LIMIT %s OFFSET %s
                """,
                (*params, normalized_limit, normalized_offset),
            ).fetchall()
        return ConnectorSyncRunPage(
            items=[_run_from_row(row) for row in rows],
            total_items=_count(total_row),
            limit=normalized_limit,
            offset=normalized_offset,
        )

    # --- quarantine ---------------------------------------------------------

    def add_quarantine_record(
        self,
        payload: ConnectorQuarantineRecordCreate,
    ) -> ConnectorQuarantineRecord:
        record = ConnectorQuarantineRecord(
            quarantine_id=f"{payload.run_id}:{generate_id()}",
            **payload.model_dump(),
        )
        with self._provider.connection() as conn:
            conn.execute(
                f"""
                INSERT INTO connector_quarantine_records ({_QUARANTINE_COLUMNS})
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    record.quarantine_id,
                    record.run_id,
                    record.connector_id,
                    record.knowledge_base_id,
                    record.source_record_id,
                    record.reason,
                    record.raw_ref,
                    record.created_at,
                ),
            )
            conn.commit()
        return record

    def list_quarantine(
        self,
        *,
        run_id: str | None = None,
        connector_id: str | None = None,
        knowledge_base_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ConnectorQuarantinePage:
        normalized_limit, normalized_offset = _page_bounds(limit, offset)
        clauses: list[str] = []
        params: list[object] = []
        if run_id is not None:
            clauses.append("run_id = %s")
            params.append(run_id)
        if connector_id is not None:
            clauses.append("connector_id = %s")
            params.append(connector_id)
        if knowledge_base_id is not None:
            clauses.append("knowledge_base_id = %s")
            params.append(knowledge_base_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._provider.connection() as conn:
            total_row = conn.execute(
                f"SELECT count(*) FROM connector_quarantine_records {where}",
                tuple(params),
            ).fetchone()
            rows = conn.execute(
                f"""
                SELECT {_QUARANTINE_COLUMNS} FROM connector_quarantine_records {where}
                 ORDER BY run_id ASC, source_record_id ASC
                 LIMIT %s OFFSET %s
                """,
                (*params, normalized_limit, normalized_offset),
            ).fetchall()
        return ConnectorQuarantinePage(
            items=[_quarantine_from_row(row) for row in rows],
            total_items=_count(total_row),
            limit=normalized_limit,
            offset=normalized_offset,
        )


# --- row decoding -----------------------------------------------------------


def _definition_from_row(row: Row) -> ConnectorDefinition:
    return ConnectorDefinition(
        connector_id=str(row[0]),
        knowledge_base_id=str(row[1]),
        name=str(row[2]),
        source_type=cast(ConnectorSourceType, str(row[3])),
        domain_name=None if row[4] is None else str(row[4]),
        status=cast(ConnectorStatus, str(row[5])),
        schedule=ConnectorSchedule(
            mode=cast(ConnectorScheduleMode, str(row[6])),
            expression=None if row[7] is None else str(row[7]),
        ),
        credentials_ref=None if row[8] is None else str(row[8]),
        config=_decode_config(row[9]),
        mapping=ConnectorMappingRef(**_decode_mapping(row[10])),
        created_at=cast(datetime, row[11]),
        updated_at=cast(datetime, row[12]),
    )


def _run_from_row(row: Row) -> ConnectorSyncRun:
    return ConnectorSyncRun(
        run_id=str(row[0]),
        connector_id=str(row[1]),
        knowledge_base_id=str(row[2]),
        requested_by=str(row[3]),
        status=cast(ConnectorSyncStatus, str(row[4])),
        counters=ConnectorSyncCounters(**_decode_counters(row[5])),
        idempotency_key=None if row[6] is None else str(row[6]),
        ingest_correlation_id=None if row[7] is None else str(row[7]),
        source_cursor=None if row[8] is None else str(row[8]),
        error_message=None if row[9] is None else str(row[9]),
        started_at=cast(datetime, row[10]),
        completed_at=None if row[11] is None else cast(datetime, row[11]),
        updated_at=cast(datetime, row[12]),
    )


def _quarantine_from_row(row: Row) -> ConnectorQuarantineRecord:
    return ConnectorQuarantineRecord(
        quarantine_id=str(row[0]),
        run_id=str(row[1]),
        connector_id=str(row[2]),
        knowledge_base_id=str(row[3]),
        source_record_id=str(row[4]),
        reason=str(row[5]),
        raw_ref=None if row[6] is None else str(row[6]),
        created_at=cast(datetime, row[7]),
    )


def _decode_object(value: object, column: str) -> dict[str, object]:
    """Decode a jsonb object column.

    `json.loads` returns `Any`, and narrowing it with `isinstance(x, dict)`
    yields `dict[Unknown, Unknown]` — iterating that is a pyright strict error.
    Pinning the decoded value as `object` and casting after the guard is what
    keeps the type gate green; this exact pattern broke CI for nine sprints.
    """

    decoded: object = (
        json.loads(value) if isinstance(value, (str, bytes, bytearray)) else value
    )
    if decoded is None:
        return {}
    if not isinstance(decoded, dict):
        raise ValueError(f"connectors.{column} did not decode to an object.")
    return cast(dict[str, object], decoded)


def _decode_config(value: object) -> dict[str, ConnectorConfigValue]:
    decoded = _decode_object(value, "config")
    config: dict[str, ConnectorConfigValue] = {}
    for key, item in decoded.items():
        if item is None or isinstance(item, (str, int, float, bool)):
            config[key] = item
        else:
            # A nested object or array cannot be represented by
            # ConnectorConfigValue; refuse rather than silently stringify it.
            raise ValueError(
                f"connectors.config['{key}'] is not a scalar config value."
            )
    return config


def _decode_mapping(value: object) -> dict[str, str]:
    decoded = _decode_object(value, "mapping")
    return {key: str(item) for key, item in decoded.items()}


def _decode_counters(value: object) -> dict[str, int]:
    decoded = _decode_object(value, "counters")
    return {key: int(cast(int, item)) for key, item in decoded.items()}


def _count(row: Row | None) -> int:
    return 0 if row is None else int(cast(int, row[0]))


def _page_bounds(limit: int, offset: int) -> tuple[int, int]:
    return max(limit, 1), max(offset, 0)


def _is_unique_violation(exc: Exception) -> bool:
    return getattr(exc, "sqlstate", None) == "23505"
