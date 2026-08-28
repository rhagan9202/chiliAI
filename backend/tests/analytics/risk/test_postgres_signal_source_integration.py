"""Integration tests for PostgresRiskSignalSource (require a live DB).

The sibling unit tests drive the adapter through a fake connection provider
that returns canned rows, so they never execute the adapter's SQL and cannot
observe which row an ``ORDER BY`` actually selects. Signal freshness is a
property of that SQL, so it is only testable against a real database.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from analytics.peerstats.adapters.postgres import PostgresDerivedRiskSignalWriter
from analytics.peerstats.models import DerivedRiskSignal
from analytics.risk.adapters.postgres import PostgresRiskSignalSource
from config.schema import DatabaseConfig
from database.protocols import ConnectionProvider
from database.runtime import create_connection_provider

pytestmark = pytest.mark.integration

_KB = "kb-risk-freshness-test"
_ENTITY = "provider:freshness-1"
_METRIC = "weekly_provider_billing"


@pytest.fixture
def provider() -> ConnectionProvider:
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL is not set; skipping risk signal source test.")
    prov = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert prov is not None
    with prov.connection() as conn:
        conn.execute(
            "DELETE FROM entity_derived_signals WHERE knowledge_base_id = %s", (_KB,)
        )
        conn.commit()
    return prov


def _signal(*, interval_start: datetime, signal_value: float) -> DerivedRiskSignal:
    return DerivedRiskSignal(
        knowledge_base_id=_KB,
        entity_id=_ENTITY,
        entity_type="provider",
        metric_name=_METRIC,
        interval_start=interval_start,
        peer_group_key="specialty=cardiology",
        aggregate_value=100.0,
        peer_mean=10.0,
        peer_std=1.0,
        z_score=signal_value * 10.0,
        signal_value=signal_value,
        weight=1.0,
        rationale=f"interval {interval_start.date().isoformat()}",
        correlation_id="corr-1",
    )


def test_load_profile_reads_the_latest_interval_not_an_arbitrary_one(
    provider: ConnectionProvider,
) -> None:
    """One metric, several intervals, one write — the newest interval wins.

    ``PeerStatsService.compute`` writes one row per (metric, interval_start)
    and ``write_signals`` commits them all in a single transaction, so every
    row shares a ``computed_at`` of ``now()``. Ordering on ``computed_at``
    alone therefore ties across intervals and Postgres is free to return any
    of them — a benign historical week can be scored instead of the current
    one.
    """
    writer = PostgresDerivedRiskSignalWriter(provider)
    benign = datetime(2026, 7, 6, tzinfo=timezone.utc)
    latest = datetime(2026, 8, 24, tzinfo=timezone.utc)
    writer.write_signals(
        [
            _signal(interval_start=benign, signal_value=0.05),
            _signal(interval_start=latest, signal_value=0.95),
        ]
    )

    profile = PostgresRiskSignalSource(provider).load_profile(
        knowledge_base_id=_KB, entity_id=_ENTITY
    )

    assert len(profile.signals) == 1
    assert profile.signals[0].value == pytest.approx(0.95)


def test_load_profile_returns_one_row_per_metric(
    provider: ConnectionProvider,
) -> None:
    """Several metrics each with several intervals collapse to one row each."""
    writer = PostgresDerivedRiskSignalWriter(provider)
    older = datetime(2026, 7, 6, tzinfo=timezone.utc)
    newer = datetime(2026, 8, 24, tzinfo=timezone.utc)
    second = _signal(interval_start=older, signal_value=0.10).model_copy(
        update={"metric_name": "weekly_provider_denials"}
    )
    third = _signal(interval_start=newer, signal_value=0.80).model_copy(
        update={"metric_name": "weekly_provider_denials"}
    )
    writer.write_signals(
        [
            _signal(interval_start=older, signal_value=0.05),
            _signal(interval_start=newer, signal_value=0.95),
            second,
            third,
        ]
    )

    profile = PostgresRiskSignalSource(provider).load_profile(
        knowledge_base_id=_KB, entity_id=_ENTITY
    )

    by_name = {s.signal_name: s.value for s in profile.signals}
    assert by_name == pytest.approx(
        {"weekly_provider_billing": 0.95, "weekly_provider_denials": 0.80}
    )


def test_latest_signal_lookup_is_index_backed(provider: ConnectionProvider) -> None:
    """The freshness ordering must be served by an index, not a sort.

    ``load_profile`` runs on the risk-scoring read path for every entity, so
    the index has to lead with the same columns the query orders on. An index
    that stops at ``computed_at`` forces Postgres to sort ``entity_derived_signals``
    on every call.
    """
    with provider.connection() as conn:
        rows = conn.execute(
            """
            SELECT indexdef FROM pg_indexes
            WHERE tablename = 'entity_derived_signals'
            """
        ).fetchall()

    definitions = " ".join(str(row[0]).lower() for row in rows)
    assert "interval_start desc" in definitions, (
        "no index covers the interval_start ordering that load_profile uses; "
        f"indexes present: {definitions}"
    )
