from __future__ import annotations

from datetime import timedelta

from policy.adapters.in_memory import InMemoryPolicyItemRepository
from policy.exceptions import PolicyItemNotFoundError
from policy.models import PolicyDisposition, PolicyItem
from shared.utils import utc_now

import pytest


def _item(*, item_id: str, rule_id: str = "rule-1", target_ref: str = "claim-1",
          kb: str = "kb-1", status: str = "open", title: str = "t") -> PolicyItem:
    now = utc_now()
    return PolicyItem(
        id=item_id, knowledge_base_id=kb, rule_id=rule_id, rule_pack_id="pack-1",
        target_kind="entity", target_ref=target_ref, title=title, severity="high",
        matched_fields={"billed_amount": 1000.0}, citations=[], status=status,  # type: ignore[arg-type]
        created_at=now, updated_at=now,
    )


def test_upsert_inserts_then_refreshes_open_item_in_place() -> None:
    repo = InMemoryPolicyItemRepository()
    repo.upsert(_item(item_id="a"))
    # Same natural key, new id/value — should refresh in place, keep the first id.
    refreshed = repo.upsert(
        _item(item_id="b").model_copy(update={"matched_fields": {"billed_amount": 2000.0}})
    )
    assert refreshed.id == "a"
    assert refreshed.matched_fields == {"billed_amount": 2000.0}
    items, total = repo.list(knowledge_base_id="kb-1", limit=10, offset=0)
    assert total == 1
    assert len(items) == 1


def test_upsert_does_not_reopen_a_disposed_item() -> None:
    repo = InMemoryPolicyItemRepository()
    repo.upsert(_item(item_id="a"))
    stored = repo.get(knowledge_base_id="kb-1", item_id="a")
    assert stored is not None
    repo.update(stored.model_copy(update={
        "status": "accepted",
        "disposition": PolicyDisposition(action="accept", actor="x", decided_at=utc_now()),
    }))
    # A later matching evaluation must NOT reopen it.
    result = repo.upsert(_item(item_id="c"))
    assert result.status == "accepted"


def test_list_filters_by_status_and_sorts_newest_first() -> None:
    repo = InMemoryPolicyItemRepository()
    older = _item(item_id="a", target_ref="claim-1")
    newer = _item(item_id="b", target_ref="claim-2").model_copy(
        update={"updated_at": older.updated_at + timedelta(minutes=5)}
    )
    repo.upsert(older)
    repo.upsert(newer)
    open_items, total = repo.list(
        knowledge_base_id="kb-1", limit=10, offset=0, statuses=["open"]
    )
    assert total == 2
    assert [i.id for i in open_items] == ["b", "a"]
    none_accepted, total2 = repo.list(
        knowledge_base_id="kb-1", limit=10, offset=0, statuses=["accepted"]
    )
    assert (none_accepted, total2) == ([], 0)


def test_list_matches_any_of_several_statuses() -> None:
    # "open OR escalated" is the working set an analyst asks for (UXA-401).
    repo = InMemoryPolicyItemRepository()
    repo.upsert(_item(item_id="a", target_ref="claim-1"))
    repo.upsert(_item(item_id="b", target_ref="claim-2", status="escalated"))
    repo.upsert(_item(item_id="c", target_ref="claim-3", status="rejected"))

    items, total = repo.list(
        knowledge_base_id="kb-1", limit=10, offset=0, statuses=["open", "escalated"]
    )

    assert total == 2
    assert {item.id for item in items} == {"a", "b"}


def test_list_with_empty_status_selection_returns_every_status() -> None:
    # An empty list means "no filter", not "match nothing" — the UI sends the
    # selection verbatim and an all-cleared strip must not empty the queue.
    repo = InMemoryPolicyItemRepository()
    repo.upsert(_item(item_id="a", target_ref="claim-1"))
    repo.upsert(_item(item_id="b", target_ref="claim-2", status="rejected"))

    assert repo.list(knowledge_base_id="kb-1", limit=10, offset=0, statuses=[])[1] == 2


def test_list_searches_titles_case_insensitively() -> None:
    repo = InMemoryPolicyItemRepository()
    repo.upsert(_item(item_id="a", target_ref="claim-1", title="Upcoding suspected"))
    repo.upsert(_item(item_id="b", target_ref="claim-2", title="Duplicate billing"))

    items, total = repo.list(
        knowledge_base_id="kb-1", limit=10, offset=0, query="UPCODING"
    )

    assert total == 1
    assert [item.id for item in items] == ["a"]


def test_list_combines_status_and_search() -> None:
    repo = InMemoryPolicyItemRepository()
    repo.upsert(_item(item_id="a", target_ref="claim-1", title="Upcoding suspected"))
    repo.upsert(
        _item(item_id="b", target_ref="claim-2", title="Upcoding again", status="rejected")
    )

    items, total = repo.list(
        knowledge_base_id="kb-1", limit=10, offset=0, statuses=["open"], query="upcoding"
    )

    assert total == 1
    assert [item.id for item in items] == ["a"]


def test_count_by_status_tallies_the_whole_kb() -> None:
    repo = InMemoryPolicyItemRepository()
    repo.upsert(_item(item_id="a", target_ref="claim-1"))
    repo.upsert(_item(item_id="b", target_ref="claim-2"))
    repo.upsert(_item(item_id="c", target_ref="claim-3", status="escalated"))
    repo.upsert(_item(item_id="d", kb="kb-2", target_ref="claim-4"))

    assert repo.count_by_status("kb-1") == {"open": 2, "escalated": 1}
    assert repo.count_by_status("kb-3") == {}


def test_update_missing_raises() -> None:
    repo = InMemoryPolicyItemRepository()
    with pytest.raises(PolicyItemNotFoundError):
        repo.update(_item(item_id="ghost"))


def test_delete_by_kb_removes_only_that_kb() -> None:
    repo = InMemoryPolicyItemRepository()
    repo.upsert(_item(item_id="a", kb="kb-1"))
    repo.upsert(_item(item_id="b", kb="kb-2", rule_id="r2"))
    removed = repo.delete_by_kb("kb-1")
    assert removed == 1
    assert repo.list(knowledge_base_id="kb-1", limit=10, offset=0)[1] == 0
    assert repo.list(knowledge_base_id="kb-2", limit=10, offset=0)[1] == 1
