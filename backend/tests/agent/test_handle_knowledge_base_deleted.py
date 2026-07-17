"""handle_knowledge_base_deleted replays the full cascade on pending_cleanup events."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock

import pytest

from agent.coordinator import handle_knowledge_base_deleted
from events.types import KnowledgeBaseDeletedEvent
from knowledgebases.cleanup import KbDeletionStores

_STORE_FIELDS = [
    "graph_service",
    "vector_service",
    "raw_record_store",
    "derived_signal_store",
    "risk_history_writer",
    "observation_writer",
    "alert_history_writer",
    "entity_metric_repository",
    "conversation_repository",
    "case_repository",
    "policy_item_repository",
    "evidence_pack_repository",
    "scorecard_run_repository",
    "document_status_store",
    "object_store",
    "gnn_cluster_store",
]

# Stores whose deletion goes through `delete_by_kb`.
_DELETE_BY_KB_FIELDS = [
    "raw_record_store",
    "derived_signal_store",
    "risk_history_writer",
    "observation_writer",
    "alert_history_writer",
    "entity_metric_repository",
    "conversation_repository",
    "case_repository",
    "policy_item_repository",
    "evidence_pack_repository",
    "scorecard_run_repository",
    "document_status_store",
    "gnn_cluster_store",
]


def _mock_stores() -> tuple[KbDeletionStores, dict[str, MagicMock]]:
    mocks = {field: MagicMock() for field in _STORE_FIELDS}
    mocks["object_store"].list_keys.return_value = []
    # The worker bundle carries no API-owned alert projection store; the
    # cascade skips that step (see knowledgebases.cleanup.KbDeletionStores).
    return (
        cast(KbDeletionStores, SimpleNamespace(**mocks, alert_projection_store=None)),
        mocks,
    )


def test_handler_does_nothing_when_cleanup_not_pending() -> None:
    stores, mocks = _mock_stores()
    kb_repository = MagicMock()
    event = KnowledgeBaseDeletedEvent(knowledge_base_id="kb-1", cleanup_pending=False)

    handle_knowledge_base_deleted(
        event,
        kb_deletion_stores=stores,
        kb_repository=kb_repository,  # type: ignore[arg-type]
    )

    mocks["graph_service"].delete_knowledge_base.assert_not_called()
    mocks["raw_record_store"].delete_by_kb.assert_not_called()
    kb_repository.delete.assert_not_called()


def test_handler_replays_full_cascade_then_deletes_metadata() -> None:
    stores, mocks = _mock_stores()
    kb_repository = MagicMock()
    event = KnowledgeBaseDeletedEvent(knowledge_base_id="kb-1", cleanup_pending=True)

    handle_knowledge_base_deleted(
        event,
        kb_deletion_stores=stores,
        kb_repository=kb_repository,  # type: ignore[arg-type]
    )

    mocks["graph_service"].delete_knowledge_base.assert_called_once_with("kb-1")
    mocks["vector_service"].delete_knowledge_base.assert_called_once_with("kb-1")
    mocks["object_store"].list_keys.assert_called_once_with("knowledgebases/kb-1/")
    for field in _DELETE_BY_KB_FIELDS:
        mocks[field].delete_by_kb.assert_called_once_with("kb-1")
    # KB metadata deleted last, after every store is purged.
    kb_repository.delete.assert_called_once_with("kb-1")


def test_handler_propagates_failure_and_skips_metadata_delete() -> None:
    """A failing step raises (DLQ retries the idempotent cascade); KB metadata stays."""
    stores, mocks = _mock_stores()
    mocks["risk_history_writer"].delete_by_kb.side_effect = RuntimeError("db down")
    kb_repository = MagicMock()
    event = KnowledgeBaseDeletedEvent(knowledge_base_id="kb-1", cleanup_pending=True)

    with pytest.raises(RuntimeError, match="db down"):
        handle_knowledge_base_deleted(
            event,
            kb_deletion_stores=stores,
            kb_repository=kb_repository,  # type: ignore[arg-type]
        )

    # Failure occurred before the metadata delete — KB is retained for retry.
    kb_repository.delete.assert_not_called()


def test_build_worker_dependencies_wires_kb_cleanup() -> None:
    """run_worker passes deps.kb_deletion_stores/kb_repository — so the handler is wired.

    The dispatch guard previously short-circuited because these were never built;
    this asserts the worker now assembles them (the wiring fix).
    """
    from agent.coordinator import build_worker_dependencies

    deps = build_worker_dependencies()
    assert isinstance(deps.kb_deletion_stores, KbDeletionStores)
    assert deps.kb_repository is not None
    # The bundle carries every per-KB store the cascade purges.
    for field in _STORE_FIELDS:
        assert getattr(deps.kb_deletion_stores, field) is not None
