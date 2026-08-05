"""Postgres-backed governance evaluation repository."""

from __future__ import annotations

import json
from datetime import datetime
from typing import cast

from database.protocols import ConnectionProvider, Row
from governance.models import (
    GovernanceBaselineDecision,
    GovernanceComponentKind,
    GovernanceDriftSummary,
    GovernanceEvalRun,
    GovernanceEvalRunPage,
    GovernanceEvalStatus,
    GovernanceMetricResult,
)

__all__ = ["PostgresGovernanceEvalRepository"]

_COLUMNS = (
    "run_id, knowledge_base_id, artifact_kind, artifact_id, artifact_version, "
    "baseline_version, dataset_id, status, metrics, drift_summary, "
    "dataset_source_refs, affected_alert_ids, affected_case_ids, created_by, created_at, "
    "approval"
)

_INSERT = f"""
    INSERT INTO governance_eval_runs (
        {_COLUMNS}
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb,
        %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, %s::jsonb
    )
"""

_UPDATE = """
    UPDATE governance_eval_runs
    SET knowledge_base_id = %s,
        artifact_kind = %s,
        artifact_id = %s,
        artifact_version = %s,
        baseline_version = %s,
        dataset_id = %s,
        status = %s,
        metrics = %s::jsonb,
        drift_summary = %s::jsonb,
        dataset_source_refs = %s::jsonb,
        affected_alert_ids = %s::jsonb,
        affected_case_ids = %s::jsonb,
        created_by = %s,
        created_at = %s,
        approval = %s::jsonb
    WHERE run_id = %s
"""

_SELECT_BY_ID = f"""
    SELECT {_COLUMNS}
    FROM governance_eval_runs
    WHERE run_id = %s
"""


