"""Tests for the DocumentsExtractionWarningEvent type and its codec registration."""

from __future__ import annotations

from events.codec import EVENT_TYPE_REGISTRY, decode_event, encode_event
from events.types import DocumentsExtractionWarningEvent, ExtractionWarningReference


def _reference() -> ExtractionWarningReference:
    return ExtractionWarningReference(
        knowledge_base_id="kb-1",
        source_document_id="doc-1",
        valid_entity_count=0,
        valid_relationship_count=0,
        dropped_entity_count=2,
        dropped_relationship_count=1,
        stripped_property_count=1,
        empty_extraction=True,
        sample_reasons=["entity cand-1: Unknown entity type 'provider'."],
        validation_storage_key="knowledgebases/kb-1/validations/extract-1.json",
    )


def test_event_has_stable_type() -> None:
    event = DocumentsExtractionWarningEvent(documents=[_reference()])
    assert event.event_type == "documents.extraction_warning"


def test_event_is_registered_in_codec() -> None:
    assert (
        EVENT_TYPE_REGISTRY["documents.extraction_warning"]
        is DocumentsExtractionWarningEvent
    )


def test_event_round_trips_through_the_codec() -> None:
    event = DocumentsExtractionWarningEvent(
        correlation_id="corr-1",
        documents=[_reference()],
    )
    decoded = decode_event(encode_event(event))
    assert isinstance(decoded, DocumentsExtractionWarningEvent)
    assert decoded.correlation_id == "corr-1"
    reference = decoded.documents[0]
    assert reference.source_document_id == "doc-1"
    assert reference.empty_extraction is True
    assert reference.dropped_entity_count == 2
    assert reference.stripped_property_count == 1
    assert reference.sample_reasons == [
        "entity cand-1: Unknown entity type 'provider'."
    ]
