"""Postgres-backed policy item repository (BL-011)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import cast

from database.protocols import ConnectionProvider, Row
from policy.exceptions import PolicyItemNotFoundError, PolicyPersistenceError
from policy.models import (
    MatchedValue,
    PolicyCitation,
    PolicyDisposition,
    PolicyItem,
    PolicyItemStatus,
    PolicySeverity,
    PolicyTargetKind,
)

__all__ = ["PostgresPolicyItemRepository"]

_COLUMNS = (
    "knowledge_base_id, rule_id, target_ref, item_id, rule_pack_id, target_kind, "
    "title, severity, matched_fields, citations, status, disposition, created_at, updated_at"
)

_SELECT_BY_KEY = f"""
    SELECT {_COLUMNS} FROM policy_items
    WHERE knowledge_base_id = %s AND rule_id = %s AND target_ref = %s
"""

_SELECT_BY_ID = f"""
    SELECT {_COLUMNS} FROM policy_items
    WHERE knowledge_base_id = %s AND item_id = %s
"""

_INSERT = """
    INSERT INTO policy_items (
        knowledge_base_id, rule_id, target_ref, item_id, rule_pack_id, target_kind,
        title, severity, matched_fields, citations, status, disposition, created_at, updated_at
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s::jsonb, %s, %s)
"""

_UPDATE_REFRESH = """
    UPDATE policy_items
       SET title = %s, severity = %s, matched_fields = %s::jsonb,
           citations = %s::jsonb, updated_at = %s
     WHERE knowledge_base_id = %s AND rule_id = %s AND target_ref = %s
"""

_UPDATE_FULL = """
    UPDATE policy_items
       SET title = %s, severity = %s, matched_fields = %s::jsonb, citations = %s::jsonb,
           status = %s, disposition = %s::jsonb, updated_at = %s
     WHERE knowledge_base_id = %s AND rule_id = %s AND target_ref = %s