class PostgresGovernanceEvalRepository:
    """Store SAFE-CMS-020 governance eval runs in Postgres."""

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def save_eval_run(self, run: GovernanceEvalRun) -> GovernanceEvalRun:
        with self._provider.connection() as conn:
            try:
                conn.execute(_INSERT, _insert_params(run))
                row = conn.execute(_SELECT_BY_ID, (run.run_id,)).fetchone()
                if row is None:
                    conn.rollback()
                    raise ValueError(f"Governance eval run '{run.run_id}' was not stored.")
                conn.commit()
                return _row_to_run(row)
            except Exception as exc:
                conn.rollback()
                if _is_unique_violation(exc):
                    raise ValueError(
                        f"Governance eval run '{run.run_id}' already exists."
                    ) from exc
                raise

    def update_eval_run(self, run: GovernanceEvalRun) -> GovernanceEvalRun:
        with self._provider.connection() as conn:
            try:
                cursor = conn.execute(_UPDATE, _update_params(run))
                if cursor.rowcount != 1:
                    conn.rollback()
                    raise KeyError(run.run_id)
                row = conn.execute(_SELECT_BY_ID, (run.run_id,)).fetchone()
                if row is None:
                    conn.rollback()
                    raise KeyError(run.run_id)
                conn.commit()
                return _row_to_run(row)
            except Exception:
                conn.rollback()
                raise

    def get_eval_run(self, run_id: str) -> GovernanceEvalRun | None:
        with self._provider.connection() as conn:
            row = conn.execute(_SELECT_BY_ID, (run_id,)).fetchone()
        return None if row is None else _row_to_run(row)

    def list_eval_runs(
        self,
        *,
        knowledge_base_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> GovernanceEvalRunPage:
        if limit < 1:
            raise ValueError("limit must be positive.")
        if offset < 0:
            raise ValueError("offset must be non-negative.")

        where_clause = ""
        params: tuple[object, ...] = ()
        if knowledge_base_id is not None:
            where_clause = "WHERE knowledge_base_id = %s"
            params = (knowledge_base_id,)

        with self._provider.connection() as conn:
            total_row = conn.execute(
                f"""
                SELECT count(*)
                FROM governance_eval_runs
                {where_clause}
                """,
                params,
            ).fetchone()
            total_items = cast(int, total_row[0]) if total_row is not None else 0
            rows = conn.execute(
                f"""
                SELECT {_COLUMNS}
                FROM governance_eval_runs
                {where_clause}
                ORDER BY created_at ASC, run_id ASC
                LIMIT %s OFFSET %s
                """,
                (*params, limit, offset),
            ).fetchall()
        return GovernanceEvalRunPage(
            items=[_row_to_run(row) for row in rows],
            total_items=total_items,
            limit=limit,
            offset=offset,
        )


def _insert_params(run: GovernanceEvalRun) -> tuple[object, ...]:
    return (
        run.run_id,
        run.knowledge_base_id,
        run.artifact_kind,
        run.artifact_id,
        run.artifact_version,
        run.baseline_version,
        run.dataset_id,
        run.status,
        _metrics_json(run.metrics),
        run.drift_summary.model_dump_json(),
        json.dumps(run.dataset_source_refs),
        json.dumps(run.affected_alert_ids),
        json.dumps(run.affected_case_ids),
        run.created_by,
        run.created_at,
        _approval_json(run.approval),
    )


def _update_params(run: GovernanceEvalRun) -> tuple[object, ...]:
    return (
        run.knowledge_base_id,
        run.artifact_kind,
        run.artifact_id,
        run.artifact_version,
        run.baseline_version,
        run.dataset_id,
        run.status,
        _metrics_json(run.metrics),
        run.drift_summary.model_dump_json(),
        json.dumps(run.dataset_source_refs),
        json.dumps(run.affected_alert_ids),
        json.dumps(run.affected_case_ids),
        run.created_by,
        run.created_at,
        _approval_json(run.approval),
        run.run_id,
    )


def _row_to_run(row: Row) -> GovernanceEvalRun:
    return GovernanceEvalRun(
        run_id=cast(str, row[0]),
        knowledge_base_id=cast(str, row[1]),
        artifact_kind=cast(GovernanceComponentKind, row[2]),
        artifact_id=cast(str, row[3]),
        artifact_version=cast(str, row[4]),
        baseline_version=cast(str, row[5]),
        dataset_id=cast(str, row[6]),
        status=cast(GovernanceEvalStatus, row[7]),
        metrics=_decode_metrics(row[8]),
        drift_summary=_decode_drift_summary(row[9]),
        dataset_source_refs=_decode_string_list(row[10]),
        affected_alert_ids=_decode_string_list(row[11]),
        affected_case_ids=_decode_string_list(row[12]),
        created_by=cast(str, row[13]),
        created_at=cast(datetime, row[14]),
        approval=_decode_approval(row[15]),
    )


def _metrics_json(metrics: list[GovernanceMetricResult]) -> str:
    return json.dumps([metric.model_dump(mode="json") for metric in metrics])


def _approval_json(approval: GovernanceBaselineDecision | None) -> str | None:
    if approval is None:
        return None
    return approval.model_dump_json()


def _decode_metrics(value: object) -> list[GovernanceMetricResult]:
    raw = _decode_json(value)
    if not isinstance(raw, list):
        raise ValueError("governance_eval_runs.metrics is not a list.")
    return [GovernanceMetricResult.model_validate(item) for item in raw]


def _decode_drift_summary(value: object) -> GovernanceDriftSummary:
    return GovernanceDriftSummary.model_validate(_decode_json(value))


def _decode_approval(value: object) -> GovernanceBaselineDecision | None:
    if value is None:
        return None
    return GovernanceBaselineDecision.model_validate(_decode_json(value))


def _decode_string_list(value: object) -> list[str]:
    raw = _decode_json(value)
    if not isinstance(raw, list):
        raise ValueError("governance_eval_runs JSON value is not a list.")
    return [str(item) for item in raw]


def _decode_json(value: object) -> object:
    return json.loads(value) if isinstance(value, (str, bytes, bytearray)) else value


def _is_unique_violation(exc: Exception) -> bool:
    return getattr(exc, "sqlstate", None) == "23505"
