"""Contract tests for the in-memory conversation repository (BL-012)."""

from __future__ import annotations

import threading
import time

import pytest

from conversations.adapters.in_memory import InMemoryConversationRepository
from conversations.exceptions import (
    ConversationConcurrentModificationError,
    ConversationNotFoundError,
)
from conversations.models import (
    Conversation,
    ConversationCitation,
    ConversationMessage,
)
from shared.utils import utc_now


def _conversation(conversation_id: str = "conv-1") -> Conversation:
    return Conversation(
        id=conversation_id,
        title="Provider anomaly review",
        knowledge_base_id="kb-1",
    )


def test_create_then_get_round_trips() -> None:
    repo = InMemoryConversationRepository()

    created = repo.create(_conversation())

    fetched = repo.get(created.id)
    assert fetched is not None
    assert fetched.id == "conv-1"
    assert fetched.knowledge_base_id == "kb-1"
    assert fetched.messages == []


def test_get_unknown_returns_none() -> None:
    repo = InMemoryConversationRepository()

    assert repo.get("missing") is None


def test_create_is_idempotent_on_id() -> None:
    repo = InMemoryConversationRepository()
    repo.create(_conversation())

    # A second create with the same id must not overwrite the first.
    repo.create(_conversation().model_copy(update={"title": "Different"}))

    stored = repo.get("conv-1")
    assert stored is not None
    assert stored.title == "Provider anomaly review"


def test_delete_by_kb_removes_matching_and_returns_count() -> None:
    repo = InMemoryConversationRepository()
    repo.create(_conversation("conv-a").model_copy(update={"knowledge_base_id": "kb-x"}))
    repo.create(_conversation("conv-b").model_copy(update={"knowledge_base_id": "kb-x"}))
    repo.create(_conversation("conv-c").model_copy(update={"knowledge_base_id": "kb-y"}))

    count = repo.delete_by_kb("kb-x")

    assert count == 2
    assert repo.get("conv-a") is None
    assert repo.get("conv-b") is None
    # kb-y must be untouched
    assert repo.get("conv-c") is not None


def test_delete_by_kb_is_idempotent() -> None:
    repo = InMemoryConversationRepository()
    repo.create(_conversation("conv-d").model_copy(update={"knowledge_base_id": "kb-z"}))

    first = repo.delete_by_kb("kb-z")
    second = repo.delete_by_kb("kb-z")

    assert first == 1
    assert second == 0


def test_save_persists_appended_messages_with_citations() -> None:
    repo = InMemoryConversationRepository()
    created = repo.create(_conversation())

    message = ConversationMessage(
        id="m-1",
        role="assistant",
        content="Provider is high risk.",
        citation_ids=["content-1"],
        citations=[
            ConversationCitation(
                record_id="record-1",
                content_id="content-1",
                score=0.91,
                snippet="peer cohort deviation",
            )
        ],
    )
    saved = repo.save(
        created.model_copy(update={"messages": [message]}),
        expected_updated_at=created.updated_at,
    )

    assert [m.id for m in saved.messages] == ["m-1"]
    reread = repo.get(created.id)
    assert reread is not None
    assert reread.messages[0].citations[0].content_id == "content-1"


def test_save_missing_raises() -> None:
    repo = InMemoryConversationRepository()

    with pytest.raises(ConversationNotFoundError):
        repo.save(_conversation("ghost"), expected_updated_at=utc_now())


def test_save_raises_when_the_row_changed_concurrently() -> None:
    repo = InMemoryConversationRepository()
    created = repo.create(_conversation())

    with pytest.raises(ConversationConcurrentModificationError):
        repo.save(
            created.model_copy(update={"title": "Different"}),
            expected_updated_at=utc_now(),
        )

    refetched = repo.get(created.id)
    assert refetched is not None
    assert refetched.title == created.title
    assert refetched.updated_at == created.updated_at


def test_save_is_atomic_under_a_widened_compare_and_write_window() -> None:
    """The compare-and-set in ``save`` must not lose a write to a race.

    ``save`` reads the existing row, compares its ``updated_at``, then
    writes -- three separate steps. Without a lock held across all three,
    two threads can interleave: both compare against the same stored value,
    then both write, with the second write silently discarding the first
    (the defect BL-012-06 exists to close, one layer down, since Postgres
    gets true atomicity for free from row-level locking and the in-memory
    adapter does not).

    A real race would only hit this on an unlucky GIL interleave, which
    makes a test that relies on it timing-lucky rather than a real guard.
    Instead, the private ``_conversations`` dict is swapped for one whose
    ``__setitem__`` sleeps before writing, deliberately widening the
    compare-to-write window so two barrier-synchronized threads reliably
    overlap inside it. With the lock in place, the second thread cannot even
    begin its compare until the first has finished writing, so it correctly
    loses via ``ConversationConcurrentModificationError`` instead of
    silently overwriting (mirrors
    ``tests/cases/test_in_memory_store.py::test_update_is_atomic_under_a_widened_compare_and_write_window``).
    """
    repo = InMemoryConversationRepository()
    created = repo.create(_conversation())

    class _SlowWriteDict(dict[str, Conversation]):
        def __setitem__(self, key: str, value: Conversation) -> None:
            time.sleep(0.05)
            super().__setitem__(key, value)

    repo._conversations = _SlowWriteDict(repo._conversations)  # pyright: ignore[reportPrivateUsage]

    start = threading.Barrier(2)
    results: dict[str, Conversation | BaseException] = {}

    def write(label: str, title: str) -> None:
        start.wait(timeout=5)
        candidate = created.model_copy(update={"title": title, "updated_at": utc_now()})
        try:
            results[label] = repo.save(candidate, expected_updated_at=created.updated_at)
        except BaseException as exc:  # captured for the joining thread to assert on
            results[label] = exc

    thread_a = threading.Thread(target=write, args=("a", "Title A"))
    thread_b = threading.Thread(target=write, args=("b", "Title B"))
    thread_a.start()
    thread_b.start()
    thread_a.join(timeout=10)
    thread_b.join(timeout=10)

    successes = {
        label: result
        for label, result in results.items()
        if isinstance(result, Conversation)
    }
    failures = {
        label: result
        for label, result in results.items()
        if isinstance(result, BaseException)
    }
    assert len(successes) == 1 and len(failures) == 1, (
        "expected exactly one writer to win and the other to raise "
        f"ConversationConcurrentModificationError under a widened "
        f"compare-and-write window; got results={results!r}"
    )
    [failure] = failures.values()
    assert isinstance(failure, ConversationConcurrentModificationError)