"""


class PostgresPolicyItemRepository:
    """A ``PolicyItemRepository`` backed by the ``policy_items`` table."""

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def upsert(self, item: PolicyItem) -> PolicyItem:
        try:
            with self._provider.connection() as conn:
                row = conn.execute(
                    _SELECT_BY_KEY,
                    (item.knowledge_base_id, item.rule_id, item.target_ref),
                ).fetchone()
                if row is None:
                    conn.execute(_INSERT, _insert_params(item))
                    conn.commit()
                    return item
                existing = _row_to_item(row)
                if existing.status != "open":
                    return existing
                conn.execute(
                    _UPDATE_REFRESH,
                    (
                        item.title,
                        item.severity,
                        json.dumps(item.matched_fields, default=str),
                        _citations_json(item.citations),
                        item.updated_at,
                        item.knowledge_base_id,
                        item.rule_id,
                        item.target_ref,
                    ),
                )
                conn.commit()
                return existing.model_copy(
                    update={
                        "title": item.title,
                        "severity": item.severity,
                        "matched_fields": item.matched_fields,
                        "citations": item.citations,
                        "updated_at": item.updated_at,
                    }
                )
        except PolicyPersistenceError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise PolicyPersistenceError("Failed to upsert policy item.") from exc

    def get(self, *, knowledge_base_id: str, item_id: str) -> PolicyItem | None:
        try:
            with self._provider.connection() as conn:
                row = conn.execute(_SELECT_BY_ID, (knowledge_base_id, item_id)).fetchone()
        except Exception as exc:  # noqa: BLE001
            raise PolicyPersistenceError("Failed to read policy item.") from exc
        return None if row is None else _row_to_item(row)

    def list(
        self, *, knowledge_base_id: str, limit: int, offset: int, status: str | None = None
    ) -> tuple[list[PolicyItem], int]:
        where = "WHERE knowledge_base_id = %s"
        params: list[object] = [knowledge_base_id]
        if status is not None:
            where += " AND status = %s"
            params.append(status)
        try:
            with self._provider.connection() as conn:
                total_row = conn.execute(
                    f"SELECT count(*) FROM policy_items {where}", tuple(params)
                ).fetchone()
                total = cast(int, total_row[0]) if total_row is not None else 0
                if limit <= 0 or offset < 0:
                    return [], total
                rows = conn.execute(
                    f"SELECT {_COLUMNS} FROM policy_items {where} "
                    "ORDER BY updated_at DESC, item_id DESC LIMIT %s OFFSET %s",
                    (*params, limit, offset),
                ).fetchall()
        except Exception as exc:  # noqa: BLE001
            raise PolicyPersistenceError("Failed to list policy items.") from exc
        return [_row_to_item(row) for row in rows], total

    def update(self, item: PolicyItem) -> PolicyItem:
        try:
            with self._provider.connection() as conn:
                cursor = conn.execute(
                    _UPDATE_FULL,
                    (
                        item.title,
                        item.severity,
                        json.dumps(item.matched_fields, default=str),
                        _citations_json(item.citations),
                        item.status,
                        _disposition_json(item.disposition),
                        item.updated_at,
                        item.knowledge_base_id,
                        item.rule_id,
                        item.target_ref,
                    ),
                )
                if cursor.rowcount == 0:
                    raise PolicyItemNotFoundError(item.knowledge_base_id, item.id)
                conn.commit()
        except PolicyItemNotFoundError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise PolicyPersistenceError("Failed to update policy item.") from exc
        return item

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        try:
            with self._provider.connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM policy_items WHERE knowledge_base_id = %s",
                    (knowledge_base_id,),
                )
                conn.commit()
                return cursor.rowcount
        except Exception as exc:  # noqa: BLE001
            raise PolicyPersistenceError("Failed to delete policy items.") from exc


def _insert_params(item: PolicyItem) -> tuple[object, ...]:
    return (
        item.knowledge_base_id,
        item.rule_id,
        item.target_ref,
        item.id,
        item.rule_pack_id,
        item.target_kind,
        item.title,
        item.severity,
        json.dumps(item.matched_fields, default=str),
        _citations_json(item.citations),
        item.status,
        _disposition_json(item.disposition),
        item.created_at,
        item.updated_at,
    )


def _citations_json(citations: list[PolicyCitation]) -> str:
    return json.dumps([c.model_dump(mode="json") for c in citations])


def _disposition_json(disposition: PolicyDisposition | None) -> str | None:
    return None if disposition is None else json.dumps(disposition.model_dump(mode="json"))


def _row_to_item(row: Row) -> PolicyItem:
    return PolicyItem(
        knowledge_base_id=cast(str, row[0]),
        rule_id=cast(str, row[1]),
        target_ref=cast(str, row[2]),
        id=cast(str, row[3]),
        rule_pack_id=cast(str, row[4]),
        target_kind=cast(PolicyTargetKind, row[5]),
        title=cast(str, row[6]),
        severity=cast(PolicySeverity, row[7]),
        matched_fields=_decode_matched(row[8]),
        citations=_decode_citations(row[9]),
        status=cast(PolicyItemStatus, row[10]),
        disposition=_decode_disposition(row[11]),
        created_at=cast(datetime, row[12]),
        updated_at=cast(datetime, row[13]),
    )


def _as_obj(value: object) -> object:
    return json.loads(value) if isinstance(value, (str, bytes)) else value


def _decode_matched(value: object) -> dict[str, MatchedValue]:
    return cast(dict[str, MatchedValue], _as_obj(value) or {})


def _decode_citations(value: object) -> list[PolicyCitation]:
    return [PolicyCitation.model_validate(c) for c in cast(list[object], _as_obj(value) or [])]


def _decode_disposition(value: object) -> PolicyDisposition | None:
    obj = _as_obj(value)
    return None if obj is None else PolicyDisposition.model_validate(obj)
