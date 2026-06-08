"""Tests for the in-memory alert-history writer."""

from __future__ import annotations

from datetime import datetime, timezone

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
