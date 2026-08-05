"""Workflow-facing adapter for the registered RAG query capability."""

from __future__ import annotations

from collections.abc import Sequence

from capabilities.models import CapabilityExecutionEnvelope, JsonValue
from capabilities.service import CapabilityRegistryService
from rag.service_models import MetadataValue, RagQueryRequest
from rag.protocols import RagServiceProtocol

RAG_QUERY_CAPABILITY_ID = "rag.query"


def execute_rag_query_capability(
    *,
    rag_service: RagServiceProtocol,
    capability_registry: CapabilityRegistryService,
    actor_roles: Sequence[str],
    knowledge_base_ids: list[str],
    question: str,
    filters: dict[str, MetadataValue] | None = None,
    domain_name: str | None = None,
    environment_tag: str | None = None,
    include_graph_context: bool = True,
) -> CapabilityExecutionEnvelope:
    """Authorize and execute the `rag.query` capability for workflow callers."""

    authorized = capability_registry.authorize(
        RAG_QUERY_CAPABILITY_ID,
        actor_roles=actor_roles,
        domain_name=domain_name,
        environment_tag=environment_tag,
    )
    if not authorized.success:
        return authorized

    try:
        response = rag_service.answer(
            RagQueryRequest(
                knowledge_base_ids=knowledge_base_ids,
                question=question,
                include_graph_context=include_graph_context,
                filters=filters or {},
            )
        )
    except Exception as exc:
        return capability_registry.execution_failure(
            RAG_QUERY_CAPABILITY_ID,
            error_code="rag_query_failed",
            error_message=str(exc),
        )

    citation_refs: list[dict[str, JsonValue]] = [
        {
            "record_id": citation.record_id,
            "content_id": citation.content_id,
            "document_id": citation.document_id,
            "chunk_index": citation.chunk_index,
        }
        for citation in response.citations
    ]
    return capability_registry.execution_success(
        RAG_QUERY_CAPABILITY_ID,
        output={
            "answer": response.answer,
            "provider": response.provider,
            "model_name": response.model_name,
            "citation_refs": citation_refs,
        },
    )


__all__ = ["RAG_QUERY_CAPABILITY_ID", "execute_rag_query_capability"]
