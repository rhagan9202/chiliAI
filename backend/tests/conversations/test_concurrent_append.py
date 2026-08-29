"""Guard the conversation append read-modify-write against concurrent turns.

``ConversationService.append_messages`` used to be an unguarded ``get ->
model_copy -> save``, and ``PostgresConversationRepository``'s upsert was
``ON CONFLICT ... SET messages = EXCLUDED.messages`` -- a full overwrite. Two
turns landing at once both read the same message list and the second write
discarded the first, with a 200 returned to the analyst whose message
vanished -- no exception raised anywhere. This module proves both adapters
close that race, following the ``ConcurrentModificationError`` contract
established in ``backend/monitoring/README.md`` (monitoring.22) and mirrored
by ``cases`` before it.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable, Generator
from contextlib import contextmanager

import pytest

from config.schema import DatabaseConfig
from conversations.adapters.in_memory import InMemoryConversationRepository
from conversations.adapters.postgres import PostgresConversationRepository
from conversations.adapters.protocols import ConversationRepository
from conversations.models import ConversationMessage
from conversations.service import create_conversation_service
from database.runtime import create_connection_provider


@contextmanager
def _make_repository(repository_name: str) -> Generator[ConversationRepository]:
    """Build a fresh repository of the named backend for one test run.

    The Postgres branch skips (matching ``tests/conversations/conftest.py``'s
    ``database_url`` fixture) when ``DATABASE_URL`` is unset, and truncates
    ``conversations`` on the way out so this test can run repeatedly against
    a persistent dev/test database.
    """
    if repository_name == "in_memory":
        yield InMemoryConversationRepository()
        return
    if repository_name != "postgres":
        raise ValueError(f"Unknown repository_name: {repository_name!r}")
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is not set; skipping conversation integration test.")
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    repository = PostgresConversationRepository(provider)
    try:
        yield repository
    finally:
        with provider.connection() as conn:
            conn.execute("TRUNCATE TABLE conversations")
            conn.commit()
        provider.close()


def _new_conversation(repository: ConversationRepository) -> str:
    service = create_conversation_service(repository)
    return service.create(knowledge_base_id="kb-concurrent-append").id


def _message(text: str) -> ConversationMessage:
    return ConversationMessage(id=f"m-{text}", role="user", content=text)


def _run_concurrently(fn: Callable[[str], None], args: list[str]) -> None:
    """Run ``fn`` for each arg on its own thread and re-raise any failure.

    Errors are captured per-thread rather than left to crash silently in the
    background, so a real guard exception (as opposed to the silent data
    loss this test exists to catch) still fails the test loudly.
    """
    errors: list[BaseException] = []

    def wrapper(arg: str) -> None:
        try:
            fn(arg)
        except BaseException as exc:  # captured for the calling thread to raise
            errors.append(exc)

    threads = [threading.Thread(target=wrapper, args=(arg,)) for arg in args]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    if errors:
        raise errors[0]


@pytest.mark.parametrize(
    "repository_name",
    ["in_memory", pytest.param("postgres", marks=pytest.mark.integration)],
)
def test_two_concurrent_turns_both_survive(
    repository_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """append_messages is get -> model_copy -> save, and the Postgres upsert is
    ON CONFLICT ... SET messages = EXCLUDED.messages -- a full overwrite. Two
    turns landing at once both read the same list and the second write
    discards the first, with a 200 returned to the analyst whose message
    vanished.

    Barrier-synchronised (with a second rendezvous right after the read) so
    both reads land before either write; a sequential test, or one that only
    barriers *before* ``append_messages`` is called, cannot reliably
    reproduce this on the in-memory adapter -- its dict get/set are cheap
    enough that the two threads' full get -> compute -> save sequences can
    run back-to-back without ever actually overlapping, passing on lucky GIL
    scheduling and proving nothing (mirrors the double-rendezvous technique
    in ``tests/cases/test_service.py::test_concurrent_attach_does_not_silently_drop_the_other_alert``).
    """
    with _make_repository(repository_name) as repository:
        service = create_conversation_service(repository)
        conversation_id = _new_conversation(repository)

        read_barrier = threading.Barrier(2)
        original_get = repository.get
        thread_state = threading.local()

        def synced_get(conv_id: str) -> object:
            # Only the first get() per thread is the "both callers read the
            # conversation" step being synchronized. append_messages retries
            # on a lost race by calling get() again; that recovery read must
            # run unsynchronized, or a thread that wins on its first attempt
            # (and so never calls get() a second time) would leave its
            # retrying sibling waiting on a barrier no one else will reach.
            if not getattr(thread_state, "synced", False):
                thread_state.synced = True
                read_barrier.wait(timeout=5)
                result = original_get(conv_id)
                read_barrier.wait(timeout=5)
                return result
            return original_get(conv_id)

        monkeypatch.setattr(repository, "get", synced_get)

        def append(text: str) -> None:
            service.append_messages(conversation_id, [_message(text)])

        _run_concurrently(append, ["from-analyst-a", "from-analyst-b"])

        # Both barrier-synced reads have happened by now; go back to the
        # unwrapped getter so this verification read isn't waiting on a
        # barrier no third thread will reach.
        stored = original_get(conversation_id)
        assert stored is not None
        texts = {m.content for m in stored.messages}
        assert {"from-analyst-a", "from-analyst-b"} <= texts, f"a turn was lost: {texts}"
