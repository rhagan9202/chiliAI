from __future__ import annotations

from policy.models import PolicyDisposition, PolicyItem


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
