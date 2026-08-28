"""Tests for the Qdrant vector store adapter."""

from __future__ import annotations

import os
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from uuid import uuid4

import pytest

from config.schema import VectorStoreConfig
import vectorstore.adapters.qdrant_adapter as qdrant_adapter
from vectorstore.adapters.qdrant_adapter import (
    UPSERT_MAX_POINTS_PER_REQUEST,
    QdrantClientProtocol,
    QdrantVectorStore,
)
from vectorstore.exceptions import VectorDimensionMismatchError, VectorStoreError
from vectorstore.models import VectorRecord

if TYPE_CHECKING:
    from qdrant_client import QdrantClient
    from qdrant_client import models as qdrant_models
else:
    qdrant_client = pytest.importorskip("qdrant_client")
    qdrant_models = pytest.importorskip("qdrant_client.models")
    QdrantClient = qdrant_client.QdrantClient


class _FakeQueryResponse:
    def __init__(self, points: list[qdrant_models.ScoredPoint]) -> None:
        self.points = points


class _FakeCollectionParams:
    def __init__(self, vectors: qdrant_models.VectorParams) -> None:
        self.vectors = vectors


class _FakeCollectionConfig:
    def __init__(self, vectors: qdrant_models.VectorParams) -> None:
        self.params = _FakeCollectionParams(vectors)


class _FakeCollectionInfo:
    def __init__(self, vectors: qdrant_models.VectorParams) -> None:
        self.config = _FakeCollectionConfig(vectors)


class _FakeCountResponse:
    def __init__(self, count: int) -> None:
        self.count = count


class _FakeQdrantClient:
    def __init__(self) -> None:
        self.created_collections: list[tuple[str, qdrant_models.VectorParams]] = []
        self.upserts: list[tuple[str, list[qdrant_models.PointStruct]]] = []
        self.queries: list[
            tuple[str, list[float], qdrant_models.Filter | None, int, bool]
        ] = []
        self.deletes: list[tuple[str, qdrant_models.PointIdsList]] = []
        self.existing_collections: set[str] = set()
        self.collection_dimensions: dict[str, int] = {}
        self.query_response = _FakeQueryResponse(points=[])
        self.retrieved_ids: list[tuple[str, list[str]]] = []
        self.retrieve_flags: list[tuple[bool, bool]] = []
        self.counted_collections: list[str] = []
        self.count_exact_flags: list[bool] = []
        self.deleted_collections: list[str] = []
        self.retrieve_response: list[qdrant_models.Record] = []
        self.count_response = _FakeCountResponse(count=0)
        self.delete_collection_response = True
        self.collection_exists_error: Exception | None = None
        self.close_calls = 0

    def collection_exists(self, collection_name: str, **_: object) -> bool:
        if self.collection_exists_error is not None:
            raise self.collection_exists_error
        return collection_name in self.existing_collections

    def get_collection(self, collection_name: str, **_: object) -> _FakeCollectionInfo:
        return _FakeCollectionInfo(
            qdrant_models.VectorParams(
                size=self.collection_dimensions[collection_name],
                distance=qdrant_models.Distance.COSINE,
            )
        )

    def create_collection(
        self,
        collection_name: str,
        vectors_config: qdrant_models.VectorParams,
        **_: object,
    ) -> bool:
        self.created_collections.append((collection_name, vectors_config))
        self.existing_collections.add(collection_name)
        self.collection_dimensions[collection_name] = vectors_config.size
        return True

    def upsert(
        self,
        collection_name: str,
        points: Sequence[qdrant_models.PointStruct],
        **_: object,
    ) -> object:
        dimension = self.collection_dimensions[collection_name]
        for point in points:
            if len(cast(list[float], point.vector)) != dimension:
                raise VectorDimensionMismatchError(
                    "Embedding dimension does not match the existing namespace dimension."
                )
        self.upserts.append((collection_name, list(points)))
        return object()

    def query_points(
        self,
        collection_name: str,
        query: list[float],
        query_filter: qdrant_models.Filter | None,
        limit: int,
        with_payload: bool,
        **_: object,
    ) -> _FakeQueryResponse:
        self.queries.append((collection_name, query, query_filter, limit, with_payload))
        return self.query_response

    def delete(
        self,
        collection_name: str,
        points_selector: qdrant_models.PointIdsList,
        **_: object,
    ) -> object:
        self.deletes.append((collection_name, points_selector))
        return object()

    def retrieve(
        self,
        collection_name: str,
        ids: Sequence[str],
        with_payload: bool,
        with_vectors: bool,
        **_: object,
    ) -> list[qdrant_models.Record]:
        self.retrieved_ids.append((collection_name, list(ids)))
        self.retrieve_flags.append((with_payload, with_vectors))
        return self.retrieve_response

    def count(
        self,
        collection_name: str,
        exact: bool,
        **_: object,
    ) -> _FakeCountResponse:
        self.counted_collections.append(collection_name)
        self.count_exact_flags.append(exact)
        return self.count_response

    def delete_collection(self, collection_name: str, **_: object) -> bool:
        self.deleted_collections.append(collection_name)
        if self.delete_collection_response:
            self.existing_collections.discard(collection_name)
        return self.delete_collection_response

    def close(self) -> None:
        self.close_calls += 1


