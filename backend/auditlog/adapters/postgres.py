"""Postgres-backed append-only audit ledger repository."""

from __future__ import annotations

import json
from datetime import datetime
from typing import cast

from auditlog.exceptions import AuditLogPersistenceError
from auditlog.models import AuditEvent, AuditEventPage, AuditEventQuery, AuditOutcome
from database.protocols import ConnectionProvider, Row

__all__ = ["PostgresAuditLogRepository"]

_COLUMNS = (
    'event_id, occurred_at, tenant_id, knowledge_base_id, actor_user_id, '
    'actor_email, actor_roles, action, resource_type, resource_id, "before", '
    '"after", correlation_id, client_ip, user_agent, outcome, failure_reason, '
    "metadata"
)

_INSERT_SQL = f"""
    INSERT INTO audit_log ({_COLUMNS})
    VALUES (
        %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s::jsonb, %s::jsonb,
        %s, %s, %s, %s, %s, %s::jsonb
    )
"""


class PostgresAuditLogRepository:
    """An ``AuditLogRepository`` backed by the ``audit_log`` table."""

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def append(self, event: AuditEvent) -> None:
        params: tuple[object, ...] = (
            event.event_id,
            event.occurred_at,
            event.tenant_id,
            event.knowledge_base_id,
            event.actor_user_id,
            event.actor_email,
            json.dumps(event.actor_roles),
            event.action,
            event.resource_type,
            event.resource_id,
            _dump_json_or_none(event.before),
            _dump_json_or_none(event.after),
            event.correlation_id,
            event.client_ip,
            event.user_agent,
            event.outcome,
            event.failure_reason,
            json.dumps(event.metadata),
        )
        try:
            with self._provider.connection() as conn:
                conn.execute(_INSERT_SQL, params)
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            raise AuditLogPersistenceError("Failed to append audit event.") from exc

    def list(self, query: AuditEventQuery) -> AuditEventPage:
        where_sql, params = _build_where(query)
        try:
            with self._provider.connection() as conn:
                count_row = conn.execute(
                    f"SELECT count(*) FROM audit_log WHERE {where_sql}",
                    tuple(params),
                ).fetchone()
                total_items = cast(int, count_row[0]) if count_row is not None else 0
                rows = conn.execute(
                    f"""
                    SELECT {_COLUMNS}
                    FROM audit_log
                    WHERE {where_sql}
                    ORDER BY occurred_at DESC, event_id DESC
                    LIMIT %s OFFSET %s
                    """,
                    tuple([*params, query.limit, query.offset]),
                ).fetchall()
        except Exception as exc:  # noqa: BLE001
            raise AuditLogPersistenceError("Failed to list audit events.") from exc
        return AuditEventPage(
            items=[_row_to_event(row) for row in rows],
            total_items=total_items,
            limit=query.limit,
            offset=query.offset,
        )


def _build_where(query: AuditEventQuery) -> tuple[str, list[object]]:
    clauses = ["tenant_id = %s"]
    params: list[object] = [query.tenant_id]
    if query.knowledge_base_id is not None:
        clauses.append("knowledge_base_id = %s")
        params.append(query.knowledge_base_id)
    if query.actor_user_id is not None:
        clauses.append("actor_user_id = %s")
        params.append(query.actor_user_id)
    if query.action_prefix is not None:
        clauses.append("action LIKE %s")
        params.append(f"{query.action_prefix}%")
    if query.resource_type is not None:
        clauses.append("resource_type = %s")
        params.append(query.resource_type)
    if query.resource_id is not None:
        clauses.append("resource_id = %s")
        params.append(query.resource_id)
    if query.outcome is not None:
        clauses.append("outcome = %s")
        params.append(query.outcome)
    if query.occurred_from is not None:
        clauses.append("occurred_at >= %s")
        params.append(query.occurred_from)
    if query.occurred_to is not None:
        clauses.append("occurred_at <= %s")
        params.append(query.occurred_to)
    return " AND ".join(clauses), params


def _row_to_event(row: Row) -> AuditEvent:
    return AuditEvent(
        event_id=cast(str, row[0]),
        occurred_at=cast(datetime, row[1]),
        tenant_id=cast(str, row[2]),
        knowledge_base_id=cast("str | None", row[3]),
        actor_user_id=cast(str, row[4]),
        actor_email=cast("str | None", row[5]),
        actor_roles=_decode_string_list(row[6]),
        action=cast(str, row[7]),
        resource_type=cast(str, row[8]),
        resource_id=cast(str, row[9]),
        before=_decode_json_summary(row[10], nullable=True),
        after=_decode_json_summary(row[11], nullable=True),
        correlation_id=cast(str, row[12]),
        client_ip=cast("str | None", row[13]),
        user_agent=cast("str | None", row[14]),
        outcome=_decode_outcome(row[15]),
        failure_reason=cast("str | None", row[16]),
        metadata=_decode_json_summary(row[17], nullable=False) or {},
    )


def _dump_json_or_none(value: object | None) -> str | None:
    return json.dumps(value) if value is not None else None


def _decode_json(value: object) -> object:
    return json.loads(value) if isinstance(value, (str, bytes, bytearray)) else value


def _decode_json_summary(
    value: object | None,
    *,
    nullable: bool,
) -> dict[str, object | None] | None:
    if value is None:
        if nullable:
            return None
        raise AuditLogPersistenceError("audit_log JSON payload unexpectedly null.")
    raw = _decode_json(value)
    if not isinstance(raw, dict):
        raise AuditLogPersistenceError("audit_log JSON payload did not decode to an object.")
    return {str(key): val for key, val in cast(dict[object, object | None], raw).items()}


def _decode_string_list(value: object) -> list[str]:
    raw = _decode_json(value)
    if not isinstance(raw, list):
        raise AuditLogPersistenceError("audit_log.actor_roles did not decode to a list.")
    return [str(item) for item in cast(list[object], raw)]


def _decode_outcome(value: object) -> AuditOutcome:
    raw = str(value)
    if raw not in ("success", "failure"):
        raise AuditLogPersistenceError(
            f"audit_log.outcome has unexpected value '{raw}'."
        )
    return raw
