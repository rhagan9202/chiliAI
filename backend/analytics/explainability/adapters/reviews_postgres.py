"""Postgres-backed explanation-review repository."""

from __future__ import annotations

import json
from datetime import datetime
from typing import cast

from analytics.explainability.reviews import (
    ExplanationReviewPage,
    ExplanationReviewQuery,
    ExplanationReviewReason,
    ExplanationReviewRecord,
    ExplanationReviewState,
    ExplanationReviewTarget,
    ExplanationReviewTargetType,
)
from database.protocols import ConnectionProvider, Row

__all__ = ["PostgresExplanationReviewRepository"]

_COLUMNS = (
    "id, knowledge_base_id, evidence_pack_id, target_type, target_id, state, "
    "reasons, comment, actor_user_id, actor_email, created_at, updated_at, update_count"
)

_UPSERT_SQL = f"""
    INSERT INTO explanation_reviews (
        id, knowledge_base_id, evidence_pack_id, target_type, target_id, state,
        reasons, comment, actor_user_id, actor_email, created_at, updated_at, update_count
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (knowledge_base_id, evidence_pack_id, target_type, target_id)
    DO UPDATE SET
        state = EXCLUDED.state,
        reasons = EXCLUDED.reasons,
        comment = EXCLUDED.comment,
        actor_user_id = EXCLUDED.actor_user_id,
        actor_email = EXCLUDED.actor_email,
        updated_at = EXCLUDED.updated_at,
        update_count = EXCLUDED.update_count
    RETURNING {_COLUMNS}
"""

_SELECT_TARGET_SQL = f"""
    SELECT {_COLUMNS}
    FROM explanation_reviews
    WHERE knowledge_base_id = %s
      AND evidence_pack_id = %s
      AND target_type = %s
      AND target_id = %s
"""


class PostgresExplanationReviewRepository:
    """An ``ExplanationReviewRepository`` backed by ``explanation_reviews``."""

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def upsert(self, review: ExplanationReviewRecord) -> ExplanationReviewRecord:
        with self._provider.connection() as conn:
            row = conn.execute(
                _UPSERT_SQL,
                (
                    review.id,
                    review.knowledge_base_id,
                    review.evidence_pack_id,
                    review.target.target_type,
                    review.target.target_id,
                    review.state,
                    json.dumps(review.reasons),
                    review.comment,
                    review.actor_user_id,
                    review.actor_email,
                    review.created_at,
                    review.updated_at,
                    review.update_count,
                ),
            ).fetchone()
            conn.commit()
        if row is None:
            raise RuntimeError("explanation_reviews upsert returned no row.")
        return _row_to_review(row)

    def get_for_target(
        self,
        *,
        knowledge_base_id: str,
        evidence_pack_id: str,
        target: ExplanationReviewTarget,
    ) -> ExplanationReviewRecord | None:
        with self._provider.connection() as conn:
            row = conn.execute(
                _SELECT_TARGET_SQL,
                (
                    knowledge_base_id,
                    evidence_pack_id,
                    target.target_type,
                    target.target_id,
                ),
            ).fetchone()
        return _row_to_review(row) if row is not None else None

    def list_reviews(self, query: ExplanationReviewQuery) -> ExplanationReviewPage:
        where_sql, params = _build_where(query)
        with self._provider.connection() as conn:
            count_row = conn.execute(
                f"SELECT count(*) FROM explanation_reviews WHERE {where_sql}",
                tuple(params),
            ).fetchone()
            total = cast(int, count_row[0]) if count_row is not None else 0
            rows = conn.execute(
                f"""
                SELECT {_COLUMNS}
                FROM explanation_reviews
                WHERE {where_sql}
                ORDER BY updated_at DESC, id DESC
                LIMIT %s OFFSET %s
                """,
                tuple([*params, query.limit, query.offset]),
            ).fetchall()
        return ExplanationReviewPage(
            items=[_row_to_review(row) for row in rows],
            total=total,
            limit=query.limit,
            offset=query.offset,
        )


def _build_where(query: ExplanationReviewQuery) -> tuple[str, list[object]]:
    clauses = ["knowledge_base_id = %s"]
    params: list[object] = [query.knowledge_base_id]
    if query.evidence_pack_id is not None:
        clauses.append("evidence_pack_id = %s")
        params.append(query.evidence_pack_id)
    if query.state is not None:
        clauses.append("state = %s")
        params.append(query.state)
    if query.target_type is not None:
        clauses.append("target_type = %s")
        params.append(query.target_type)
    return " AND ".join(clauses), params


def _row_to_review(row: Row) -> ExplanationReviewRecord:
    return ExplanationReviewRecord(
        id=cast(str, row[0]),
        knowledge_base_id=cast(str, row[1]),
        evidence_pack_id=cast(str, row[2]),
        target=ExplanationReviewTarget(
            target_type=_decode_target_type(row[3]),
            target_id=cast(str, row[4]),
        ),
        state=_decode_state(row[5]),
        reasons=_decode_reasons(row[6]),
        comment=cast("str | None", row[7]),
        actor_user_id=cast(str, row[8]),
        actor_email=cast("str | None", row[9]),
        created_at=cast(datetime, row[10]),
        updated_at=cast(datetime, row[11]),
        update_count=cast(int, row[12]),
    )


def _decode_json(value: object) -> object:
    return json.loads(value) if isinstance(value, (str, bytes, bytearray)) else value


def _decode_reasons(value: object) -> list[ExplanationReviewReason]:
    raw = _decode_json(value)
    if not isinstance(raw, list):
        raise RuntimeError("explanation_reviews.reasons did not decode to a list.")
    return [cast(ExplanationReviewReason, str(item)) for item in raw]


def _decode_target_type(value: object) -> ExplanationReviewTargetType:
    raw = str(value)
    if raw not in (
        "narrative",
        "narrative_section",
        "feature_attribution",
        "evidence_item",
        "provenance_reference",
    ):
        raise RuntimeError(f"explanation_reviews.target_type has unexpected value '{raw}'.")
    return cast(ExplanationReviewTargetType, raw)


def _decode_state(value: object) -> ExplanationReviewState:
    raw = str(value)
    if raw not in (
        "useful",
        "incomplete",
        "misleading",
        "unsupported",
        "approved",
        "rejected",
        "regeneration_requested",
    ):
        raise RuntimeError(f"explanation_reviews.state has unexpected value '{raw}'.")
    return cast(ExplanationReviewState, raw)
