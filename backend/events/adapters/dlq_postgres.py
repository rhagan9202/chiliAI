"""Postgres-backed DLQ record store (BL-023, events.10).

Mirrors ``ingestion.adapters.postgres.PostgresSourceDocumentStatusStore``'s
connection handling, cursor usage, and JSONB round-tripping style.

``persist`` is an upsert keyed on ``dlq_id``: a repeat ``persist`` call for an
id that already exists replaces every non-PK column via
``ON CONFLICT (dlq_id) DO UPDATE SET`` rather than erroring or duplicating a
row (see ``events.protocols.DlqRecordStore.persist``). Every updated column
in that upsert carries a terminal-state guard —
``CASE WHEN event_dlq.status = 'pending' THEN EXCLUDED.<col> ELSE
event_dlq.<col> END`` — so a ``persist`` against a row that is already
``replayed``/``discarded`` is a no-op: the row (and the value returned) is
unchanged rather than reverted back to ``pending``. ``mark_replayed`` /
``mark_discarded`` are compare-and-swap transitions implemented in SQL: the
``UPDATE ... WHERE dlq_id = %s AND status = 'pending'`` only touches a row
still pending, and returns ``None`` when no row comes back (already
replayed/discarded, or unknown id).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import cast

from database.protocols import ConnectionProvider, Row
from events.dlq_models import DlqRecord, DlqRecordStatus
from events.exceptions import DlqPersistenceError
from shared.utils import utc_now

__all__ = ["PostgresDlqRecordStore"]

_COLUMNS = (
    "dlq_id, event_type, correlation_id, payload, error_message, "
    "error_traceback, retry_count, failed_at, status, replayed_at, created_at"
)

_UPSERT_SQL = f"""
    INSERT INTO event_dlq ({_COLUMNS})
    VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (dlq_id) DO UPDATE SET
        event_type = CASE WHEN event_dlq.status = 'pending'
            THEN EXCLUDED.event_type ELSE event_dlq.event_type END,
        correlation_id = CASE WHEN event_dlq.status = 'pending'
            THEN EXCLUDED.correlation_id ELSE event_dlq.correlation_id END,
        payload = CASE WHEN event_dlq.status = 'pending'
            THEN EXCLUDED.payload ELSE event_dlq.payload END,
        error_message = CASE WHEN event_dlq.status = 'pending'
            THEN EXCLUDED.error_message ELSE event_dlq.error_message END,
        error_traceback = CASE WHEN event_dlq.status = 'pending'
            THEN EXCLUDED.error_traceback ELSE event_dlq.error_traceback END,
        retry_count = CASE WHEN event_dlq.status = 'pending'
            THEN EXCLUDED.retry_count ELSE event_dlq.retry_count END,
        failed_at = CASE WHEN event_dlq.status = 'pending'
            THEN EXCLUDED.failed_at ELSE event_dlq.failed_at END,
        status = CASE WHEN event_dlq.status = 'pending'
            THEN EXCLUDED.status ELSE event_dlq.status END,
        replayed_at = CASE WHEN event_dlq.status = 'pending'
            THEN EXCLUDED.replayed_at ELSE event_dlq.replayed_at END,
        created_at = CASE WHEN event_dlq.status = 'pending'
            THEN EXCLUDED.created_at ELSE event_dlq.created_at END
    RETURNING {_COLUMNS}
"""

_GET_SQL = f"SELECT {_COLUMNS} FROM event_dlq WHERE dlq_id = %s"

_LIST_SQL = f"""
    SELECT {_COLUMNS} FROM event_dlq
    WHERE (%s::text IS NULL OR status = %s::text)
      AND (%s::text IS NULL OR event_type = %s::text)
    ORDER BY created_at DESC, dlq_id DESC
    LIMIT %s OFFSET %s
"""

_COUNT_SQL = """
    SELECT count(*) FROM event_dlq
    WHERE (%s::text IS NULL OR status = %s::text)
      AND (%s::text IS NULL OR event_type = %s::text)
