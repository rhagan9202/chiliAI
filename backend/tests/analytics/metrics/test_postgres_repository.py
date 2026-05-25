"""Integration tests for the Postgres entity-metric repository."""

from __future__ import annotations

import os

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
