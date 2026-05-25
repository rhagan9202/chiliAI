"""Integration tests for the Postgres observation writer."""

from __future__ import annotations

import os

import pytest

from config.schema import DatabaseConfig
from database.runtime import create_connection_provider
from monitoring.adapters.postgres import PostgresObservationStore
from monitoring.models import MonitoringBatch, MonitoringObservation

pytestmark = pytest.mark.integration


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set; skipping observation store integration test.")
    return url


def _batch() -> MonitoringBatch:
    return MonitoringBatch(
        knowledge_base_id="kb-obs-test",
        batch_id="corr-obs-1",
        observations=[
            MonitoringObservation(
                entity_id="claim:c1",
                entity_type="claim",
                metric_name="claim_anomaly",
                score=0.8,
                rationale="integration test",
            )
        ],
    )


def test_write_observations_is_idempotent(database_url: str) -> None:
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    store = PostgresObservationStore(provider)
    batch = _batch()
    try:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM observations WHERE knowledge_base_id = 'kb-obs-test'"
            )
            conn.commit()

        assert store.write_observations(batch, correlation_id="corr-obs-1") == 1
        assert store.write_observations(batch, correlation_id="corr-obs-1") == 0

        with provider.connection() as conn:
            rows = conn.execute(
                "SELECT count(*) FROM observations WHERE knowledge_base_id = 'kb-obs-test'"
            ).fetchone()
            assert rows is not None and rows[0] == 1
    finally:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM observations WHERE knowledge_base_id = 'kb-obs-test'"
            )
            conn.commit()
        provider.close()
