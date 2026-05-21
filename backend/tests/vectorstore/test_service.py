"""Tests for the vectorstore service."""

from __future__ import annotations

from events.adapters.in_memory import InMemoryEventBus
from events.types import VectorsIndexedEvent
from storage.adapters.in_memory import InMemoryObjectStore
from storage.models import StoredObjectWriteResult
from vectorstore.adapters.in_memory import InMemoryVectorStore
from vectorstore.exceptions import VectorDimensionMismatchError, VectorStoreError
from vectorstore.models import MetadataValue, VectorMatch, VectorRecord
from vectorstore.service import create_vector_service
from vectorstore.service_models import (
    VectorAuditArtifact,
    VectorDeleteResponse,
    VectorIndexRequest,
    VectorIndexSubmission,
    VectorSearchMatch,
    VectorSearchRequest,
)
import pytest


class _DroppingVectorStore:
    def upsert_records(
        self,
        knowledge_base_id: str,
        records: list[VectorRecord],
    ) -> list[VectorRecord]:
        del knowledge_base_id
        return records[:1]

    def search(
        self,
        knowledge_base_id: str,
        query_vector: list[float],
        limit: int,
        filters: dict[str, MetadataValue] | None = None,
    ) -> list[VectorMatch]:
        del knowledge_base_id, query_vector, limit, filters
        return []

    def get_record(
        self,
        knowledge_base_id: str,
        record_id: str,
    ) -> VectorRecord | None:
        del knowledge_base_id, record_id
        return None

    def count_records(self, knowledge_base_id: str) -> int:
        del knowledge_base_id
        return 0

    def delete_record(self, knowledge_base_id: str, record_id: str) -> bool:
        del knowledge_base_id, record_id
        return False

    def delete_namespace(self, knowledge_base_id: str) -> int:
        del knowledge_base_id
        return 0


class _RecordingVectorStore(InMemoryVectorStore):
    def __init__(self) -> None:
        super().__init__()
        self.upsert_batch_sizes: list[int] = []

    def upsert_records(
        self,
        knowledge_base_id: str,
        records: list[VectorRecord],
    ) -> list[VectorRecord]:
        self.upsert_batch_sizes.append(len(records))
        return super().upsert_records(knowledge_base_id, records)


