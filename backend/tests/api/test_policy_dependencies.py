from __future__ import annotations

import pytest

from api.contracts import PolicyTriageRequest
from api.dependencies import _apply_policy_triage
from cases.adapters.in_memory import InMemoryCaseRepository
from cases.service import CaseService, create_case_service
from policy.adapters.in_memory import InMemoryPolicyItemRepository
from policy.models import PolicyItem
from policy.service import PolicyService, create_policy_service


def _wire() -> tuple[PolicyService, CaseService, PolicyItem]:
    policy = create_policy_service(InMemoryPolicyItemRepository())
    cases = create_case_service(InMemoryCaseRepository())
    item = policy.record_match(
        knowledge_base_id="kb-1",
        rule_id="r1",
        rule_pack_id="p1",
        target_kind="entity",
        target_ref="claim-1",
        title="Claim claim-1 over threshold",
        severity="high",
        matched_fields={"properties.amount": 1500.0},
        citations=[],
    )
    return policy, cases, item


def test_escalate_creates_and_links_case() -> None:
    policy, cases, item = _wire()
    detail = _apply_policy_triage(
        policy_service=policy,
        case_service=cases,
        knowledge_base_id="kb-1",
        item_id=item.id,
        payload=PolicyTriageRequest(action="escalate", note="urgent"),
        actor="ana@example.com",
    )
    assert detail.item.status == "escalated"
    assert detail.disposition is not None and detail.disposition.case_id is not None
    listed, total = cases.list(knowledge_base_id="kb-1", limit=10, offset=0)
    assert total == 1
    assert listed[0].timeline  # carries the policy-origin event


def test_accept_does_not_create_a_case() -> None:
    policy, cases, item = _wire()
    detail = _apply_policy_triage(
        policy_service=policy,
        case_service=cases,
        knowledge_base_id="kb-1",
        item_id=item.id,
        payload=PolicyTriageRequest(action="accept"),
        actor="ana",
    )
    assert detail.item.status == "accepted"
    assert cases.list(knowledge_base_id="kb-1", limit=10, offset=0)[1] == 0


def test_escalate_on_already_triaged_item_creates_no_case() -> None:
    # Orphan-prevention: a 409 on triage must not leave a committed case behind.
    from fastapi import HTTPException

    policy, cases, item = _wire()
    policy.triage(knowledge_base_id="kb-1", item_id=item.id, action="accept", actor="ana")
    before = cases.list(knowledge_base_id="kb-1", limit=10, offset=0)[1]
    with pytest.raises(HTTPException) as exc_info:
        _apply_policy_triage(
            policy_service=policy, case_service=cases, knowledge_base_id="kb-1",
            item_id=item.id, payload=PolicyTriageRequest(action="escalate"), actor="ana",
        )
    assert exc_info.value.status_code == 409
    after = cases.list(knowledge_base_id="kb-1", limit=10, offset=0)[1]
    assert after == before  # no orphaned case was created
