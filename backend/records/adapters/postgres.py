"""Postgres-backed raw record store.

This adapter depends only on the psycopg-free ``database.ConnectionProvider``
protocol — it imports no psycopg and is safe to import unconditionally. The
``payload`` column is jsonb; rows are inserted with an explicit ``::jsonb``
cast over a serialized-JSON text parameter so no psycopg JSON adapter is
needed.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Literal, cast

from database.protocols import ConnectionProvider, Row
from records.exceptions import RecordPersistenceError
from records.models import RawRecord

_INSERT_SQL = """
    INSERT INTO raw_records (
        knowledge_base_id, record_type, record_id, payload,
        source_type, source_ref, correlation_id, content_hash, ingested_at
    ) VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s)
    ON CONFLICT (knowledge_base_id, record_type, record_id) DO NOTHING
"""

_SELECT_SQL = """
    SELECT knowledge_base_id, record_type, record_id, payload,
           source_type, source_ref, correlation_id, content_hash, ingested_at
    FROM raw_records
    WHERE knowledge_base_id = %s AND correlation_id = %s
    ORDER BY record_type, record_id
"""


class PostgresRawRecordStore:
    """A ``RawRecordStore`` backed by the ``raw_records`` table."""

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def persist(self, records: list[RawRecord]) -> int:
        if not records:
            return 0
        inserted = 0
        try:
            with self._provider.connection() as conn:
                for record in records:
                    cursor = conn.execute(
                        _INSERT_SQL,
                        (
                            record.knowledge_base_id,
                            record.record_type,
                            record.record_id,
                            json.dumps(record.payload, default=str),
                            record.source_type,
                            record.source_ref,
                            record.correlation_id,
                            record.content_hash,
                            record.ingested_at,
                        ),
                    )
                    inserted += cursor.rowcount
                conn.commit()
        except Exception as exc:
            raise RecordPersistenceError("Failed to persist raw records.") from exc
        return inserted

    def load_batch(
        self, *, knowledge_base_id: str, correlation_id: str
    ) -> list[RawRecord]:
        try:
            with self._provider.connection() as conn:
                rows = conn.execute(
                    _SELECT_SQL, (knowledge_base_id, correlation_id)
                ).fetchall()
        except Exception as exc:
            raise RecordPersistenceError("Failed to load raw records.") from exc
        return [_row_to_record(row) for row in rows]


def _row_to_record(row: Row) -> RawRecord:
    raw_payload = row[3]
    if isinstance(raw_payload, str):
        raw_payload = json.loads(raw_payload)
    if not isinstance(raw_payload, dict):
        raise RecordPersistenceError("raw_records.payload did not decode to an object.")
    payload = cast(dict[str, object], raw_payload)
    raw_source_type = str(row[4])
    if raw_source_type not in {"file_upload", "api_push"}:
        raise RecordPersistenceError(
            f"raw_records.source_type has unexpected value '{raw_source_type}'."
        )
    source_type = cast(Literal["file_upload", "api_push"], raw_source_type)
    return RawRecord(
        knowledge_base_id=str(row[0]),
        record_type=str(row[1]),
        record_id=str(row[2]),
        payload=payload,
        source_type=source_type,
        source_ref=None if row[5] is None else str(row[5]),
        correlation_id=str(row[6]),
        content_hash=str(row[7]),
        ingested_at=cast(datetime, row[8]),
    )


__all__ = [
    "PostgresRawRecordStore",
]
