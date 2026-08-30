"""Tests for the conversation service over a durable repository (BL-012)."""

from __future__ import annotations

from datetime import datetime

import pytest

from conversations.adapters.in_memory import InMemoryConversationRepository
from conversations.adapters.postgres import PostgresConversationRepository
from conversations.adapters.protocols import ConversationRepository
from conversations.exceptions import (
    ConversationConcurrentModificationError,
    ConversationNotFoundError,
)
from conversations.models import Conversation, ConversationMessage
from conversations.service import MAX_APPEND_ATTEMPTS, create_conversation_service


def test_create_defaults_title_when_absent() -> None:
    service = create_conversation_service(InMemoryConversationRepository())

    conversation = service.create(knowledge_base_id="kb-1")

    assert conversation.title == "Untitled investigation chat"
    assert conversation.knowledge_base_id == "kb-1"
    assert conversation.id


def test_create_uses_supplied_title() -> None:
    service = create_conversation_service(InMemoryConversationRepository())

    conversation = service.create(knowledge_base_id="kb-1", title="Triage")

    assert conversation.title == "Triage"


def test_append_messages_persists_in_order() -> None:
    service = create_conversation_service(InMemoryConversationRepository())
    conversation = service.create(knowledge_base_id="kb-1")

    user = ConversationMessage(id="u-1", role="user", content="Why risky?")
    assistant = ConversationMessage(id="a-1", role="assistant", content="Because.")
    updated = service.append_messages(conversation.id, [user, assistant])

    assert [m.id for m in updated.messages] == ["u-1", "a-1"]
    reread = service.get(conversation.id)
    assert reread is not None
    assert len(reread.messages) == 2


def test_append_messages_unknown_conversation_raises() -> None:
    service = create_conversation_service(InMemoryConversationRepository())

    with pytest.raises(ConversationNotFoundError):
        service.append_messages("missing", [])


@pytest.mark.integration
def test_appending_messages_advances_updated_at_in_every_adapter(
    conversation_pg_repo: PostgresConversationRepository,
) -> None:
    """The in-memory adapter used to re-stamp updated_at inside save(); the
    Postgres one writes back whatever it was handed. So `/chat/conversations`,
    ordered "most recently updated first", was really ordered by creation
    time -- but only in production, because the in-memory adapter the rest of
    the tests exercise hid it.

    The service must own the timestamp so both adapters agree.
    """
    repositories: tuple[ConversationRepository, ...] = (
        InMemoryConversationRepository(),
        conversation_pg_repo,
    )
    for repository in repositories:
        service = create_conversation_service(repository)
        created = service.create(knowledge_base_id="kb-1")
        original = created.updated_at

        appended = service.append_messages(
            created.id,
            [ConversationMessage(id="m-1", role="user", content="hello")],
        )

        assert appended.updated_at > original, (
            f"{type(repository).__name__} did not advance updated_at"
        )
        reloaded = repository.get(created.id)
        assert reloaded is not None
        assert reloaded.updated_at == appended.updated_at


class _AlwaysLosesTheRace(InMemoryConversationRepository):
    """A repository whose ``save`` never wins the CAS.

    Stands in for a pathologically contended row. The service's retry loop is
    bounded precisely so this fails loudly instead of spinning forever, and
    the exception it ends on is the one caller-visible artefact of
    conversations.06 -- ``api.dependencies`` turns it into a 409.
    """

    def __init__(self) -> None:
        super().__init__()
        self.save_attempts = 0

    def save(
        self, conversation: Conversation, *, expected_updated_at: datetime
    ) -> Conversation:
        self.save_attempts += 1
        raise ConversationConcurrentModificationError(conversation.id)


def test_append_gives_up_after_the_retry_budget_instead_of_spinning() -> None:
    """``append_messages`` retries a lost race because appending is a pure
    merge, but the loop is bounded at ``MAX_APPEND_ATTEMPTS``. On a row that
    never lets a write land it must surface the typed error -- the "reload and
    retry" signal the shared contract defines -- not loop forever and not
    raise something the gateway would turn into a 500.
    """
    repository = _AlwaysLosesTheRace()
    service = create_conversation_service(repository)
    conversation = service.create(knowledge_base_id="kb-1")

    with pytest.raises(ConversationConcurrentModificationError):
        service.append_messages(
            conversation.id, [ConversationMessage(id="m-1", role="user", content="hi")]
        )

    assert repository.save_attempts == MAX_APPEND_ATTEMPTS
