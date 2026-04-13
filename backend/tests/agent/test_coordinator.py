"""Tests for the worker coordinator ingestion wiring."""

from __future__ import annotations

from agent.coordinator import (
    drain_ingestion_events,
    handle_documents_chunked,
    handle_documents_parsed,
    handle_entities_extracted,
    handle_entities_validated,
)
from events.adapters.in_memory import InMemoryEventBus
from events.types import (
    ChunkedDocumentReference,
    DocumentsChunkedEvent,
    DocumentsParsedEvent,
    EntitiesExtractedEvent,
    EntitiesValidatedEvent,
    ExtractedDocumentReference,
    GraphUpdatedEvent,
    ParsedDocumentReference,
    ValidatedDocumentReference,
)
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.service import create_graph_service
from ingestion.chunker import ChunkingResult, create_document_chunker
from ingestion.extractor import create_document_extractor
from ingestion.models import ExtractionResult, ParsedDocument, ValidationReport
from ingestion.orchestrators.parser import DocumentParsingOrchestrator
from ingestion.parsers.registry import create_default_registry
from ingestion.parsers.remote import HttpxRemoteDocumentFetcher
from ingestion.service import IngestionService
from ingestion.service_models import DocumentSubmission
from ingestion.validator import create_extraction_validator
from storage.adapters.in_memory import InMemoryObjectStore


def test_drain_ingestion_events_processes_uploaded_documents() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    chunker = create_document_chunker()
    extractor = create_document_extractor([])
    validator = create_extraction_validator([], [])
    graph_service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=object_store,
        event_bus=event_bus,
    )
    service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=event_bus,
    )

    service.register_documents(
        "kb-1",
        [
            DocumentSubmission(
                filename="claims.json",
                content=b'{"claim_id": "42"}',
                content_type="application/json",
            )
        ],
    )

    processed = drain_ingestion_events(
        event_bus,
        service,
        chunker,
        extractor,
        validator,
        graph_service,
        object_store,
        consumer_group="test-workers",
        consumer_name="worker-1",
    )

    assert processed == 1
    assert any(isinstance(event, DocumentsParsedEvent) for event in event_bus.published_events)


def test_drain_ingestion_events_processes_parsed_documents_into_chunks() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    chunker = create_document_chunker()
    extractor = create_document_extractor([])
    validator = create_extraction_validator([], [])
    graph_service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=object_store,
        event_bus=event_bus,
    )
    service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=event_bus,
    )

    service.register_documents(
        "kb-1",
        [
            DocumentSubmission(
                filename="claims.json",
                content=b'{"claim_id": "42"}',
                content_type="application/json",
            )
        ],
    )

    parsed_count = drain_ingestion_events(
        event_bus,
        service,
        chunker,
        extractor,
        validator,
        graph_service,
        object_store,
        consumer_group="test-workers",
        consumer_name="worker-1",
    )
    chunked_count = drain_ingestion_events(
        event_bus,
        service,
        chunker,
        extractor,
        validator,
        graph_service,
        object_store,
        consumer_group="test-workers",
        consumer_name="worker-1",
    )

    assert parsed_count == 1
    assert chunked_count == 1
    chunked_events = [
        event for event in event_bus.published_events if isinstance(event, DocumentsChunkedEvent)
    ]
    assert len(chunked_events) == 1
    assert chunked_events[0].documents[0].chunk_count >= 1
    assert chunked_events[0].documents[0].chunks_storage_key is not None

    stored_chunks = object_store.get_bytes(chunked_events[0].documents[0].chunks_storage_key or "")
    chunking_result = ChunkingResult.model_validate_json(stored_chunks.content)
    assert chunking_result.parsed_document_id == chunked_events[0].documents[0].parsed_document_id
    assert len(chunking_result.chunks) == chunked_events[0].documents[0].chunk_count


