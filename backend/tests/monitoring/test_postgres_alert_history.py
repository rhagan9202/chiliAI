"""Integration tests for the Postgres alert-history store."""

from __future__ import annotations

import os
from datetime import datetime, timezone

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


def test_write_alerts_keeps_first_row_on_conflicting_rewrite(database_url: str) -> None:
    kb_id = "kb-alert-conflict-test"
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    store = PostgresAlertHistoryStore(provider)
    try:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM alert_history WHERE knowledge_base_id = %s", (kb_id,)
            )
            conn.commit()

        original = AlertHistoryRecord(
            knowledge_base_id=kb_id,
            alert_id="a-conflict-1",
            entity_id="claim:c1",
            entity_type="claim",
            severity="high",
            status="open",
            title="Original title",
            reasoning="score exceeded threshold",
            metric_name="claim_anomaly",
            entity_label="Dr. Original",
            confidence=0.42,
            tags=["original-tag"],
        )
        rewritten = original.model_copy(
            update={
                "title": "Rewritten title",
                "status": "closed",
                "entity_label": "Dr. Rewritten",
                "confidence": 0.99,
                "tags": ["rewritten-tag"],
            }
        )

        assert store.write_alerts([original]) == 1
        assert store.write_alerts([rewritten]) == 0

        fetched = store.get_alert("a-conflict-1")
        assert fetched is not None
        assert fetched.title == "Original title"
        assert fetched.status == "open"
        assert fetched.entity_label == "Dr. Original"
        assert fetched.confidence == 0.42
        assert fetched.tags == ["original-tag"]
    finally:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM alert_history WHERE knowledge_base_id = %s", (kb_id,)
            )
            conn.commit()
        provider.close()


def test_list_alerts_ordering_status_filter_and_pagination(database_url: str) -> None:
    kb_id = "kb-alert-list-test"
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    store = PostgresAlertHistoryStore(provider)
    try:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM alert_history WHERE knowledge_base_id = %s", (kb_id,)
            )
            conn.commit()

        same_time = datetime(2026, 5, 16, tzinfo=timezone.utc)
        store.write_alerts(
            [
                AlertHistoryRecord(
                    knowledge_base_id=kb_id,
                    alert_id="a-1",
                    entity_id="claim:c1",
                    entity_type="claim",
                    severity="high",
                    status="open",
                    title="Anomalous claim",
                    reasoning="score exceeded threshold",
                    metric_name="claim_anomaly",
                    created_at=datetime(2026, 5, 15, tzinfo=timezone.utc),
                ),
                AlertHistoryRecord(
                    knowledge_base_id=kb_id,
                    alert_id="a-3",
                    entity_id="claim:c1",
                    entity_type="claim",
                    severity="high",
                    status="closed",
                    title="Anomalous claim",
                    reasoning="score exceeded threshold",
                    metric_name="claim_anomaly",
                    created_at=same_time,
                ),
                AlertHistoryRecord(
                    knowledge_base_id=kb_id,
                    alert_id="a-2",
                    entity_id="claim:c1",
                    entity_type="claim",
                    severity="high",
                    status="open",
                    title="Anomalous claim",
                    reasoning="score exceeded threshold",
                    metric_name="claim_anomaly",
                    created_at=same_time,
                ),
            ]
        )

        records, total = store.list_alerts(limit=10, offset=0)
        our_records = [r for r in records if r.knowledge_base_id == kb_id]
        assert total >= 3
        assert [r.alert_id for r in our_records] == ["a-3", "a-2", "a-1"]

        filtered, filtered_total = store.list_alerts(
            statuses=["open"], limit=10, offset=0
        )
        our_filtered = [r for r in filtered if r.knowledge_base_id == kb_id]
        assert {r.alert_id for r in our_filtered} == {"a-1", "a-2"}
        assert filtered_total >= 2

        page, page_total = store.list_alerts(
            statuses=["open"], limit=1, offset=0
        )
        assert page_total == filtered_total
        assert len(page) == 1

        # Empty statuses list is parity with statuses=None: unfiltered.
        unfiltered_none, total_none = store.list_alerts(
            statuses=None, limit=10, offset=0
        )
        unfiltered_empty, total_empty = store.list_alerts(
            statuses=[], limit=10, offset=0
        )
        assert total_empty == total_none
        our_none = {r.alert_id for r in unfiltered_none if r.knowledge_base_id == kb_id}
        our_empty = {r.alert_id for r in unfiltered_empty if r.knowledge_base_id == kb_id}
        assert our_empty == our_none == {"a-1", "a-2", "a-3"}
    finally:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM alert_history WHERE knowledge_base_id = %s", (kb_id,)
            )
            conn.commit()
        provider.close()


