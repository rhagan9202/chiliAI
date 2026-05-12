"""Live knowledge-base metadata projection helpers.

The API owns the lightweight KB/document metadata projection, while graph
contents and raw artifacts remain behind their module protocols. These helpers
merge persisted KB metadata with live graph/object-store signals and write the
result back through ``KnowledgeBaseRepository`` so list/detail/SSE reads stay
consistent after API reloads.
"""

from __future__ import annotations

from api._kb_store import DocumentRecord, KnowledgeBaseRepository
from graph.models import GraphMetrics
from graph.protocols import GraphServiceProtocol
from shared.types import KnowledgeBase
from storage.protocols import ObjectStore

__all__ = [
    "document_status_for_knowledge_base",
    "project_knowledge_base",
]


def project_knowledge_base(
    knowledge_base: KnowledgeBase,
    repository: KnowledgeBaseRepository,
    graph_service: GraphServiceProtocol,
    object_store: ObjectStore,
) -> KnowledgeBase:
    """Return and persist the current live projection for a KB record."""

    metrics = _safe_compute_graph_metrics(knowledge_base.id, graph_service)
    status = _derive_status(
        knowledge_base,
        metrics=metrics,
        graph_build_complete=_has_completed_graph_update(knowledge_base, object_store),
    )
    projected = repository.update_summary(
        knowledge_base.id,
        status=status,
        entity_count=metrics.entity_count if metrics is not None else None,
        relationship_count=metrics.relationship_count if metrics is not None else None,
    )
    return projected if projected is not None else knowledge_base


def document_status_for_knowledge_base(
    record: DocumentRecord,
    knowledge_base: KnowledgeBase,
    repository: KnowledgeBaseRepository,
) -> str:
    """Return and persist the document status implied by the KB projection."""

    status = record.status
    if knowledge_base.status == "ready" and status in {"pending", "registered", "building"}:
        status = "ready"
    elif knowledge_base.status == "building" and status in {"pending", "registered"}:
        status = "building"

    if status != record.status:
        repository.update_document_status(record.knowledge_base_id, record.id, status)
    return status


def _derive_status(
    knowledge_base: KnowledgeBase,
    *,
    metrics: GraphMetrics | None,
    graph_build_complete: bool,
) -> str:
    if knowledge_base.status in {"archived", "error"}:
        return knowledge_base.status
    if (
        graph_build_complete
        or (metrics is not None and (metrics.entity_count > 0 or metrics.relationship_count > 0))
    ):
        return "ready"
    if knowledge_base.document_count > 0 and knowledge_base.status == "active":
        return "building"
    return knowledge_base.status


def _safe_compute_graph_metrics(
    knowledge_base_id: str,
    graph_service: GraphServiceProtocol,
) -> GraphMetrics | None:
    try:
        return graph_service.compute_metrics(knowledge_base_id)
    except Exception:  # noqa: BLE001 - metadata reads should survive graph outages
        return None


def _has_completed_graph_update(
    knowledge_base: KnowledgeBase,
    object_store: ObjectStore,
) -> bool:
    """Return true once every registered document reached graph update output."""

    if knowledge_base.document_count <= 0:
        return False
    try:
        graph_update_keys = object_store.list_keys(
            f"knowledgebases/{knowledge_base.id}/graph_updates/"
        )
    except Exception:  # noqa: BLE001 - metadata reads should survive storage outages
        return False
    artifact_keys = [
        key for key in graph_update_keys
        if key.endswith(".json") and not key.endswith(".meta.json")
    ]
    return len(artifact_keys) >= knowledge_base.document_count
