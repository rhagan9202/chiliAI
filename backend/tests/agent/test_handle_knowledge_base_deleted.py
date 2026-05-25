"""handle_knowledge_base_deleted retries cascade on pending_cleanup events."""

from __future__ import annotations

from unittest.mock import MagicMock

from agent.coordinator import handle_knowledge_base_deleted
from events.types import KnowledgeBaseDeletedEvent
from storage.adapters.in_memory import InMemoryObjectStore


def test_handler_does_nothing_when_cleanup_not_pending() -> None:
    graph_service = MagicMock()
    vector_service = MagicMock()
    raw_record_store = MagicMock()
    repository = MagicMock()

    event = KnowledgeBaseDeletedEvent(knowledge_base_id="kb-1", cleanup_pending=False)
    handle_knowledge_base_deleted(
        event,
        graph_service=graph_service,
        vector_service=vector_service,
        raw_record_store=raw_record_store,
        kb_repository=repository,
    )
    graph_service.delete_knowledge_base.assert_not_called()
    vector_service.delete_knowledge_base.assert_not_called()
    raw_record_store.delete_by_kb.assert_not_called()
    repository.delete.assert_not_called()


def test_handler_retries_cascade_when_pending() -> None:
    graph_service = MagicMock()
    vector_service = MagicMock()
    raw_record_store = MagicMock()
    repository = MagicMock()
    object_store = MagicMock()
    object_store.list_keys.return_value = [
        "knowledgebases/kb-1/documents/doc-1/source",
        "knowledgebases/kb-1/documents/doc-2/source",
    ]

    event = KnowledgeBaseDeletedEvent(knowledge_base_id="kb-1", cleanup_pending=True)
    handle_knowledge_base_deleted(
        event,
        graph_service=graph_service,
        vector_service=vector_service,
        raw_record_store=raw_record_store,
        kb_repository=repository,
        object_store=object_store,
    )
    graph_service.delete_knowledge_base.assert_called_once_with("kb-1")
    vector_service.delete_knowledge_base.assert_called_once_with("kb-1")
    raw_record_store.delete_by_kb.assert_called_once_with("kb-1")
    object_store.list_keys.assert_called_once_with("knowledgebases/kb-1/")
    assert object_store.delete.call_count == 2
    object_store.delete.assert_any_call("knowledgebases/kb-1/documents/doc-1/source")
    object_store.delete.assert_any_call("knowledgebases/kb-1/documents/doc-2/source")
    repository.delete.assert_called_once_with("kb-1")


def test_handler_retries_cascade_when_pending_no_object_store() -> None:
    """object_store defaults to None for backward compatibility."""
    graph_service = MagicMock()
    vector_service = MagicMock()
    raw_record_store = MagicMock()
    repository = MagicMock()

    event = KnowledgeBaseDeletedEvent(knowledge_base_id="kb-1", cleanup_pending=True)
    handle_knowledge_base_deleted(
        event,
        graph_service=graph_service,
        vector_service=vector_service,
        raw_record_store=raw_record_store,
        kb_repository=repository,
        # object_store omitted — backward compat
    )
    graph_service.delete_knowledge_base.assert_called_once_with("kb-1")
    vector_service.delete_knowledge_base.assert_called_once_with("kb-1")
    raw_record_store.delete_by_kb.assert_called_once_with("kb-1")
    repository.delete.assert_called_once_with("kb-1")


def test_handler_object_store_cleanup_uses_in_memory_store() -> None:
    """Verify cleanup actually removes keys from a real InMemoryObjectStore."""
    graph_service = MagicMock()
    vector_service = MagicMock()
    raw_record_store = MagicMock()
    repository = MagicMock()
    object_store = InMemoryObjectStore()

    # Pre-populate with two objects under the KB prefix.
    object_store.put_bytes(
        "knowledgebases/kb-1/documents/doc-1/source",
        b"content-1",
        media_type="application/json",
    )
    object_store.put_bytes(
        "knowledgebases/kb-1/documents/doc-2/source",
        b"content-2",
        media_type="application/json",
    )
    assert len(object_store.list_keys("knowledgebases/kb-1/")) == 2

    event = KnowledgeBaseDeletedEvent(knowledge_base_id="kb-1", cleanup_pending=True)
    handle_knowledge_base_deleted(
        event,
        graph_service=graph_service,
        vector_service=vector_service,
        raw_record_store=raw_record_store,
        kb_repository=repository,
        object_store=object_store,
    )

    assert object_store.list_keys("knowledgebases/kb-1/") == [], (
        "All object-store keys under the KB prefix should be deleted."
    )