def test_get_and_acknowledge_alert(database_url: str) -> None:
    kb_id = "kb-alert-ack-test"
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
            alert_id="a-ack-1",
            entity_id="claim:c1",
            entity_type="claim",
            severity="high",
            status="open",
            title="Anomalous claim",
            reasoning="score exceeded threshold",
            metric_name="claim_anomaly",
            entity_label="Dr. Jane Doe",
            confidence=0.87,
            tags=["peer-deviation", "billing-spike"],
        )
        store.write_alerts([record])

        fetched = store.get_alert("a-ack-1")
        assert fetched is not None
        assert fetched.entity_label == "Dr. Jane Doe"
        assert fetched.confidence == 0.87
        assert fetched.tags == ["peer-deviation", "billing-spike"]

        assert store.get_alert("missing-alert-id") is None

        updated = store.acknowledge("a-ack-1")
        assert updated is not None
        assert updated.status == "acknowledged"

        refetched = store.get_alert("a-ack-1")
        assert refetched is not None
        assert refetched.status == "acknowledged"

        assert store.acknowledge("missing-alert-id") is None
    finally:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM alert_history WHERE knowledge_base_id = %s", (kb_id,)
            )
            conn.commit()
        provider.close()


def test_assign_and_transition_alert_status(database_url: str) -> None:
    kb_id = "kb-alert-triage-test"
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
            alert_id="a-triage-1",
            entity_id="claim:c1",
            entity_type="claim",
            severity="high",
            status="acknowledged",
            title="Anomalous claim",
            reasoning="score exceeded threshold",
            metric_name="claim_anomaly",
        )
        store.write_alerts([record])

        assigned = store.assign(
            "a-triage-1",
            knowledge_base_id=kb_id,
            assignee="maya.patel@example.com",
            actor="supervisor@example.com",
        )
        assert assigned is not None
        assert assigned.assignee == "maya.patel@example.com"
        assert assigned.triage_history[-1].event_type == "assigned"

        transitioned = store.transition_status(
            "a-triage-1",
            knowledge_base_id=kb_id,
            status="investigating",
            actor="analyst@example.com",
            reason="Confirmed peer deviation.",
        )
        assert transitioned is not None
        assert transitioned.status == "investigating"
        assert transitioned.assignee == "maya.patel@example.com"
        assert [event.event_type for event in transitioned.triage_history] == [
            "assigned",
            "status_changed",
        ]
        assert transitioned.triage_history[-1].from_status == "acknowledged"
        assert transitioned.triage_history[-1].to_status == "investigating"
    finally:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM alert_history WHERE knowledge_base_id = %s", (kb_id,)
            )
            conn.commit()
        provider.close()


def test_count_by_statuses(database_url: str) -> None:
    kb_id = "kb-alert-count-test"
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    store = PostgresAlertHistoryStore(provider)
    try:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM alert_history WHERE knowledge_base_id = %s", (kb_id,)
            )
            conn.commit()

        before_open = store.count_by_statuses({"open"})

        store.write_alerts(
            [
                AlertHistoryRecord(
                    knowledge_base_id=kb_id,
                    alert_id="a-count-1",
                    entity_id="claim:c1",
                    entity_type="claim",
                    severity="high",
                    status="open",
                    title="Anomalous claim",
                    reasoning="score exceeded threshold",
                    metric_name="claim_anomaly",
                ),
                AlertHistoryRecord(
                    knowledge_base_id=kb_id,
                    alert_id="a-count-2",
                    entity_id="claim:c1",
                    entity_type="claim",
                    severity="high",
                    status="closed",
                    title="Anomalous claim",
                    reasoning="score exceeded threshold",
                    metric_name="claim_anomaly",
                ),
            ]
        )

        assert store.count_by_statuses({"open"}) == before_open + 1
        assert store.count_by_statuses({"closed"}) >= 1
    finally:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM alert_history WHERE knowledge_base_id = %s", (kb_id,)
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
