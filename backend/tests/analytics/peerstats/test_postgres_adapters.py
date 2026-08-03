"""Tests for Postgres peerstats adapters (SQL/params consistency, no live DB)."""

from __future__ import annotations

from config.schema import PeerMetricSpec


def _spec(**overrides: object) -> PeerMetricSpec:
    base: dict[str, object] = dict(
        name="weekly_billing",
        record_type="claim_record",
        entity_type="provider",
        entity_id_field="provider_npi",
        value_column="billed_amount",
        aggregation="sum",
        interval="week",
    )
    base.update(overrides)
    return PeerMetricSpec(**base)  # type: ignore[arg-type]


def test_module_imports_without_psycopg() -> None:
    from analytics.peerstats.adapters.postgres import (
        PostgresDerivedRiskSignalWriter,
        PostgresRecordColumnSource,
    )

    assert PostgresRecordColumnSource is not None
    assert PostgresDerivedRiskSignalWriter is not None


def test_agg_sql_placeholder_count_matches_params_basic() -> None:
    from analytics.peerstats.adapters.postgres import (
        build_agg_params,
        build_agg_sql,
    )

    spec = _spec()
    sql = build_agg_sql(spec)
    params = build_agg_params(spec, knowledge_base_id="kb1")
    assert sql.count("%s") == len(params)


def test_agg_sql_placeholder_count_matches_params_with_group_and_time() -> None:
    from analytics.peerstats.adapters.postgres import (
        build_agg_params,
        build_agg_sql,
    )

    spec = _spec(group_by=["specialty", "state"], time_column="service_date")
    sql = build_agg_sql(spec)
    params = build_agg_params(spec, knowledge_base_id="kb1")
    assert sql.count("%s") == len(params)
    # group_by values appear in order within the params
    assert "specialty" in params
    assert "state" in params
    assert "service_date" in params


def test_agg_sql_guards_missing_time_column_when_time_column_set() -> None:
    """A row lacking the time_column key must be excluded from aggregation,
    mirroring the existing value-column jsonb_exists guard, so it never
    reaches the ::timestamptz cast and produces a NULL interval_start."""

    from analytics.peerstats.adapters.postgres import (
        build_agg_params,
        build_agg_sql,
    )

    spec = _spec(time_column="service_date")
    sql = build_agg_sql(spec)
    params = build_agg_params(spec, knowledge_base_id="kb1")
    assert sql.count("%s") == len(params)
    # Base guards (value + entity_id existence) are 2 jsonb_exists calls;
    # a time_column spec adds a third, existence-checking the time column,
    # same style as the value column guard immediately below it.
    where_clause = sql.split("WHERE", 1)[1]
    assert where_clause.count("jsonb_exists(payload, %s)") == 3
    assert "(payload->>%s) <> ''" in where_clause
    # service_date must appear as a param for each of: the SELECT time_expr,
    # the jsonb_exists guard, and the non-empty guard.
    assert params.count("service_date") == 3


def test_agg_sql_unchanged_without_time_column() -> None:
    from analytics.peerstats.adapters.postgres import (
        build_agg_params,
        build_agg_sql,
    )

    spec = _spec()
    sql = build_agg_sql(spec)
    params = build_agg_params(spec, knowledge_base_id="kb1")
    assert sql.count("%s") == len(params)
    where_clause = sql.split("WHERE", 1)[1]
    assert where_clause.count("jsonb_exists(payload, %s)") == 2
    assert "<> ''" not in where_clause


def test_upsert_placeholder_count_matches_signal_params() -> None:
    from datetime import datetime, timezone

    from analytics.peerstats.adapters.postgres import UPSERT_SQL, signal_params
    from analytics.peerstats.models import DerivedRiskSignal

    signal = DerivedRiskSignal(
        knowledge_base_id="kb1", entity_id="provider:1", entity_type="provider",
        metric_name="weekly_billing",
        interval_start=datetime(2026, 1, 5, tzinfo=timezone.utc),
        peer_group_key="provider", aggregate_value=15.0, peer_mean=9.0, peer_std=6.0,
        z_score=1.0, signal_value=0.25, weight=1.0, rationale="x", correlation_id="c1",
    )
    params = signal_params(signal)
    # The INSERT column list has 14 columns / 14 placeholders in the VALUES clause.
    assert UPSERT_SQL.count("%s") == len(params)
    assert len(params) == 14


def test_peer_group_signal_query_placeholder_count_matches_params() -> None:
    from datetime import datetime, timezone

    from analytics.peerstats.adapters.postgres import (
        PEER_GROUP_SIGNALS_SQL,
        peer_group_signals_params,
    )

    params = peer_group_signals_params(
        knowledge_base_id="kb1",
        metric_name="weekly_billing",
        interval_start=datetime(2026, 1, 5, tzinfo=timezone.utc),
        peer_group_key="provider|cardiology",
    )

    assert PEER_GROUP_SIGNALS_SQL.count("%s") == len(params)
    assert "knowledge_base_id = %s" in PEER_GROUP_SIGNALS_SQL
    assert "metric_name = %s" in PEER_GROUP_SIGNALS_SQL
    assert "interval_start = %s" in PEER_GROUP_SIGNALS_SQL
    assert "peer_group_key = %s" in PEER_GROUP_SIGNALS_SQL
