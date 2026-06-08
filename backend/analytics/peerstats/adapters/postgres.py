"""Postgres-backed peerstats adapters.

``PostgresRecordColumnSource`` aggregates the ``raw_records`` JSONB payload in
SQL (one row per entity per interval bucket); ``PostgresDerivedRiskSignalWriter``
upserts ``entity_derived_signals``. Both depend only on the psycopg-free
``database.ConnectionProvider`` protocol and use positional ``%s`` parameters.

Notes:
- ``date_trunc`` runs in the database session timezone; the deployment runs
  Postgres in UTC, matching the Python ``bucket_start`` helper used to compute
  the ``interval_starts`` filter.
- Rows whose value column is present but not numeric-castable are excluded by a
  regex guard in the subquery (implements the design's "non-numeric value →
  record skipped" rule), so one bad value never aborts the whole batch. For the
  ``count`` aggregation this means counting records with a numeric value column.

The helper functions and ``UPSERT_SQL`` are public so the no-DB consistency
tests can assert placeholder/param alignment without importing private names.
"""

from __future__ import annotations

from datetime import datetime
from typing import cast

from analytics.peerstats.exceptions import PeerStatsSourceError
from analytics.peerstats.models import DerivedRiskSignal, PeerAggregate
from config.schema import PeerMetricSpec
from database.protocols import ConnectionProvider, Row

_AGG_EXPR: dict[str, str] = {
    "sum": "sum(val)",
    "mean": "avg(val)",
    "count": "count(*)",
    "max": "max(val)",
    "min": "min(val)",
}

UPSERT_SQL = """
    INSERT INTO entity_derived_signals (
        knowledge_base_id, entity_id, entity_type, metric_name, interval_start,
        peer_group_key, aggregate_value, peer_mean, peer_std, z_score,
        signal_value, weight, rationale, correlation_id
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (knowledge_base_id, entity_id, metric_name, interval_start)
    DO UPDATE SET
        entity_type = EXCLUDED.entity_type,
        peer_group_key = EXCLUDED.peer_group_key,
        aggregate_value = EXCLUDED.aggregate_value,
        peer_mean = EXCLUDED.peer_mean,
        peer_std = EXCLUDED.peer_std,
        z_score = EXCLUDED.z_score,
        signal_value = EXCLUDED.signal_value,
        weight = EXCLUDED.weight,
        rationale = EXCLUDED.rationale,
        correlation_id = EXCLUDED.correlation_id,
        computed_at = now()
"""

_DELETE_BY_KB_SQL = "DELETE FROM entity_derived_signals WHERE knowledge_base_id = %s"


def build_agg_sql(spec: PeerMetricSpec) -> str:
    """Build the per-entity, per-interval aggregation SQL (positional %s)."""

    group_concat = "".join(
        " || '|' || coalesce(payload->>%s, '')" for _ in spec.group_by
    )
    time_expr = (
        "ingested_at"
        if spec.time_column is None
        else "(payload->>%s)::timestamptz"
    )
    return f"""
        SELECT
            %s || ':' || (payload->>%s) AS entity_id,
            %s AS entity_type,
            (%s{group_concat}) AS peer_group_key,
            date_trunc(%s, {time_expr}) AS interval_start,
            {_AGG_EXPR[spec.aggregation]} AS aggregate_value
        FROM (
            SELECT payload, ingested_at, (payload->>%s)::numeric AS val
            FROM raw_records
            WHERE knowledge_base_id = %s
              AND record_type = %s
              AND jsonb_exists(payload, %s)
              AND jsonb_exists(payload, %s)
              AND (payload->>%s) ~ '^-?[0-9]+([.][0-9]+)?$'
        ) AS rows
        GROUP BY entity_id, entity_type, peer_group_key, interval_start
    """