def test_qdrant_vector_store_close_closes_the_underlying_client() -> None:
    client = _FakeQdrantClient()
    store = QdrantVectorStore(
        VectorStoreConfig(backend="qdrant", uri="http://qdrant:6333", dimensions=2),
        client=cast(QdrantClientProtocol, client),
    )

    store.close()

    assert client.close_calls == 1


def test_qdrant_vector_store_uses_http_client_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_kwargs: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            client_kwargs.update(kwargs)

    monkeypatch.setattr(qdrant_adapter, "QdrantClient", FakeClient)

    QdrantVectorStore(
        VectorStoreConfig(backend="qdrant", uri="http://qdrant:6333", dimensions=2)
    )

    assert client_kwargs == {
        "url": "http://qdrant:6333",
        "prefer_grpc": False,
        "check_compatibility": False,
    }


def test_qdrant_vector_store_creates_collection_and_upserts_records() -> None:
    client = _FakeQdrantClient()
    store = QdrantVectorStore(
        VectorStoreConfig(backend="qdrant", uri="http://qdrant:6333", dimensions=2),
        client=cast(QdrantClientProtocol, client),
    )
    records = [
        VectorRecord(
            id="11111111-1111-1111-1111-111111111111",
            knowledge_base_id="kb-1",
            content_id="content-1",
            embedding=[1.0, 0.0],
            metadata={"source": "policy"},
        )
    ]

    stored_records = store.upsert_records("kb-1", records)

    assert stored_records == records
    assert client.created_collections[0][0] == "chili_kb-1"
    assert client.created_collections[0][1].size == 2
    assert client.created_collections[0][1].distance == qdrant_models.Distance.COSINE
    assert client.upserts[0][0] == "chili_kb-1"
    payload = client.upserts[0][1][0].payload
    assert payload is not None
    assert str(client.upserts[0][1][0].id) != records[0].id
    assert payload["record_id"] == records[0].id
    assert payload["metadata"] == {"source": "policy"}


def test_qdrant_vector_store_accepts_composite_record_ids() -> None:
    client = _FakeQdrantClient()
    store = QdrantVectorStore(
        VectorStoreConfig(backend="qdrant", uri="http://qdrant:6333", dimensions=2),
        client=cast(QdrantClientProtocol, client),
    )
    record = VectorRecord(
        id="kb-1:entity-1",
        knowledge_base_id="kb-1",
        content_id="entity-1",
        embedding=[1.0, 0.0],
    )

    store.upsert_records("kb-1", [record])

    point = client.upserts[0][1][0]
    assert point.id != record.id
    assert point.payload is not None
    assert point.payload["record_id"] == "kb-1:entity-1"


