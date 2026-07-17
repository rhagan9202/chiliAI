"""Integration tests for the Postgres timeseries anomaly store."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from analytics.timeseries.adapters.postgres import PostgresTimeseriesAnomalyStore
from analytics.timeseries.models import TimeseriesAnomalyRecord
from config.schema import DatabaseConfig
from database.runtime import create_connection_provider

pytestmark = pytest.mark.integration


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set; skipping timeseries anomaly store test.")
    return url


def test_write_load_upsert_and_delete_by_kb(database_url: str) -> None:
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    store = PostgresTimeseriesAnomalyStore(provider)
    knowledge_base_id = f"kb-anomaly-test-{uuid4()}"
    base = datetime(2026, 5, 16, 12, 0, 0, tzinfo=timezone.utc)

    def _record(
        observed_at: datetime, *, severity: float, correlation_id: str
    ) -> TimeseriesAnomalyRecord:
        return TimeseriesAnomalyRecord(
            knowledge_base_id=knowledge_base_id,
            entity_id="provider:1",
            metric_name="weekly_billing_self",
            observed_at=observed_at,
            observed_value=900.0,
            expected_value=100.0,
            z_score=3.2,
            severity=severity,
            detection_strategy="z_score",
            correlation_id=correlation_id,
        )

    try:
        first = _record(base, severity=0.5, correlation_id="corr-1")
        second = _record(base + timedelta(minutes=1), severity=0.6, correlation_id="corr-2")
        assert store.write_anomalies([first, second]) == 2

        rewritten_first = _record(base, severity=0.9, correlation_id="corr-1-rewrite")
        assert store.write_anomalies([rewritten_first]) == 1

        loaded = store.load_anomalies(
            knowledge_base_id=knowledge_base_id,
            entity_id="provider:1",
            metric_name="weekly_billing_self",
        )
        assert [record.observed_at for record in loaded] == [
            first.observed_at,
            second.observed_at,
        ]
        assert loaded[0].severity == 0.9
        assert loaded[0].correlation_id == "corr-1-rewrite"
        assert loaded[1].severity == 0.6

        assert store.delete_by_kb(knowledge_base_id) == 2
        assert (
            store.load_anomalies(
                knowledge_base_id=knowledge_base_id,
                entity_id="provider:1",
                metric_name="weekly_billing_self",
            )
            == []
        )
    finally:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM timeseries_anomalies WHERE knowledge_base_id = %s",
                (knowledge_base_id,),
            )
            conn.commit()
        provider.close()
