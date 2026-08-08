"""Postgres-backed score-run repository.

Durable state for score-all runs and their batches. The in-memory adapter is
process-lifetime, so a run started before an API restart vanished mid-execution
and `replay_failed_batches` had nothing to replay.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import cast

from analytics.score_runs.models import (
    ScoreBatch,
    ScoreBatchStatus,
    ScoreRun,
    ScoreRunStatus,
)
from analytics.score_runs.protocols import ScoreRunPage
from database.protocols import ConnectionProvider, Row
from shared.utils import utc_now

__all__ = ["PostgresScoreRunRepository"]

_UNSET: object = object()

_RUN_COLUMNS = (
    "id, knowledge_base_id, status, requested_by, idempotency_key, "
    "model_version, catalog_version, replay_of_run_id, entity_cursor, "
    "total_entities, scored_entities, failed_entities, skipped_entities, "
    "error_summary, "
    "created_at, updated_at, started_at, finished_at"
)

_BATCH_COLUMNS = (
    "id, run_id, knowledge_base_id, batch_number, status, entity_ids, "
    "scored_entities, failed_entities, skipped_entities, attempts, error_summary, "
    "created_at, updated_at, started_at, finished_at"
)


class PostgresScoreRunRepository:
    """Persist score-all runs and batches in Postgres."""

    def __init__(self, connection_provider: ConnectionProvider) -> None:
        self._provider = connection_provider

    # --- runs ---------------------------------------------------------------

    def save_run(self, run: ScoreRun) -> ScoreRun:
        with self._provider.connection() as conn:
            try:
                conn.execute(
                    f"""
                    INSERT INTO score_runs ({_RUN_COLUMNS})
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        status = EXCLUDED.status,
                        total_entities = EXCLUDED.total_entities,
                        scored_entities = EXCLUDED.scored_entities,
                        failed_entities = EXCLUDED.failed_entities,
                        skipped_entities = EXCLUDED.skipped_entities,
                        error_summary = EXCLUDED.error_summary,
                        entity_cursor = EXCLUDED.entity_cursor,
                        updated_at = EXCLUDED.updated_at,
                        started_at = EXCLUDED.started_at,
                        finished_at = EXCLUDED.finished_at
                    """,
                    _run_params(run),
                )
                conn.commit()
            except Exception as exc:
                conn.rollback()
                # The partial unique index on (knowledge_base_id,
                # idempotency_key) is what makes concurrent starts safe; surface
                # it as the same ValueError the in-memory adapter raises so the
                # service sees one behaviour regardless of backend.
                if _is_unique_violation(exc):
                    raise ValueError(
                        "ScoreRun idempotency_key already exists for this knowledge base."
                    ) from exc
                raise
        stored = self.get_run(run.id)
        if stored is None:
            raise ValueError(f"ScoreRun '{run.id}' was not stored.")
        return stored

    def get_run(self, run_id: str) -> ScoreRun | None:
        with self._provider.connection() as conn:
            row = conn.execute(
                f"SELECT {_RUN_COLUMNS} FROM score_runs WHERE id = %s", (run_id,)
            ).fetchone()
        return None if row is None else _run_from_row(row)

    def find_by_idempotency_key(
        self, *, knowledge_base_id: str, idempotency_key: str
    ) -> ScoreRun | None:
        with self._provider.connection() as conn:
            row = conn.execute(
                f"""
                SELECT {_RUN_COLUMNS} FROM score_runs
                 WHERE knowledge_base_id = %s AND idempotency_key = %s
                """,
                (knowledge_base_id, idempotency_key),
            ).fetchone()
        return None if row is None else _run_from_row(row)

    def list_runs(
        self,
        *,
        knowledge_base_id: str,
        status: ScoreRunStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ScoreRunPage:
        clauses = ["knowledge_base_id = %s"]
        params: list[object] = [knowledge_base_id]
        if status is not None:
            clauses.append("status = %s")
            params.append(status)
        where = " AND ".join(clauses)
        with self._provider.connection() as conn:
            total_row = conn.execute(
                f"SELECT count(*) FROM score_runs WHERE {where}", tuple(params)
            ).fetchone()
            rows = conn.execute(
                f"""
                SELECT {_RUN_COLUMNS} FROM score_runs
                 WHERE {where}
                 ORDER BY created_at DESC, id ASC
                 LIMIT %s OFFSET %s
                """,
                (*params, limit, offset),
            ).fetchall()
        total = 0 if total_row is None else int(cast(int, total_row[0]))
        return ScoreRunPage(items=[_run_from_row(row) for row in rows], total=total)

    def update_run(
        self,
        run_id: str,
        *,
        status: ScoreRunStatus | None = None,
        total_entities: int | None = None,
        scored_entities: int | None = None,
        failed_entities: int | None = None,
        skipped_entities: int | None = None,
        error_summary: str | None | object = _UNSET,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> ScoreRun:
        assignments: list[str] = []
        params: list[object] = []
        for column, value in (
            ("status", status),
            ("total_entities", total_entities),
            ("scored_entities", scored_entities),
            ("failed_entities", failed_entities),
            ("skipped_entities", skipped_entities),
            ("started_at", started_at),
            ("finished_at", finished_at),
        ):
            if value is not None:
                assignments.append(f"{column} = %s")
                params.append(value)
        if error_summary is not _UNSET:
            assignments.append("error_summary = %s")
            params.append(cast(str | None, error_summary))
        assignments.append("updated_at = %s")
        params.append(updated_at or utc_now())

        with self._provider.connection() as conn:
            try:
                cursor = conn.execute(
                    f"UPDATE score_runs SET {', '.join(assignments)} WHERE id = %s",
                    (*params, run_id),
                )
                if cursor.rowcount != 1:
                    conn.rollback()
                    raise KeyError(run_id)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        stored = self.get_run(run_id)
        if stored is None:
            raise KeyError(run_id)
        return stored

    # --- batches ------------------------------------------------------------

    def upsert_batch(self, batch: ScoreBatch) -> ScoreBatch:
        with self._provider.connection() as conn:
            try:
                conn.execute(
                    f"""
                    INSERT INTO score_batches ({_BATCH_COLUMNS})
                    VALUES (
                        %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (run_id, batch_number) DO UPDATE SET
                        status = EXCLUDED.status,
                        entity_ids = EXCLUDED.entity_ids,
                        scored_entities = EXCLUDED.scored_entities,
                        failed_entities = EXCLUDED.failed_entities,
                        skipped_entities = EXCLUDED.skipped_entities,
                        attempts = EXCLUDED.attempts,
                        error_summary = EXCLUDED.error_summary,
                        updated_at = EXCLUDED.updated_at,
                        started_at = EXCLUDED.started_at,
                        finished_at = EXCLUDED.finished_at
                    """,
                    _batch_params(batch),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        stored = self.get_batch(run_id=batch.run_id, batch_number=batch.batch_number)
        if stored is None:
            raise ValueError(f"ScoreBatch '{batch.id}' was not stored.")
        return stored

    def get_batch(self, *, run_id: str, batch_number: int) -> ScoreBatch | None:
        with self._provider.connection() as conn:
            row = conn.execute(
                f"""
                SELECT {_BATCH_COLUMNS} FROM score_batches
                 WHERE run_id = %s AND batch_number = %s
                """,
                (run_id, batch_number),
            ).fetchone()
        return None if row is None else _batch_from_row(row)

    def claim_batch(
        self,
        *,
        run_id: str,
        batch_number: int,
        now: datetime,
        stale_running_before: datetime | None = None,
    ) -> ScoreBatch | None:
        """Atomically transition a `queued` batch to `running`.

        `WHERE status = 'queued'` is what makes this safe: a second worker
        handed the same event matches zero rows and gets None back.
        """
        with self._provider.connection() as conn:
            try:
                row = conn.execute(
                    f"""
                    UPDATE score_batches
                       SET status = 'running',
                           attempts = attempts + 1,
                           started_at = COALESCE(started_at, %s),
                           updated_at = %s
                     WHERE run_id = %s AND batch_number = %s
                       AND (
                            status = 'queued'
                            OR (
                                %s::timestamptz IS NOT NULL
                                AND status = 'running'
                                AND updated_at < %s::timestamptz
                            )
                       )
                    RETURNING {_BATCH_COLUMNS}
                    """,
                    (
                        now,
                        now,
                        run_id,
                        batch_number,
                        stale_running_before,
                        stale_running_before,
                    ),
                ).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return None if row is None else _batch_from_row(row)

    def list_batches(
        self, *, run_id: str, status: ScoreBatchStatus | None = None
    ) -> list[ScoreBatch]:
        clauses = ["run_id = %s"]
        params: list[object] = [run_id]
        if status is not None:
            clauses.append("status = %s")
            params.append(status)
        with self._provider.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT {_BATCH_COLUMNS} FROM score_batches
                 WHERE {" AND ".join(clauses)}
                 ORDER BY batch_number ASC
                """,
                tuple(params),
            ).fetchall()
        return [_batch_from_row(row) for row in rows]

    def list_stale_runs(
        self,
        *,
        statuses: tuple[ScoreRunStatus, ...],
        updated_before: datetime,
        limit: int = 1000,
    ) -> list[ScoreRun]:
        if not statuses:
            return []
        placeholders = ", ".join(["%s"] * len(statuses))
        with self._provider.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT {_RUN_COLUMNS} FROM score_runs
                 WHERE status IN ({placeholders}) AND updated_at < %s
                 ORDER BY updated_at ASC
                 LIMIT %s
                """,
                (*statuses, updated_before, limit),
            ).fetchall()
        return [_run_from_row(row) for row in rows]

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        with self._provider.connection() as conn:
            try:
                # score_batches cascades via its run_id foreign key.
                cursor = conn.execute(
                    "DELETE FROM score_runs WHERE knowledge_base_id = %s",
                    (knowledge_base_id,),
                )
                deleted = cursor.rowcount
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return int(deleted)


def _run_params(run: ScoreRun) -> tuple[object, ...]:
    return (
        run.id,
        run.knowledge_base_id,
        run.status,
        run.requested_by,
        run.idempotency_key,
        run.model_version,
        run.catalog_version,
        run.replay_of_run_id,
        None,
        run.total_entities,
        run.scored_entities,
        run.failed_entities,
        run.skipped_entities,
        run.error_summary,
        run.created_at,
        run.updated_at,
        run.started_at,
        run.finished_at,
    )


def _batch_params(batch: ScoreBatch) -> tuple[object, ...]:
    return (
        batch.id,
        batch.run_id,
        batch.knowledge_base_id,
        batch.batch_number,
        batch.status,
        json.dumps(list(batch.entity_ids)),
        batch.scored_entities,
        batch.failed_entities,
        batch.skipped_entities,
        batch.attempts,
        batch.error_summary,
        batch.created_at,
        batch.updated_at,
        batch.started_at,
        batch.finished_at,
    )


def _run_from_row(row: Row) -> ScoreRun:
    return ScoreRun(
        id=cast(str, row[0]),
        knowledge_base_id=cast(str, row[1]),
        status=cast(ScoreRunStatus, row[2]),
        requested_by=cast(str | None, row[3]),
        idempotency_key=cast(str | None, row[4]),
        model_version=cast(str, row[5]),
        catalog_version=cast(str, row[6]),
        replay_of_run_id=cast(str | None, row[7]),
        total_entities=int(cast(int, row[9])),
        scored_entities=int(cast(int, row[10])),
        failed_entities=int(cast(int, row[11])),
        skipped_entities=int(cast(int, row[12])),
        error_summary=cast(str | None, row[13]),
        created_at=cast(datetime, row[14]),
        updated_at=cast(datetime, row[15]),
        started_at=cast(datetime | None, row[16]),
        finished_at=cast(datetime | None, row[17]),
    )


def _batch_from_row(row: Row) -> ScoreBatch:
    return ScoreBatch(
        id=cast(str, row[0]),
        run_id=cast(str, row[1]),
        knowledge_base_id=cast(str, row[2]),
        batch_number=int(cast(int, row[3])),
        status=cast(ScoreBatchStatus, row[4]),
        entity_ids=_decode_string_list(row[5]),
        scored_entities=int(cast(int, row[6])),
        failed_entities=int(cast(int, row[7])),
        skipped_entities=int(cast(int, row[8])),
        attempts=int(cast(int, row[9])),
        error_summary=cast(str | None, row[10]),
        created_at=cast(datetime, row[11]),
        updated_at=cast(datetime, row[12]),
        started_at=cast(datetime | None, row[13]),
        finished_at=cast(datetime | None, row[14]),
    )


def _decode_string_list(value: object) -> list[str]:
    """Decode a jsonb array of entity ids.

    `json.loads` returns `Any`, and narrowing it with `isinstance(x, list)`
    yields `list[Unknown]` — iterating that is a pyright strict error. Pinning
    the decoded value as `object` and casting after the guard is what keeps the
    type gate green; this exact pattern broke CI for nine sprints.
    """

    decoded: object = (
        json.loads(value) if isinstance(value, (str, bytes, bytearray)) else value
    )
    if decoded is None:
        return []
    if not isinstance(decoded, list):
        raise ValueError("score_batches.entity_ids did not decode to a list.")
    return [str(item) for item in cast(list[object], decoded)]


def _is_unique_violation(exc: Exception) -> bool:
    return getattr(exc, "sqlstate", None) == "23505"
