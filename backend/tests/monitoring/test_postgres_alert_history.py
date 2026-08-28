"""Integration tests for the Postgres alert-history store."""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone

import pytest

import monitoring.adapters.postgres as postgres_module
from config.schema import DatabaseConfig
from database.runtime import create_connection_provider
from monitoring.adapters.postgres import PostgresAlertHistoryStore
from monitoring.exceptions import AlertLifecycleError, MonitoringSourceError
from monitoring.lifecycle import validate_alert_transition
from monitoring.models import AlertHistoryRecord
from playbooks.models import PlaybookRef

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


def test_alert_history_preserves_playbook_ref_in_generation_metadata(
    database_url: str,
) -> None:
    kb_id = "kb-alert-playbook-ref-test"
    expected = {
        "playbook_id": "provider_billing_spike_review",
        "playbook_version": "v1",
        "title": "Provider billing spike review",
    }
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    store = PostgresAlertHistoryStore(provider)
    try:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM alert_history WHERE knowledge_base_id = %s", (kb_id,)
            )
            conn.commit()

        record = _record("a-playbook-ref").model_copy(
            update={
                "knowledge_base_id": kb_id,
                "generation_metadata": {
                    "playbook_ref": PlaybookRef(**expected),
                    "generation": {"source": "test"},
                },
            }
        )

        assert store.write_alerts([record]) == 1
        fetched = store.get_alert("a-playbook-ref")

        assert fetched is not None
        assert fetched.generation_metadata["playbook_ref"] == expected
        assert fetched.generation_metadata["generation"] == {"source": "test"}
    finally:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM alert_history WHERE knowledge_base_id = %s", (kb_id,)
            )
            conn.commit()
        provider.close()


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
        metadata_record = _record("a-1").model_copy(
            update={
                "generation_metadata": {
                    "suppression": {"decision": "retained"},
                    "deduplication": {"window_seconds": 900},
                }
            }
        )
        assert store.write_alerts([metadata_record, _record("a-2")]) == 2
        # Idempotent on (knowledge_base_id, alert_id).
        assert store.write_alerts([_record("a-1")]) == 0
        fetched = store.get_alert("a-1")
        assert fetched is not None
        assert fetched.generation_metadata["suppression"]["decision"] == "retained"
        assert fetched.generation_metadata["deduplication"]["window_seconds"] == 900
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
            generation_metadata={
                "suppression": {
                    "decision": "retained",
                    "reason": "No active suppression rule matched claim and claim_anomaly.",
                },
                "deduplication": {
                    "decision": "retained",
                    "window_seconds": 900,
                },
            },
        )
        rewritten = original.model_copy(
            update={
                "title": "Rewritten title",
                "status": "closed",
                "entity_label": "Dr. Rewritten",
                "confidence": 0.99,
                "tags": ["rewritten-tag"],
                "generation_metadata": {
                    "suppression": {"decision": "rewritten"},
                },
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
        assert fetched.generation_metadata["suppression"]["decision"] == "retained"
        assert fetched.generation_metadata["deduplication"]["window_seconds"] == 900
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

        updated = store.acknowledge(
            "a-ack-1",
            knowledge_base_id=kb_id,
            actor="analyst@example.com",
        )
        assert updated is not None
        assert updated.status == "acknowledged"
        assert updated.triage_history[-1].event_type == "status_changed"
        assert updated.triage_history[-1].actor == "analyst@example.com"
        assert updated.triage_history[-1].from_status == "open"
        assert updated.triage_history[-1].to_status == "acknowledged"

        refetched = store.get_alert("a-ack-1")
        assert refetched is not None
        assert refetched.status == "acknowledged"
        assert refetched.triage_history[-1].to_status == "acknowledged"

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


def test_concurrent_transition_loses_instead_of_committing_a_forbidden_one(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two analysts transition one alert at once; the loser must not commit.

    ALERT_TRANSITIONS['resolved'] == {'open'}, so 'resolved' -> 'dismissed' is
    forbidden. Both analysts read the alert while it is still 'investigating'
    and both pass validation against that snapshot. Without a compare-and-set
    on the UPDATE, the second writer's blind UPDATE (WHERE knowledge_base_id
    AND alert_id only) still matches the row after the first writer commits,
    so it silently overwrites 'resolved' with the lifecycle-forbidden
    'dismissed' and appends a triage event claiming from_status='investigating'
    -- a false audit trail, since the real prior status was 'resolved'.

    A ``threading.Barrier`` forces both threads' read-and-validate step
    (inside the real ``transition_status`` call) to happen before either
    writer proceeds, reproducing the interleave without touching production
    code. The 'dismissed' writer is given a short additional delay after the
    barrier so the 'resolved' writer reliably commits first -- matching the
    "read happens for both, then the first commits" scenario this guards
    against, without leaving the outcome to nondeterministic thread
    scheduling.
    """
    kb_id = "kb-alert-cas-test"
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    store = PostgresAlertHistoryStore(provider)
    try:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM alert_history WHERE knowledge_base_id = %s", (kb_id,)
            )
            conn.commit()

        store.write_alerts(
            [
                AlertHistoryRecord(
                    knowledge_base_id=kb_id,
                    alert_id="alert-cas-1",
                    entity_id="claim:c1",
                    entity_type="claim",
                    severity="high",
                    status="investigating",
                    title="Anomalous claim",
                    reasoning="score exceeded threshold",
                    metric_name="claim_anomaly",
                )
            ]
        )

        read_barrier = threading.Barrier(2)
        thread_state = threading.local()

        def synced_validate(current_status: str, new_status: str) -> None:
            # Only the first call per thread is the "both analysts read the
            # alert" step being synchronized. The compare-and-set fix issues
            # a second, recovery validate() against fresh state after a lost
            # race -- that call must run unsynchronized, or the losing
            # thread would block on a barrier no other thread will reach.
            if not getattr(thread_state, "synced", False):
                thread_state.synced = True
                read_barrier.wait(timeout=5)
                if new_status == "dismissed":
                    time.sleep(0.2)
            validate_alert_transition(current_status, new_status)

        monkeypatch.setattr(
            postgres_module, "validate_alert_transition", synced_validate
        )

        results: dict[str, AlertHistoryRecord | BaseException | None] = {}

        def run(actor: str, status: str) -> None:
            try:
                results[actor] = store.transition_status(
                    "alert-cas-1",
                    knowledge_base_id=kb_id,
                    status=status,
                    actor=actor,
                )
            except BaseException as exc:  # captured for the joining thread to assert on
                results[actor] = exc

        winner = threading.Thread(target=run, args=("analyst-1", "resolved"))
        loser = threading.Thread(target=run, args=("analyst-2", "dismissed"))
        winner.start()
        loser.start()
        winner.join(timeout=10)
        loser.join(timeout=10)

        assert isinstance(results["analyst-1"], AlertHistoryRecord)
        assert results["analyst-1"].status == "resolved"
        assert isinstance(results["analyst-2"], AlertLifecycleError)

        row = store.get_alert("alert-cas-1")
        assert row is not None
        assert row.status == "resolved"
        assert [event.to_status for event in row.triage_history] == ["resolved"]
    finally:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM alert_history WHERE knowledge_base_id = %s", (kb_id,)
            )
            conn.commit()
        provider.close()


def test_concurrent_transition_to_the_same_status_signals_retry_not_forbidden(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The race-lost branch where the retried transition is still valid.

    Sibling of ``test_concurrent_transition_loses_instead_of_committing_a_
    forbidden_one``: there, the loser's transition became forbidden by the
    time it lost the compare-and-set. Here, both analysts submit the *same*
    target status, so after the loser re-reads and re-validates against the
    now-current row, ``validate_alert_transition`` finds the transition
    still valid (new_status == current_status) and does not raise -- the
    code must fall through to the concurrent-retry signal instead of
    silently returning a stale/duplicated result.

    That signal must reach the caller as ``MonitoringSourceError`` with its
    original message intact, not re-wrapped by the method's own broad
    ``except Exception`` handler into the generic "Failed to transition
    alert status." text -- which would bury the retry hint at
    ``exc.__cause__.__cause__``, invisible to any caller that logs or
    renders ``str(exc)``.
    """
    kb_id = "kb-alert-cas-retry-test"
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    store = PostgresAlertHistoryStore(provider)
    try:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM alert_history WHERE knowledge_base_id = %s", (kb_id,)
            )
            conn.commit()

        store.write_alerts(
            [
                AlertHistoryRecord(
                    knowledge_base_id=kb_id,
                    alert_id="alert-cas-retry-1",
                    entity_id="claim:c1",
                    entity_type="claim",
                    severity="high",
                    status="investigating",
                    title="Anomalous claim",
                    reasoning="score exceeded threshold",
                    metric_name="claim_anomaly",
                )
            ]
        )

        read_barrier = threading.Barrier(2)
        thread_state = threading.local()

        def synced_validate(current_status: str, new_status: str) -> None:
            # Only the first call per thread is the "both analysts read the
            # alert" step being synchronized. The compare-and-set fix issues
            # a second, recovery validate() against fresh state after a lost
            # race -- that call must run unsynchronized, or the losing
            # thread would block on a barrier no other thread will reach.
            if not getattr(thread_state, "synced", False):
                thread_state.synced = True
                read_barrier.wait(timeout=5)
                if getattr(thread_state, "delay_after_barrier", False):
                    time.sleep(0.2)
            validate_alert_transition(current_status, new_status)

        monkeypatch.setattr(
            postgres_module, "validate_alert_transition", synced_validate
        )

        results: dict[str, AlertHistoryRecord | BaseException | None] = {}

        def run(actor: str, *, delay_after_barrier: bool) -> None:
            thread_state.delay_after_barrier = delay_after_barrier
            try:
                results[actor] = store.transition_status(
                    "alert-cas-retry-1",
                    knowledge_base_id=kb_id,
                    status="resolved",
                    actor=actor,
                )
            except BaseException as exc:  # captured for the joining thread to assert on
                results[actor] = exc

        winner = threading.Thread(
            target=run, args=("analyst-1",), kwargs={"delay_after_barrier": False}
        )
        loser = threading.Thread(
            target=run, args=("analyst-2",), kwargs={"delay_after_barrier": True}
        )
        winner.start()
        loser.start()
        winner.join(timeout=10)
        loser.join(timeout=10)

        assert isinstance(results["analyst-1"], AlertHistoryRecord)
        assert results["analyst-1"].status == "resolved"

        loser_result = results["analyst-2"]
        assert isinstance(loser_result, MonitoringSourceError)
        assert not isinstance(loser_result, AlertLifecycleError)
        assert str(loser_result) == (
            "Alert status changed concurrently; retry the transition."
        )

        row = store.get_alert("alert-cas-retry-1")
        assert row is not None
        assert row.status == "resolved"
        assert [event.to_status for event in row.triage_history] == ["resolved"]
    finally:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM alert_history WHERE knowledge_base_id = %s", (kb_id,)
            )
            conn.commit()
        provider.close()
