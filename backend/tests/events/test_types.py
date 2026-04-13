"""Tests for events.types — event model construction and validation."""

from __future__ import annotations

from datetime import datetime, timezone

from events.types import (
    DocumentReference,
    DocumentsParsedEvent,
    EventBase,
    KnowledgeBaseCreatedEvent,
    ParsedDocumentReference,
)


class TestEventBase:
    def test_occurred_at_default(self) -> None:
        event = KnowledgeBaseCreatedEvent(knowledge_base_id="kb-1")
        assert isinstance(event.occurred_at, datetime)
        assert event.occurred_at.tzinfo == timezone.utc

    def test_event_type_literal(self) -> None:
        event = KnowledgeBaseCreatedEvent(knowledge_base_id="kb-1")
        assert event.event_type == "kb.create"


class TestDocumentReference:
    def test_round_trip(self) -> None:
        ref = DocumentReference(
            knowledge_base_id="kb-1",
            source_document_id="doc-1",
            filename="test.csv",
        )
        data = ref.model_dump()
        restored = DocumentReference.model_validate(data)
        assert restored == ref


class TestDocumentsParsedEvent:
    def test_construction(self) -> None:
        ref = ParsedDocumentReference(
            knowledge_base_id="kb-1",
            source_document_id="doc-1",
            parsed_document_id="pd-1",
            parser_name="csv",
        )
        event = DocumentsParsedEvent(documents=[ref])
        assert event.event_type == "documents.parsed"
        assert len(event.documents) == 1

    def test_serialization(self) -> None:
        ref = ParsedDocumentReference(
            knowledge_base_id="kb-1",
            source_document_id="doc-1",
            parsed_document_id="pd-1",
            parser_name="csv",
        )
        event = DocumentsParsedEvent(documents=[ref])
        data = event.model_dump()
        restored = DocumentsParsedEvent.model_validate(data)
        assert restored.event_type == event.event_type
        assert len(restored.documents) == len(event.documents)
