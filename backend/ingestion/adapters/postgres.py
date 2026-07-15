"""Postgres-backed document status store (BL-041).

The monotonic-transition semantics enforced here (see
``ingestion.adapters.protocols.SourceDocumentStatusStore``) must stay
behaviorally identical to ``ingestion.adapters.in_memory``:

* ``current_status`` / ``status_rank`` advance only when the incoming rank
  is strictly greater than the stored rank.
* ``dropped_entity_count``, ``dropped_relationship_count``, and
  ``sample_reasons`` are absolute values that overwrite whenever the
  transition carries them (its field is not ``None``), regardless of rank.
* ``last_error`` (and ``updated_at``) also refresh when the transition
  advances the rank, OR when the transition's status is FAILED and its rank
  is ``>=`` the stored rank (a second, newer failure replaces the recorded
  error even though it does not advance the status) — provided the
  transition's ``error_message`` is not ``None``. A lower-rank event after
  FAILED never touches ``last_error``, and a FAILED transition with a
  ``None`` error message never wipes a stored one.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import cast

from database.protocols import ConnectionProvider, Row
from ingestion.exceptions import DocumentStatusPersistenceError
from ingestion.models import (
    STATUS_RANK,
    DocumentStatusTransition,
    IngestionStatus,
    SourceDocumentStatusRecord,
)

__all__ = ["PostgresSourceDocumentStatusStore"]

_COLUMNS = (
    "knowledge_base_id, source_document_id, current_status, status_rank, "
    "last_error, dropped_entity_count, dropped_relationship_count, "
    "sample_reasons, first_event_at, updated_at"
)

_FAILED_STATUS_VALUE = IngestionStatus.FAILED.value

# Monotonic upsert: current_status/status_rank only advance when the incoming
# rank is strictly greater than the stored rank. last_error additionally
# refreshes on a same-or-higher-rank FAILED redelivery (a newer failure
# message), but never on a lower-rank event after FAILED and never when the
# incoming error_message is NULL. Counts and sample_reasons are absolute
# values that overwrite whenever provided, independent of rank (NULL params
# mean "keep existing" — the raw, non-defaulted params are reused in the
# UPDATE SET so that signal survives the INSERT-side COALESCE(..., 0/[]) )).
_APPLY_SQL = f"""
    INSERT INTO source_document_status ({_COLUMNS})
    VALUES (
        %s, %s, %s, %s, %s, COALESCE(%s, 0), COALESCE(%s, 0),
        COALESCE(%s::jsonb, '[]'::jsonb), %s, %s
    )
    ON CONFLICT (knowledge_base_id, source_document_id) DO UPDATE SET
        current_status = CASE
            WHEN EXCLUDED.status_rank > source_document_status.status_rank
            THEN EXCLUDED.current_status
            ELSE source_document_status.current_status
        END,
        last_error = CASE
            WHEN EXCLUDED.last_error IS NOT NULL
                 AND (
                     EXCLUDED.status_rank > source_document_status.status_rank
                     OR (
                         EXCLUDED.current_status = %s
                         AND EXCLUDED.status_rank
                             >= source_document_status.status_rank
                     )
                 )
            THEN EXCLUDED.last_error
            ELSE source_document_status.last_error
        END,
        status_rank = GREATEST(
            source_document_status.status_rank, EXCLUDED.status_rank
        ),
        dropped_entity_count = COALESCE(
            %s, source_document_status.dropped_entity_count
        ),
        dropped_relationship_count = COALESCE(
            %s, source_document_status.dropped_relationship_count
        ),
        sample_reasons = COALESCE(
            %s::jsonb, source_document_status.sample_reasons
        ),
        updated_at = GREATEST(
            source_document_status.updated_at, EXCLUDED.updated_at
        )
    RETURNING {_COLUMNS}
"""

_GET_MANY_SQL = f"""
    SELECT {_COLUMNS} FROM source_document_status
    WHERE knowledge_base_id = %s AND source_document_id = ANY(%s)
"""

_DELETE_BY_KB_SQL = """
    DELETE FROM source_document_status
    WHERE knowledge_base_id = %s
"""

_DELETE_BY_DOCUMENT_SQL = """
    DELETE FROM source_document_status
    WHERE knowledge_base_id = %s AND source_document_id = %s
