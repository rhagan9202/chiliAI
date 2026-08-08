"""Tests for the production context retriever bridge."""

from __future__ import annotations

from rag.adapters.protocols import ContextRetrieverProtocol
from api._rag_bridges import ServiceContextRetriever
from events.adapters.in_memory import InMemoryEventBus
from shared.provenance import (
    EMBEDDING_CHANNEL_KEY,
    EMBEDDING_CHANNEL_TEXT,
    SOURCE_ID_KEY,
    SOURCE_KIND_KEY,
    SOURCE_KIND_RECORD,
)
from vectorstore.adapters.in_memory import InMemoryVectorStore
from vectorstore.models import VectorRecord
from vectorstore.service import VectorService
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

    def delete_by_source_document(
        self,
        knowledge_base_id: str,
        source_document_id: str,
    ) -> VectorDeleteResponse:
        del source_document_id
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


def _record_shaped_vector(kb: str, content_id: str) -> VectorRecord:
    """A vector shaped the way `agent.coordinator` indexes record-derived rows."""
    return VectorRecord(
        id=f"record:{kb}:{content_id}",
        knowledge_base_id=kb,
        content_id=content_id,
        embedding=[0.1, 0.2, 0.3],
        content="id=claim:LCLM00014\ntype=claim\namount=1400.0",
        metadata={
            SOURCE_KIND_KEY: SOURCE_KIND_RECORD,
            SOURCE_ID_KEY: content_id,
            "entity_type": "claim",
            EMBEDDING_CHANNEL_KEY: EMBEDDING_CHANNEL_TEXT,
        },
    )


def test_record_derived_vectors_are_retrievable_through_rag() -> None:
    """The defect this file's other tests could not see.

    `ServiceContextRetriever` filters every search on the text channel, and the
    records indexing path never stamped it — so a knowledge base ingested from
    records retrieved **nothing**, with no error anywhere. The existing test
    above asserts the forwarded filter *contains* `embedding_channel: text`,
    which was true and useless: it never checked that an indexed vector could
    satisfy it.

    This one runs a real store so the filter is applied rather than recorded.
    """
    store = InMemoryVectorStore()
    store.upsert_records("kb-records", [_record_shaped_vector("kb-records", "claim:LCLM00014")])
    retriever = ServiceContextRetriever(
        VectorService(store, event_bus=InMemoryEventBus())
    )

    items = retriever.retrieve(
        knowledge_base_id="kb-records",
        query_vector=[0.1, 0.2, 0.3],
        limit=5,
        filters={},
    )

    assert [item.content_id for item in items] == ["claim:LCLM00014"]
    assert items[0].content.startswith("id=claim:LCLM00014")


def test_a_vector_without_the_channel_is_invisible_to_rag() -> None:
    """Pins *why* the stamp matters, so removing it fails loudly.

    This is the pre-fix state reproduced deliberately: identical vector, same
    query, channel key absent. It retrieves nothing — which is what every
    record-ingested knowledge base did.
    """
    unstamped = _record_shaped_vector("kb-unstamped", "claim:LCLM00014")
    unstamped.metadata.pop(EMBEDDING_CHANNEL_KEY)
    store = InMemoryVectorStore()
    store.upsert_records("kb-unstamped", [unstamped])
    retriever = ServiceContextRetriever(
        VectorService(store, event_bus=InMemoryEventBus())
    )

    items = retriever.retrieve(
        knowledge_base_id="kb-unstamped",
        query_vector=[0.1, 0.2, 0.3],
        limit=5,
        filters={},
    )

    assert items == []
