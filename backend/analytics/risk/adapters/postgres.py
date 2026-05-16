"""Postgres-backed risk-history store.

Writes the ``risk_score_history`` table and exposes the latest score per
entity. Depends only on the psycopg-free ``database.ConnectionProvider``
protocol. The ``factors`` jsonb column is written via an explicit ``::jsonb``
cast over serialized JSON.
"""

from __future__ import annotations

import json
from typing import cast

from analytics.risk.exceptions import RiskHistoryError
from analytics.risk.models import RiskAssessmentRecord, RiskFactor
from database.protocols import ConnectionProvider

_INSERT_SQL = """
    INSERT INTO risk_score_history (
        knowledge_base_id, entity_id, request_id, overall_score,
        risk_level, factors, assessed_at
    ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)
    ON CONFLICT (request_id) DO NOTHING
"""

_LATEST_SCORE_SQL = """
    SELECT overall_score
    FROM risk_score_history
    WHERE knowledge_base_id = %s AND entity_id = %s
    ORDER BY assessed_at DESC
    LIMIT 1
"""


def _factor_to_dict(factor: RiskFactor) -> dict[str, object]:
    return {
        "factor_name": factor.factor_name,
        "raw_value": factor.raw_value,
        "weight": factor.weight,
        "contribution": factor.contribution,
        "rationale": factor.rationale,
    }


class PostgresRiskHistoryStore:
    """A ``RiskHistoryWriter`` backed by the ``risk_score_history`` table."""

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def write_assessment(self, record: RiskAssessmentRecord) -> bool:
        factors_json = json.dumps(
            [_factor_to_dict(factor) for factor in record.factors], default=str
        )
        try:
            with self._provider.connection() as conn:
                cursor = conn.execute(
                    _INSERT_SQL,
                    (
                        record.knowledge_base_id,
                        record.entity_id,
                        record.request_id,
                        record.overall_score,
                        record.risk_level,
                        factors_json,
                        record.assessed_at,
                    ),
                )
                written = cursor.rowcount
                conn.commit()
        except Exception as exc:
            raise RiskHistoryError("Failed to write risk assessment.") from exc
        return written > 0

    def load_historical_score(
        self, *, knowledge_base_id: str, entity_id: str
    ) -> float | None:
        try:
            with self._provider.connection() as conn:
                row = conn.execute(
                    _LATEST_SCORE_SQL, (knowledge_base_id, entity_id)
                ).fetchone()
        except Exception as exc:
            raise RiskHistoryError("Failed to load historical risk score.") from exc
        if row is None:
            return None
        return float(cast(float, row[0]))


__all__ = [
    "PostgresRiskHistoryStore",
]