def test_drain_ingestion_events_processes_chunked_documents_into_extractions() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    chunker = create_document_chunker()
    extractor = create_document_extractor([])
    validator = create_extraction_validator([], [])
    graph_service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=object_store,
        event_bus=event_bus,
    )
    service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=event_bus,
    )

    service.register_documents(
        "kb-1",
        [
            DocumentSubmission(
                filename="claims.json",
                content=b'{"claim_id": "42"}',
                content_type="application/json",
            )
        ],
    )

    drain_ingestion_events(
        event_bus,
        service,
        chunker,
        extractor,
        validator,
        graph_service,
        object_store,
        consumer_group="test-workers",
        consumer_name="worker-1",
    )
    drain_ingestion_events(
        event_bus,
        service,
        chunker,
        extractor,
        validator,
        graph_service,
        object_store,
        consumer_group="test-workers",
        consumer_name="worker-1",
    )
    extracted_count = drain_ingestion_events(
        event_bus,
        service,
        chunker,
        extractor,
        validator,
        graph_service,
        object_store,
        consumer_group="test-workers",
        consumer_name="worker-1",
    )

    assert extracted_count == 1
    extracted_events = [
        event for event in event_bus.published_events if isinstance(event, EntitiesExtractedEvent)
    ]
    assert len(extracted_events) == 1
    assert extracted_events[0].documents[0].extraction_storage_key is not None

    stored_extraction = object_store.get_bytes(
        extracted_events[0].documents[0].extraction_storage_key or ""
    )
    extraction_result = ExtractionResult.model_validate_json(stored_extraction.content)
    assert extraction_result.parsed_document_id == extracted_events[0].documents[0].parsed_document_id


def test_drain_ingestion_events_processes_extracted_documents_into_validations() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    chunker = create_document_chunker()
    extractor = create_document_extractor([])
    validator = create_extraction_validator([], [])
    graph_service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=object_store,
        event_bus=event_bus,
    )
    service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=event_bus,
    )

    service.register_documents(
        "kb-1",
        [
            DocumentSubmission(
                filename="claims.json",
                content=b'{"claim_id": "42"}',
                content_type="application/json",
            )
        ],
    )

    for _ in range(3):
        drain_ingestion_events(
            event_bus,
            service,
            chunker,
            extractor,
            validator,
            graph_service,
            object_store,
            consumer_group="test-workers",
            consumer_name="worker-1",
        )
    validated_count = drain_ingestion_events(
        event_bus,
        service,
        chunker,
        extractor,
        validator,
        graph_service,
        object_store,
        consumer_group="test-workers",
        consumer_name="worker-1",
    )

    assert validated_count == 1
    validated_events = [
        event for event in event_bus.published_events if isinstance(event, EntitiesValidatedEvent)
    ]
    assert len(validated_events) == 1
    assert validated_events[0].documents[0].validation_storage_key is not None

    stored_report = object_store.get_bytes(validated_events[0].documents[0].validation_storage_key or "")
    report = ValidationReport.model_validate_json(stored_report.content)
    assert report.extraction_result_id == validated_events[0].documents[0].extraction_result_id


def test_handle_documents_parsed_publishes_chunked_event() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    chunker = create_document_chunker()
    parsed_document = ParsedDocument(
        id="parsed-1",
        source_document_id="doc-1",
        text_content="Claim 42 was filed by provider A.",
        parser_name="test-parser",
    )
    storage_key = "knowledgebases/kb-1/parsed/parsed-1.json"
    object_store.put_bytes(
        storage_key,
        parsed_document.model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    processed = handle_documents_parsed(
        DocumentsParsedEvent(
            documents=[
                ParsedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-1",
                    parsed_document_id="parsed-1",
                    parser_name="test-parser",
                    storage_key="knowledgebases/kb-1/documents/doc-1/claims.txt",
                    parsed_document_storage_key=storage_key,
                )
            ]
        ),
        document_chunker=chunker,
        object_store=object_store,
        event_bus=event_bus,
    )

    assert processed == 1
    assert isinstance(event_bus.published_events[-1], DocumentsChunkedEvent)
    reference = event_bus.published_events[-1].documents[0]
    assert reference.parsed_document_storage_key == storage_key
    assert reference.chunks_storage_key == "knowledgebases/kb-1/chunks/parsed-1.json"
    assert reference.chunk_count >= 1

    stored_chunks = object_store.get_bytes(reference.chunks_storage_key or "")
    chunking_result = ChunkingResult.model_validate_json(stored_chunks.content)
    assert chunking_result.strategy_used == reference.strategy
    assert len(chunking_result.chunks) == reference.chunk_count


