"""Tests for the in-memory case repository (BL-010)."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

import pytest

from cases.adapters.in_memory import InMemoryCaseRepository
from cases.exceptions import CaseConcurrentModificationError, CaseNotFoundError
from cases.models import Case, CasePriority, CaseStatus
from shared.utils import utc_now


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
    created = repo.create(_case("c1", status="open"))

    updated = repo.update(
        _case("c1", status="closed"), expected_updated_at=created.updated_at
    )

    assert updated.status == "closed"
    refetched = repo.get(knowledge_base_id="kb-1", case_id="c1")
    assert refetched is not None
    assert refetched.status == "closed"


def test_update_missing_raises() -> None:
    repo = InMemoryCaseRepository()

    with pytest.raises(CaseNotFoundError):
        repo.update(_case("ghost"), expected_updated_at=utc_now())


def test_update_raises_when_the_row_changed_concurrently() -> None:
    repo = InMemoryCaseRepository()
    created = repo.create(_case("c1", status="open"))

    with pytest.raises(CaseConcurrentModificationError):
        repo.update(_case("c1", status="closed"), expected_updated_at=utc_now())

    refetched = repo.get(knowledge_base_id="kb-1", case_id="c1")
    assert refetched is not None
    assert refetched.status == "open"
    assert refetched.updated_at == created.updated_at


def test_update_is_atomic_under_a_widened_compare_and_write_window() -> None:
    """The compare-and-set in ``update`` must not lose a write to a race.

    ``update`` reads the existing row, compares its ``updated_at``, then
    writes -- three separate steps. Without a lock held across all three, two
    threads can interleave: both compare against the same stored value, then
    both write, with the second write silently discarding the first (the
    same defect this task exists to close, one layer down, since Postgres
    gets true atomicity for free from row-level locking and the in-memory
    adapter does not).

    A real race would only hit this on an unlucky GIL interleave, which makes
    a test that relies on it timing-lucky rather than a real guard. Instead,
    the private ``_cases`` dict is swapped for one whose ``__setitem__``
    sleeps before writing, deliberately widening the compare-to-write window
    so two barrier-synchronized threads reliably overlap inside it. With the
    lock in place, the second thread cannot even begin its compare until the
    first has finished writing, so it correctly loses via
    ``CaseConcurrentModificationError`` instead of silently overwriting.
    """
    repo = InMemoryCaseRepository()
    created = repo.create(_case("c1", status="open"))

    class _SlowWriteDict(dict[tuple[str, str], Case]):
        def __setitem__(self, key: tuple[str, str], value: Case) -> None:
            time.sleep(0.05)
            super().__setitem__(key, value)

    repo._cases = _SlowWriteDict(repo._cases)  # pyright: ignore[reportPrivateUsage]

    start = threading.Barrier(2)
    results: dict[str, Case | BaseException] = {}

    def write(label: str, status: CaseStatus) -> None:
        start.wait(timeout=5)
        candidate = created.model_copy(update={"status": status, "updated_at": utc_now()})
        try:
            results[label] = repo.update(candidate, expected_updated_at=created.updated_at)
        except BaseException as exc:  # captured for the joining thread to assert on
            results[label] = exc

    thread_closed = threading.Thread(target=write, args=("closed", "closed"))
    thread_review = threading.Thread(target=write, args=("in_review", "in_review"))
    thread_closed.start()
    thread_review.start()
    thread_closed.join(timeout=10)
    thread_review.join(timeout=10)

    successes = {
        label: result for label, result in results.items() if isinstance(result, Case)
    }
    failures = {
        label: result
        for label, result in results.items()
        if isinstance(result, BaseException)
    }
    assert len(successes) == 1 and len(failures) == 1, (
        "expected exactly one writer to win and the other to raise "
        f"CaseConcurrentModificationError under a widened compare-and-write "
        f"window; got results={results!r}"
    )
    [failure] = failures.values()
    assert isinstance(failure, CaseConcurrentModificationError)

    winner_label = next(iter(successes))
    refetched = repo.get(knowledge_base_id="kb-1", case_id="c1")
    assert refetched is not None
    assert refetched.status == winner_label


def test_delete_by_kb() -> None:
    repo = InMemoryCaseRepository()
    repo.create(_case("c1", knowledge_base_id="kb-1"))
    repo.create(_case("c2", knowledge_base_id="kb-1"))
    repo.create(_case("c3", knowledge_base_id="kb-2"))

    removed = repo.delete_by_kb("kb-1")

    assert removed == 2
    assert repo.get(knowledge_base_id="kb-1", case_id="c1") is None
    assert repo.get(knowledge_base_id="kb-2", case_id="c3") is not None