def test_qdrant_vector_store_chunks_oversized_upsert_batches() -> None:
    client = _FakeQdrantClient()
    store = QdrantVectorStore(
        VectorStoreConfig(backend="qdrant", uri="http://qdrant:6333", dimensions=2),
        client=cast(QdrantClientProtocol, client),
    )
    total = UPSERT_MAX_POINTS_PER_REQUEST * 2 + 1
    records = [
        VectorRecord(
            id=f"kb-1:entity-{index}",
            knowledge_base_id="kb-1",
            content_id=f"entity-{index}",
            embedding=[1.0, 0.0],
        )
        for index in range(total)
    ]

    stored_records = store.upsert_records("kb-1", records)

    assert stored_records == records
    assert [len(points) for _, points in client.upserts] == [
        UPSERT_MAX_POINTS_PER_REQUEST,
        UPSERT_MAX_POINTS_PER_REQUEST,
        1,
    ]
    upserted_record_ids = [
        point.payload["record_id"]
        for _, points in client.upserts
        for point in points
        if point.payload is not None
    ]
    assert upserted_record_ids == [record.id for record in records]


def test_qdrant_vector_store_creates_collection_with_batch_dimension() -> None:
    client = _FakeQdrantClient()
    store = QdrantVectorStore(
        VectorStoreConfig(backend="qdrant", uri="http://qdrant:6333", dimensions=384),
        client=cast(QdrantClientProtocol, client),
    )

    store.upsert_records(
        "kb-1_custom",
        [
            VectorRecord(
                id="kb-1:entity-1:custom",
                knowledge_base_id="kb-1",
                content_id="entity-1",
                embedding=[0.1, 0.2, 0.3],
                metadata={"source": "custom"},
            )
        ],
    )

    assert client.created_collections[0][0] == "chili_kb-1_custom"
    assert client.created_collections[0][1].size == 3


def test_qdrant_vector_store_rejects_existing_collection_dimension_mismatch() -> None:
    client = _FakeQdrantClient()
    client.existing_collections.add("chili_kb-1")
    client.collection_dimensions["chili_kb-1"] = 2
    store = QdrantVectorStore(
        VectorStoreConfig(backend="qdrant", uri="http://qdrant:6333", dimensions=2),
        client=cast(QdrantClientProtocol, client),
    )

    with pytest.raises(VectorDimensionMismatchError, match="existing Qdrant collection"):
        store.upsert_records(
            "kb-1",
            [
                VectorRecord(
                    id="kb-1:entity-1",
                    knowledge_base_id="kb-1",
                    content_id="entity-1",
                    embedding=[0.1, 0.2, 0.3],
                )
            ],
        )

    assert client.upserts == []


def test_qdrant_vector_store_search_translates_filters_and_returns_matches() -> None:
    client = _FakeQdrantClient()
    client.existing_collections.add("chili_kb-1")
    client.query_response = _FakeQueryResponse(
        points=[
            qdrant_models.ScoredPoint(
                id="11111111-1111-1111-1111-111111111111",
                version=1,
                score=0.98,
                payload={
                    "record_id": "kb-1:content-1",
                    "content_id": "content-1",
                    "content": "Alpha",
                    "metadata": {"source": "policy", "rank": 1},
                },
                vector=None,
                shard_key=None,
                order_value=None,
            )
        ]
    )
    store = QdrantVectorStore(
        VectorStoreConfig(backend="qdrant", uri="http://qdrant:6333", dimensions=2),
        client=cast(QdrantClientProtocol, client),
    )

    matches = store.search(
        "kb-1",
        [1.0, 0.0],
        5,
        {"source": "policy", "rank": 1, "risk_score": 0.75},
    )

    assert [match.content_id for match in matches] == ["content-1"]
    assert [match.record_id for match in matches] == ["kb-1:content-1"]
    query_filter = client.queries[0][2]
    assert query_filter is not None
    conditions = cast(list[qdrant_models.FieldCondition], query_filter.must or [])
    assert [condition.key for condition in conditions] == [
        "metadata.source",
        "metadata.rank",
        "metadata.risk_score",
    ]
    assert [cast(qdrant_models.MatchValue, condition.match).value for condition in conditions[:2]] == [
        "policy",
        1,
    ]
    risk_range = cast(qdrant_models.Range, conditions[2].range)
    assert risk_range.gte == 0.75
    assert risk_range.lte == 0.75


