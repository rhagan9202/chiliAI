"""handle_knowledge_base_deleted retries cascade on pending_cleanup events."""

from __future__ import annotations

from unittest.mock import MagicMock

from agent.coordinator import handle_knowledge_base_deleted
from events.types import KnowledgeBaseDeletedEvent


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

    event = KnowledgeBaseDeletedEvent(knowledge_base_id="kb-1", cleanup_pending=True)
    handle_knowledge_base_deleted(
        event,
        graph_service=graph_service,
        vector_service=vector_service,
        raw_record_store=raw_record_store,
        kb_repository=repository,
    )
    graph_service.delete_knowledge_base.assert_called_once_with("kb-1")
    vector_service.delete_knowledge_base.assert_called_once_with("kb-1")
    raw_record_store.delete_by_kb.assert_called_once_with("kb-1")
    repository.delete.assert_called_once_with("kb-1")
