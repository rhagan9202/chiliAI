"""Integration tests for the Postgres conversation repository (BL-012).

Requires DATABASE_URL + the 0005_conversations migration.
"""

from __future__ import annotations

import threading

import pytest

from conversations.adapters.postgres import PostgresConversationRepository
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

pytestmark = pytest.mark.integration


def _conversation(conversation_id: str = "conv-pg") -> Conversation:
    return Conversation(
        id=conversation_id,
        title="Provider anomaly review",
        knowledge_base_id="kb-pg",
    )


def test_create_then_get_round_trips(
    conversation_pg_repo: PostgresConversationRepository,
) -> None:
    repo = conversation_pg_repo
    repo.create(_conversation())

    stored = repo.get("conv-pg")
    assert stored is not None
    assert stored.knowledge_base_id == "kb-pg"
    assert stored.messages == []


def test_save_round_trips_messages_with_citations(
    conversation_pg_repo: PostgresConversationRepository,
) -> None:
    repo = conversation_pg_repo
    created = repo.create(_conversation())

    message = ConversationMessage(
        id="m-1",
        role="assistant",
        content="High risk.",
        citation_ids=["content-1"],
        citations=[
            ConversationCitation(
                record_id="record-1",
                content_id="content-1",
                score=0.9,
                snippet="peer deviation",
                chunk_index=2,
            )
        ],
    )
    repo.save(
        created.model_copy(update={"messages": [message]}),
        expected_updated_at=created.updated_at,
    )

    stored = repo.get("conv-pg")
    assert stored is not None
    assert stored.messages[0].citations[0].content_id == "content-1"
    assert stored.messages[0].citations[0].chunk_index == 2


def test_create_is_idempotent(
    conversation_pg_repo: PostgresConversationRepository,
) -> None:
    repo = conversation_pg_repo
    repo.create(_conversation())
    repo.create(_conversation().model_copy(update={"title": "Other"}))

    stored = repo.get("conv-pg")
    assert stored is not None
    assert stored.title == "Provider anomaly review"


def test_delete_by_kb_removes_rows_and_returns_count(
    database_url: str,
) -> None:
    from config.schema import DatabaseConfig
    from database.runtime import create_connection_provider

    unique_kb = "kb-delete-test-unique-001"
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    repo = PostgresConversationRepository(provider)
    try:
        conv_a = Conversation(
            id="conv-del-a",
            title="Delete test A",
            knowledge_base_id=unique_kb,
        )
        conv_b = Conversation(
            id="conv-del-b",
            title="Delete test B",
            knowledge_base_id=unique_kb,
        )
        conv_other = Conversation(
            id="conv-del-other",
            title="Other KB",
            knowledge_base_id="kb-other-unique-001",
        )
        repo.create(conv_a)
        repo.create(conv_b)
        repo.create(conv_other)

        count = repo.delete_by_kb(unique_kb)

        assert count == 2
        assert repo.get("conv-del-a") is None
        assert repo.get("conv-del-b") is None
        # row from a different KB must survive
        assert repo.get("conv-del-other") is not None

        # idempotent: second call returns 0
        second = repo.delete_by_kb(unique_kb)
        assert second == 0
    finally:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM conversations WHERE conversation_id IN (%s, %s, %s)",
                ("conv-del-a", "conv-del-b", "conv-del-other"),
            )
            conn.commit()
        provider.close()


def test_save_missing_raises(
    conversation_pg_repo: PostgresConversationRepository,
) -> None:
    with pytest.raises(ConversationNotFoundError):
        conversation_pg_repo.save(_conversation("ghost-conv"), expected_updated_at=utc_now())


def test_save_raises_when_the_row_changed_concurrently(
    conversation_pg_repo: PostgresConversationRepository,
) -> None:
    """A stale ``updated_at`` snapshot must not be honored (unit-level guard).

    Same defect as the threaded test below, exercised directly against the
    repository with an explicit stale snapshot instead of real concurrency.
    """
    repo = conversation_pg_repo
    created = repo.create(_conversation())
    stale = repo.get("conv-pg")
    assert stale is not None

    # A legitimate concurrent writer commits first, using the same snapshot.
    winner = stale.model_copy(update={"title": "Winner", "updated_at": utc_now()})
    repo.save(winner, expected_updated_at=stale.updated_at)

    with pytest.raises(ConversationConcurrentModificationError):
        repo.save(
            stale.model_copy(update={"title": "Loser", "updated_at": utc_now()}),
            expected_updated_at=stale.updated_at,
        )

    final = repo.get("conv-pg")
    assert final is not None
    assert final.title == "Winner"  # the loser's write never landed
    assert created.title == "Provider anomaly review"


def test_concurrent_append_does_not_silently_drop_the_other_turn(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two analysts append different turns to one conversation at the same time.

    Both read the same message list, and -- pre-fix -- both write the whole
    jsonb array from their own stale copy; whoever commits second wins and
    the other turn vanishes, with no error raised to the loser. Post-fix,
    the guarded ``UPDATE ... WHERE updated_at = %s`` means exactly one
    thread's ``save`` can win per attempt; ``ConversationService`` retries
    the loser, so both turns must ultimately land and neither thread raises.

    A ``threading.Barrier`` forces both threads' ``repository.get`` (the read
    inside ``ConversationService.append_messages``) to complete before either
    thread's write proceeds, reproducing the interleave deterministically
    (mirrors ``tests/cases/test_postgres_store.py::test_concurrent_attach_does_not_silently_drop_the_other_alert``).
    """
    from config.schema import DatabaseConfig
    from conversations.service import create_conversation_service
    from database.runtime import create_connection_provider

    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    repo = PostgresConversationRepository(provider)
    service = create_conversation_service(repo)
    try:
        created = repo.create(_conversation("conv-pg-race"))

        barrier = threading.Barrier(2)
        original_get = repo.get
        thread_state = threading.local()

        def synced_get(conversation_id: str) -> Conversation | None:
            # Only the first get() per thread -- the "both callers read the
            # conversation" step -- is synchronized; append_messages' own
            # retry-on-conflict re-read must run unsynchronized, or the
            # winner (which never retries) would leave the loser waiting on
            # a barrier no one else reaches.
            if not getattr(thread_state, "synced", False):
                thread_state.synced = True
                barrier.wait(timeout=5)
                result = original_get(conversation_id)
                barrier.wait(timeout=5)
                return result
            return original_get(conversation_id)

        monkeypatch.setattr(repo, "get", synced_get)

        results: dict[str, Conversation | BaseException] = {}

        def append(label: str) -> None:
            try:
                results[label] = service.append_messages(
                    created.id,
                    [ConversationMessage(id=f"m-{label}", role="user", content=label)],
                )
            except BaseException as exc:  # captured for the joining thread to assert on
                results[label] = exc

        thread_a = threading.Thread(target=append, args=("turn-a",))
        thread_b = threading.Thread(target=append, args=("turn-b",))
        thread_a.start()
        thread_b.start()
        thread_a.join(timeout=10)
        thread_b.join(timeout=10)

        final = original_get(created.id)
        assert final is not None

        for label, result in results.items():
            assert isinstance(result, Conversation), (
                f"expected {label} to succeed via retry, got {result!r}"
            )
        contents = {message.content for message in final.messages}
        assert {"turn-a", "turn-b"} <= contents, (
            f"a turn was lost: {contents}"
        )
    finally:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM conversations WHERE conversation_id = %s",
                ("conv-pg-race",),
            )
            conn.commit()
        provider.close()
