"""Tests for the in-memory alert-history writer."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

import pytest

import monitoring.adapters.in_memory as in_memory_module
from monitoring.exceptions import AlertConcurrentModificationError, AlertLifecycleError
from monitoring.adapters.in_memory import InMemoryAlertHistoryWriter
from monitoring.adapters.protocols import AlertHistoryWriter
from monitoring.lifecycle import validate_alert_transition
from monitoring.models import AlertHistoryRecord


def _record(
    alert_id: str, *, entity_id: str = "claim:c1", status: str = "open"
) -> AlertHistoryRecord:
    return AlertHistoryRecord(
        knowledge_base_id="kb-1",
        alert_id=alert_id,
        entity_id=entity_id,
        entity_type="claim",
        severity="high",
        status=status,
        title="Anomalous claim",
        reasoning="score exceeded threshold",
        metric_name="claim_anomaly",
        created_at=datetime(2026, 5, 16, tzinfo=timezone.utc),
    )


def test_writer_satisfies_protocol() -> None:
    writer: AlertHistoryWriter = InMemoryAlertHistoryWriter()
    assert writer.write_alerts([]) == 0


def test_write_alerts_is_idempotent_per_alert_id() -> None:
    writer = InMemoryAlertHistoryWriter()
    assert writer.write_alerts([_record("a-1")]) == 1
    assert writer.write_alerts([_record("a-1")]) == 0


def test_write_alerts_keeps_first_row_on_conflicting_rewrite() -> None:
    writer = InMemoryAlertHistoryWriter()
    original = AlertHistoryRecord(
        knowledge_base_id="kb-1",
        alert_id="a-1",
        entity_id="claim:c1",
        entity_type="claim",
        severity="high",
        status="open",
        title="Original title",
        reasoning="score exceeded threshold",
        metric_name="claim_anomaly",
        created_at=datetime(2026, 5, 16, tzinfo=timezone.utc),
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

    assert writer.write_alerts([original]) == 1
    assert writer.write_alerts([rewritten]) == 0

    fetched = writer.get_alert("a-1")
    assert fetched is not None
    assert fetched.title == "Original title"
    assert fetched.status == "open"
    assert fetched.entity_label == "Dr. Original"
    assert fetched.confidence == 0.42
    assert fetched.tags == ["original-tag"]


def test_write_alerts_preserves_generation_metadata() -> None:
    writer = InMemoryAlertHistoryWriter()
    record = _record("a-1").model_copy(
        update={
            "generation_metadata": {
                "suppression": {
                    "decision": "retained",
                    "reason": "No active suppression rule matched claim and claim_anomaly.",
                },
                "deduplication": {
                    "decision": "retained",
                    "reason": "No existing alert inside the dedup window.",
                    "window_seconds": 900,
                },
            }
        }
    )

    writer.write_alerts([record])

    fetched = writer.get_alert("a-1")
    assert fetched is not None
    assert fetched.generation_metadata["suppression"]["decision"] == "retained"
    assert fetched.generation_metadata["deduplication"]["window_seconds"] == 900


def test_count_open_alerts_filters_by_entity_and_status() -> None:
    writer = InMemoryAlertHistoryWriter()
    writer.write_alerts([
        _record("a-1"),
        _record("a-2"),
        _record("a-3", status="closed"),
    ])
    # closed record must not be counted
    assert writer.count_open_alerts(knowledge_base_id="kb-1", entity_id="claim:c1") == 2
    # entity mismatch must also return 0
    assert (
        writer.count_open_alerts(knowledge_base_id="kb-1", entity_id="claim:other") == 0
    )


def _record_for_kb(alert_id: str, *, knowledge_base_id: str) -> AlertHistoryRecord:
    return AlertHistoryRecord(
        knowledge_base_id=knowledge_base_id,
        alert_id=alert_id,
        entity_id="claim:c1",
        entity_type="claim",
        severity="high",
        status="open",
        title="Anomalous claim",
        reasoning="score exceeded threshold",
        metric_name="claim_anomaly",
        created_at=datetime(2026, 5, 16, tzinfo=timezone.utc),
    )


def test_delete_by_kb_removes_only_matching_kb_alerts() -> None:
    writer = InMemoryAlertHistoryWriter()
    writer.write_alerts([
        _record_for_kb("a-keep", knowledge_base_id="kb-keep"),
        _record_for_kb("a-del-1", knowledge_base_id="kb-delete"),
        _record_for_kb("a-del-2", knowledge_base_id="kb-delete"),
    ])

    count = writer.delete_by_kb("kb-delete")

    assert count == 2
    assert (
        writer.count_open_alerts(knowledge_base_id="kb-delete", entity_id="claim:c1") == 0
    )
    assert (
        writer.count_open_alerts(knowledge_base_id="kb-keep", entity_id="claim:c1") == 1
    )


def test_delete_by_kb_is_idempotent_for_alert_history() -> None:
    writer = InMemoryAlertHistoryWriter()
    writer.write_alerts([_record_for_kb("a-1", knowledge_base_id="kb-delete")])
    writer.delete_by_kb("kb-delete")

    assert writer.delete_by_kb("kb-delete") == 0


def test_list_alerts_orders_by_created_at_desc_with_alert_id_tiebreak() -> None:
    writer = InMemoryAlertHistoryWriter()
    same_time = datetime(2026, 5, 16, tzinfo=timezone.utc)
    writer.write_alerts(
        [
            AlertHistoryRecord(
                knowledge_base_id="kb-1",
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
                knowledge_base_id="kb-1",
                alert_id="a-3",
                entity_id="claim:c1",
                entity_type="claim",
                severity="high",
                status="open",
                title="Anomalous claim",
                reasoning="score exceeded threshold",
                metric_name="claim_anomaly",
                created_at=same_time,
            ),
            AlertHistoryRecord(
                knowledge_base_id="kb-1",
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

    records, total = writer.list_alerts(limit=10, offset=0)

    assert total == 3
    assert [r.alert_id for r in records] == ["a-3", "a-2", "a-1"]


def test_list_alerts_paginates() -> None:
    writer = InMemoryAlertHistoryWriter()
    writer.write_alerts([_record("a-1"), _record("a-2"), _record("a-3")])

    records, total = writer.list_alerts(limit=1, offset=1)

    assert total == 3
    assert len(records) == 1


def test_list_alerts_filters_by_status() -> None:
    writer = InMemoryAlertHistoryWriter()
    writer.write_alerts(
        [
            _record("a-1", status="open"),
            _record("a-2", status="closed"),
            _record("a-3", status="acknowledged"),
        ]
    )

    records, total = writer.list_alerts(statuses=["open", "acknowledged"], limit=10, offset=0)

    assert total == 2
    assert {r.alert_id for r in records} == {"a-1", "a-3"}


def test_list_alerts_empty_statuses_list_means_unfiltered() -> None:
    writer = InMemoryAlertHistoryWriter()
    writer.write_alerts(
        [
            _record("a-1", status="open"),
            _record("a-2", status="closed"),
            _record("a-3", status="acknowledged"),
        ]
    )

    unfiltered_none, total_none = writer.list_alerts(statuses=None, limit=10, offset=0)
    unfiltered_empty, total_empty = writer.list_alerts(statuses=[], limit=10, offset=0)

    assert total_empty == total_none == 3
    assert {r.alert_id for r in unfiltered_empty} == {r.alert_id for r in unfiltered_none}


def test_get_alert_returns_record_or_none() -> None:
    writer = InMemoryAlertHistoryWriter()
    writer.write_alerts([_record("a-1")])

    assert writer.get_alert("a-1") is not None
    assert writer.get_alert("missing") is None


def test_acknowledge_persists_and_returns_updated_record() -> None:
    writer = InMemoryAlertHistoryWriter()
    writer.write_alerts([_record("a-1", status="open")])

    updated = writer.acknowledge("a-1", actor="analyst@example.com")

    assert updated is not None
    assert updated.status == "acknowledged"
    assert updated.triage_history[-1].event_type == "status_changed"
    assert updated.triage_history[-1].actor == "analyst@example.com"
    assert updated.triage_history[-1].from_status == "open"
    assert updated.triage_history[-1].to_status == "acknowledged"
    assert writer.get_alert("a-1") is not None
    assert writer.get_alert("a-1").status == "acknowledged"  # type: ignore[union-attr]


def test_acknowledge_unknown_alert_returns_none() -> None:
    writer = InMemoryAlertHistoryWriter()

    assert writer.acknowledge("missing") is None


def test_assign_alert_persists_assignee_and_audit_event() -> None:
    writer = InMemoryAlertHistoryWriter()
    writer.write_alerts([_record("a-1", status="open")])

    updated = writer.assign(
        "a-1",
        knowledge_base_id="kb-1",
        assignee="maya.patel@example.com",
        actor="supervisor@example.com",
    )

    assert updated is not None
    assert updated.assignee == "maya.patel@example.com"
    assert updated.triage_history[-1].event_type == "assigned"
    assert updated.triage_history[-1].actor == "supervisor@example.com"
    assert updated.triage_history[-1].assignee == "maya.patel@example.com"
    assert writer.get_alert("a-1").assignee == "maya.patel@example.com"  # type: ignore[union-attr]


def test_assign_alert_is_knowledge_base_scoped() -> None:
    writer = InMemoryAlertHistoryWriter()
    writer.write_alerts([_record_for_kb("a-1", knowledge_base_id="kb-2")])

    assert (
        writer.assign(
            "a-1",
            knowledge_base_id="kb-1",
            assignee="maya.patel@example.com",
            actor="supervisor@example.com",
        )
        is None
    )
    assert writer.get_alert("a-1").assignee is None  # type: ignore[union-attr]


def test_transition_alert_status_persists_valid_transition_and_audit_event() -> None:
    writer = InMemoryAlertHistoryWriter()
    writer.write_alerts([_record("a-1", status="acknowledged")])

    updated = writer.transition_status(
        "a-1",
        knowledge_base_id="kb-1",
        status="investigating",
        actor="analyst@example.com",
        reason="Ready for review.",
    )

    assert updated is not None
    assert updated.status == "investigating"
    assert updated.triage_history[-1].event_type == "status_changed"
    assert updated.triage_history[-1].actor == "analyst@example.com"
    assert updated.triage_history[-1].from_status == "acknowledged"
    assert updated.triage_history[-1].to_status == "investigating"
    assert updated.triage_history[-1].reason == "Ready for review."


def test_transition_alert_status_rejects_invalid_transition() -> None:
    writer = InMemoryAlertHistoryWriter()
    writer.write_alerts([_record("a-1", status="open")])

    with pytest.raises(AlertLifecycleError):
        writer.transition_status(
            "a-1",
            knowledge_base_id="kb-1",
            status="resolved",
            actor="analyst@example.com",
        )


def test_a_racing_acknowledge_does_not_silently_land_over_a_winning_dismissal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The lost-write race this task exists to close, reproduced in-memory.

    ALERT_TRANSITIONS['dismissed'] == {'open'}, so 'dismissed' -> 'acknowledged'
    is forbidden. Both callers read the alert while it is still 'open' and
    both pass validation against that snapshot -- mirroring
    ``PostgresAlertHistoryStore``'s own race (see
    ``test_concurrent_acknowledge_loses_instead_of_committing_over_a_dismissal``
    in ``test_postgres_alert_history.py``). Without a guard across the
    read-validate-write, the racing acknowledge's write still lands after the
    dismiss commits, silently overwriting 'dismissed' with the
    lifecycle-forbidden 'acknowledged' and dropping the dismiss's triage
    event -- a false audit trail, since the real prior status was
    'dismissed', not 'open'.

    ``get_alert_feed_store`` is an ``lru_cache(maxsize=1)`` process
    singleton shared across threadpool requests, so this interleave is
    genuinely reachable, not theoretical.

    A ``threading.Barrier`` forces both threads' pre-lock validate call
    (``in_memory.py``'s own module-level ``validate_alert_transition``,
    monkeypatched here) to happen before either can reach its lock-guarded
    re-check-and-write, deliberately widening the compare-to-write window so
    two barrier-synchronized threads reliably overlap inside it instead of
    depending on lucky GIL scheduling.
    """
    writer = InMemoryAlertHistoryWriter()
    writer.write_alerts([_record("a-race-1", status="open")])

    read_barrier = threading.Barrier(2)
    thread_state = threading.local()

    def synced_validate(current_status: str, new_status: str) -> None:
        # Only the first call per thread is the "both callers read the
        # alert" step being synchronized. The guard's second, recovery
        # validate() against fresh state after a lost race must run
        # unsynchronized, or the losing thread would block on a barrier no
        # other thread will reach.
        if not getattr(thread_state, "synced", False):
            thread_state.synced = True
            read_barrier.wait(timeout=5)
            if new_status == "acknowledged":
                time.sleep(0.2)
        validate_alert_transition(current_status, new_status)

    monkeypatch.setattr(in_memory_module, "validate_alert_transition", synced_validate)

    results: dict[str, AlertHistoryRecord | BaseException | None] = {}

    def run_dismiss() -> None:
        try:
            results["dismiss"] = writer.transition_status(
                "a-race-1",
                knowledge_base_id="kb-1",
                status="dismissed",
                actor="analyst-1",
            )
        except BaseException as exc:  # captured for the joining thread to assert on
            results["dismiss"] = exc

    def run_acknowledge() -> None:
        try:
            results["acknowledge"] = writer.acknowledge(
                "a-race-1", knowledge_base_id="kb-1", actor="analyst-2"
            )
        except BaseException as exc:  # captured for the joining thread to assert on
            results["acknowledge"] = exc

    t_dismiss = threading.Thread(target=run_dismiss)
    t_acknowledge = threading.Thread(target=run_acknowledge)
    t_dismiss.start()
    t_acknowledge.start()
    t_dismiss.join(timeout=10)
    t_acknowledge.join(timeout=10)

    assert isinstance(results["dismiss"], AlertHistoryRecord)
    assert results["dismiss"].status == "dismissed"

    ack_result = results["acknowledge"]
    assert isinstance(ack_result, AlertLifecycleError), (
        "expected the racing acknowledge to be rejected as forbidden once it "
        f"re-validates against the committed dismissal; got {ack_result!r} -- "
        "if this is an AlertHistoryRecord, the in-memory store silently "
        "applied a lifecycle-forbidden transition over a winning write"
    )

    row = writer.get_alert("a-race-1")
    assert row is not None
    assert row.status == "dismissed"
    assert [event.to_status for event in row.triage_history] == ["dismissed"]


