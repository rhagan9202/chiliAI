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