def test_handle_documents_chunked_publishes_entities_extracted_event() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    chunking_result = ChunkingResult(
        source_document_id="doc-1",
        parsed_document_id="parsed-1",
        strategy_used="StructuredRecordChunker",
        chunks=[],
    )
    chunks_storage_key = "knowledgebases/kb-1/chunks/parsed-1.json"
    object_store.put_bytes(
        chunks_storage_key,
        chunking_result.model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    processed = handle_documents_chunked(
        DocumentsChunkedEvent(
            documents=[
                ChunkedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-1",
                    parsed_document_id="parsed-1",
                    chunk_count=0,
                    strategy="StructuredRecordChunker",
                    chunks_storage_key=chunks_storage_key,
                )
            ]
        ),
        document_extractor=create_document_extractor([]),
        object_store=object_store,
        event_bus=event_bus,
    )

    assert processed == 1
    assert isinstance(event_bus.published_events[-1], EntitiesExtractedEvent)
    reference = event_bus.published_events[-1].documents[0]
    assert reference.extraction_storage_key is not None

    stored_extraction = object_store.get_bytes(reference.extraction_storage_key)
    extraction_result = ExtractionResult.model_validate_json(stored_extraction.content)
    assert extraction_result.source_document_id == "doc-1"


def test_handle_entities_extracted_publishes_entities_validated_event() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    extraction_result = ExtractionResult(
        id="extract-1",
        source_document_id="doc-1",
        parsed_document_id="parsed-1",
    )
    extraction_storage_key = "knowledgebases/kb-1/extractions/extract-1.json"
    object_store.put_bytes(
        extraction_storage_key,
        extraction_result.model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    processed = handle_entities_extracted(
        EntitiesExtractedEvent(
            documents=[
                ExtractedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-1",
                    parsed_document_id="parsed-1",
                    extraction_result_id="extract-1",
                    entity_count=0,
                    relationship_count=0,
                    extraction_storage_key=extraction_storage_key,
                )
            ]
        ),
        extraction_validator=create_extraction_validator([], []),
        object_store=object_store,
        event_bus=event_bus,
    )

    assert processed == 1
    assert isinstance(event_bus.published_events[-1], EntitiesValidatedEvent)
    reference = event_bus.published_events[-1].documents[0]
    assert reference.validation_storage_key == "knowledgebases/kb-1/validations/extract-1.json"


def test_handle_entities_validated_publishes_graph_updated_event() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    validation_report = ValidationReport(
        id="validate-1",
        extraction_result_id="extract-1",
        source_document_id="doc-1",
    )
    validation_storage_key = "knowledgebases/kb-1/validations/extract-1.json"
    object_store.put_bytes(
        validation_storage_key,
        validation_report.model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    processed = handle_entities_validated(
        EntitiesValidatedEvent(
            documents=[
                ValidatedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-1",
                    parsed_document_id="parsed-1",
                    extraction_result_id="extract-1",
                    validation_report_id="validate-1",
                    valid_entity_count=0,
                    valid_relationship_count=0,
                    entity_error_count=0,
                    relationship_error_count=0,
                    validation_storage_key=validation_storage_key,
                )
            ]
        ),
        graph_service=create_graph_service(
            InMemoryGraphRepository(),
            object_store=object_store,
            event_bus=event_bus,
        ),
        object_store=object_store,
    )

    assert processed == 1
    assert isinstance(event_bus.published_events[-1], GraphUpdatedEvent)
    reference = event_bus.published_events[-1].documents[0]
    assert reference.graph_update_storage_key == "knowledgebases/kb-1/graph_updates/extract-1.json"


def test_drain_ingestion_events_processes_validated_documents_into_graph_updates() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    chunker = create_document_chunker()
    extractor = create_document_extractor([])
    validator = create_extraction_validator([], [])
    graph_service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=object_store,
        event_bus=event_bus,
    )
    service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=event_bus,
    )

    service.register_documents(
        "kb-1",
        [
            DocumentSubmission(
                filename="claims.json",
                content=b'{"claim_id": "42"}',
                content_type="application/json",
            )
        ],
    )

    for _ in range(4):
        drain_ingestion_events(
            event_bus,
            service,
            chunker,
            extractor,
            validator,
            graph_service,
            object_store,
            consumer_group="test-workers",
            consumer_name="worker-1",
        )
    graph_count = drain_ingestion_events(
        event_bus,
        service,
        chunker,
        extractor,
        validator,
        graph_service,
        object_store,
        consumer_group="test-workers",
        consumer_name="worker-1",
    )

    assert graph_count == 1
    graph_events = [
        event for event in event_bus.published_events if isinstance(event, GraphUpdatedEvent)
    ]
    assert len(graph_events) == 1
    assert graph_events[0].documents[0].graph_update_storage_key is not None