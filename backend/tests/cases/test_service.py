"""Tests for the case service, including promote-from-alert (BL-010)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from cases.adapters.in_memory import InMemoryCaseRepository
from cases.exceptions import CaseNotFoundError
from cases.models import CaseTimelineEvent
from cases.service import create_case_service
from shared.types import Alert


def _alert(severity: str = "high") -> Alert:
    return Alert(
        id="alert-1",
        entity_type="provider",
        entity_id="provider-1",
        severity=severity,
        title="Elevated risk: provider-1",
        reasoning="Unusual billing.",
        evidence_pack_id="ev-1",
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )


def test_create_and_get() -> None:
    service = create_case_service(InMemoryCaseRepository())

    created = service.create(
        knowledge_base_id="kb-1", title="Manual case", priority="medium"
    )

    assert created.status == "open"
    assert service.get(knowledge_base_id="kb-1", case_id=created.id) is not None


def test_update_partial_fields() -> None:
    service = create_case_service(InMemoryCaseRepository())
    created = service.create(
        knowledge_base_id="kb-1", title="t", priority="low", assignee="alice"
    )

    updated = service.update(
        knowledge_base_id="kb-1", case_id=created.id, status="closed"
    )

    assert updated.status == "closed"
    assert updated.title == "t"  # unchanged
    assert updated.assignee == "alice"  # unchanged


def test_update_missing_raises() -> None:
    service = create_case_service(InMemoryCaseRepository())

    with pytest.raises(CaseNotFoundError):
        service.update(knowledge_base_id="kb-1", case_id="ghost", status="closed")


def test_promote_from_alert_captures_evidence_and_timeline() -> None:
    service = create_case_service(InMemoryCaseRepository())
    timeline = [
        CaseTimelineEvent(
            occurred_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
            label="alert",
            detail="Alert raised.",
        )
    ]

    case = service.promote_from_alert(
        knowledge_base_id="kb-1", alert=_alert(), timeline=timeline
    )

    assert case.originating_alert_id == "alert-1"
    assert case.evidence_pack_id == "ev-1"
    assert case.alert_ids == ["alert-1"]
    assert case.priority == "high"  # mapped from alert severity
    assert case.status == "open"
    assert case.timeline[0].label == "alert"
    # Persisted via the repository.
    assert service.get(knowledge_base_id="kb-1", case_id=case.id) is not None


def test_promote_maps_unknown_severity_to_medium() -> None:
    service = create_case_service(InMemoryCaseRepository())

    case = service.promote_from_alert(knowledge_base_id="kb-1", alert=_alert(severity="weird"))

    assert case.priority == "medium"
