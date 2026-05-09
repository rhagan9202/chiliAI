"""Tests for the Qdrant vector store adapter."""

from __future__ import annotations

import os
from collections.abc import Sequence
from uuid import uuid4
from typing import TYPE_CHECKING, cast

import pytest

from config.schema import VectorStoreConfig
from vectorstore.adapters.qdrant_adapter import QdrantClientProtocol, QdrantVectorStore
from vectorstore.exceptions import VectorDimensionMismatchError
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


class _FakeQdrantClient:
    def __init__(self) -> None:
        self.created_collections: list[tuple[str, qdrant_models.VectorParams]] = []
        self.upserts: list[tuple[str, list[qdrant_models.PointStruct]]] = []
        self.queries: list[
            tuple[str, list[float], qdrant_models.Filter | None, int, bool]
        ] = []
        self.deletes: list[tuple[str, qdrant_models.PointIdsList]] = []
        self.existing_collections: set[str] = set()
        self.query_response = _FakeQueryResponse(points=[])

    def collection_exists(self, collection_name: str, **_: object) -> bool:
        return collection_name in self.existing_collections

    def create_collection(
        self,
        collection_name: str,
        vectors_config: qdrant_models.VectorParams,
        **_: object,
    ) -> bool:
        self.created_collections.append((collection_name, vectors_config))
        self.existing_collections.add(collection_name)
        return True

    def upsert(
        self,
        collection_name: str,
        points: Sequence[qdrant_models.PointStruct],
        **_: object,
    ) -> object:
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


def test_qdrant_vector_store_rejects_dimension_mismatch() -> None:
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
                )
            ],
        )

    with pytest.raises(VectorDimensionMismatchError, match="dimension"):
        store.search("kb-1", [1.0, 0.0], 1)


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
    finally:
        store.delete_records(knowledge_base_id, [record.id])
        cleanup_client = QdrantClient(url=uri, prefer_grpc=True)
        cleanup_client.delete_collection(f"chili_{knowledge_base_id}")
