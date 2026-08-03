"""Postgres-backed identity-link repository."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, cast

from analytics.identity_resolution.models import (
    IdentityLinkDecision,
    IdentityLinkDecisionRecord,
    IdentityLinkPage,
    IdentityLinkRecord,
    IdentityLinkRepositoryQuery,
    IdentityLinkReviewState,
    IdentityMatchConfidence,
)
from database.protocols import ConnectionProvider, Row

__all__ = ["PostgresIdentityLinkRepository"]

_COLUMNS = (
    "id, knowledge_base_id, canonical_entity_id, source_entity_id, "
    "relationship_type, confidence, score, review_state, decision_source, "
    "source_refs, match_reasons, decision_history, created_at, updated_at"
)

_UPSERT_SQL = f"""
    INSERT INTO identity_links (
        id, knowledge_base_id, canonical_entity_id, source_entity_id,
        relationship_type, confidence, score, review_state, decision_source,
        source_refs, match_reasons, decision_history, created_at, updated_at
    )
    VALUES (
        %s, %s, %s, %s,
        %s, %s, %s, %s, %s,
        %s::jsonb, %s::jsonb, %s::jsonb, %s, %s
    )
    ON CONFLICT (knowledge_base_id, id)
    DO UPDATE SET
        canonical_entity_id = EXCLUDED.canonical_entity_id,
        source_entity_id = EXCLUDED.source_entity_id,
        relationship_type = EXCLUDED.relationship_type,
        confidence = EXCLUDED.confidence,
        score = EXCLUDED.score,
        review_state = EXCLUDED.review_state,
        decision_source = EXCLUDED.decision_source,
        source_refs = EXCLUDED.source_refs,
        match_reasons = EXCLUDED.match_reasons,
        decision_history = EXCLUDED.decision_history,
        updated_at = EXCLUDED.updated_at
    RETURNING {_COLUMNS}
"""

_GET_SQL = f"""
    SELECT {_COLUMNS}
    FROM identity_links
    WHERE knowledge_base_id = %s AND id = %s
