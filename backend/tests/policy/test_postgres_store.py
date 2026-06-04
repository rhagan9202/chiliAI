"""Integration tests for the Postgres policy item repository (BL-011)."""

from __future__ import annotations

import pytest

from policy.adapters.postgres import PostgresPolicyItemRepository
from policy.models import PolicyDisposition, PolicyItem
from shared.utils import utc_now

pytestmark = pytest.mark.integration


def _item(item_id: str, *, target_ref: str = "claim-1", status: str = "open") -> PolicyItem:
    now = utc_now()
    return PolicyItem(
        id=item_id, knowledge_base_id="kb-pg", rule_id="rule-1", rule_pack_id="pack-1",
        target_kind="entity", target_ref=target_ref, title="t", severity="high",
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
    items, total = repo.list(knowledge_base_id="kb-pg", limit=10, offset=0, status="open")
    assert total == 2 and len(items) == 2
    assert repo.delete_by_kb("kb-pg") == 2
