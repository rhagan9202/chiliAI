"""Tests for the in-memory alert-history writer."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from monitoring.exceptions import AlertLifecycleError
from monitoring.adapters.in_memory import InMemoryAlertHistoryWriter
from monitoring.adapters.protocols import AlertHistoryWriter
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