def build_agg_params(
    spec: PeerMetricSpec, *, knowledge_base_id: str
) -> tuple[object, ...]:
    """Positional params for ``build_agg_sql``, in textual %s order.

    Placeholder positions (base case, no group_by, no time_column):
      1  entity_type        — entity_id prefix
      2  entity_id_field    — entity_id JSONB key
      3  entity_type        — entity_type literal column
      4  entity_type        — peer_group_key base value
      5  interval           — date_trunc field
      6  value_column       — (payload->>%s)::numeric AS val
      7  knowledge_base_id  — WHERE knowledge_base_id
      8  record_type        — WHERE record_type
      9  value_column       — jsonb_exists value column
      10 entity_id_field    — jsonb_exists id field
      11 value_column       — numeric-castability regex guard

    Each group_by item inserts one %s between position 4 and 5.
    time_column (when not None) inserts one %s between interval and value_column.
    """

    params: list[object] = [
        spec.entity_type,      # %s #1: entity_id prefix
        spec.entity_id_field,  # %s #2: entity_id JSONB key
        spec.entity_type,      # %s #3: entity_type column
        spec.entity_type,      # %s #4: peer_group_key base
    ]
    params.extend(spec.group_by)  # %s #5..N: peer_group_key group cols
    params.append(spec.interval)  # next: date_trunc field
    if spec.time_column is not None:
        params.append(spec.time_column)  # next: time_expr JSONB key
    params.append(spec.value_column)     # next: (payload->>%s)::numeric AS val
    params.append(knowledge_base_id)     # next: WHERE knowledge_base_id
    params.append(spec.record_type)      # next: WHERE record_type
    params.append(spec.value_column)     # next: jsonb_exists value_column
    params.append(spec.entity_id_field)  # next: jsonb_exists entity_id_field
    params.append(spec.value_column)     # next: numeric-castability regex guard
    return tuple(params)


def signal_params(signal: DerivedRiskSignal) -> tuple[object, ...]:
    """Positional params for ``UPSERT_SQL`` (14 values)."""

    return (
        signal.knowledge_base_id,
        signal.entity_id,
        signal.entity_type,
        signal.metric_name,
        signal.interval_start,
        signal.peer_group_key,
        signal.aggregate_value,
        signal.peer_mean,
        signal.peer_std,
        signal.z_score,
        signal.signal_value,
        signal.weight,
        signal.rationale,
        signal.correlation_id,
    )


class PostgresRecordColumnSource:
    """Aggregate raw_records JSONB columns per entity per interval in SQL."""

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def load_interval_aggregates(
        self,
        *,
        knowledge_base_id: str,
        spec: PeerMetricSpec,
        interval_starts: list[datetime],
    ) -> list[PeerAggregate]:
        """Load per-entity, per-interval aggregates from raw_records.

        Filters the result set to only the requested ``interval_starts`` after
        fetching — the SQL intentionally omits a time-range predicate so the
        query plan stays simple and the caller controls filtering granularity.
        An empty ``interval_starts`` disables the filter and returns aggregates
        for all available intervals.
        """

        try:
            with self._provider.connection() as conn:
                rows: list[Row] = conn.execute(
                    build_agg_sql(spec),
                    build_agg_params(spec, knowledge_base_id=knowledge_base_id),
                ).fetchall()
        except Exception as exc:
            raise PeerStatsSourceError("Failed to aggregate record columns.") from exc
        wanted = set(interval_starts)
        aggregates: list[PeerAggregate] = []
        for row in rows:
            interval_start = cast(datetime, row[3])
            if wanted and interval_start not in wanted:
                continue
            aggregates.append(
                PeerAggregate(
                    entity_id=str(row[0]),
                    entity_type=str(row[1]),
                    peer_group_key=str(row[2]),
                    interval_start=interval_start,
                    aggregate_value=float(cast(float, row[4])),
                )
            )
        return aggregates


class PostgresDerivedRiskSignalWriter:
    """Upsert derived risk signals into entity_derived_signals."""

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def write_signals(self, signals: list[DerivedRiskSignal]) -> int:
        """Upsert each signal; return the count of signals processed."""

        if not signals:
            return 0
        try:
            with self._provider.connection() as conn:
                for signal in signals:
                    conn.execute(UPSERT_SQL, signal_params(signal))
                conn.commit()
        except Exception as exc:
            raise PeerStatsSourceError(
                "Failed to write derived risk signals."
            ) from exc
        return len(signals)

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        """Delete all derived signals for a knowledge base; return rows removed."""

        try:
            with self._provider.connection() as conn:
                cursor = conn.execute(_DELETE_BY_KB_SQL, (knowledge_base_id,))
                conn.commit()
                return cursor.rowcount
        except Exception as exc:
            raise PeerStatsSourceError(
                "Failed to delete derived risk signals."
            ) from exc


__all__ = [
    "UPSERT_SQL",
    "PostgresDerivedRiskSignalWriter",
    "PostgresRecordColumnSource",
    "build_agg_params",
    "build_agg_sql",
    "signal_params",
]
