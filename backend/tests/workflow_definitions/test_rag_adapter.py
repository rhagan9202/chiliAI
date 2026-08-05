from __future__ import annotations

from collections.abc import Iterator

from capabilities.service import create_default_capability_registry_service
from rag.service_models import (
    RagAnswer,
    RagCitation,
    RagQueryRequest,
    RagQueryResponse,
    RagStreamChunk,
)
from workflow_definitions.rag_adapter import execute_rag_query_capability


class _RagService:
    def __init__(self) -> None:
        self.requests: list[RagQueryRequest] = []

    def answer(self, request: RagQueryRequest) -> RagQueryResponse:
        self.requests.append(request)
        return RagQueryResponse(
            request_id="rag-request-1",
            knowledge_base_ids=request.knowledge_base_ids,
            answer="Provider billing exceeds peer context.",
            provider="test-provider",
            model_name="test-model",
            citations=[
                RagCitation(
                    record_id="record-1",
                    content_id="content-1",
                    document_id="claims.csv",
                    chunk_index=2,
                    score=0.91,
                    snippet="Repeated high-intensity claims.",
                )
            ],
        )

    def answer_question(
        self,
        *,
        knowledge_base_ids: list[str],
        question: str,
    ) -> RagAnswer:
        raise NotImplementedError

    def stream_answer(self, request: RagQueryRequest) -> Iterator[RagStreamChunk]:
        raise NotImplementedError


def test_execute_rag_query_capability_returns_auditable_citation_envelope() -> None:
    rag_service = _RagService()
    registry = create_default_capability_registry_service()

    envelope = execute_rag_query_capability(
        rag_service=rag_service,
        capability_registry=registry,
        actor_roles=["viewer"],
        knowledge_base_ids=["kb-1"],
        question="Why is this alert risky?",
        filters={"alert_id": "alert-1", "entity_id": "provider-204"},
        domain_name="medicare_fraud",
        environment_tag="production",
    )

    assert envelope.success is True
    assert envelope.audit_required is True
    assert envelope.output == {
        "answer": "Provider billing exceeds peer context.",
        "provider": "test-provider",
        "model_name": "test-model",
        "citation_refs": [
            {
                "record_id": "record-1",
                "content_id": "content-1",
                "document_id": "claims.csv",
                "chunk_index": 2,
            }
        ],
    }
    assert len(rag_service.requests) == 1
    request = rag_service.requests[0]
    assert request.knowledge_base_ids == ["kb-1"]
    assert request.question == "Why is this alert risky?"
    assert request.filters == {"alert_id": "alert-1", "entity_id": "provider-204"}


def test_execute_rag_query_capability_denies_actor_without_viewer_role() -> None:
    rag_service = _RagService()
    registry = create_default_capability_registry_service()

    envelope = execute_rag_query_capability(
        rag_service=rag_service,
        capability_registry=registry,
        actor_roles=["guest"],
        knowledge_base_ids=["kb-1"],
        question="Why is this alert risky?",
        domain_name="medicare_fraud",
        environment_tag="production",
    )

    assert envelope.success is False
    assert envelope.error_code == "capability_role_denied"
    assert envelope.audit_required is True
    assert rag_service.requests == []