class _FailingObjectStore(InMemoryObjectStore):
    def put_bytes(
        self,
        key: str,
        content: bytes,
        *,
        media_type: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> StoredObjectWriteResult:
        del key, content, media_type, metadata
        raise RuntimeError("object store unavailable")


class _FailingIndexVectorStore(InMemoryVectorStore):
    def __init__(self, exc: Exception) -> None:
        super().__init__()
        self._exc = exc

    def upsert_records(
        self,
        knowledge_base_id: str,
        records: list[VectorRecord],
    ) -> list[VectorRecord]:
        del knowledge_base_id, records
        raise self._exc


class _FailingSearchVectorStore(InMemoryVectorStore):
    def __init__(self, exc: Exception) -> None:
        super().__init__()
        self._exc = exc

    def search(
        self,
        knowledge_base_id: str,
        query_vector: list[float],
        limit: int,
        filters: dict[str, MetadataValue] | None = None,
    ) -> list[VectorMatch]:
        del knowledge_base_id, query_vector, limit, filters
        raise self._exc


def test_vector_service_indexes_records_and_publishes_event() -> None:
    event_bus = InMemoryEventBus()
    service = create_vector_service(InMemoryVectorStore(), event_bus=event_bus)

    receipts = service.index(
        VectorIndexRequest(
            knowledge_base_id="kb-1",
            submissions=[
                VectorIndexSubmission(
                    content_id="content-1",
                    embedding=[0.1, 0.2, 0.3],
                    content="Policy text",
                )
            ],
        )
    )

    assert len(receipts) == 1
    assert receipts[0].dimension == 3
    assert isinstance(event_bus.published_events[-1], VectorsIndexedEvent)


def test_vector_service_rejects_partial_upsert_results() -> None:
    event_bus = InMemoryEventBus()
    service = create_vector_service(_DroppingVectorStore(), event_bus=event_bus)

    with pytest.raises(VectorStoreError, match="missing records"):
        service.index(
            VectorIndexRequest(
                knowledge_base_id="kb-1",
                submissions=[
                    VectorIndexSubmission(content_id="content-1", embedding=[0.1, 0.2]),
                    VectorIndexSubmission(content_id="content-2", embedding=[0.3, 0.4]),
                ],
            )
        )

    assert event_bus.published_events == []


def test_vector_service_search_returns_best_match() -> None:
    event_bus = InMemoryEventBus()
    service = create_vector_service(InMemoryVectorStore(), event_bus=event_bus)
    service.index(
        VectorIndexRequest(
            knowledge_base_id="kb-1",
            submissions=[
                VectorIndexSubmission(
                    content_id="content-1",
                    embedding=[1.0, 0.0, 0.0],
                    content="Alpha",
                ),
                VectorIndexSubmission(
                    content_id="content-2",
                    embedding=[0.0, 1.0, 0.0],
                    content="Beta",
                ),
            ],
        )
    )

    response = service.search(
        VectorSearchRequest(
            knowledge_base_ids=["kb-1"],
            query_vector=[0.9, 0.1, 0.0],
            limit=1,
        )
    )

    assert len(response.matches) == 1
    assert response.matches[0].content_id == "content-1"


def test_vector_search_match_allows_distance_scores_above_one() -> None:
    match = VectorSearchMatch(
        record_id="record-1",
        content_id="content-1",
        score=2.75,
    )

    assert match.score == 2.75


# ---------------------------------------------------------------------------
# Error-path tests — cover generic Exception and multi-KB branches.
# Adapters raise typed ``VectorDimensionMismatchError`` for dimension issues;
# the service wraps unexpected exceptions (including bare ``ValueError`` from
# the adapter layer) as ``VectorStoreError``.
# ---------------------------------------------------------------------------


def test_vector_index_wraps_generic_exception_as_store_error() -> None:
    service = create_vector_service(
        _FailingIndexVectorStore(RuntimeError("backend unavailable")),
        event_bus=InMemoryEventBus(),
    )
    with pytest.raises(VectorStoreError, match="Failed to index"):
        service.index(
            VectorIndexRequest(
                knowledge_base_id="kb-1",
                submissions=[VectorIndexSubmission(content_id="c1", embedding=[0.1])],
            )
        )


def test_vector_search_wraps_generic_exception_as_store_error() -> None:
    service = create_vector_service(
        _FailingSearchVectorStore(RuntimeError("backend unavailable on search")),
        event_bus=InMemoryEventBus(),
    )
    with pytest.raises(VectorStoreError, match="Failed to search"):
        service.search(
            VectorSearchRequest(knowledge_base_ids=["kb-1"], query_vector=[0.1], limit=5)
        )


def test_vector_service_search_spans_multiple_knowledge_base_ids() -> None:
    """Service merges and rank-orders results across multiple knowledge bases."""
    event_bus = InMemoryEventBus()
    service = create_vector_service(InMemoryVectorStore(), event_bus=event_bus)

    for kb_id, content_id in [("kb-a", "content-a-1"), ("kb-b", "content-b-1")]:
        service.index(
            VectorIndexRequest(
                knowledge_base_id=kb_id,
                submissions=[
                    VectorIndexSubmission(
                        content_id=content_id,
                        embedding=[1.0, 0.0, 0.0],
                        metadata={},
                    ),
                ],
            )
        )

    response = service.search(
        VectorSearchRequest(
            knowledge_base_ids=["kb-a", "kb-b"],
            query_vector=[1.0, 0.0, 0.0],
            limit=10,
        )
    )

    content_ids = {match.content_id for match in response.matches}
    assert content_ids == {"content-a-1", "content-b-1"}
    assert response.knowledge_base_ids == ["kb-a", "kb-b"]


def test_vector_service_search_merges_cross_kb_results_by_score_and_applies_limit_after_merge() -> None:
    event_bus = InMemoryEventBus()
    service = create_vector_service(InMemoryVectorStore(), event_bus=event_bus)

    service.index(
        VectorIndexRequest(
            knowledge_base_id="kb-a",
            submissions=[
                VectorIndexSubmission(
                    content_id="content-a-1",
                    embedding=[1.0, 0.0, 0.0],
                    metadata={},
                ),
            ],
        )
    )

    service.index(
        VectorIndexRequest(
            knowledge_base_id="kb-b",
            submissions=[
                VectorIndexSubmission(
                    content_id="content-b-1",
                    embedding=[0.6, 0.8, 0.0],
                    metadata={},
                ),
            ],
        )
    )

    response = service.search(
        VectorSearchRequest(
            knowledge_base_ids=["kb-a", "kb-b"],
            query_vector=[1.0, 0.0, 0.0],
            limit=1,
        )
    )

    assert len(response.matches) == 1
    assert response.matches[0].content_id == "content-a-1"
    assert response.knowledge_base_ids == ["kb-a", "kb-b"]


# ---------------------------------------------------------------------------
# Lifecycle tests — batching, audit persistence, batch_search, delete flow.
# ---------------------------------------------------------------------------


def test_vector_service_splits_large_index_batches_and_preserves_order() -> None:
    event_bus = InMemoryEventBus()
    store = _RecordingVectorStore()
    service = create_vector_service(store, event_bus=event_bus, max_batch_size=2)

    receipts = service.index(
        VectorIndexRequest(
            knowledge_base_id="kb-1",
            submissions=[
                VectorIndexSubmission(content_id="content-1", embedding=[1.0, 0.0]),
                VectorIndexSubmission(content_id="content-2", embedding=[0.0, 1.0]),
                VectorIndexSubmission(content_id="content-3", embedding=[1.0, 1.0]),
            ],
        )
    )

    assert store.upsert_batch_sizes == [2, 1]
    assert [receipt.content_id for receipt in receipts] == [
        "content-1",
        "content-2",
        "content-3",
    ]


def test_vector_service_persists_audit_artifact() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    service = create_vector_service(
        InMemoryVectorStore(),
        event_bus=event_bus,
        object_store=object_store,
    )

    receipts = service.index(
        VectorIndexRequest(
            knowledge_base_id="kb-1",
            submissions=[
                VectorIndexSubmission(content_id="content-1", embedding=[1.0, 0.0])
            ],
        )
    )

    keys = object_store.list_keys("knowledgebases/kb-1/vector_index/")
    assert len(keys) == 1
    stored = object_store.get_bytes(keys[0])
    artifact = VectorAuditArtifact.model_validate_json(stored.content)
    assert artifact.knowledge_base_id == "kb-1"
    assert artifact.receipts == receipts
    assert stored.media_type == "application/json"


def test_vector_service_logs_audit_failure_without_rollback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    event_bus = InMemoryEventBus()
    service = create_vector_service(
        InMemoryVectorStore(),
        event_bus=event_bus,
        object_store=_FailingObjectStore(),
    )

    receipts = service.index(
        VectorIndexRequest(
            knowledge_base_id="kb-1",
            submissions=[
                VectorIndexSubmission(content_id="content-1", embedding=[1.0, 0.0])
            ],
        )
    )

    assert len(receipts) == 1
    assert "Failed to persist vector index audit artifact" in caplog.text


def test_vector_service_batch_search_preserves_request_order() -> None:
    event_bus = InMemoryEventBus()
    service = create_vector_service(InMemoryVectorStore(), event_bus=event_bus)
    service.index(
        VectorIndexRequest(
            knowledge_base_id="kb-1",
            submissions=[
                VectorIndexSubmission(content_id="alpha", embedding=[1.0, 0.0]),
                VectorIndexSubmission(content_id="beta", embedding=[0.0, 1.0]),
            ],
        )
    )

    responses = service.batch_search(
        [
            VectorSearchRequest(
                knowledge_base_ids=["kb-1"], query_vector=[0.0, 1.0], limit=1
            ),
            VectorSearchRequest(
                knowledge_base_ids=["kb-1"], query_vector=[1.0, 0.0], limit=1
            ),
        ]
    )

    assert [response.matches[0].content_id for response in responses] == [
        "beta",
        "alpha",
    ]


def test_vector_service_get_count_and_delete_record() -> None:
    event_bus = InMemoryEventBus()
    service = create_vector_service(InMemoryVectorStore(), event_bus=event_bus)
    receipt = service.index(
        VectorIndexRequest(
            knowledge_base_id="kb-1",
            submissions=[
                VectorIndexSubmission(content_id="content-1", embedding=[1.0, 0.0])
            ],
        )
    )[0]

    record = service.get_record("kb-1", receipt.record_id)
    assert record is not None
    assert record.content_id == "content-1"
    assert service.count("kb-1") == 1
    assert service.delete_record("kb-1", receipt.record_id) is True
    assert service.delete_record("kb-1", receipt.record_id) is False
    assert service.count("kb-1") == 0


def test_vector_service_delete_knowledge_base_publishes_event() -> None:
    event_bus = InMemoryEventBus()
    service = create_vector_service(InMemoryVectorStore(), event_bus=event_bus)
    service.index(
        VectorIndexRequest(
            knowledge_base_id="kb-1",
            submissions=[
                VectorIndexSubmission(content_id="content-1", embedding=[1.0, 0.0]),
                VectorIndexSubmission(content_id="content-2", embedding=[0.0, 1.0]),
            ],
        )
    )

    response = service.delete_knowledge_base("kb-1")

    assert isinstance(response, VectorDeleteResponse)
    assert response.deleted_count == 2
    assert service.count("kb-1") == 0
    assert event_bus.published_events[-1].event_type == "vectors.deleted"


def test_vector_service_search_preserves_adapter_dimension_mismatch() -> None:
    event_bus = InMemoryEventBus()
    service = create_vector_service(
        _FailingSearchVectorStore(VectorDimensionMismatchError("dimension mismatch")),
        event_bus=event_bus,
    )

    with pytest.raises(VectorDimensionMismatchError, match="dimension mismatch"):
        service.search(
            VectorSearchRequest(
                knowledge_base_ids=["kb-1"],
                query_vector=[1.0],
                limit=1,
            )
        )


def test_vector_service_index_preserves_adapter_dimension_mismatch() -> None:
    event_bus = InMemoryEventBus()
    service = create_vector_service(
        _FailingIndexVectorStore(VectorDimensionMismatchError("dimension mismatch")),
        event_bus=event_bus,
    )

    with pytest.raises(VectorDimensionMismatchError, match="dimension mismatch"):
        service.index(
            VectorIndexRequest(
                knowledge_base_id="kb-1",
                submissions=[
                    VectorIndexSubmission(content_id="content-1", embedding=[1.0])
                ],
            )
        )

    assert event_bus.published_events == []


def test_vector_service_search_wraps_adapter_value_error() -> None:
    event_bus = InMemoryEventBus()
    service = create_vector_service(
        _FailingSearchVectorStore(ValueError("backend value failure")),
        event_bus=event_bus,
    )

    with pytest.raises(VectorStoreError, match="Failed to search vector records"):
        service.search(
            VectorSearchRequest(
                knowledge_base_ids=["kb-1"],
                query_vector=[1.0],
                limit=1,
            )
        )


def test_vector_service_index_wraps_adapter_value_error() -> None:
    event_bus = InMemoryEventBus()
    service = create_vector_service(
        _FailingIndexVectorStore(ValueError("backend value failure")),
        event_bus=event_bus,
    )

    with pytest.raises(VectorStoreError, match="Failed to index vector records"):
        service.index(
            VectorIndexRequest(
                knowledge_base_id="kb-1",
                submissions=[
                    VectorIndexSubmission(content_id="content-1", embedding=[1.0])
                ],
            )
        )

    assert event_bus.published_events == []