"""

_TRANSITION_SQL = f"""
    UPDATE event_dlq
    SET status = %s, replayed_at = %s
    WHERE dlq_id = %s AND status = 'pending'
    RETURNING {_COLUMNS}
"""


class PostgresDlqRecordStore:
    """A ``DlqRecordStore`` backed by the ``event_dlq`` table."""

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def persist(self, record: DlqRecord) -> DlqRecord:
        params: tuple[object, ...] = (
            record.dlq_id,
            record.event_type,
            record.correlation_id,
            json.dumps(record.payload),
            record.error_message,
            record.error_traceback,
            record.retry_count,
            record.failed_at,
            record.status,
            record.replayed_at,
            record.created_at,
        )
        try:
            with self._provider.connection() as conn:
                row = conn.execute(_UPSERT_SQL, params).fetchone()
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            raise DlqPersistenceError("Failed to persist DLQ record.") from exc
        if row is None:
            raise DlqPersistenceError("DLQ record upsert returned no row.")
        return _row_to_record(row)

    def list(
        self,
        *,
        status: DlqRecordStatus | None = None,
        event_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[DlqRecord], int]:
        try:
            with self._provider.connection() as conn:
                total_row = conn.execute(
                    _COUNT_SQL, (status, status, event_type, event_type)
                ).fetchone()
                total = cast(int, total_row[0]) if total_row is not None else 0
                rows = conn.execute(
                    _LIST_SQL,
                    (status, status, event_type, event_type, limit, offset),
                ).fetchall()
        except Exception as exc:  # noqa: BLE001
            raise DlqPersistenceError("Failed to list DLQ records.") from exc
        return [_row_to_record(row) for row in rows], total

    def get(self, dlq_id: str) -> DlqRecord | None:
        try:
            with self._provider.connection() as conn:
                row = conn.execute(_GET_SQL, (dlq_id,)).fetchone()
        except Exception as exc:  # noqa: BLE001
            raise DlqPersistenceError("Failed to read DLQ record.") from exc
        return _row_to_record(row) if row is not None else None

    def mark_replayed(self, dlq_id: str) -> DlqRecord | None:
        return self._transition(dlq_id, "replayed", replayed_at=utc_now())

    def mark_discarded(self, dlq_id: str) -> DlqRecord | None:
        return self._transition(dlq_id, "discarded", replayed_at=None)

    def _transition(
        self,
        dlq_id: str,
        status: DlqRecordStatus,
        *,
        replayed_at: datetime | None,
    ) -> DlqRecord | None:
        try:
            with self._provider.connection() as conn:
                row = conn.execute(
                    _TRANSITION_SQL, (status, replayed_at, dlq_id)
                ).fetchone()
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            raise DlqPersistenceError(
                "Failed to transition DLQ record status."
            ) from exc
        return _row_to_record(row) if row is not None else None


def _row_to_record(row: Row) -> DlqRecord:
    return DlqRecord(
        dlq_id=cast(str, row[0]),
        event_type=cast(str, row[1]),
        correlation_id=cast(str, row[2]),
        payload=_decode_payload(row[3]),
        error_message=cast(str, row[4]),
        error_traceback=cast(str, row[5]),
        retry_count=cast(int, row[6]),
        failed_at=cast(datetime, row[7]),
        status=_decode_status(row[8]),
        replayed_at=cast("datetime | None", row[9]),
        created_at=cast(datetime, row[10]),
    )


def _decode_payload(value: object) -> dict[str, str]:
    raw = json.loads(value) if isinstance(value, (str, bytes)) else value
    if not isinstance(raw, dict):
        raise DlqPersistenceError("event_dlq.payload did not decode to an object.")
    return {str(key): str(val) for key, val in cast(dict[object, object], raw).items()}


def _decode_status(value: object) -> DlqRecordStatus:
    raw = str(value)
    if raw not in ("pending", "replayed", "discarded"):
        raise DlqPersistenceError(
            f"event_dlq.status has unexpected value '{raw}'."
        )
    return raw
