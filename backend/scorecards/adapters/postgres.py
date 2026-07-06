"""Postgres-backed scorecard run repository."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import cast

from database.protocols import ConnectionProvider, Row
from scorecards.exceptions import ScorecardPersistenceError
from scorecards.models import (
    ScorecardExportFormat,
    ScorecardHealth,
    ScorecardRun,
    ScorecardRunStatus,
    ScorecardSectionResult,
)

__all__ = ["PostgresScorecardRunRepository"]

_COLUMNS = (
    "knowledge_base_id, run_id, template_id, template_name, scope_type, scope_id, "
    "period_start, period_end, source_snapshot_hash, status, overall_health, "
    "sections, export_payloads, created_at, updated_at"
)

_INSERT_SQL = f"""
    INSERT INTO scorecard_runs (
        {_COLUMNS}
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s
    )
    ON CONFLICT (
        knowledge_base_id, template_id, scope_type, scope_id,
        period_start, period_end, source_snapshot_hash
    ) DO NOTHING
"""

_SELECT_BY_ID_SQL = f"""
    SELECT {_COLUMNS} FROM scorecard_runs
    WHERE knowledge_base_id = %s AND run_id = %s
"""

_SELECT_BY_NATURAL_KEY_SQL = f"""
    SELECT {_COLUMNS} FROM scorecard_runs
    WHERE knowledge_base_id = %s
      AND template_id = %s
      AND scope_type = %s
      AND scope_id = %s
      AND period_start = %s
      AND period_end = %s
      AND source_snapshot_hash = %s
"""

_DELETE_BY_KB_SQL = """
    DELETE FROM scorecard_runs
    WHERE knowledge_base_id = %s
"""


class PostgresScorecardRunRepository:
    """A ``ScorecardRunRepository`` backed by the ``scorecard_runs`` table."""

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def upsert(self, run: ScorecardRun) -> ScorecardRun:
        try:
            with self._provider.connection() as conn:
                cursor = conn.execute(_INSERT_SQL, _insert_params(run))
                if cursor.rowcount > 0:
                    conn.commit()
                    return run
                row = conn.execute(_SELECT_BY_NATURAL_KEY_SQL, _key_params(run)).fetchone()
                conn.commit()
        except ScorecardPersistenceError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ScorecardPersistenceError("Failed to upsert scorecard run.") from exc
        if row is None:
            raise ScorecardPersistenceError(
                "Scorecard run conflict could not be resolved."
            )
        return _row_to_run(row)

    def get(self, *, knowledge_base_id: str, run_id: str) -> ScorecardRun | None:
        try:
            with self._provider.connection() as conn:
                row = conn.execute(
                    _SELECT_BY_ID_SQL, (knowledge_base_id, run_id)
                ).fetchone()
        except Exception as exc:  # noqa: BLE001
            raise ScorecardPersistenceError("Failed to read scorecard run.") from exc
        return None if row is None else _row_to_run(row)

    def list(
        self,
        *,
        knowledge_base_id: str,
        limit: int,
        offset: int,
        template_id: str | None = None,
        status: ScorecardRunStatus | None = None,
    ) -> tuple[list[ScorecardRun], int]:
        where = "WHERE knowledge_base_id = %s"
        params: list[object] = [knowledge_base_id]
        if template_id is not None:
            where += " AND template_id = %s"
            params.append(template_id)
        if status is not None:
            where += " AND status = %s"
            params.append(status)
        try:
            with self._provider.connection() as conn:
                total_row = conn.execute(
                    f"SELECT count(*) FROM scorecard_runs {where}", tuple(params)
                ).fetchone()
                total = cast(int, total_row[0]) if total_row is not None else 0
                if limit <= 0 or offset < 0:
                    return [], total
                rows = conn.execute(
                    f"SELECT {_COLUMNS} FROM scorecard_runs {where} "
                    "ORDER BY created_at DESC, run_id DESC LIMIT %s OFFSET %s",
                    (*params, limit, offset),
                ).fetchall()
        except Exception as exc:  # noqa: BLE001
            raise ScorecardPersistenceError("Failed to list scorecard runs.") from exc
        return [_row_to_run(row) for row in rows], total

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        try:
            with self._provider.connection() as conn:
                cursor = conn.execute(_DELETE_BY_KB_SQL, (knowledge_base_id,))
                conn.commit()
                return cursor.rowcount
        except Exception as exc:  # noqa: BLE001
            raise ScorecardPersistenceError(
                "Failed to delete scorecard runs for knowledge base."
            ) from exc


def _insert_params(run: ScorecardRun) -> tuple[object, ...]:
    return (
        run.knowledge_base_id,
        run.id,
        run.template_id,
        run.template_name,
        run.scope_type,
        run.scope_id,
        run.period_start,
        run.period_end,
        run.source_snapshot_hash,
        run.status,
        run.overall_health,
        json.dumps([section.model_dump(mode="json") for section in run.sections]),
        json.dumps(run.export_payloads),
        run.created_at,
        run.updated_at,
    )


def _key_params(run: ScorecardRun) -> tuple[object, ...]:
    return (
        run.knowledge_base_id,
        run.template_id,
        run.scope_type,
        run.scope_id,
        run.period_start,
        run.period_end,
        run.source_snapshot_hash,
    )


def _row_to_run(row: Row) -> ScorecardRun:
    return ScorecardRun(
        knowledge_base_id=cast(str, row[0]),
        id=cast(str, row[1]),
        template_id=cast(str, row[2]),
        template_name=cast(str, row[3]),
        scope_type=cast(str, row[4]),
        scope_id=cast(str, row[5]),
        period_start=cast(date, row[6]),
        period_end=cast(date, row[7]),
        source_snapshot_hash=cast(str, row[8]),
        status=cast(ScorecardRunStatus, row[9]),
        overall_health=cast(ScorecardHealth, row[10]),
        sections=_decode_sections(row[11]),
        export_payloads=_decode_export_payloads(row[12]),
        created_at=cast(datetime, row[13]),
        updated_at=cast(datetime, row[14]),
    )


def _as_obj(value: object) -> object:
    return json.loads(value) if isinstance(value, (str, bytes)) else value


def _decode_sections(value: object) -> list[ScorecardSectionResult]:
    raw = _as_obj(value) or []
    if not isinstance(raw, list):
        raise ScorecardPersistenceError("scorecard_runs.sections is not a list.")
    return [ScorecardSectionResult.model_validate(item) for item in raw]


def _decode_export_payloads(value: object) -> dict[ScorecardExportFormat, str]:
    raw = _as_obj(value) or {}
    if not isinstance(raw, dict):
        raise ScorecardPersistenceError("scorecard_runs.export_payloads is not an object.")
    return cast(dict[ScorecardExportFormat, str], raw)