"""


class PostgresSourceDocumentStatusStore:
    """A ``SourceDocumentStatusStore`` backed by ``source_document_status``."""

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def apply(
        self, transition: DocumentStatusTransition
    ) -> SourceDocumentStatusRecord:
        reasons_json = (
            json.dumps(transition.sample_reasons)
            if transition.sample_reasons is not None
            else None
        )
        params: tuple[object, ...] = (
            transition.knowledge_base_id,
            transition.source_document_id,
            transition.status.value,
            STATUS_RANK[transition.status],
            transition.error_message,
            transition.dropped_entity_count,
            transition.dropped_relationship_count,
            reasons_json,
            transition.occurred_at,
            transition.occurred_at,
            _FAILED_STATUS_VALUE,
            transition.dropped_entity_count,
            transition.dropped_relationship_count,
            reasons_json,
        )
        try:
            with self._provider.connection() as conn:
                row = conn.execute(_APPLY_SQL, params).fetchone()
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            raise DocumentStatusPersistenceError(
                "Failed to apply document status transition."
            ) from exc
        if row is None:
            raise DocumentStatusPersistenceError(
                "Document status upsert returned no row."
            )
        return _row_to_record(row)

    def get_many(
        self,
        *,
        knowledge_base_id: str,
        source_document_ids: list[str],
    ) -> dict[str, SourceDocumentStatusRecord]:
        if not source_document_ids:
            return {}
        try:
            with self._provider.connection() as conn:
                rows = conn.execute(
                    _GET_MANY_SQL, (knowledge_base_id, source_document_ids)
                ).fetchall()
        except Exception as exc:  # noqa: BLE001
            raise DocumentStatusPersistenceError(
                "Failed to read document status rows."
            ) from exc
        records = [_row_to_record(row) for row in rows]
        return {record.source_document_id: record for record in records}

    def list(
        self,
        *,
        knowledge_base_id: str,
        limit: int,
        offset: int,
        status: IngestionStatus | None = None,
    ) -> tuple[list[SourceDocumentStatusRecord], int]:
        where = "WHERE knowledge_base_id = %s"
        params: list[object] = [knowledge_base_id]
        if status is not None:
            where += " AND current_status = %s"
            params.append(status.value)
        try:
            with self._provider.connection() as conn:
                total_row = conn.execute(
                    f"SELECT count(*) FROM source_document_status {where}",
                    tuple(params),
                ).fetchone()
                total = cast(int, total_row[0]) if total_row is not None else 0
                if limit <= 0 or offset < 0:
                    return [], total
                rows = conn.execute(
                    f"SELECT {_COLUMNS} FROM source_document_status {where} "
                    "ORDER BY updated_at DESC, source_document_id DESC "
                    "LIMIT %s OFFSET %s",
                    (*params, limit, offset),
                ).fetchall()
        except Exception as exc:  # noqa: BLE001
            raise DocumentStatusPersistenceError(
                "Failed to list document status rows."
            ) from exc
        return [_row_to_record(row) for row in rows], total

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        try:
            with self._provider.connection() as conn:
                cursor = conn.execute(_DELETE_BY_KB_SQL, (knowledge_base_id,))
                conn.commit()
                return cursor.rowcount
        except Exception as exc:  # noqa: BLE001
            raise DocumentStatusPersistenceError(
                "Failed to delete document status rows for knowledge base."
            ) from exc

    def delete_by_document(
        self, knowledge_base_id: str, source_document_id: str
    ) -> bool:
        try:
            with self._provider.connection() as conn:
                cursor = conn.execute(
                    _DELETE_BY_DOCUMENT_SQL,
                    (knowledge_base_id, source_document_id),
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as exc:  # noqa: BLE001
            raise DocumentStatusPersistenceError(
                "Failed to delete document status row for document."
            ) from exc


def _row_to_record(row: Row) -> SourceDocumentStatusRecord:
    return SourceDocumentStatusRecord(
        knowledge_base_id=cast(str, row[0]),
        source_document_id=cast(str, row[1]),
        current_status=IngestionStatus(cast(str, row[2])),
        status_rank=cast(int, row[3]),
        last_error=cast(str | None, row[4]),
        dropped_entity_count=cast(int, row[5]),
        dropped_relationship_count=cast(int, row[6]),
        sample_reasons=_decode_reasons(row[7]),
        first_event_at=cast(datetime, row[8]),
        updated_at=cast(datetime, row[9]),
    )


def _decode_reasons(value: object) -> list[str]:
    raw = json.loads(value) if isinstance(value, (str, bytes)) else value
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise DocumentStatusPersistenceError(
            "source_document_status.sample_reasons is not a list."
        )
    return [str(item) for item in cast(list[object], raw)]
