"""Contract tests for the in-memory conversation repository (BL-012)."""

from __future__ import annotations

from conversations.adapters.in_memory import InMemoryConversationRepository
from conversations.models import (
    Conversation,
    ConversationCitation,
    ConversationMessage,
)


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
    saved = repo.save(created.model_copy(update={"messages": [message]}))

    assert [m.id for m in saved.messages] == ["m-1"]
    reread = repo.get(created.id)
    assert reread is not None
    assert reread.messages[0].citations[0].content_id == "content-1"
