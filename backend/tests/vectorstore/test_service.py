"""Tests for the vectorstore service."""

from __future__ import annotations

from events.adapters.in_memory import InMemoryEventBus
from events.types import VectorsIndexedEvent
from vectorstore.adapters.in_memory import InMemoryVectorStore
from vectorstore.adapters.protocols import VectorStoreProtocol
from vectorstore.exceptions import VectorStoreError
from vectorstore.models import MetadataValue, VectorMatch, VectorRecord
from vectorstore.service import create_vector_service
from vectorstore.service_models import (
    VectorIndexRequest,
    VectorIndexSubmission,
    VectorSearchMatch,
    VectorSearchRequest,
)
import pytest


class _DroppingVectorStore(VectorStoreProtocol):
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
            knowledge_base_id="kb-1",
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
