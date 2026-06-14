"""Postgres-backed case repository.

Depends only on the psycopg-free ``database.ConnectionProvider`` protocol. The
``alert_ids``, ``timeline``, and ``feedback_history`` columns are jsonb,
written with explicit ``::jsonb`` casts over serialized-JSON text parameters.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import cast

from cases.exceptions import CaseNotFoundError, CasePersistenceError
from cases.models import (
    AnalystFeedback,
    Case,
    CasePriority,
    CaseStatus,
    CaseTimelineEvent,
)
from database.protocols import ConnectionProvider, Row

_COLUMNS = (
    "knowledge_base_id, case_id, title, status, priority, assignee, "
    "originating_alert_id, evidence_pack_id, alert_ids, timeline, feedback_history, "
    "created_at, updated_at"
)

_INSERT_SQL = f"""
    INSERT INTO cases ({_COLUMNS})
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s)
    ON CONFLICT (knowledge_base_id, case_id) DO NOTHING
"""

_GET_SQL = f"""
    SELECT {_COLUMNS}
    FROM cases
    WHERE knowledge_base_id = %s AND case_id = %s
"""

_UPDATE_SQL = """
    UPDATE cases
    SET title = %s, status = %s, priority = %s, assignee = %s,
        originating_alert_id = %s, evidence_pack_id = %s,
        alert_ids = %s::jsonb, timeline = %s::jsonb,
        feedback_history = %s::jsonb, updated_at = %s
    WHERE knowledge_base_id = %s AND case_id = %s
"""

_DELETE_BY_KB_SQL = "DELETE FROM cases WHERE knowledge_base_id = %s"

_VALID_STATUSES = {"open", "in_review", "closed"}
_VALID_PRIORITIES = {"low", "medium", "high", "critical"}


class PostgresCaseRepository:
    """A ``CaseRepository`` backed by the ``cases`` table."""

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def create(self, case: Case) -> Case:
        try:
            with self._provider.connection() as conn:
                conn.execute(_INSERT_SQL, self._insert_params(case))
                conn.commit()
        except Exception as exc:
            raise CasePersistenceError("Failed to persist case.") from exc
        return case

    def get(self, *, knowledge_base_id: str, case_id: str) -> Case | None:
        try:
            with self._provider.connection() as conn:
                row = conn.execute(_GET_SQL, (knowledge_base_id, case_id)).fetchone()
        except Exception as exc:
            raise CasePersistenceError("Failed to load case.") from exc
        return None if row is None else _row_to_case(row)

    def list(
        self,
        *,
        knowledge_base_id: str,
        limit: int,
        offset: int,
        status: str | None = None,
        priority: str | None = None,
    ) -> tuple[list[Case], int]:
        where = ["knowledge_base_id = %s"]
        params: list[object] = [knowledge_base_id]
        if status is not None:
            where.append("status = %s")
            params.append(status)
        if priority is not None:
            where.append("priority = %s")
            params.append(priority)
        where_clause = " AND ".join(where)

        count_sql = f"SELECT count(*) FROM cases WHERE {where_clause}"
        page_sql = (
            f"SELECT {_COLUMNS} FROM cases WHERE {where_clause} "
            "ORDER BY updated_at DESC, case_id DESC LIMIT %s OFFSET %s"
        )
        try:
            with self._provider.connection() as conn:
                count_row = conn.execute(count_sql, tuple(params)).fetchone()
                total = cast(int, count_row[0]) if count_row is not None else 0
                if limit <= 0 or offset < 0:
                    return [], total
                rows = conn.execute(
                    page_sql, (*params, limit, offset)
                ).fetchall()
        except Exception as exc:
            raise CasePersistenceError("Failed to list cases.") from exc
        return [_row_to_case(row) for row in rows], total

    def update(self, case: Case) -> Case:
        try:
            with self._provider.connection() as conn:
                cursor = conn.execute(
                    _UPDATE_SQL,
                    (
                        case.title,
                        case.status,
                        case.priority,
                        case.assignee,
                        case.originating_alert_id,
                        case.evidence_pack_id,
                        json.dumps(case.alert_ids, default=str),
                        _timeline_to_json(case.timeline),
                        _feedback_history_to_json(case.feedback_history),
                        case.updated_at,
                        case.knowledge_base_id,
                        case.id,
                    ),
                )
                if cursor.rowcount == 0:
                    raise CaseNotFoundError(case.knowledge_base_id, case.id)
                conn.commit()
        except CaseNotFoundError:
            raise
        except Exception as exc:
            raise CasePersistenceError("Failed to update case.") from exc
        return case

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        try:
            with self._provider.connection() as conn:
                cursor = conn.execute(_DELETE_BY_KB_SQL, (knowledge_base_id,))
                conn.commit()
                return cursor.rowcount
        except Exception as exc:
            raise CasePersistenceError("Failed to delete cases for knowledge base.") from exc

    @staticmethod
    def _insert_params(case: Case) -> tuple[object, ...]:
        return (
            case.knowledge_base_id,
            case.id,
            case.title,
            case.status,
            case.priority,
            case.assignee,
            case.originating_alert_id,
            case.evidence_pack_id,
            json.dumps(case.alert_ids, default=str),
            _timeline_to_json(case.timeline),
            _feedback_history_to_json(case.feedback_history),
            case.created_at,
            case.updated_at,
        )


def _timeline_to_json(timeline: list[CaseTimelineEvent]) -> str:
    return json.dumps(
        [event.model_dump(mode="json") for event in timeline], default=str
    )


def _feedback_history_to_json(feedback_history: list[AnalystFeedback]) -> str:
    return json.dumps(
        [feedback.model_dump(mode="json") for feedback in feedback_history],
        default=str,
    )


def _row_to_case(row: Row) -> Case:
    raw_status = str(row[3])
    if raw_status not in _VALID_STATUSES:
        raise CasePersistenceError(f"cases.status has unexpected value '{raw_status}'.")
    raw_priority = str(row[4])
    if raw_priority not in _VALID_PRIORITIES:
        raise CasePersistenceError(
            f"cases.priority has unexpected value '{raw_priority}'."
        )
    return Case(
        knowledge_base_id=str(row[0]),
        id=str(row[1]),
        title=str(row[2]),
        status=cast(CaseStatus, raw_status),
        priority=cast(CasePriority, raw_priority),
        assignee=None if row[5] is None else str(row[5]),
        originating_alert_id=None if row[6] is None else str(row[6]),
        evidence_pack_id=None if row[7] is None else str(row[7]),
        alert_ids=_decode_str_list(row[8]),
        timeline=_decode_timeline(row[9]),
        feedback_history=_decode_feedback_history(row[10]),
        created_at=cast(datetime, row[11]),
        updated_at=cast(datetime, row[12]),
    )


def _decode_str_list(raw: object) -> list[str]:
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not isinstance(raw, list):
        raise CasePersistenceError("cases.alert_ids did not decode to a list.")
    return [str(item) for item in cast(list[object], raw)]


def _decode_timeline(raw: object) -> list[CaseTimelineEvent]:
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not isinstance(raw, list):
        raise CasePersistenceError("cases.timeline did not decode to a list.")
    return [CaseTimelineEvent.model_validate(item) for item in cast(list[object], raw)]


def _decode_feedback_history(raw: object) -> list[AnalystFeedback]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CasePersistenceError(
                "cases.feedback_history did not decode to a list."
            ) from exc
    if not isinstance(raw, list):
        raise CasePersistenceError("cases.feedback_history did not decode to a list.")
    return [AnalystFeedback.model_validate(item) for item in cast(list[object], raw)]


__all__ = ["PostgresCaseRepository"]
