"""Tests for the case service, including promote-from-alert (BL-010)."""

from __future__ import annotations

import threading
from datetime import datetime, timezone

import pytest

from cases.adapters.in_memory import InMemoryCaseRepository
from cases.exceptions import (
    AlertAlreadyAttachedError,
    CaseConcurrentModificationError,
    CaseNotFoundError,
)
from cases.models import Case, CaseTimelineEvent
from cases.service import CaseService, create_case_service
from shared.types import Alert

_KB = "kb-1"


def _alert(severity: str = "high", alert_id: str = "alert-1") -> Alert:
    return Alert(
        id=alert_id,
        entity_type="provider",
        entity_id="provider-1",
        severity=severity,
        title="Elevated risk: provider-1",
        reasoning="Unusual billing.",
        evidence_pack_id="ev-1",
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )


def _open_case(service: CaseService, *, alert_ids: list[str]) -> Case:
    return service.create(
        knowledge_base_id=_KB, title="Manual case", priority="high", alert_ids=alert_ids
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


def test_add_feedback_persists_on_case() -> None:
    service = create_case_service(InMemoryCaseRepository())
    created = service.create(
        knowledge_base_id="kb-1", title="Manual case", priority="medium"
    )

    updated = service.add_feedback(
        knowledge_base_id="kb-1",
        case_id=created.id,
        label="insufficient_evidence",
        evidence_adequacy="medium",
        missing_evidence=["prior authorization records"],
        notes="Need prior authorization before closing.",
    )

    assert len(updated.feedback_history) == 1
    persisted = service.get(knowledge_base_id="kb-1", case_id=created.id)
    assert persisted is not None
    assert len(persisted.feedback_history) == 1
    feedback = persisted.feedback_history[0]
    assert feedback.case_id == created.id
    assert feedback.label == "insufficient_evidence"
    assert feedback.evidence_adequacy == "medium"
    assert feedback.missing_evidence == ["prior authorization records"]
    assert feedback.notes == "Need prior authorization before closing."
    assert updated.updated_at > created.updated_at


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


def test_create_accepts_optional_timeline() -> None:
    from shared.utils import utc_now

    service = create_case_service(InMemoryCaseRepository())
    event = CaseTimelineEvent(occurred_at=utc_now(), label="Policy escalation", detail="rule x")
    case = service.create(
        knowledge_base_id="kb-1",
        title="Policy escalation: t",
        priority="high",
        timeline=[event],
    )
    assert case.timeline == [event]


def test_attach_alert_grows_the_case_without_rewriting_its_origin() -> None:
    """Attach is the workflow promote cannot express (UXA-405)."""
    service = create_case_service(InMemoryCaseRepository())
    case = service.promote_from_alert(knowledge_base_id="kb-1", alert=_alert())

    updated = service.attach_alert(
        knowledge_base_id="kb-1",
        case_id=case.id,
        alert=_alert(alert_id="alert-2", severity="critical"),
        notes="Same billing pattern.",
    )

    assert updated.alert_ids == ["alert-1", "alert-2"]
    # The case's origin is what it was opened from; attaching must not move it.
    assert updated.originating_alert_id == "alert-1"
    assert updated.evidence_pack_id == "ev-1"
    assert updated.priority == "high"  # attaching a critical alert does not re-prioritise
    attached = updated.timeline[-1]
    assert attached.label == "Alert attached"
    assert "Same billing pattern." in attached.detail
    assert updated.updated_at >= case.updated_at
    # Persisted, not just returned.
    stored = service.get(knowledge_base_id="kb-1", case_id=case.id)
    assert stored is not None and stored.alert_ids == ["alert-1", "alert-2"]


def test_attach_alert_without_notes_still_records_the_alert() -> None:
    service = create_case_service(InMemoryCaseRepository())
    case = service.promote_from_alert(knowledge_base_id="kb-1", alert=_alert())

    updated = service.attach_alert(
        knowledge_base_id="kb-1", case_id=case.id, alert=_alert(alert_id="alert-2")
    )

    assert "Elevated risk: provider-1" in updated.timeline[-1].detail


def test_attach_alert_refuses_a_duplicate() -> None:
    service = create_case_service(InMemoryCaseRepository())
    case = service.promote_from_alert(knowledge_base_id="kb-1", alert=_alert())

    with pytest.raises(AlertAlreadyAttachedError):
        service.attach_alert(
            knowledge_base_id="kb-1", case_id=case.id, alert=_alert()
        )


def test_attach_alert_to_unknown_case_raises() -> None:
    service = create_case_service(InMemoryCaseRepository())

    with pytest.raises(CaseNotFoundError):
        service.attach_alert(
            knowledge_base_id="kb-1", case_id="ghost", alert=_alert()
        )


def test_attach_alert_is_knowledge_base_scoped() -> None:
    service = create_case_service(InMemoryCaseRepository())
    case = service.promote_from_alert(knowledge_base_id="kb-1", alert=_alert())

    with pytest.raises(CaseNotFoundError):
        service.attach_alert(
            knowledge_base_id="kb-2", case_id=case.id, alert=_alert(alert_id="alert-2")
        )


def test_concurrent_attach_does_not_silently_drop_the_other_alert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two analysts attach different alerts to one case at the same time.

    Both read alert_ids=['A'], both pass the duplicate check, and -- pre-fix --
    both write the whole jsonb-equivalent array from their own stale copy.
    Whoever commits second wins and the other attachment vanishes, with no
    error raised to the loser. Post-fix, exactly one thread must succeed and
    the other must raise CaseConcurrentModificationError instead of silently
    losing data.

    A threading.Barrier forces both threads' ``repository.get`` (the read
    inside ``attach_alert``) to complete before either thread's ``update``
    (the write) runs, reproducing the interleave deterministically.
    """
    repository = InMemoryCaseRepository()
    service = create_case_service(repository)
    case = _open_case(service, alert_ids=["A"])

    barrier = threading.Barrier(2)
    original_get = repository.get

    def synced_get(*, knowledge_base_id: str, case_id: str) -> Case | None:
        # Rendezvous before the read so neither thread's get() runs ahead of
        # the other, then rendezvous again right after so neither thread can
        # race all the way through its own read-compute-write before the
        # other's read has even returned. A Barrier resets after each full
        # release, so the same one serves both rendezvous points.
        barrier.wait(timeout=5)
        result = original_get(knowledge_base_id=knowledge_base_id, case_id=case_id)
        barrier.wait(timeout=5)
        return result

    monkeypatch.setattr(repository, "get", synced_get)

    results: dict[str, Case | BaseException] = {}

    def attach(alert_id: str) -> None:
        try:
            results[alert_id] = service.attach_alert(
                knowledge_base_id=_KB, case_id=case.id, alert=_alert(alert_id=alert_id)
            )
        except BaseException as exc:  # captured for the joining thread to assert on
            results[alert_id] = exc

    thread_b = threading.Thread(target=attach, args=("B",))
    thread_c = threading.Thread(target=attach, args=("C",))
    thread_b.start()
    thread_c.start()
    thread_b.join(timeout=10)
    thread_c.join(timeout=10)

    # Both reads have happened by now; go back to the unwrapped getter so this
    # verification read isn't waiting on a barrier no third thread will reach.
    final = original_get(knowledge_base_id=_KB, case_id=case.id)
    assert final is not None

    successes = {
        alert_id: result for alert_id, result in results.items() if isinstance(result, Case)
    }
    failures = {
        alert_id: result
        for alert_id, result in results.items()
        if isinstance(result, BaseException)
    }
    assert len(successes) == 1 and len(failures) == 1, (
        "expected exactly one thread to succeed and the other to raise "
        f"CaseConcurrentModificationError; got results={results!r}, "
        f"final.alert_ids={final.alert_ids!r}"
    )
    [failure] = failures.values()
    assert isinstance(failure, CaseConcurrentModificationError)

    winner_alert_id = next(iter(successes))
    assert final.alert_ids == ["A", winner_alert_id]
    assert final.timeline[-1].label == "Alert attached"


def test_attach_alert_raises_when_the_case_changed_since_it_was_read() -> None:
    """Unit-level guard: a stale ``updated_at`` snapshot must not be honored.

    This is the same defect as the threaded test above, exercised directly
    against the repository with an explicit stale snapshot instead of real
    concurrency.
    """
    repository = InMemoryCaseRepository()
    service = create_case_service(repository)
    case = _open_case(service, alert_ids=["A"])

    stale = repository.get(knowledge_base_id=_KB, case_id=case.id)
    assert stale is not None

    service.attach_alert(knowledge_base_id=_KB, case_id=case.id, alert=_alert(alert_id="B"))

    with pytest.raises(CaseConcurrentModificationError):
        repository.update(
            stale.model_copy(update={"alert_ids": [*stale.alert_ids, "C"]}),
            expected_updated_at=stale.updated_at,
        )

    final = repository.get(knowledge_base_id=_KB, case_id=case.id)
    assert final is not None
    assert final.alert_ids == ["A", "B"]
