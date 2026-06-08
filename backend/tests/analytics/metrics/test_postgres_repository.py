"""Integration tests for the Postgres entity-metric repository."""

from __future__ import annotations

import os
from typing import cast

import pytest

from analytics.metrics.adapters.postgres import PostgresEntityMetricRepository
from analytics.metrics.models import EntityMetricSample
from config.schema import DatabaseConfig
from database.runtime import create_connection_provider

pytestmark = pytest.mark.integration


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set; skipping metrics integration test.")
    return url


def _sample(metric: str, value: float) -> EntityMetricSample:
    return EntityMetricSample(
        knowledge_base_id="kb-metrics-test",
        entity_id="__graph__",
        metric_name=metric,
        value=value,
        correlation_id="corr-metrics-1",
    )


def _sample_for_kb(kb: str, metric: str, value: float) -> EntityMetricSample:
    return EntityMetricSample(
        knowledge_base_id=kb,
        entity_id="__graph__",
        metric_name=metric,
        value=value,
        correlation_id="corr-del",
    )


TEST_KB = "kb-metrics-delete-test"


def test_delete_by_kb_purges_both_tables(database_url: str) -> None:
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    repo = PostgresEntityMetricRepository(provider)
    try:
        # Seed two metrics for the test KB.
        repo.record_metrics([
            _sample_for_kb(TEST_KB, "entity_count", 3.0),
            _sample_for_kb(TEST_KB, "edge_count", 7.0),
        ])

        removed = repo.delete_by_kb(TEST_KB)

        assert removed == 2

        # entity_metric_history should have 0 rows for this KB.
        with provider.connection() as conn:
            hist_rows = conn.execute(
                "SELECT COUNT(*) FROM entity_metric_history WHERE knowledge_base_id = %s",
                (TEST_KB,),
            ).fetchone()
            assert hist_rows is not None
            assert cast(int, hist_rows[0]) == 0

            curr_rows = conn.execute(
                "SELECT COUNT(*) FROM entity_metrics_current WHERE knowledge_base_id = %s",
                (TEST_KB,),
            ).fetchone()
            assert curr_rows is not None
            assert cast(int, curr_rows[0]) == 0

        # Idempotent — second call returns 0.
        assert repo.delete_by_kb(TEST_KB) == 0
    finally:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM entity_metric_history WHERE knowledge_base_id = %s",
                (TEST_KB,),
            )
            conn.execute(
                "DELETE FROM entity_metrics_current WHERE knowledge_base_id = %s",
                (TEST_KB,),
            )
            conn.commit()
        provider.close()


def test_record_metrics_round_trip_and_idempotent(database_url: str) -> None:
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    repo = PostgresEntityMetricRepository(provider)
    try:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM entity_metric_history "
                "WHERE knowledge_base_id = 'kb-metrics-test'"
            )
            conn.execute(
                "DELETE FROM entity_metrics_current "
                "WHERE knowledge_base_id = 'kb-metrics-test'"
            )
            conn.commit()

        assert repo.record_metrics([]) == 0

        sample = _sample("entity_count", 5.0)
        assert repo.record_metrics([sample]) == 1
        # Same observed_at -> idempotent, no new history row.
        assert repo.record_metrics([sample]) == 0

        current = repo.load_current_metrics(
            knowledge_base_id="kb-metrics-test", entity_id="__graph__"
        )
        assert [(c.metric_name, c.value) for c in current] == [("entity_count", 5.0)]
    finally:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM entity_metric_history "
                "WHERE knowledge_base_id = 'kb-metrics-test'"
            )
            conn.execute(
                "DELETE FROM entity_metrics_current "
                "WHERE knowledge_base_id = 'kb-metrics-test'"
            )
            conn.commit()
        provider.close()
