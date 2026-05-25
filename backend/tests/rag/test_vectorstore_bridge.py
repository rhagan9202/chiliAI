"""Tests for the production context retriever bridge."""

from __future__ import annotations

from rag.adapters.protocols import ContextRetrieverProtocol
from api._rag_bridges import ServiceContextRetriever
from vectorstore.models import VectorRecord
from vectorstore.service_models import (
    VectorDeleteResponse,
    VectorIndexReceipt,
    VectorIndexRequest,
    VectorSearchMatch,
    VectorSearchRequest,
    VectorSearchResponse,
)


class _RecordingVectorService:
    """In-memory fake conforming to `VectorServiceProtocol`."""

    def __init__(self, response: VectorSearchResponse) -> None:
        self._response = response
        self.search_requests: list[VectorSearchRequest] = []

    def index(self, request: VectorIndexRequest) -> list[VectorIndexReceipt]:
        del request
        return []

    def search(self, request: VectorSearchRequest) -> VectorSearchResponse:
        self.search_requests.append(request)
        return self._response

    def batch_search(
        self, requests: list[VectorSearchRequest]
    ) -> list[VectorSearchResponse]:
        return [self.search(request) for request in requests]

    def get_record(
        self,
        knowledge_base_id: str,
        record_id: str,
    ) -> VectorRecord | None:
        del knowledge_base_id, record_id
        return None

    def count(self, knowledge_base_id: str) -> int:
        del knowledge_base_id
        return 0

    def delete_record(self, knowledge_base_id: str, record_id: str) -> bool:
        del knowledge_base_id, record_id
        return False

    def delete_knowledge_base(self, knowledge_base_id: str) -> VectorDeleteResponse:
        return VectorDeleteResponse(knowledge_base_id=knowledge_base_id, deleted_count=0)


def _make_response(
    *,
    matches: list[VectorSearchMatch],
    knowledge_base_ids: list[str] | None = None,
    query_dimension: int = 3,
) -> VectorSearchResponse:
    return VectorSearchResponse(
        knowledge_base_ids=knowledge_base_ids if knowledge_base_ids is not None else ["kb-1"],
        query_dimension=query_dimension,
        matches=matches,
    )


def test_service_context_retriever_satisfies_protocol() -> None:
    service = _RecordingVectorService(_make_response(matches=[]))

    retriever: ContextRetrieverProtocol = ServiceContextRetriever(service)

    assert isinstance(retriever, ContextRetrieverProtocol)


def test_service_context_retriever_builds_request_and_maps_matches() -> None:
    matches = [
        VectorSearchMatch(
            record_id="record-1",
            content_id="content-1",
            score=0.92,
            content="Claim 42 duplicate billing",
            metadata={"document_id": "doc-7", "chunk_index": 3},
        ),
        VectorSearchMatch(
            record_id="record-2",
            content_id="content-2",
            score=0.41,
            content="Provider enrollment guidance",
            metadata={"document_id": "doc-9"},
        ),
    ]
    service = _RecordingVectorService(_make_response(matches=matches))
    retriever = ServiceContextRetriever(service)

    items = retriever.retrieve(
        knowledge_base_id="kb-42",
        query_vector=[0.1, 0.2, 0.3],
        limit=5,
        filters={"document_id": "doc-7"},
    )

    assert [item.record_id for item in items] == ["record-1", "record-2"]
    assert items[0].score == 0.92
    assert items[0].content == "Claim 42 duplicate billing"
    assert items[0].metadata == {"document_id": "doc-7", "chunk_index": 3}
    assert items[1].score == 0.41
    assert items[1].metadata == {"document_id": "doc-9"}

    assert len(service.search_requests) == 1
    forwarded = service.search_requests[0]
    assert forwarded.knowledge_base_ids == ["kb-42"]
    assert forwarded.query_vector == [0.1, 0.2, 0.3]
    assert forwarded.limit == 5
    assert forwarded.filters == {"document_id": "doc-7", "embedding_channel": "text"}


def test_service_context_retriever_returns_empty_list_when_no_matches() -> None:
    service = _RecordingVectorService(_make_response(matches=[]))
    retriever = ServiceContextRetriever(service)

    items = retriever.retrieve(
        knowledge_base_id="kb-1",
        query_vector=[1.0, 0.0],
        limit=10,
        filters={},
    )

    assert items == []


def test_service_context_retriever_substitutes_empty_string_when_match_content_missing() -> None:
    matches = [
        VectorSearchMatch(
            record_id="record-1",
            content_id="content-1",
            score=0.5,
            content=None,
            metadata={},
        ),
    ]
    service = _RecordingVectorService(_make_response(matches=matches))
    retriever = ServiceContextRetriever(service)

    items = retriever.retrieve(
        knowledge_base_id="kb-1",
        query_vector=[0.5, 0.5],
        limit=1,
        filters={},
    )

    assert len(items) == 1
    assert items[0].content == ""
    assert items[0].metadata == {}


def test_service_context_retriever_does_not_share_metadata_dict_with_match() -> None:
    metadata: dict[str, str | int | float | bool] = {"document_id": "doc-1"}
    matches = [
        VectorSearchMatch(
            record_id="record-1",
            content_id="content-1",
            score=0.7,
            content="snippet",
            metadata=metadata,
        ),
    ]
    service = _RecordingVectorService(_make_response(matches=matches))
    retriever = ServiceContextRetriever(service)

    items = retriever.retrieve(
        knowledge_base_id="kb-1",
        query_vector=[0.1, 0.2],
        limit=1,
        filters={},
    )

    items[0].metadata["mutated"] = "yes"
    assert "mutated" not in matches[0].metadata
