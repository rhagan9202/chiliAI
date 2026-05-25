"""Tests for VectorService.delete_by_source_document."""

from __future__ import annotations

from events.adapters.in_memory import InMemoryEventBus
from shared.provenance import (
    SOURCE_DOCUMENT_ID_KEY,
    SOURCE_FEED_KEY,
    SOURCE_KIND_DOCUMENT,
    SOURCE_KIND_KEY,
    SOURCE_KIND_RECORD,
)
from vectorstore.adapters.in_memory import InMemoryVectorStore
from vectorstore.models import VectorRecord
from vectorstore.service import VectorService


def test_delete_by_source_document_removes_only_matching_points() -> None:
    store = InMemoryVectorStore()
    service = VectorService(store, event_bus=InMemoryEventBus())

    store.upsert_records("kb-1", [
        VectorRecord(
            id="v1",
            knowledge_base_id="kb-1",
            content_id="c1",
            embedding=[1.0, 0.0, 0.0],
            content="a",
            metadata={
                SOURCE_KIND_KEY: SOURCE_KIND_DOCUMENT,
                SOURCE_DOCUMENT_ID_KEY: "doc-A",
            },
        ),
        VectorRecord(
            id="v2",
            knowledge_base_id="kb-1",
            content_id="c2",
            embedding=[0.0, 1.0, 0.0],
            content="b",
            metadata={
                SOURCE_KIND_KEY: SOURCE_KIND_DOCUMENT,
                SOURCE_DOCUMENT_ID_KEY: "doc-B",
            },
        ),
        VectorRecord(
            id="v3",
            knowledge_base_id="kb-1",
            content_id="c3",
            embedding=[0.0, 0.0, 1.0],
            content="c",
            metadata={
                SOURCE_KIND_KEY: SOURCE_KIND_RECORD,
                SOURCE_FEED_KEY: "nppes_providers",
            },
        ),
    ])

    response = service.delete_by_source_document("kb-1", "doc-A")
    assert response.deleted_count == 1
    assert store.count_records("kb-1") == 2


def test_delete_by_source_document_multiple_chunks() -> None:
    """All chunks from the same document are removed together."""
    store = InMemoryVectorStore()
    service = VectorService(store, event_bus=InMemoryEventBus())

    store.upsert_records("kb-1", [
        VectorRecord(
            id="v1",
            knowledge_base_id="kb-1",
            content_id="c1",
            embedding=[1.0, 0.0, 0.0],
            content="chunk 1",
            metadata={SOURCE_KIND_KEY: SOURCE_KIND_DOCUMENT, SOURCE_DOCUMENT_ID_KEY: "doc-X"},
        ),
        VectorRecord(
            id="v2",
            knowledge_base_id="kb-1",
            content_id="c2",
            embedding=[0.0, 1.0, 0.0],
            content="chunk 2",
            metadata={SOURCE_KIND_KEY: SOURCE_KIND_DOCUMENT, SOURCE_DOCUMENT_ID_KEY: "doc-X"},
        ),
        VectorRecord(
            id="v3",
            knowledge_base_id="kb-1",
            content_id="c3",
            embedding=[0.0, 0.0, 1.0],
            content="other",
            metadata={SOURCE_KIND_KEY: SOURCE_KIND_DOCUMENT, SOURCE_DOCUMENT_ID_KEY: "doc-Y"},
        ),
    ])

    response = service.delete_by_source_document("kb-1", "doc-X")
    assert response.deleted_count == 2
    assert store.count_records("kb-1") == 1


def test_delete_by_source_document_no_match_returns_zero() -> None:
    """Returns zero when no records match the given source document ID."""
    store = InMemoryVectorStore()
    service = VectorService(store, event_bus=InMemoryEventBus())

    store.upsert_records("kb-1", [
        VectorRecord(
            id="v1",
            knowledge_base_id="kb-1",
            content_id="c1",
            embedding=[1.0, 0.0, 0.0],
            content="a",
            metadata={SOURCE_KIND_KEY: SOURCE_KIND_DOCUMENT, SOURCE_DOCUMENT_ID_KEY: "doc-A"},
        ),
    ])

    response = service.delete_by_source_document("kb-1", "doc-UNKNOWN")
    assert response.deleted_count == 0
    assert store.count_records("kb-1") == 1


def test_delete_by_source_document_missing_kb_returns_zero() -> None:
    """Returns zero when the knowledge base doesn't exist."""
    store = InMemoryVectorStore()
    service = VectorService(store, event_bus=InMemoryEventBus())

    response = service.delete_by_source_document("kb-nonexistent", "doc-A")
    assert response.deleted_count == 0


def test_delete_by_source_document_response_has_correct_kb_id() -> None:
    """The response carries back the knowledge_base_id that was targeted."""
    store = InMemoryVectorStore()
    service = VectorService(store, event_bus=InMemoryEventBus())

    store.upsert_records("kb-42", [
        VectorRecord(
            id="v1",
            knowledge_base_id="kb-42",
            content_id="c1",
            embedding=[1.0, 0.0, 0.0],
            content="a",
            metadata={SOURCE_KIND_KEY: SOURCE_KIND_DOCUMENT, SOURCE_DOCUMENT_ID_KEY: "doc-A"},
        ),
    ])

    response = service.delete_by_source_document("kb-42", "doc-A")
    assert response.knowledge_base_id == "kb-42"
    assert response.deleted_count == 1
