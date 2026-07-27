"""Integration tests for the Postgres policy item repository (BL-011)."""

from __future__ import annotations

import pytest

from policy.adapters.postgres import PostgresPolicyItemRepository
from policy.models import PolicyDisposition, PolicyItem
from shared.utils import utc_now

pytestmark = pytest.mark.integration


def _item(
    item_id: str,
    *,
    target_ref: str = "claim-1",
    status: str = "open",
    title: str = "t",
    rule_id: str = "rule-1",
) -> PolicyItem:
    now = utc_now()
    return PolicyItem(
        id=item_id, knowledge_base_id="kb-pg", rule_id=rule_id, rule_pack_id="pack-1",
        target_kind="entity", target_ref=target_ref, title=title, severity="high",
        matched_fields={"properties.amount": 1500.0}, citations=[], status=status,  # type: ignore[arg-type]
        created_at=now, updated_at=now,
    )


def test_upsert_conflict_refreshes_open_but_not_disposed(policy_pg_repo: PostgresPolicyItemRepository) -> None:
    repo = policy_pg_repo
    repo.upsert(_item("a"))
    # Same natural key while open -> refresh, keep id "a".
    refreshed = repo.upsert(_item("b").model_copy(update={"matched_fields": {"properties.amount": 9.0}}))
    assert refreshed.id == "a"
    assert refreshed.matched_fields == {"properties.amount": 9.0}

    stored = repo.get(knowledge_base_id="kb-pg", item_id="a")
    assert stored is not None
    repo.update(stored.model_copy(update={
        "status": "accepted",
        "disposition": PolicyDisposition(action="accept", actor="x", decided_at=utc_now()),
    }))
    # Disposed -> upsert must not reopen.
    after = repo.upsert(_item("c"))
    assert after.status == "accepted"


def test_list_filter_and_delete(policy_pg_repo: PostgresPolicyItemRepository) -> None:
    repo = policy_pg_repo
    repo.upsert(_item("a", target_ref="claim-1"))
    repo.upsert(_item("b", target_ref="claim-2"))
    items, total = repo.list(knowledge_base_id="kb-pg", limit=10, offset=0, statuses=["open"])
    assert total == 2 and len(items) == 2
    assert repo.delete_by_kb("kb-pg") == 2


def test_list_matches_any_of_several_statuses(
    policy_pg_repo: PostgresPolicyItemRepository,
) -> None:
    # status = ANY(%s) against real SQL, not just the in-memory tally (UXA-401).
    repo = policy_pg_repo
    repo.upsert(_item("a", target_ref="claim-1"))
    repo.upsert(_item("b", target_ref="claim-2", status="escalated"))
    repo.upsert(_item("c", target_ref="claim-3", status="rejected"))

    items, total = repo.list(
        knowledge_base_id="kb-pg", limit=10, offset=0, statuses=["open", "escalated"]
    )

    assert total == 2
    assert {item.id for item in items} == {"a", "b"}
    # Empty selection is "no filter", not "match nothing".
    assert repo.list(knowledge_base_id="kb-pg", limit=10, offset=0, statuses=[])[1] == 3


def test_list_search_is_case_insensitive_and_literal(
    policy_pg_repo: PostgresPolicyItemRepository,
) -> None:
    repo = policy_pg_repo
    repo.upsert(_item("a", target_ref="claim-1", title="Upcoding suspected"))
    repo.upsert(_item("b", target_ref="claim-2", title="Duplicate billing"))
    repo.upsert(_item("c", target_ref="claim-3", title="Paid at 50% of billed"))

    matched, total = repo.list(
        knowledge_base_id="kb-pg", limit=10, offset=0, query="UPCODING"
    )
    assert total == 1
    assert [item.id for item in matched] == ["a"]

    # A searched "%" is a literal, not a wildcard that matches every title.
    wildcard, wildcard_total = repo.list(
        knowledge_base_id="kb-pg", limit=10, offset=0, query="50%"
    )
    assert wildcard_total == 1
    assert [item.id for item in wildcard] == ["c"]


def test_count_by_status_groups_over_the_whole_kb(
    policy_pg_repo: PostgresPolicyItemRepository,
) -> None:
    repo = policy_pg_repo
    repo.upsert(_item("a", target_ref="claim-1"))
    repo.upsert(_item("b", target_ref="claim-2"))
    repo.upsert(_item("c", target_ref="claim-3", status="escalated"))

    assert repo.count_by_status("kb-pg") == {"open": 2, "escalated": 1}
    assert repo.count_by_status("kb-absent") == {}