def test_racing_to_the_same_target_status_signals_concurrent_modification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sibling of the forbidden-after-race test above.

    Here both racers submit the *same* target status, so after the loser
    re-reads and re-validates against the now-current row,
    ``validate_alert_transition`` finds the transition still valid
    (``new_status == current_status``) and does not raise. The store must
    not silently land a second, duplicate transition on top -- it must
    signal ``AlertConcurrentModificationError`` instead, mirroring
    ``PostgresAlertHistoryStore``'s identical behaviour (see
    ``test_concurrent_transition_to_the_same_status_signals_retry_not_forbidden``).
    """
    # Imported locally (not at module scope) so a run of this file before
    # the exception type exists fails only *this* test with a clean
    # ImportError, rather than an import failure at collection time hiding
    # the sibling test's real-data-loss proof above.
    from monitoring.exceptions import AlertConcurrentModificationError

    writer = InMemoryAlertHistoryWriter()
    writer.write_alerts([_record("a-race-2", status="investigating")])

    read_barrier = threading.Barrier(2)
    thread_state = threading.local()

    def synced_validate(current_status: str, new_status: str) -> None:
        if not getattr(thread_state, "synced", False):
            thread_state.synced = True
            read_barrier.wait(timeout=5)
            if getattr(thread_state, "delay_after_barrier", False):
                time.sleep(0.2)
        validate_alert_transition(current_status, new_status)

    monkeypatch.setattr(in_memory_module, "validate_alert_transition", synced_validate)

    results: dict[str, AlertHistoryRecord | BaseException | None] = {}

    def run(actor: str, *, delay_after_barrier: bool) -> None:
        thread_state.delay_after_barrier = delay_after_barrier
        try:
            results[actor] = writer.transition_status(
                "a-race-2",
                knowledge_base_id="kb-1",
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
    assert isinstance(loser_result, AlertConcurrentModificationError)
    assert not isinstance(loser_result, AlertLifecycleError)
    assert str(loser_result) == (
        "Alert 'a-race-2' changed concurrently; reload it and retry."
    )

    row = writer.get_alert("a-race-2")
    assert row is not None
    assert row.status == "resolved"
    assert [event.to_status for event in row.triage_history] == ["resolved"]


def test_count_by_statuses() -> None:
    writer = InMemoryAlertHistoryWriter()
    writer.write_alerts(
        [
            _record("a-1", status="open"),
            _record("a-2", status="closed"),
            _record("a-3", status="acknowledged"),
        ]
    )

    assert writer.count_by_statuses({"open", "acknowledged"}) == 2
    assert writer.count_by_statuses({"closed"}) == 1
    assert writer.count_by_statuses({"investigating"}) == 0


def test_new_fields_round_trip_including_tags_list() -> None:
    writer = InMemoryAlertHistoryWriter()
    record = AlertHistoryRecord(
        knowledge_base_id="kb-1",
        alert_id="a-1",
        entity_id="claim:c1",
        entity_type="claim",
        severity="high",
        status="open",
        title="Anomalous claim",
        reasoning="score exceeded threshold",
        metric_name="claim_anomaly",
        created_at=datetime(2026, 5, 16, tzinfo=timezone.utc),
        entity_label="Dr. Jane Doe",
        confidence=0.87,
        tags=["peer-deviation", "billing-spike"],
    )
    writer.write_alerts([record])

    fetched = writer.get_alert("a-1")

    assert fetched is not None
    assert fetched.entity_label == "Dr. Jane Doe"
    assert fetched.confidence == 0.87
    assert fetched.tags == ["peer-deviation", "billing-spike"]


def test_the_transition_lock_makes_the_recheck_and_the_write_atomic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_transition_lock`` is held across the re-check and the write.
    ``PostgresAlertHistoryStore`` gets that atomicity free from row locking;
    the in-memory adapter's re-read -> compare -> build -> write is four
    separate Python steps, and the window between the compare and the write
    spans a ``utc_now()``, a pydantic model construction and a ``model_copy``
    -- comfortably long enough for a GIL switch.

    ``test_a_racing_acknowledge_does_not_silently_land_over_a_winning_dismissal``
    does not prove the lock. Its barrier synchronises the *pre-lock*
    ``validate_alert_transition``, so the guarded re-check catches the
    conflict with or without the lock -- verified by mutation: replacing
    ``threading.Lock()`` with a no-op context manager leaves that whole file
    passing. The lock's own window is never entered.

    This test enters it, using the one call the critical section makes:
    ``in_memory.py``'s module-level ``utc_now``. The first caller into it
    stalls there -- inside the lock -- while a second caller attempts the
    same transition. Under the lock the second caller cannot get in until the
    first has written, so it sees the new status and raises the documented
    ``AlertConcurrentModificationError``. Without the lock it passes the
    stale compare, writes, and is then silently overwritten by the stalled
    caller: two "successes", one of them a lie.
    """
    writer = InMemoryAlertHistoryWriter()
    writer.write_alerts([_record("a-lock-1", status="open")])

    sibling_done = threading.Event()
    first_call_seen = threading.Event()

    def stalling_utc_now() -> datetime:
        if not first_call_seen.is_set():
            first_call_seen.set()
            sibling_done.wait(timeout=1.0)
        return datetime.now(timezone.utc)

    monkeypatch.setattr(in_memory_module, "utc_now", stalling_utc_now)

    outcomes: dict[str, AlertHistoryRecord | BaseException | None] = {}

    def acknowledge_as(actor: str) -> None:
        try:
            outcomes[actor] = writer.acknowledge(
                "a-lock-1", knowledge_base_id="kb-1", actor=actor
            )
        except BaseException as exc:  # captured for the joining thread to assert on
            outcomes[actor] = exc

    def run_sibling() -> None:
        try:
            acknowledge_as("sibling")
        finally:
            sibling_done.set()

    stalled = threading.Thread(target=acknowledge_as, args=("stalled",))
    sibling = threading.Thread(target=run_sibling)
    stalled.start()
    # Let the stalled caller take the lock and reach utc_now() before the
    # sibling attempts the same transition.
    assert first_call_seen.wait(timeout=5), "the stalled caller never reached utc_now"
    sibling.start()
    stalled.join(timeout=10)
    sibling.join(timeout=10)

    written = [actor for actor, outcome in outcomes.items() if isinstance(outcome, AlertHistoryRecord)]
    assert len(written) == 1, (
        "both acknowledges reported success, so one write was silently "
        f"discarded: {outcomes}"
    )
    loser = next(actor for actor in outcomes if actor not in written)
    assert isinstance(outcomes[loser], AlertConcurrentModificationError), (
        f"the losing caller got {outcomes[loser]!r}, not the documented "
        "AlertConcurrentModificationError"
    )
    stored = writer.get_alert("a-lock-1")
    assert stored is not None
    assert stored.status == "acknowledged"
    # One transition, one audit event -- not one event silently replacing another.
    assert [event.actor for event in stored.triage_history] == [written[0]]
