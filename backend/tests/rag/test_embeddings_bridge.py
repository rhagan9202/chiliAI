"""Tests for the production query embedder bridge."""

from __future__ import annotations

import pytest

from embeddings.service_models import (
    EmbeddedItem,
    EmbedRequest,
    EmbedResponse,
)
from api._rag_bridges import ServiceQueryEmbedder
from rag.adapters.protocols import QueryEmbedderProtocol
from rag.exceptions import RagConfigurationError


class _RecordingEmbeddingsService:
    """In-memory fake conforming to `EmbeddingsServiceProtocol`."""

    def __init__(self, response: EmbedResponse) -> None:
        self._response = response
        self.requests: list[EmbedRequest] = []

    def embed(self, request: EmbedRequest) -> EmbedResponse:
        self.requests.append(request)
        return self._response


def _make_response(
    *,
    items: list[EmbeddedItem],
    dimensions: int = 3,
    model_name: str = "fake-model",
    request_id: str = "req-1",
) -> EmbedResponse:
    return EmbedResponse(
        request_id=request_id,
        model_name=model_name,
        dimensions=dimensions,
        items=items,
    )


def test_service_query_embedder_satisfies_protocol() -> None:
    service = _RecordingEmbeddingsService(
        _make_response(items=[EmbeddedItem(content_id="rag-query", vector=[0.1, 0.2, 0.3])])
    )

    embedder: QueryEmbedderProtocol = ServiceQueryEmbedder(service)

    assert isinstance(embedder, QueryEmbedderProtocol)


def test_service_query_embedder_forwards_call_and_returns_vector() -> None:
    service = _RecordingEmbeddingsService(
        _make_response(items=[EmbeddedItem(content_id="rag-query", vector=[0.1, 0.2, 0.3])])
    )
    embedder = ServiceQueryEmbedder(service)

    vector = embedder.embed_query(knowledge_base_id="kb-42", question="What is fraud?")

    assert vector == [0.1, 0.2, 0.3]
    assert len(service.requests) == 1
    forwarded = service.requests[0]
    assert forwarded.knowledge_base_id == "kb-42"
    assert len(forwarded.submissions) == 1
    assert forwarded.submissions[0].content == "What is fraud?"
    assert forwarded.submissions[0].content_id == "rag-query"


def test_service_query_embedder_uses_configured_model_name() -> None:
    service = _RecordingEmbeddingsService(
        _make_response(
            items=[EmbeddedItem(content_id="rag-query", vector=[1.0])],
            dimensions=1,
            model_name="custom-model",
        )
    )
    embedder = ServiceQueryEmbedder(service, model_name="custom-model")

    embedder.embed_query(knowledge_base_id="kb-1", question="hello")

    assert service.requests[0].model_name == "custom-model"


def test_service_query_embedder_uses_configured_content_id() -> None:
    service = _RecordingEmbeddingsService(
        _make_response(items=[EmbeddedItem(content_id="probe", vector=[0.5])], dimensions=1)
    )
    embedder = ServiceQueryEmbedder(service, content_id="probe")

    embedder.embed_query(knowledge_base_id="kb-1", question="ping")

    assert service.requests[0].submissions[0].content_id == "probe"


def test_service_query_embedder_raises_when_items_empty() -> None:
    service = _RecordingEmbeddingsService(_make_response(items=[]))
    embedder = ServiceQueryEmbedder(service)

    with pytest.raises(RagConfigurationError):
        embedder.embed_query(knowledge_base_id="kb-1", question="What is fraud?")


def test_service_query_embedder_raises_when_first_vector_empty() -> None:
    service = _RecordingEmbeddingsService(
        _make_response(items=[EmbeddedItem(content_id="rag-query", vector=[])])
    )
    embedder = ServiceQueryEmbedder(service)

    with pytest.raises(RagConfigurationError):
        embedder.embed_query(knowledge_base_id="kb-1", question="What is fraud?")


def test_service_query_embedder_rejects_blank_question() -> None:
    service = _RecordingEmbeddingsService(
        _make_response(items=[EmbeddedItem(content_id="rag-query", vector=[0.1])], dimensions=1)
    )
    embedder = ServiceQueryEmbedder(service)

    with pytest.raises(RagConfigurationError):
        embedder.embed_query(knowledge_base_id="kb-1", question="   ")
    assert service.requests == []
