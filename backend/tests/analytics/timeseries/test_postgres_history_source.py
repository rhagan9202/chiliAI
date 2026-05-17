"""Integration tests for the Postgres time-series history source."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from analytics.metrics.adapters.postgres import PostgresEntityMetricRepository
from analytics.metrics.models import EntityMetricSample
from analytics.timeseries.adapters.postgres import PostgresTimeSeriesHistorySource
from config.schema import DatabaseConfig
from database.runtime import create_connection_provider

pytestmark = pytest.mark.integration


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set; skipping timeseries source test.")
    return url


def test_load_series_and_metric_range(database_url: str) -> None:
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    repo = PostgresEntityMetricRepository(provider)
    source = PostgresTimeSeriesHistorySource(provider)
    base = datetime(2026, 5, 16, 12, 0, 0, tzinfo=timezone.utc)
    try:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM entity_metric_history "
                "WHERE knowledge_base_id = 'kb-ts-test'"
            )
            conn.execute(
                "DELETE FROM entity_metrics_current "
                "WHERE knowledge_base_id = 'kb-ts-test'"
            )
            conn.commit()

        repo.record_metrics(
            [
                EntityMetricSample(
                    knowledge_base_id="kb-ts-test",
                    entity_id="__graph__",
                    metric_name="entity_count",
                    value=float(index),
                    observed_at=base + timedelta(minutes=index),
                    correlation_id=f"corr-{index}",
                )
                for index in range(3)
            ]
        )

        series = source.load_series(
            knowledge_base_id="kb-ts-test",
            entity_id="__graph__",
            metric_name="entity_count",
        )
        assert [obs.value for obs in series.observations] == [0.0, 1.0, 2.0]

        window = source.load_metric_range(
            knowledge_base_id="kb-ts-test",
            metric_name="entity_count",
            start=base,
            end=base + timedelta(minutes=1),
        )
        assert [obs.value for obs in window] == [0.0, 1.0]
    finally:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM entity_metric_history "
                "WHERE knowledge_base_id = 'kb-ts-test'"
            )
            conn.execute(
                "DELETE FROM entity_metrics_current "
                "WHERE knowledge_base_id = 'kb-ts-test'"
            )
            conn.commit()
        provider.close()


def test_load_series_unknown_raises_value_error(database_url: str) -> None:
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    source = PostgresTimeSeriesHistorySource(provider)
    try:
        with pytest.raises(ValueError, match="No time series"):
            source.load_series(
                knowledge_base_id="kb-missing",
                entity_id="e-missing",
                metric_name="entity_count",
            )
    finally:
        provider.close()
