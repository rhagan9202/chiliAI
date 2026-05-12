"""Tests for live knowledge-base metadata projection helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from api._kb_projection import (
    document_status_for_knowledge_base,
    project_knowledge_base,
)
from api._kb_store import DocumentRecord, InMemoryKnowledgeBaseRepository
from graph.models import GraphMetrics
from storage.adapters.in_memory import InMemoryObjectStore
from shared.types import KnowledgeBase


class _GraphService:
    """Minimal graph service test double for KB projection tests."""

    def __init__(self, metrics: GraphMetrics | None, *, fail: bool = False) -> None:
        self._metrics = metrics
        self._fail = fail

    def compute_metrics(self, knowledge_base_id: str) -> GraphMetrics:
        """Return configured metrics or simulate a graph outage."""

        del knowledge_base_id
        if self._fail:
            raise RuntimeError("graph unavailable")
        if self._metrics is None:
            return GraphMetrics(entity_count=0, relationship_count=0, avg_degree=0.0)
        return self._metrics


def _knowledge_base(
    *,
    status: str = "active",
    document_count: int = 1,
    entity_count: int = 0,
    relationship_count: int = 0,
) -> KnowledgeBase:
    return KnowledgeBase(
        id="kb-1",
        name="KB",
        description="Knowledge base",
        document_count=document_count,
        entity_count=entity_count,
        relationship_count=relationship_count,
        status=status,  # type: ignore[arg-type]
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _repository_with(knowledge_base: KnowledgeBase) -> InMemoryKnowledgeBaseRepository:
    repository = InMemoryKnowledgeBaseRepository()
    repository.create(knowledge_base)
    return repository


def test_project_knowledge_base_ready_when_graph_has_metrics() -> None:
    knowledge_base = _knowledge_base(status="active", document_count=1)
    repository = _repository_with(knowledge_base)
    graph_service = _GraphService(
        GraphMetrics(entity_count=12, relationship_count=4, avg_degree=1.5)
    )

    projected = project_knowledge_base(
        knowledge_base,
        repository,
        graph_service,  # type: ignore[arg-type]
        InMemoryObjectStore(),
    )

    assert projected.status == "ready"
    assert projected.entity_count == 12
    assert projected.relationship_count == 4
    assert repository.get("kb-1") == projected


def test_project_knowledge_base_ready_when_graph_artifacts_exist() -> None:
    knowledge_base = _knowledge_base(status="active", document_count=2)
    repository = _repository_with(knowledge_base)
    object_store = InMemoryObjectStore()
    object_store.put_bytes(
        "knowledgebases/kb-1/graph_updates/doc-1.json",
        b"{}",
        media_type="application/json",
    )
    object_store.put_bytes(
        "knowledgebases/kb-1/graph_updates/doc-2.json",
        b"{}",
        media_type="application/json",
    )
    object_store.put_bytes(
        "knowledgebases/kb-1/graph_updates/doc-2.meta.json",
        b"{}",
        media_type="application/json",
    )

    projected = project_knowledge_base(
        knowledge_base,
        repository,
        _GraphService(GraphMetrics(entity_count=0, relationship_count=0, avg_degree=0.0)),  # type: ignore[arg-type]
        object_store,
    )

    assert projected.status == "ready"


def test_project_knowledge_base_preserves_terminal_statuses() -> None:
    for status in ("archived", "error"):
        knowledge_base = _knowledge_base(status=status, document_count=1)
        repository = _repository_with(knowledge_base)

        projected = project_knowledge_base(
            knowledge_base,
            repository,
            _GraphService(GraphMetrics(entity_count=9, relationship_count=9, avg_degree=2.0)),  # type: ignore[arg-type]
            InMemoryObjectStore(),
        )

        assert projected.status == status


def test_project_knowledge_base_degrades_when_dependencies_fail() -> None:
    class _FailingObjectStore(InMemoryObjectStore):
        def list_keys(self, prefix: str) -> list[str]:
            del prefix
            raise RuntimeError("storage unavailable")

    knowledge_base = _knowledge_base(status="active", document_count=1)
    repository = _repository_with(knowledge_base)

    projected = project_knowledge_base(
        knowledge_base,
        repository,
        _GraphService(None, fail=True),  # type: ignore[arg-type]
        _FailingObjectStore(),
    )

    assert projected.status == "building"
    assert projected.entity_count == 0
    assert projected.relationship_count == 0


def test_document_status_tracks_knowledge_base_status() -> None:
    repository = _repository_with(_knowledge_base(status="active"))
    record = repository.add_document(
        DocumentRecord(
            id="doc-1",
            knowledge_base_id="kb-1",
            filename="claim.txt",
            status="registered",
        )
    )

    building = document_status_for_knowledge_base(
        record,
        _knowledge_base(status="building"),
        repository,
    )
    ready_record = repository.get_document("kb-1", "doc-1")
    assert ready_record is not None
    ready = document_status_for_knowledge_base(
        ready_record,
        _knowledge_base(status="ready"),
        repository,
    )

    assert building == "building"
    assert ready == "ready"
    stored = repository.get_document("kb-1", "doc-1")
    assert stored is not None
    assert stored.status == "ready"
