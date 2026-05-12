"""Tests for durable alert projection repository behavior."""

from __future__ import annotations

from datetime import datetime, timezone

from api._alert_store import (
    ObjectStoreAlertProjectionRepository,
    AlertProjectionRecord,
    acknowledge_alert_projection,
    count_active_alerts,
    project_alert_detail,
    project_alert_feed,
)
from api.contracts import PolicyCitation
from shared.types import Alert
from storage.adapters.in_memory import InMemoryObjectStore


def _alert(
    alert_id: str,
    *,
    severity: str = "high",
    status: str = "open",
    created_at: datetime | None = None,
) -> Alert:
    return Alert(
        id=alert_id,
        entity_type="provider",
        entity_id=f"provider-{alert_id}",
        severity=severity,
        title=f"Alert {alert_id}",
        reasoning="Risk signal exceeded threshold.",
        evidence_pack_id=f"evidence-{alert_id}",
        status=status,  # type: ignore[arg-type]
        created_at=created_at or datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _record(
    alert_id: str,
    *,
    severity: str = "high",
    status: str = "open",
    created_at: datetime | None = None,
) -> AlertProjectionRecord:
    return AlertProjectionRecord(
        alert=_alert(
            alert_id,
            severity=severity,
            status=status,
            created_at=created_at,
        ),
        entity_label=f"Provider {alert_id}",
        confidence=0.92,
        tags=["billing", "outlier"],
        related_entity_ids=[f"provider-{alert_id}", "claim-1"],
        policy_citations=[
            PolicyCitation(
                citation_id="policy-1",
                title="Billing policy",
                excerpt="Claims must be medically necessary.",
                source_document_id="policy-doc-1",
            )
        ],
    )


def test_object_store_repository_starts_empty() -> None:
    repository = ObjectStoreAlertProjectionRepository(InMemoryObjectStore())

    records, total = repository.list(limit=10, offset=0)

    assert records == []
    assert total == 0
    assert count_active_alerts(repository) == 0


def test_upsert_persists_across_repository_instances() -> None:
    object_store = InMemoryObjectStore()
    first = ObjectStoreAlertProjectionRepository(object_store)
    first.upsert(_record("a-1"))

    second = ObjectStoreAlertProjectionRepository(object_store)

    stored = second.get("a-1")
    assert stored is not None
    assert stored.alert.id == "a-1"
    assert stored.entity_label == "Provider a-1"


def test_list_returns_newest_first_with_pagination() -> None:
    object_store = InMemoryObjectStore()
    repository = ObjectStoreAlertProjectionRepository(object_store)
    repository.upsert(
        _record("old", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    )
    repository.upsert(
        _record("new", created_at=datetime(2026, 1, 5, tzinfo=timezone.utc))
    )
    repository.upsert(
        _record("middle", created_at=datetime(2026, 1, 3, tzinfo=timezone.utc))
    )

    records, total = repository.list(limit=2, offset=1)

    assert total == 3
    assert [record.alert.id for record in records] == ["middle", "old"]


def test_acknowledge_persists_across_repository_instances() -> None:
    object_store = InMemoryObjectStore()
    repository = ObjectStoreAlertProjectionRepository(object_store)
    repository.upsert(_record("a-1"))

    updated = acknowledge_alert_projection(repository, "a-1")
    reloaded = ObjectStoreAlertProjectionRepository(object_store).get("a-1")

    assert updated is not None
    assert updated.alert.status == "acknowledged"
    assert updated.alert.acknowledged is True
    assert reloaded is not None
    assert reloaded.alert.status == "acknowledged"
    assert reloaded.alert.acknowledged is True


def test_count_by_statuses_tracks_active_statuses() -> None:
    repository = ObjectStoreAlertProjectionRepository(InMemoryObjectStore())
    repository.upsert(_record("open", status="open"))
    repository.upsert(_record("ack", status="acknowledged"))
    repository.upsert(_record("investigating", status="investigating"))
    repository.upsert(_record("resolved", status="resolved"))

    assert count_active_alerts(repository) == 3
    assert repository.count_by_statuses({"resolved"}) == 1


def test_projection_helpers_shape_feed_and_detail() -> None:
    repository = ObjectStoreAlertProjectionRepository(InMemoryObjectStore())
    record = repository.upsert(_record("a-1", severity="unexpected"))

    feed = project_alert_feed(repository, limit=10, offset=0)
    detail = project_alert_detail(record)

    assert feed.page.total_items == 1
    [item] = feed.items
    assert item.id == "a-1"
    assert item.entity_label == "Provider a-1"
    assert item.severity == "critical"
    assert item.tags == ["billing", "outlier"]
    assert item.evidence_pack_id == "evidence-a-1"
    assert detail.related_entity_ids == ["provider-a-1", "claim-1"]
    assert detail.policy_citations[0].citation_id == "policy-1"
