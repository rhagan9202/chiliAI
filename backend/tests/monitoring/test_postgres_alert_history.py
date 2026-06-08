"""Integration tests for the Postgres alert-history store."""

from __future__ import annotations

import os

import pytest

from config.schema import DatabaseConfig
from database.runtime import create_connection_provider
from monitoring.adapters.postgres import PostgresAlertHistoryStore
from monitoring.models import AlertHistoryRecord

pytestmark = pytest.mark.integration


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set; skipping alert-history test.")
    return url


def _record(alert_id: str) -> AlertHistoryRecord:
    return AlertHistoryRecord(
        knowledge_base_id="kb-alert-test",
        alert_id=alert_id,
        entity_id="claim:c1",
        entity_type="claim",
        severity="high",
        status="open",
        title="Anomalous claim",
        reasoning="score exceeded threshold",
        metric_name="claim_anomaly",
    )


def test_write_and_count_round_trip(database_url: str) -> None:
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    store = PostgresAlertHistoryStore(provider)
    try:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM alert_history WHERE knowledge_base_id = 'kb-alert-test'"
            )
            conn.commit()

        assert store.write_alerts([]) == 0
        assert store.write_alerts([_record("a-1"), _record("a-2")]) == 2
        # Idempotent on (knowledge_base_id, alert_id).
        assert store.write_alerts([_record("a-1")]) == 0
        assert (
            store.count_open_alerts(
                knowledge_base_id="kb-alert-test", entity_id="claim:c1"
            )
            == 2
        )
    finally:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM alert_history WHERE knowledge_base_id = 'kb-alert-test'"
            )
            conn.commit()
        provider.close()


def test_delete_by_kb_removes_alert_history(database_url: str) -> None:
    kb_id = "kb-alert-delete-test-unique"
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    store = PostgresAlertHistoryStore(provider)
    try:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM alert_history WHERE knowledge_base_id = %s", (kb_id,)
            )
            conn.commit()

        record = AlertHistoryRecord(
            knowledge_base_id=kb_id,
            alert_id="a-del-1",
            entity_id="claim:c1",
            entity_type="claim",
            severity="high",
            status="open",
            title="Anomalous claim",
            reasoning="score exceeded threshold",
            metric_name="claim_anomaly",
        )
        store.write_alerts([record])

        count = store.delete_by_kb(kb_id)
        assert count == 1

        with provider.connection() as conn:
            rows = conn.execute(
                "SELECT count(*) FROM alert_history WHERE knowledge_base_id = %s",
                (kb_id,),
            ).fetchone()
            assert rows is not None and rows[0] == 0

        # Idempotent second call.
        assert store.delete_by_kb(kb_id) == 0
    finally:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM alert_history WHERE knowledge_base_id = %s", (kb_id,)
            )
            conn.commit()
        provider.close()
