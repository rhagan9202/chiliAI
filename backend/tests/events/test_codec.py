"""Tests for typed event serialization."""

from __future__ import annotations

from events.codec import decode_event, encode_event
from events.types import DocumentReference, DocumentsUploadedEvent


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