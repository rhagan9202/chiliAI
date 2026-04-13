"""Tests for typed event serialization."""

from __future__ import annotations

from events.codec import decode_event, encode_event
from events.types import (
    ChunkedDocumentReference,
    DocumentReference,
    DocumentsChunkedEvent,
    DocumentsUploadedEvent,
    EntitiesExtractedEvent,
    ExtractedDocumentReference,
)


def test_event_codec_round_trips_documents_uploaded_event() -> None:
    event = DocumentsUploadedEvent(
        documents=[
            DocumentReference(
                knowledge_base_id="kb-1",
                source_document_id="doc-1",
                filename="claims.json",
                content_type="application/json",
                storage_key="knowledgebases/kb-1/documents/doc-1/claims.json",
                document_format="json",
                size_bytes=18,
            )
        ]
    )

    encoded = encode_event(event)
    decoded = decode_event(encoded)

    assert decoded == event
    assert decoded.event_type == "documents.uploaded"


def test_event_codec_round_trips_documents_chunked_event() -> None:
    event = DocumentsChunkedEvent(
        documents=[
            ChunkedDocumentReference(
                knowledge_base_id="kb-1",
                source_document_id="doc-1",
                parsed_document_id="parsed-1",
                chunk_count=3,
                strategy="RecursiveCharacterSplitter",
                storage_key="knowledgebases/kb-1/documents/doc-1/claims.json",
                parsed_document_storage_key="knowledgebases/kb-1/parsed/parsed-1.json",
                chunks_storage_key="knowledgebases/kb-1/chunks/parsed-1.json",
            )
        ]
    )

    encoded = encode_event(event)
    decoded = decode_event(encoded)

    assert decoded == event
    assert decoded.event_type == "documents.chunked"


def test_event_codec_round_trips_entities_extracted_event() -> None:
    event = EntitiesExtractedEvent(
        documents=[
            ExtractedDocumentReference(
                knowledge_base_id="kb-1",
                source_document_id="doc-1",
                parsed_document_id="parsed-1",
                extraction_result_id="extract-1",
                entity_count=2,
                relationship_count=0,
                storage_key="knowledgebases/kb-1/documents/doc-1/claims.json",
                parsed_document_storage_key="knowledgebases/kb-1/parsed/parsed-1.json",
                chunks_storage_key="knowledgebases/kb-1/chunks/parsed-1.json",
                extraction_storage_key="knowledgebases/kb-1/extractions/extract-1.json",
            )
        ]
    )

    encoded = encode_event(event)
    decoded = decode_event(encoded)

    assert decoded == event
    assert decoded.event_type == "entities.extracted"