def test_qdrant_vector_store_search_wraps_malformed_matches() -> None:
    client = _FakeQdrantClient()
    client.existing_collections.add("chili_kb-1")
    client.query_response = _FakeQueryResponse(
        points=[
            qdrant_models.ScoredPoint(
                id="11111111-1111-1111-1111-111111111111",
                version=1,
                score=0.98,
                payload={"record_id": "kb-1:content-1"},
                vector=None,
                shard_key=None,
                order_value=None,
            )
        ]
    )
    store = QdrantVectorStore(
        VectorStoreConfig(backend="qdrant", uri="http://qdrant:6333", dimensions=2),
        client=cast(QdrantClientProtocol, client),
    )

    with pytest.raises(VectorStoreError, match="Failed to search Qdrant vector records."):
        store.search("kb-1", [1.0, 0.0], 5)


def test_qdrant_vector_store_delete_records_targets_collection_ids() -> None:
    client = _FakeQdrantClient()
    client.existing_collections.add("chili_kb-1")
    store = QdrantVectorStore(
        VectorStoreConfig(backend="qdrant", uri="http://qdrant:6333", dimensions=2),
        client=cast(QdrantClientProtocol, client),
    )

    deleted_count = store.delete_records(
        "kb-1",
        [
            "kb-1:entity-1",
            "kb-1:entity-2",
        ],
    )

    assert deleted_count == 2
    assert client.deletes[0][0] == "chili_kb-1"
    assert client.deletes[0][1].points == [
        "aa874bcd-be3a-5c5d-90d5-3bf5a7ae1b54",
        "4759df70-72b3-5b1a-b95d-4335d2e14254",
    ]


def test_qdrant_vector_store_get_record_reconstructs_payload_and_vector() -> None:
    client = _FakeQdrantClient()
    client.existing_collections.add("chili_kb-1")
    indexed_at = datetime(2026, 5, 19, 12, 30, tzinfo=UTC)
    client.retrieve_response = [
        qdrant_models.Record(
            id="11111111-1111-1111-1111-111111111111",
            payload={
                "record_id": "kb-1:content-1",
                "knowledge_base_id": "kb-1",
                "content_id": "content-1",
                "content": "Alpha",
                "metadata": {"source": "policy"},
                "indexed_at": indexed_at.isoformat(),
            },
            vector=[1.0, 0.0],
            shard_key=None,
        )
    ]
    store = QdrantVectorStore(
        VectorStoreConfig(backend="qdrant", uri="http://qdrant:6333", dimensions=2),
        client=cast(QdrantClientProtocol, client),
    )

    record = store.get_record("kb-1", "kb-1:content-1")

    assert record is not None
    assert record.id == "kb-1:content-1"
    assert record.embedding == [1.0, 0.0]
    assert record.metadata == {"source": "policy"}
    assert record.indexed_at == indexed_at
    assert client.retrieved_ids[0][0] == "chili_kb-1"
    assert client.retrieve_flags == [(True, True)]


@pytest.mark.parametrize(
    "record",
    [
        qdrant_models.Record(
            id="11111111-1111-1111-1111-111111111111",
            payload={"record_id": "record-1"},
            vector=[1.0, 0.0],
            shard_key=None,
        ),
        qdrant_models.Record(
            id="11111111-1111-1111-1111-111111111111",
            payload={"record_id": "record-1", "content_id": "content-1"},
            vector=None,
            shard_key=None,
        ),
        qdrant_models.Record(
            id="11111111-1111-1111-1111-111111111111",
            payload={"record_id": "record-1", "content_id": "content-1"},
            vector=[[1.0, 0.0]],
            shard_key=None,
        ),
    ],
)
def test_qdrant_vector_store_get_record_wraps_malformed_records(
    record: qdrant_models.Record,
) -> None:
    client = _FakeQdrantClient()
    client.existing_collections.add("chili_kb-1")
    client.retrieve_response = [record]
    store = QdrantVectorStore(
        VectorStoreConfig(backend="qdrant", uri="http://qdrant:6333", dimensions=2),
        client=cast(QdrantClientProtocol, client),
    )

    with pytest.raises(
        VectorStoreError,
        match="Failed to retrieve Qdrant vector record.",
    ):
        store.get_record("kb-1", "record-1")


