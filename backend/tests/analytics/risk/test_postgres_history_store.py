"""Integration tests for the Postgres risk-history store."""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from analytics.risk.adapters.postgres import PostgresRiskHistoryStore
from analytics.risk.models import RiskAssessmentRecord, RiskFactor
from config.schema import DatabaseConfig
from database.runtime import create_connection_provider

pytestmark = pytest.mark.integration


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set; skipping risk-history test.")
    return url


def _record(request_id: str, *, score: float, assessed_at: datetime) -> RiskAssessmentRecord:
    return RiskAssessmentRecord(
        knowledge_base_id="kb-risk-test",
        entity_id="claim:c1",
        request_id=request_id,
        overall_score=score,
        risk_level="high",
        factors=[
            RiskFactor(
                factor_name="anomaly",
                raw_value=0.9,
                weight=1.0,
                contribution=score,
                rationale="integration test",
            )
        ],
        assessed_at=assessed_at,
    )


def test_write_and_load_latest_score(database_url: str) -> None:
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    store = PostgresRiskHistoryStore(provider)
    try:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM risk_score_history "
                "WHERE knowledge_base_id = 'kb-risk-test'"
            )
            conn.commit()

        first = _record(
            "req-risk-1", score=0.4,
            assessed_at=datetime(2026, 5, 16, tzinfo=timezone.utc),
        )
        second = _record(
            "req-risk-2", score=0.8,
            assessed_at=datetime(2026, 5, 17, tzinfo=timezone.utc),
        )
        assert store.write_assessment(first) is True
        # Idempotent on request_id.
        assert store.write_assessment(first) is False
        assert store.write_assessment(second) is True

        assert (
            store.load_historical_score(
                knowledge_base_id="kb-risk-test", entity_id="claim:c1"
            )
            == 0.8
        )
        assert (
            store.load_historical_score(
                knowledge_base_id="kb-risk-test", entity_id="claim:absent"
            )
            is None
        )
    finally:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM risk_score_history "
                "WHERE knowledge_base_id = 'kb-risk-test'"
            )
            conn.commit()
        provider.close()