"""


class PostgresIdentityLinkRepository:
    """An ``IdentityLinkRepository`` backed by ``identity_links``."""

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def upsert_link(self, link: IdentityLinkRecord) -> IdentityLinkRecord:
        with self._provider.connection() as conn:
            row = conn.execute(
                _UPSERT_SQL,
                (
                    link.id,
                    link.knowledge_base_id,
                    link.canonical_entity_id,
                    link.source_entity_id,
                    link.relationship_type,
                    link.confidence,
                    link.score,
                    link.review_state,
                    link.decision_source,
                    json.dumps(link.source_refs),
                    json.dumps(link.match_reasons, default=str),
                    json.dumps(
                        [
                            decision.model_dump(mode="json")
                            for decision in link.decision_history
                        ]
                    ),
                    link.created_at,
                    link.updated_at,
                ),
            ).fetchone()
            conn.commit()
        if row is None:
            raise RuntimeError("identity_links upsert returned no row.")
        return _row_to_link(row)

    def get_link(
        self, *, knowledge_base_id: str, link_id: str
    ) -> IdentityLinkRecord | None:
        with self._provider.connection() as conn:
            row = conn.execute(_GET_SQL, (knowledge_base_id, link_id)).fetchone()
        return _row_to_link(row) if row is not None else None

    def list_links(self, query: IdentityLinkRepositoryQuery) -> IdentityLinkPage:
        where_sql, params = _build_where(query)
        with self._provider.connection() as conn:
            count_row = conn.execute(
                f"SELECT count(*) FROM identity_links WHERE {where_sql}",
                tuple(params),
            ).fetchone()
            rows = conn.execute(
                f"""
                SELECT {_COLUMNS}
                FROM identity_links
                WHERE {where_sql}
                ORDER BY updated_at DESC, id DESC
                LIMIT %s OFFSET %s
                """,
                tuple([*params, query.limit, query.offset]),
            ).fetchall()
        total = cast(int, count_row[0]) if count_row is not None else 0
        return IdentityLinkPage(
            items=[_row_to_link(row) for row in rows],
            total=total,
            limit=query.limit,
            offset=query.offset,
        )


def _build_where(query: IdentityLinkRepositoryQuery) -> tuple[str, list[object]]:
    clauses = ["knowledge_base_id = %s"]
    params: list[object] = [query.knowledge_base_id]
    if query.canonical_entity_id is not None:
        clauses.append("canonical_entity_id = %s")
        params.append(query.canonical_entity_id)
    if query.source_entity_id is not None:
        clauses.append("source_entity_id = %s")
        params.append(query.source_entity_id)
    if query.review_state is not None:
        clauses.append("review_state = %s")
        params.append(query.review_state)
    return " AND ".join(clauses), params


def _row_to_link(row: Row) -> IdentityLinkRecord:
    return IdentityLinkRecord(
        id=cast(str, row[0]),
        knowledge_base_id=cast(str, row[1]),
        canonical_entity_id=cast(str, row[2]),
        source_entity_id=cast(str, row[3]),
        relationship_type=cast(str, row[4]),
        confidence=_decode_confidence(row[5]),
        score=float(cast(float, row[6])),
        review_state=_decode_review_state(row[7]),
        decision_source=cast(str, row[8]),
        source_refs=_decode_string_list(row[9], field="identity_links.source_refs"),
        match_reasons=_decode_dict_list(row[10], field="identity_links.match_reasons"),
        decision_history=_decode_decisions(row[11]),
        created_at=cast(datetime, row[12]),
        updated_at=cast(datetime, row[13]),
    )


def _decode_json(value: object) -> object:
    return json.loads(value) if isinstance(value, (str, bytes, bytearray)) else value


def _decode_string_list(value: object, *, field: str) -> list[str]:
    raw = _decode_json(value)
    if not isinstance(raw, list):
        raise RuntimeError(f"{field} did not decode to a list.")
    return [str(item) for item in raw]


def _decode_dict_list(value: object, *, field: str) -> list[dict[str, Any]]:
    raw = _decode_json(value)
    if not isinstance(raw, list):
        raise RuntimeError(f"{field} did not decode to a list.")
    items: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise RuntimeError(f"{field} contained a non-object item.")
        items.append({str(key): item[key] for key in item})
    return items


def _decode_decisions(value: object) -> list[IdentityLinkDecisionRecord]:
    raw_items = _decode_dict_list(value, field="identity_links.decision_history")
    decisions: list[IdentityLinkDecisionRecord] = []
    for item in raw_items:
        decisions.append(
            IdentityLinkDecisionRecord(
                decision=_decode_decision(item.get("decision")),
                actor_user_id=str(item.get("actor_user_id")),
                comment=(
                    str(item["comment"])
                    if item.get("comment") is not None
                    else None
                ),
                created_at=_decode_datetime(item.get("created_at")),
            )
        )
    return decisions


def _decode_confidence(value: object) -> IdentityMatchConfidence:
    raw = str(value)
    if raw not in ("high", "medium", "low"):
        raise RuntimeError(f"identity_links.confidence has unexpected value '{raw}'.")
    return cast(IdentityMatchConfidence, raw)


def _decode_review_state(value: object) -> IdentityLinkReviewState:
    raw = str(value)
    if raw not in (
        "auto_linkable",
        "steward_review",
        "needs_review",
        "merged",
        "rejected",
        "split",
    ):
        raise RuntimeError(f"identity_links.review_state has unexpected value '{raw}'.")
    return cast(IdentityLinkReviewState, raw)


def _decode_decision(value: object) -> IdentityLinkDecision:
    raw = str(value)
    if raw not in ("approve_merge", "reject_merge", "split_identity"):
        raise RuntimeError(
            f"identity_links.decision_history decision has unexpected value '{raw}'."
        )
    return cast(IdentityLinkDecision, raw)


def _decode_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise RuntimeError("identity_links.decision_history created_at was not a datetime.")