def test_qdrant_vector_store_get_record_returns_none_for_missing_collection() -> None:
    client = _FakeQdrantClient()
    store = QdrantVectorStore(
        VectorStoreConfig(backend="qdrant", uri="http://qdrant:6333", dimensions=2),
        client=cast(QdrantClientProtocol, client),
    )

    assert store.get_record("kb-1", "record-1") is None
    assert client.retrieved_ids == []


def test_qdrant_vector_store_counts_records() -> None:
    client = _FakeQdrantClient()
    client.existing_collections.add("chili_kb-1")
    client.count_response = _FakeCountResponse(count=4)
    store = QdrantVectorStore(
        VectorStoreConfig(backend="qdrant", uri="http://qdrant:6333", dimensions=2),
        client=cast(QdrantClientProtocol, client),
    )

    assert store.count_records("kb-1") == 4
    assert store.count_records("missing-kb") == 0
    assert client.count_exact_flags == [True]


def test_qdrant_vector_store_delete_record_is_idempotent() -> None:
    client = _FakeQdrantClient()
    client.existing_collections.add("chili_kb-1")
    client.retrieve_response = [
        qdrant_models.Record(
            id="11111111-1111-1111-1111-111111111111",
            payload={"record_id": "record-1", "content_id": "content-1"},
            vector=[1.0, 0.0],
            shard_key=None,
        )
    ]
    store = QdrantVectorStore(
        VectorStoreConfig(backend="qdrant", uri="http://qdrant:6333", dimensions=2),
        client=cast(QdrantClientProtocol, client),
    )

    assert store.delete_record("kb-1", "record-1") is True
    client.retrieve_response = []
    assert store.delete_record("kb-1", "record-1") is False


def test_qdrant_vector_store_delete_namespace_counts_then_deletes_collection() -> None:
    client = _FakeQdrantClient()
    client.existing_collections.add("chili_kb-1")
    client.count_response = _FakeCountResponse(count=3)
    store = QdrantVectorStore(
        VectorStoreConfig(backend="qdrant", uri="http://qdrant:6333", dimensions=2),
        client=cast(QdrantClientProtocol, client),
    )

    assert store.delete_namespace("kb-1") == 3
    assert client.deleted_collections == ["chili_kb-1"]
    assert store.delete_namespace("kb-1") == 0


def test_qdrant_vector_store_delete_namespace_raises_when_delete_fails() -> None:
    client = _FakeQdrantClient()
    client.existing_collections.add("chili_kb-1")
    client.count_response = _FakeCountResponse(count=3)
    client.delete_collection_response = False
    store = QdrantVectorStore(
        VectorStoreConfig(backend="qdrant", uri="http://qdrant:6333", dimensions=2),
        client=cast(QdrantClientProtocol, client),
    )

    with pytest.raises(
        VectorStoreError,
        match="Failed to delete Qdrant vector namespace.",
    ):
        store.delete_namespace("kb-1")

    assert client.deleted_collections == ["chili_kb-1"]
    assert client.count_exact_flags == [True]


def test_qdrant_vector_store_rejects_inconsistent_batch_dimensions() -> None:
    client = _FakeQdrantClient()
    store = QdrantVectorStore(
        VectorStoreConfig(backend="qdrant", uri="http://qdrant:6333", dimensions=3),
        client=cast(QdrantClientProtocol, client),
    )

    with pytest.raises(VectorDimensionMismatchError, match="dimension"):
        store.upsert_records(
            "kb-1",
            [
                VectorRecord(
                    id="11111111-1111-1111-1111-111111111111",
                    knowledge_base_id="kb-1",
                    content_id="content-1",
                    embedding=[1.0, 0.0],
                ),
                VectorRecord(
                    id="22222222-2222-2222-2222-222222222222",
                    knowledge_base_id="kb-1",
                    content_id="content-2",
                    embedding=[1.0, 0.0, 0.0],
                )
            ],
        )


