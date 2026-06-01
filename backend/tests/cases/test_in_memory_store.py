"""Tests for the in-memory case repository (BL-010)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from cases.adapters.in_memory import InMemoryCaseRepository
from cases.exceptions import CaseNotFoundError
from cases.models import Case, CasePriority, CaseStatus


def _case(
    case_id: str,
    *,
    knowledge_base_id: str = "kb-1",
    status: CaseStatus = "open",
    priority: CasePriority = "high",
    updated_minute: int = 0,
) -> Case:
    stamp = datetime(2026, 6, 1, 12, updated_minute, 0, tzinfo=timezone.utc)
    return Case(
        id=case_id,
        knowledge_base_id=knowledge_base_id,
        title=f"Case {case_id}",
        status=status,
        priority=priority,
        created_at=stamp,
        updated_at=stamp,
    )


def test_create_then_get_roundtrip() -> None:
    repo = InMemoryCaseRepository()
    repo.create(_case("c1"))

    fetched = repo.get(knowledge_base_id="kb-1", case_id="c1")

    assert fetched is not None
    assert fetched.id == "c1"


def test_get_missing_returns_none() -> None:
    assert InMemoryCaseRepository().get(knowledge_base_id="kb-1", case_id="nope") is None


def test_kb_isolation() -> None:
    repo = InMemoryCaseRepository()
    repo.create(_case("c1", knowledge_base_id="kb-1"))

    assert repo.get(knowledge_base_id="kb-2", case_id="c1") is None
    items, total = repo.list(knowledge_base_id="kb-2", limit=10, offset=0)
    assert items == [] and total == 0


def test_list_orders_newest_first_with_total() -> None:
    repo = InMemoryCaseRepository()
    repo.create(_case("old", updated_minute=0))
    repo.create(_case("new", updated_minute=5))

    items, total = repo.list(knowledge_base_id="kb-1", limit=10, offset=0)

    assert [case.id for case in items] == ["new", "old"]
    assert total == 2


def test_list_filters_by_status_and_priority() -> None:
    repo = InMemoryCaseRepository()
    repo.create(_case("a", status="open", priority="high"))
    repo.create(_case("b", status="closed", priority="high"))
    repo.create(_case("c", status="open", priority="low"))

    open_items, open_total = repo.list(knowledge_base_id="kb-1", limit=10, offset=0, status="open")
    high_items, high_total = repo.list(
        knowledge_base_id="kb-1", limit=10, offset=0, priority="high"
    )

    assert {case.id for case in open_items} == {"a", "c"} and open_total == 2
    assert {case.id for case in high_items} == {"a", "b"} and high_total == 2


def test_list_paginates() -> None:
    repo = InMemoryCaseRepository()
    for index in range(5):
        repo.create(_case(f"c{index}", updated_minute=index))

    items, total = repo.list(knowledge_base_id="kb-1", limit=2, offset=0)

    assert len(items) == 2
    assert total == 5


def test_update_existing_case() -> None:
    repo = InMemoryCaseRepository()
    repo.create(_case("c1", status="open"))

    updated = repo.update(_case("c1", status="closed"))

    assert updated.status == "closed"
    refetched = repo.get(knowledge_base_id="kb-1", case_id="c1")
    assert refetched is not None
    assert refetched.status == "closed"


def test_update_missing_raises() -> None:
    repo = InMemoryCaseRepository()

    with pytest.raises(CaseNotFoundError):
        repo.update(_case("ghost"))


def test_delete_by_kb() -> None:
    repo = InMemoryCaseRepository()
    repo.create(_case("c1", knowledge_base_id="kb-1"))
    repo.create(_case("c2", knowledge_base_id="kb-1"))
    repo.create(_case("c3", knowledge_base_id="kb-2"))

    removed = repo.delete_by_kb("kb-1")

    assert removed == 2
    assert repo.get(knowledge_base_id="kb-1", case_id="c1") is None
    assert repo.get(knowledge_base_id="kb-2", case_id="c3") is not None
