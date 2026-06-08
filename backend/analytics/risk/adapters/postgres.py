"""Postgres-backed risk-history store and derived-signal source.

Writes the ``risk_score_history`` table and exposes the latest score per
entity. Depends only on the psycopg-free ``database.ConnectionProvider``
protocol. The ``factors`` jsonb column is written via an explicit ``::jsonb``
cast over serialized JSON.

``PostgresRiskSignalSource`` reads the ``entity_derived_signals`` table
(created by migration 0006) to assemble ``RiskProfile`` objects for use by
the risk scoring pipeline.
"""

from __future__ import annotations

import json
from typing import cast

from analytics.risk.exceptions import RiskHistoryError, RiskSourceError
from analytics.risk.models import (
    RankedRiskEntry,
    RiskAssessmentRecord,
    RiskFactor,
    RiskProfile,
    RiskSignal,
)
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

_LATEST_SIGNALS_SQL = """
    SELECT DISTINCT ON (metric_name)
        metric_name, signal_value, weight, rationale
    FROM entity_derived_signals
    WHERE knowledge_base_id = %s AND entity_id = %s
    ORDER BY metric_name, computed_at DESC
"""

_RANKED_SQL = """
    SELECT DISTINCT ON (entity_id)
        entity_id, overall_score, risk_level
    FROM risk_score_history
    WHERE knowledge_base_id = %s
    ORDER BY entity_id, assessed_at DESC
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


class PostgresRiskSignalSource:
    """A ``RiskSignalSourceProtocol`` backed by ``entity_derived_signals``.

    ``load_profile`` assembles a profile from the latest derived signal per
    metric; ranking and historical lookups read ``risk_score_history``.
    """

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def load_profile(
        self, *, knowledge_base_id: str, entity_id: str
    ) -> RiskProfile:
        try:
            with self._provider.connection() as conn:
                rows = conn.execute(
                    _LATEST_SIGNALS_SQL, (knowledge_base_id, entity_id)
                ).fetchall()
        except Exception as exc:
            raise RiskSourceError("Failed to load derived risk signals.") from exc
        signals = [
            RiskSignal(
                signal_name=str(row[0]),
                value=float(cast(float, row[1])),
                weight=float(cast(float, row[2])),
                rationale=None if row[3] is None else str(row[3]),
            )
            for row in rows
        ]
        if not signals:
            raise ValueError(
                "No derived risk signals registered for "
                f"knowledge_base_id='{knowledge_base_id}', entity_id='{entity_id}'."
            )
        return RiskProfile(
            knowledge_base_id=knowledge_base_id,
            entity_id=entity_id,
            signals=signals,
        )

    def list_ranked_entries(
        self,
        *,
        knowledge_base_id: str,
        entity_type: str | None,
        limit: int,
    ) -> list[RankedRiskEntry]:
        try:
            with self._provider.connection() as conn:
                rows = conn.execute(_RANKED_SQL, (knowledge_base_id,)).fetchall()
        except Exception as exc:
            raise RiskSourceError("Failed to load ranked risk entries.") from exc
        entries = [
            RankedRiskEntry(
                knowledge_base_id=knowledge_base_id,
                entity_id=str(row[0]),
                entity_type=_entity_type_of(str(row[0])),
                overall_score=float(cast(float, row[1])),
                risk_level=str(row[2]),
            )
            for row in rows
        ]
        if entity_type is not None:
            entries = [e for e in entries if e.entity_type == entity_type]
        entries.sort(key=lambda entry: entry.overall_score, reverse=True)
        return entries[:limit]

    def load_historical_score(
        self, *, knowledge_base_id: str, entity_id: str
    ) -> float | None:
        try:
            with self._provider.connection() as conn:
                row = conn.execute(
                    _LATEST_SCORE_SQL, (knowledge_base_id, entity_id)
                ).fetchone()
        except Exception as exc:
            raise RiskSourceError("Failed to load historical risk score.") from exc
        if row is None:
            return None
        return float(cast(float, row[0]))


def _entity_type_of(entity_id: str) -> str:
    """Derive entity type from the ``type:raw_id`` id convention."""

    return entity_id.split(":", 1)[0] if ":" in entity_id else entity_id


__all__ = [
    "PostgresRiskHistoryStore",
    "PostgresRiskSignalSource",
]
