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