def test_qdrant_vector_store_rejects_query_dimension_mismatch() -> None:
    client = _FakeQdrantClient()
    store = QdrantVectorStore(
        VectorStoreConfig(backend="qdrant", uri="http://qdrant:6333", dimensions=3),
        client=cast(QdrantClientProtocol, client),
    )

    with pytest.raises(VectorDimensionMismatchError, match="dimension"):
        store.search("kb-1", [1.0, 0.0], 1)


def test_qdrant_vector_store_upsert_wraps_collection_errors() -> None:
    client = _FakeQdrantClient()
    client.collection_exists_error = RuntimeError("connection refused")
    store = QdrantVectorStore(
        VectorStoreConfig(backend="qdrant", uri="http://qdrant:6333", dimensions=2),
        client=cast(QdrantClientProtocol, client),
    )

    with pytest.raises(VectorStoreError, match="Failed to upsert Qdrant vector records."):
        store.upsert_records(
            "kb-1",
            [
                VectorRecord(
                    id="11111111-1111-1111-1111-111111111111",
                    knowledge_base_id="kb-1",
                    content_id="content-1",
                    embedding=[1.0, 0.0],
                )
            ],
        )


@pytest.mark.integration
def test_qdrant_vector_store_round_trip_search() -> None:
    uri = os.getenv("QDRANT_URL")
    if uri is None:
        pytest.skip("QDRANT_URL is required for Qdrant integration tests.")

    knowledge_base_id = f"kb-qdrant-{uuid4()}"
    store = QdrantVectorStore(
        VectorStoreConfig(
            backend="qdrant",
            uri=uri,
            dimensions=2,
            distance_metric="cosine",
        )
    )
    record = VectorRecord(
        id=str(uuid4()),
        knowledge_base_id=knowledge_base_id,
        content_id="content-1",
        embedding=[1.0, 0.0],
        content="Policy text",
        metadata={"source": "policy"},
    )

    try:
        store.upsert_records(knowledge_base_id, [record])
        matches = store.search(
            knowledge_base_id,
            [1.0, 0.0],
            1,
            {"source": "policy"},
        )

        assert len(matches) == 1
        assert matches[0].record_id == record.id
        assert matches[0].content_id == "content-1"

        fetched = store.get_record(knowledge_base_id, record.id)
        assert fetched is not None
        assert fetched.id == record.id
        assert fetched.embedding == [1.0, 0.0]
        assert store.count_records(knowledge_base_id) == 1
        assert store.delete_record(knowledge_base_id, record.id) is True
        assert store.delete_record(knowledge_base_id, record.id) is False
        assert store.count_records(knowledge_base_id) == 0
    finally:
        store.delete_records(knowledge_base_id, [record.id])
        cleanup_client = QdrantClient(url=uri)
        cleanup_client.delete_collection(f"chili_{knowledge_base_id}")


@pytest.mark.integration
def test_qdrant_vector_store_live_delete_namespace() -> None:
    uri = os.getenv("QDRANT_URL")
    if uri is None:
        pytest.skip("QDRANT_URL is required for Qdrant integration tests.")

    knowledge_base_id = f"kb-qdrant-delete-{uuid4()}"
    store = QdrantVectorStore(
        VectorStoreConfig(
            backend="qdrant",
            uri=uri,
            dimensions=2,
            distance_metric="cosine",
        )
    )
    records = [
        VectorRecord(
            id=str(uuid4()),
            knowledge_base_id=knowledge_base_id,
            content_id="content-1",
            embedding=[1.0, 0.0],
        ),
        VectorRecord(
            id=str(uuid4()),
            knowledge_base_id=knowledge_base_id,
            content_id="content-2",
            embedding=[0.0, 1.0],
        ),
    ]

    try:
        store.upsert_records(knowledge_base_id, records)

        assert store.delete_namespace(knowledge_base_id) == 2
        assert store.delete_namespace(knowledge_base_id) == 0
    finally:
        cleanup_client = QdrantClient(url=uri)
        cleanup_client.delete_collection(f"chili_{knowledge_base_id}")
