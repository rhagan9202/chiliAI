from __future__ import annotations

from policy.adapters.in_memory import InMemoryPolicyItemRepository
from policy.exceptions import PolicyItemAlreadyTriagedError, PolicyItemNotFoundError
from policy.models import PolicyDisposition, PolicyItem
from policy.service import create_policy_service

import pytest


def _service() -> tuple[object, InMemoryPolicyItemRepository]:
    repo = InMemoryPolicyItemRepository()
    return create_policy_service(repo), repo


def test_policy_item_defaults_to_open_with_timestamps() -> None:
    item = PolicyItem(
        id="item-1",
        knowledge_base_id="kb-1",
        rule_id="rule-1",
        rule_pack_id="pack-1",
        target_kind="entity",
        target_ref="claim-9",
        title="Claim claim-9 exceeds billing threshold",
        severity="high",
        matched_fields={"billed_amount": 1200.0},
        citations=[],
    )
    assert item.status == "open"
    assert item.disposition is None
    # Both timestamps are stamped at construction; a fresh item has not been
    # updated after creation, so updated_at is no earlier than created_at.
    assert item.updated_at >= item.created_at


def test_policy_disposition_carries_case_link() -> None:
    disp = PolicyDisposition(
        action="escalate",
        actor="analyst@example.com",
        note=None,
        decided_at=PolicyItem.model_fields["created_at"].default_factory(),  # type: ignore[misc]
        case_id="case-77",
    )
    assert disp.case_id == "case-77"
    assert disp.action == "escalate"


def test_record_match_creates_open_item() -> None:
    service, _ = _service()
    item = service.record_match(
        knowledge_base_id="kb-1", rule_id="r1", rule_pack_id="p1",
        target_kind="entity", target_ref="claim-1",
        title="Claim claim-1 over threshold", severity="high",
        matched_fields={"billed_amount": 1500.0}, citations=[],
    )
    assert item.status == "open"
    assert item.id  # generated


def test_triage_records_disposition_and_status() -> None:
    service, _ = _service()
    item = service.record_match(
        knowledge_base_id="kb-1", rule_id="r1", rule_pack_id="p1",
        target_kind="entity", target_ref="claim-1", title="t", severity="high",
        matched_fields={}, citations=[],
    )
    triaged = service.triage(
        knowledge_base_id="kb-1", item_id=item.id, action="accept", actor="ana", note="ok",
    )
    assert triaged.status == "accepted"
    assert triaged.disposition is not None
    assert triaged.disposition.actor == "ana"


def test_triage_escalate_stores_case_id() -> None:
    service, _ = _service()
    item = service.record_match(
        knowledge_base_id="kb-1", rule_id="r1", rule_pack_id="p1",
        target_kind="entity", target_ref="claim-1", title="t", severity="high",
        matched_fields={}, citations=[],
    )
    triaged = service.triage(
        knowledge_base_id="kb-1", item_id=item.id, action="escalate",
        actor="ana", case_id="case-9",
    )
    assert triaged.status == "escalated"
    assert triaged.disposition is not None and triaged.disposition.case_id == "case-9"


def test_triage_missing_item_raises_not_found() -> None:
    service, _ = _service()
    with pytest.raises(PolicyItemNotFoundError):
        service.triage(knowledge_base_id="kb-1", item_id="nope", action="accept", actor="ana")


def test_triage_already_disposed_raises_conflict() -> None:
    service, _ = _service()
    item = service.record_match(
        knowledge_base_id="kb-1", rule_id="r1", rule_pack_id="p1",
        target_kind="entity", target_ref="claim-1", title="t", severity="high",
        matched_fields={}, citations=[],
    )
    service.triage(knowledge_base_id="kb-1", item_id=item.id, action="accept", actor="ana")
    with pytest.raises(PolicyItemAlreadyTriagedError):
        service.triage(knowledge_base_id="kb-1", item_id=item.id, action="reject", actor="ana")
