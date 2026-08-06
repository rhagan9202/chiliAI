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
from datetime import datetime, timedelta
from typing import cast

from analytics.risk.exceptions import RiskHistoryError, RiskProjectionError, RiskSourceError
from analytics.risk.models import (
    RankedRiskEntry,
    RiskAssessmentRecord,
    RiskFactor,
    RiskProfile,
    RiskSignal,
)
from analytics.risk.projections import (
    RiskProjectionLevel,
    RiskProjectionPage,
    RiskProjectionQuery,
    RiskProjectionRow,
    RiskProjectionStatus,
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

_DELETE_BY_KB_SQL = "DELETE FROM risk_score_history WHERE knowledge_base_id = %s"

_PROJECTION_UPSERT_SQL = """
    INSERT INTO risk_projections (
        knowledge_base_id, entity_id, entity_type, overall_score, risk_level,
        top_typology_ids, alert_ids, case_ids, evidence_pack_ids, score_run_id,
        model_version, catalog_version, scored_at, updated_at, status
    ) VALUES (
        %s, %s, %s, %s, %s,
        %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s,
        %s, %s, %s, %s, %s
    )
    ON CONFLICT (knowledge_base_id, entity_id)
    DO UPDATE SET
        entity_type = EXCLUDED.entity_type,
        overall_score = EXCLUDED.overall_score,
        risk_level = EXCLUDED.risk_level,
        top_typology_ids = EXCLUDED.top_typology_ids,
        alert_ids = EXCLUDED.alert_ids,
        case_ids = EXCLUDED.case_ids,
        evidence_pack_ids = EXCLUDED.evidence_pack_ids,
        score_run_id = EXCLUDED.score_run_id,
        model_version = EXCLUDED.model_version,
        catalog_version = EXCLUDED.catalog_version,
        scored_at = EXCLUDED.scored_at,
        updated_at = EXCLUDED.updated_at,
        status = EXCLUDED.status
    WHERE risk_projections.scored_at <= EXCLUDED.scored_at
"""

_PROJECTION_SELECT_COLUMNS = """
    knowledge_base_id, entity_id, entity_type, overall_score, risk_level,
    top_typology_ids, alert_ids, case_ids, evidence_pack_ids, score_run_id,
    model_version, catalog_version, scored_at, updated_at, status
"""

_PROJECTION_GET_SQL = f"""
    SELECT {_PROJECTION_SELECT_COLUMNS}
    FROM risk_projections
    WHERE knowledge_base_id = %s AND entity_id = %s
"""

_PROJECTION_LIST_ALL_SQL = f"""
    SELECT {_PROJECTION_SELECT_COLUMNS}
    FROM risk_projections
    WHERE knowledge_base_id = %s
"""

_PROJECTION_COUNT_PREFIX = "SELECT count(*) FROM risk_projections"
_PROJECTION_LIST_PREFIX = f"""
    SELECT {_PROJECTION_SELECT_COLUMNS}
    FROM risk_projections
"""

_PROJECTION_DELETE_BY_KB_SQL = "DELETE FROM risk_projections WHERE knowledge_base_id = %s"

_PROJECTION_REBUILD_SOURCE_SQL = """
    WITH latest_scores AS (
        SELECT DISTINCT ON (entity_id)
            knowledge_base_id,
            entity_id,
            overall_score,
            risk_level,
            factors,
            request_id,
            assessed_at
        FROM risk_score_history
        WHERE knowledge_base_id = %s
        ORDER BY entity_id, assessed_at DESC
    ),
    alert_refs AS (
        SELECT
            entity_id,
            max(entity_type) AS entity_type,
            jsonb_agg(alert_id ORDER BY updated_at DESC) FILTER (WHERE alert_id IS NOT NULL) AS alert_ids,
            jsonb_agg(evidence_pack_id ORDER BY updated_at DESC) FILTER (WHERE evidence_pack_id IS NOT NULL) AS evidence_pack_ids,
            max(updated_at) AS updated_at
        FROM alert_history
        WHERE knowledge_base_id = %s
        GROUP BY entity_id
    )
    SELECT
        latest_scores.entity_id,
        latest_scores.overall_score,
        latest_scores.risk_level,
        latest_scores.factors,
        latest_scores.request_id,
        latest_scores.assessed_at,
        coalesce(alert_refs.entity_type, split_part(latest_scores.entity_id, ':', 1)) AS entity_type,
        coalesce(alert_refs.alert_ids, '[]'::jsonb) AS alert_ids,
        coalesce(alert_refs.evidence_pack_ids, '[]'::jsonb) AS evidence_pack_ids,
        coalesce(alert_refs.updated_at, latest_scores.assessed_at) AS updated_at
    FROM latest_scores
    LEFT JOIN alert_refs ON alert_refs.entity_id = latest_scores.entity_id
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

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        """Delete all risk-score history for a knowledge base; return rows removed."""

        try:
            with self._provider.connection() as conn:
                cursor = conn.execute(_DELETE_BY_KB_SQL, (knowledge_base_id,))
                conn.commit()
                return cursor.rowcount
        except Exception as exc:
            raise RiskHistoryError(
                "Failed to delete risk score history."
            ) from exc


class PostgresRiskProjectionRepository:
    """A durable ``RiskProjectionRepositoryProtocol`` backed by Postgres."""

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def upsert(self, row: RiskProjectionRow) -> RiskProjectionRow:
        try:
            with self._provider.connection() as conn:
                conn.execute(_PROJECTION_UPSERT_SQL, _projection_insert_params(row))
                conn.commit()
        except Exception as exc:
            raise RiskProjectionError("Failed to upsert risk projection.") from exc
        stored = self.get(row.knowledge_base_id, row.entity_id)
        return stored if stored is not None else row.model_copy(deep=True)

    def get(self, knowledge_base_id: str, entity_id: str) -> RiskProjectionRow | None:
        try:
            with self._provider.connection() as conn:
                row = conn.execute(
                    _PROJECTION_GET_SQL,
                    (knowledge_base_id, entity_id),
                ).fetchone()
        except Exception as exc:
            raise RiskProjectionError("Failed to load risk projection.") from exc
        return _projection_row_from_db(row) if row is not None else None

    def list(self, query: RiskProjectionQuery) -> RiskProjectionPage:
        where_sql, where_params = _projection_where_clause(query)
        list_sql = f"""
            {_PROJECTION_LIST_PREFIX}
            {where_sql}
            ORDER BY overall_score DESC, scored_at DESC, entity_id ASC
            LIMIT %s OFFSET %s
        """
        try:
            with self._provider.connection() as conn:
                total_row = conn.execute(
                    f"{_PROJECTION_COUNT_PREFIX} {where_sql}",
                    where_params,
                ).fetchone()
                rows = conn.execute(
                    list_sql,
                    (*where_params, query.limit, query.offset),
                ).fetchall()
        except Exception as exc:
            raise RiskProjectionError("Failed to list risk projections.") from exc
        total = int(cast(int, total_row[0])) if total_row is not None else 0
        return RiskProjectionPage(
            items=[
                _projection_row_from_db(row)
                for row in rows
            ],
            total=total,
            limit=query.limit,
            offset=query.offset,
        )

    def list_all(self, knowledge_base_id: str) -> list[RiskProjectionRow]:
        try:
            with self._provider.connection() as conn:
                rows = conn.execute(
                    _PROJECTION_LIST_ALL_SQL,
                    (knowledge_base_id,),
                ).fetchall()
        except Exception as exc:
            raise RiskProjectionError("Failed to list risk projections.") from exc
        return [
            _projection_row_from_db(row)
            for row in rows
        ]

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        try:
            with self._provider.connection() as conn:
                cursor = conn.execute(_PROJECTION_DELETE_BY_KB_SQL, (knowledge_base_id,))
                conn.commit()
                return cursor.rowcount
        except Exception as exc:
            raise RiskProjectionError("Failed to delete risk projections.") from exc

    def replace_knowledge_base(
        self,
        knowledge_base_id: str,
        rows: list[RiskProjectionRow],
    ) -> tuple[int, int]:
        incoming = [
            row
            for row in rows
            if row.knowledge_base_id == knowledge_base_id
        ]
        try:
            with self._provider.connection() as conn:
                try:
                    delete_cursor = conn.execute(
                        _PROJECTION_DELETE_BY_KB_SQL,
                        (knowledge_base_id,),
                    )
                    for row in incoming:
                        conn.execute(_PROJECTION_UPSERT_SQL, _projection_insert_params(row))
                    conn.commit()
                    return delete_cursor.rowcount, len(incoming)
                except Exception:
                    conn.rollback()
                    raise
        except Exception as exc:
            raise RiskProjectionError("Failed to replace risk projections.") from exc


class PostgresRiskProjectionRebuildSource:
    """Build projection rows from durable risk score history and alert refs."""

    def __init__(
        self,
        provider: ConnectionProvider,
        *,
        feature_typology_index: dict[str, list[str]] | None = None,
    ) -> None:
        self._provider = provider
        self._feature_typology_index = feature_typology_index or {}

    def load_projection_rows(self, knowledge_base_id: str) -> list[RiskProjectionRow]:
        try:
            with self._provider.connection() as conn:
                rows = conn.execute(
                    _PROJECTION_REBUILD_SOURCE_SQL,
                    (knowledge_base_id, knowledge_base_id),
                ).fetchall()
        except Exception as exc:
            raise RiskProjectionError(
                "Failed to load risk projection rebuild source rows."
            ) from exc
        return [
            _projection_row_from_rebuild_source(
                knowledge_base_id,
                row,
                feature_typology_index=self._feature_typology_index,
            )
            for row in rows
        ]


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
        """Return entities ranked by latest score.

        The SQL returns the latest score per entity; ``entity_type`` filtering,
        ranking, and ``limit`` slicing are applied in Python, mirroring
        ``InMemoryRiskSignalSource`` (``entity_type`` is derived from the id and
        is not a column on ``risk_score_history``). For large entity counts this
        ordering/limiting could be pushed into SQL.
        """

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


def _projection_insert_params(row: RiskProjectionRow) -> tuple[object, ...]:
    return (
        row.knowledge_base_id,
        row.entity_id,
        row.entity_type,
        row.overall_score,
        row.risk_level,
        json.dumps(row.top_typology_ids),
        json.dumps(row.alert_ids),
        json.dumps(row.case_ids),
        json.dumps(row.evidence_pack_ids),
        row.score_run_id,
        row.model_version,
        row.catalog_version,
        row.scored_at,
        row.updated_at,
        row.status,
    )


def _projection_where_clause(query: RiskProjectionQuery) -> tuple[str, tuple[object, ...]]:
    clauses = ["knowledge_base_id = %s"]
    params: list[object] = [query.knowledge_base_id]
    if query.entity_type is not None:
        clauses.append("entity_type = %s")
        params.append(query.entity_type)
    if query.risk_level is not None:
        clauses.append("risk_level = %s")
        params.append(query.risk_level)
    if query.typology_id is not None:
        clauses.append("top_typology_ids ? %s")
        params.append(query.typology_id)
    if query.status is not None:
        clauses.append("status = %s")
        params.append(query.status)
    if query.max_score_age_hours is not None:
        clauses.append("scored_at >= %s")
        params.append(query.as_of - timedelta(hours=query.max_score_age_hours))
    return f"WHERE {' AND '.join(clauses)}", tuple(params)


def _json_list(value: object) -> list[str]:
    if value is None:
        return []
    loaded: object = json.loads(value) if isinstance(value, str) else value
    if not isinstance(loaded, list):
        return []
    return [
        str(item)
        for item in cast(list[object], loaded)
        if item is not None
    ]


def _projection_row_from_db(row: tuple[object, ...]) -> RiskProjectionRow:
    return RiskProjectionRow(
        knowledge_base_id=str(row[0]),
        entity_id=str(row[1]),
        entity_type=str(row[2]),
        overall_score=float(cast(float, row[3])),
        risk_level=cast(RiskProjectionLevel, row[4]),
        top_typology_ids=_json_list(row[5]),
        alert_ids=_json_list(row[6]),
        case_ids=_json_list(row[7]),
        evidence_pack_ids=_json_list(row[8]),
        score_run_id=None if row[9] is None else str(row[9]),
        model_version=str(row[10]),
        catalog_version=str(row[11]),
        scored_at=cast(datetime, row[12]),
        updated_at=cast(datetime, row[13]),
        status=cast(RiskProjectionStatus, row[14]),
    )


def _projection_row_from_rebuild_source(
    knowledge_base_id: str,
    row: tuple[object, ...],
    *,
    feature_typology_index: dict[str, list[str]],
) -> RiskProjectionRow:
    return RiskProjectionRow(
        knowledge_base_id=knowledge_base_id,
        entity_id=str(row[0]),
        entity_type=str(row[6]),
        overall_score=float(cast(float, row[1])),
        risk_level=cast(RiskProjectionLevel, row[2]),
        top_typology_ids=_typology_ids_from_factor_json(row[3], feature_typology_index),
        alert_ids=_json_list(row[7]),
        case_ids=[],
        evidence_pack_ids=_json_list(row[8]),
        score_run_id=None if row[4] is None else str(row[4]),
        model_version="risk-score-history",
        catalog_version="risk-score-history",
        scored_at=cast(datetime, row[5]),
        updated_at=cast(datetime, row[9]),
        status="active",
    )


def _typology_ids_from_factor_json(
    value: object,
    feature_typology_index: dict[str, list[str]],
) -> list[str]:
    factors: object = json.loads(value) if isinstance(value, str) else value
    if not isinstance(factors, list):
        return []
    typology_ids: set[str] = set()
    for factor in cast(list[object], factors):
        if not isinstance(factor, dict):
            continue
        factor_name = cast(dict[str, object], factor).get("factor_name")
        if factor_name is None:
            continue
        typology_ids.update(feature_typology_index.get(str(factor_name), ()))
    return sorted(typology_ids)


__all__ = [
    "PostgresRiskHistoryStore",
    "PostgresRiskProjectionRebuildSource",
    "PostgresRiskProjectionRepository",
    "PostgresRiskSignalSource",
]
