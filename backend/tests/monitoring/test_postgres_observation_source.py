"""Integration tests for the Postgres observation source (read side)."""

from __future__ import annotations

import os

import pytest

from config.schema import DatabaseConfig
from database.runtime import create_connection_provider
from monitoring.adapters.postgres import PostgresObservationSource, PostgresObservationStore
from monitoring.models import MonitoringBatch, MonitoringObservation

pytestmark = pytest.mark.integration


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set; skipping observation source test.")
    return url


def _batch() -> MonitoringBatch:
    return MonitoringBatch(
        knowledge_base_id="kb-obs-src-test",
        batch_id="corr-obs-src-1",
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


def test_load_batch_round_trip(database_url: str) -> None:
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    writer = PostgresObservationStore(provider)
    source = PostgresObservationSource(provider)
    try:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM observations WHERE knowledge_base_id = 'kb-obs-src-test'"
            )
            conn.commit()

        writer.write_observations(_batch(), correlation_id="corr-obs-src-1")
        loaded = source.load_batch(
            knowledge_base_id="kb-obs-src-test", batch_id="corr-obs-src-1"
        )
        assert loaded.knowledge_base_id == "kb-obs-src-test"
        assert loaded.observations[0].metric_name == "claim_anomaly"
        assert loaded.observations[0].score == 0.8
    finally:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM observations WHERE knowledge_base_id = 'kb-obs-src-test'"
            )
            conn.commit()
        provider.close()


def test_load_batch_unknown_raises_value_error(database_url: str) -> None:
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    source = PostgresObservationSource(provider)
    try:
        with pytest.raises(ValueError, match="No monitoring batch"):
            source.load_batch(knowledge_base_id="kb-missing", batch_id="corr-missing")
    finally:
        provider.close()
