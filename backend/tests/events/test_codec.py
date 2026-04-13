"""Tests for typed event serialization."""

from __future__ import annotations

from events.codec import decode_event, encode_event
from events.types import (
    ChunkedDocumentReference,
    DocumentReference,
    DocumentsChunkedEvent,
    DocumentsUploadedEvent,
    EmbeddingGeneratedReference,
    EmbeddingsGeneratedEvent,
    EntitiesExtractedEvent,
    EntitiesValidatedEvent,
    ExtractedDocumentReference,
    GraphUpdatedDocumentReference,
    GraphUpdatedEvent,
    LlmCompletedEvent,
    LlmCompletionReference,
    RagCompletedEvent,
    RagCompletionReference,
    ValidatedDocumentReference,
    VectorIndexedReference,
    VectorsIndexedEvent,
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


def test_event_codec_round_trips_entities_validated_event() -> None:
    event = EntitiesValidatedEvent(
        documents=[
            ValidatedDocumentReference(
                knowledge_base_id="kb-1",
                source_document_id="doc-1",
                parsed_document_id="parsed-1",
                extraction_result_id="extract-1",
                validation_report_id="validate-1",
                valid_entity_count=2,
                valid_relationship_count=1,
                entity_error_count=0,
                relationship_error_count=0,
                storage_key="knowledgebases/kb-1/documents/doc-1/claims.json",
                parsed_document_storage_key="knowledgebases/kb-1/parsed/parsed-1.json",
                chunks_storage_key="knowledgebases/kb-1/chunks/parsed-1.json",
                extraction_storage_key="knowledgebases/kb-1/extractions/extract-1.json",
                validation_storage_key="knowledgebases/kb-1/validations/extract-1.json",
            )
        ]
    )

    encoded = encode_event(event)
    decoded = decode_event(encoded)

    assert decoded == event
    assert decoded.event_type == "entities.validated"


def test_event_codec_round_trips_graph_updated_event() -> None:
    event = GraphUpdatedEvent(
        documents=[
            GraphUpdatedDocumentReference(
                knowledge_base_id="kb-1",
                source_document_id="doc-1",
                parsed_document_id="parsed-1",
                extraction_result_id="extract-1",
                validation_report_id="validate-1",
                upserted_entity_count=2,
                upserted_relationship_count=1,
                validation_storage_key="knowledgebases/kb-1/validations/extract-1.json",
                graph_update_storage_key="knowledgebases/kb-1/graph_updates/extract-1.json",
            )
        ]
    )

    encoded = encode_event(event)
    decoded = decode_event(encoded)

    assert decoded == event
    assert decoded.event_type == "graph.updated"


def test_event_codec_round_trips_vectors_indexed_event() -> None:
    event = VectorsIndexedEvent(
        records=[
            VectorIndexedReference(
                knowledge_base_id="kb-1",
                record_id="record-1",
                content_id="content-1",
                dimension=3,
            )
        ]
    )

    encoded = encode_event(event)
    decoded = decode_event(encoded)

    assert decoded == event
    assert decoded.event_type == "vectors.indexed"


def test_event_codec_round_trips_llm_completed_event() -> None:
    event = LlmCompletedEvent(
        completions=[
            LlmCompletionReference(
                knowledge_base_id="kb-1",
                request_id="request-1",
                model_name="in-memory-test-model",
                provider="in-memory",
                message_count=2,
                completion_length=24,
            )
        ]
    )

    encoded = encode_event(event)
    decoded = decode_event(encoded)

    assert decoded == event
    assert decoded.event_type == "llm.completed"


def test_event_codec_round_trips_embeddings_generated_event() -> None:
    event = EmbeddingsGeneratedEvent(
        batches=[
            EmbeddingGeneratedReference(
                knowledge_base_id="kb-1",
                request_id="request-1",
                item_count=2,
                dimensions=4,
                model_name="in-memory-embedder",
            )
        ]
    )

    encoded = encode_event(event)
    decoded = decode_event(encoded)

    assert decoded == event
    assert decoded.event_type == "embeddings.generated"


def test_event_codec_round_trips_rag_completed_event() -> None:
    event = RagCompletedEvent(
        replies=[
            RagCompletionReference(
                knowledge_base_id="kb-1",
                request_id="request-1",
                provider="in-memory",
                model_name="in-memory-rag-model",
                context_item_count=2,
                citation_count=2,
                answer_length=84,
            )
        ]
    )

    encoded = encode_event(event)
    decoded = decode_event(encoded)

    assert decoded == event
    assert decoded.event_type == "rag.completed"