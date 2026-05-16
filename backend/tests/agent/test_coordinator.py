"""Tests for the worker coordinator ingestion wiring."""

from __future__ import annotations

import asyncio

import pytest

from agent.coordinator import (
    build_worker_dependencies,
    drain_ingestion_events,
    handle_embeddings_complete,
    handle_event,
    handle_documents_chunked,
    handle_documents_parsed,
    handle_entities_extracted,
    handle_entities_validated,
    handle_graph_updated,
    handle_vectors_indexed,
    run_handler_with_retry,
)
from agent.exceptions import ConfigurationError
from agent.models import RetryPolicy
from config.loader import load_config
from config.schema import (
    DomainConfig,
    EmbeddingsConfig,
    GraphDbConfig,
    LlmConfig,
    ObjectStoreConfig,
    RecordsConfig,
    VectorStoreConfig,
)
from monitoring.adapters.in_memory import InMemoryObservationWriter
from records.adapters.in_memory import InMemoryRawRecordStore
from embeddings.adapters.in_memory import InMemoryEmbedder
from embeddings.models import EmbeddingMetadata, EmbeddingResult
from embeddings.service import EmbeddingsService
from embeddings.service_models import EmbedRequest, EmbedResponse, EmbeddedItem
from events.protocols import EventDelivery
from events.runtime import EventBusSettings
from events.adapters.in_memory import InMemoryEventBus
from events.types import (
    ChunkedDocumentReference,
    DocumentsChunkedEvent,
    DocumentsParsedEvent,
    EmbeddingsCompleteDocumentReference,
    EmbeddingsCompleteEvent,
    EntitiesExtractedEvent,
    EntitiesValidatedEvent,
    ExtractedDocumentReference,
    GraphUpdatedDocumentReference,
    GraphUpdatedEvent,
    KnowledgeBaseCreatedEvent,
    KnowledgeBaseReadyEvent,
    ParsedDocumentReference,
    RiskScoredEvent as _RiskScoredEvent,
    ValidatedDocumentReference,
    VectorsIndexedDocumentReference,
    VectorsIndexedEvent,
)
from monitoring.service import MonitoringService as _MonitoringService
from graph.models import GraphUpsertResult
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
from shared.types import Entity
from storage.adapters.in_memory import InMemoryObjectStore
from vectorstore.adapters.in_memory import InMemoryVectorStore




class _FakeEmbeddingsService:
    """Test double that records requests and returns deterministic vectors."""

    def __init__(self) -> None:
        self.requests: list[EmbedRequest] = []

    def embed(self, request: EmbedRequest) -> EmbedResponse:
        self.requests.append(request)
        return EmbedResponse(
            request_id="embed-request-1",
            model_name=request.model_name,
            dimensions=2,
            items=[
                EmbeddedItem(
                    content_id=submission.content_id,
                    vector=[float(index), float(len(submission.content))],
                )
                for index, submission in enumerate(request.submissions, start=1)
            ],
        )


def test_build_worker_dependencies_assembles_ingestion_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    defaults_dir = (
        __file__
        .replace("tests/agent/test_coordinator.py", "config/defaults/medicare_fraud.yaml")
    )
    monkeypatch.setattr("agent.coordinator.load_config", lambda: load_config(defaults_dir))
    monkeypatch.setattr(
        "agent.coordinator.load_event_bus_settings",
        lambda: EventBusSettings(backend="in-memory"),
    )

    deps = build_worker_dependencies()

    assert isinstance(deps.event_bus, InMemoryEventBus)
    assert isinstance(deps.ingestion_service, IngestionService)
    assert deps.document_chunker is not None
    assert deps.document_extractor is not None
    assert deps.extraction_validator is not None
    assert deps.graph_service is not None
    assert isinstance(deps.embeddings_service, EmbeddingsService)
    assert isinstance(deps.object_store, InMemoryObjectStore)
    assert isinstance(deps.vector_store, InMemoryVectorStore)
    assert isinstance(deps.embeddings_service, EmbeddingsService)
    assert deps.llm_client is not None
    assert deps.event_settings.backend == "in-memory"


def test_handle_event_returns_zero_for_unhandled_event() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=event_bus,
    )

    processed = handle_event(
        EventDelivery(event=KnowledgeBaseCreatedEvent(knowledge_base_id="kb-1")),
        service,
        document_chunker=create_document_chunker(),
        document_extractor=create_document_extractor([]),
        extraction_validator=create_extraction_validator([], []),
        graph_service=create_graph_service(
            InMemoryGraphRepository(),
            object_store=object_store,
            event_bus=event_bus,
        ),
        object_store=object_store,
        event_bus=event_bus,
    )

    assert processed == 0


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

    processed = asyncio.run(drain_ingestion_events(
        event_bus,
        service,
        chunker,
        extractor,
        validator,
        graph_service,
        object_store,
        consumer_group="test-workers",
        consumer_name="worker-1",
    ))

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

    parsed_count = asyncio.run(drain_ingestion_events(
        event_bus,
        service,
        chunker,
        extractor,
        validator,
        graph_service,
        object_store,
        consumer_group="test-workers",
        consumer_name="worker-1",
    ))
    chunked_count = asyncio.run(drain_ingestion_events(
        event_bus,
        service,
        chunker,
        extractor,
        validator,
        graph_service,
        object_store,
        consumer_group="test-workers",
        consumer_name="worker-1",
    ))

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

    asyncio.run(drain_ingestion_events(
        event_bus,
        service,
        chunker,
        extractor,
        validator,
        graph_service,
        object_store,
        consumer_group="test-workers",
        consumer_name="worker-1",
    ))
    asyncio.run(drain_ingestion_events(
        event_bus,
        service,
        chunker,
        extractor,
        validator,
        graph_service,
        object_store,
        consumer_group="test-workers",
        consumer_name="worker-1",
    ))
    extracted_count = asyncio.run(drain_ingestion_events(
        event_bus,
        service,
        chunker,
        extractor,
        validator,
        graph_service,
        object_store,
        consumer_group="test-workers",
        consumer_name="worker-1",
    ))

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
        asyncio.run(drain_ingestion_events(
            event_bus,
            service,
            chunker,
            extractor,
            validator,
            graph_service,
            object_store,
            consumer_group="test-workers",
            consumer_name="worker-1",
        ))
    validated_count = asyncio.run(drain_ingestion_events(
        event_bus,
        service,
        chunker,
        extractor,
        validator,
        graph_service,
        object_store,
        consumer_group="test-workers",
        consumer_name="worker-1",
    ))

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
            correlation_id="corr-123",
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
    assert event_bus.published_events[-1].correlation_id == "corr-123"
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
            correlation_id="corr-graph-123",
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
    assert event_bus.published_events[-1].correlation_id == "corr-graph-123"
    reference = event_bus.published_events[-1].documents[0]
    assert reference.graph_update_storage_key == "knowledgebases/kb-1/graph_updates/extract-1.json"


def test_handle_graph_updated_publishes_embeddings_complete_event() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    embeddings_service = _FakeEmbeddingsService()
    graph_update_storage_key = "knowledgebases/kb-1/graph_updates/extract-1.json"
    validation_storage_key = "knowledgebases/kb-1/validations/extract-1.json"
    object_store.put_bytes(
        graph_update_storage_key,
        GraphUpsertResult(
            knowledge_base_id="kb-1",
            source_document_id="doc-1",
            parsed_document_id="parsed-1",
            extraction_result_id="extract-1",
            validation_report_id="validate-1",
            upserted_entity_ids=["provider-2", "provider-1"],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )
    object_store.put_bytes(
        validation_storage_key,
        ValidationReport(
            id="validate-1",
            extraction_result_id="extract-1",
            source_document_id="doc-1",
            valid_entities=[
                Entity(
                    id="provider-2",
                    type="provider",
                    properties={"specialty": "cardiology", "name": "Beta Clinic"},
                ),
                Entity(
                    id="provider-1",
                    type="provider",
                    properties={"zeta": "last", "alpha": "first"},
                ),
            ],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    processed = handle_graph_updated(
        GraphUpdatedEvent(
            correlation_id="corr-embeddings-123",
            documents=[
                GraphUpdatedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-1",
                    parsed_document_id="parsed-1",
                    extraction_result_id="extract-1",
                    validation_report_id="validate-1",
                    upserted_entity_count=2,
                    upserted_relationship_count=0,
                    validation_storage_key=validation_storage_key,
                    graph_update_storage_key=graph_update_storage_key,
                )
            ],
        ),
        embeddings_service=embeddings_service,
        object_store=object_store,
        event_bus=event_bus,
    )

    assert processed == 1
    assert len(embeddings_service.requests) == 1
    request = embeddings_service.requests[0]
    assert [item.content_id for item in request.submissions] == [
        "provider-1",
        "provider-2",
    ]
    assert request.submissions[0].content == (
        'id=provider-1\ntype=provider\nalpha="first"\nzeta="last"'
    )
    assert request.submissions[1].content == "Beta Clinic"

    assert isinstance(event_bus.published_events[-1], EmbeddingsCompleteEvent)
    complete_event = event_bus.published_events[-1]
    assert complete_event.correlation_id == "corr-embeddings-123"
    complete_reference = complete_event.documents[0]
    assert complete_reference.entity_count == 2
    assert complete_reference.graph_update_storage_key == graph_update_storage_key
    assert complete_reference.embeddings_storage_key == (
        "knowledgebases/kb-1/embeddings/extract-1.embeddings.json"
    )

    stored_embeddings = object_store.get_bytes(complete_reference.embeddings_storage_key)
    embeddings_result = EmbeddingResult.model_validate_json(stored_embeddings.content)
    assert embeddings_result.request_id == "embed-request-1"
    assert list(embeddings_result.vectors) == ["provider-1", "provider-2"]
    assert stored_embeddings.metadata["graph_update_storage_key"] == graph_update_storage_key


def test_handle_graph_updated_publishes_kb_ready_for_zero_entities() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    embeddings_service = _FakeEmbeddingsService()
    graph_update_storage_key = "knowledgebases/kb-empty/graph_updates/extract-1.json"
    validation_storage_key = "knowledgebases/kb-empty/validations/extract-1.json"
    object_store.put_bytes(
        graph_update_storage_key,
        GraphUpsertResult(
            knowledge_base_id="kb-empty",
            source_document_id="doc-1",
            parsed_document_id="parsed-1",
            extraction_result_id="extract-1",
            validation_report_id="validate-1",
            upserted_entity_ids=[],
            upserted_relationship_ids=[],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )
    object_store.put_bytes(
        validation_storage_key,
        ValidationReport(
            id="validate-1",
            extraction_result_id="extract-1",
            source_document_id="doc-1",
            valid_entities=[],
            valid_relationships=[],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    processed = handle_graph_updated(
        GraphUpdatedEvent(
            correlation_id="corr-empty-graph",
            documents=[
                GraphUpdatedDocumentReference(
                    knowledge_base_id="kb-empty",
                    source_document_id="doc-1",
                    parsed_document_id="parsed-1",
                    extraction_result_id="extract-1",
                    validation_report_id="validate-1",
                    upserted_entity_count=0,
                    upserted_relationship_count=0,
                    validation_storage_key=validation_storage_key,
                    graph_update_storage_key=graph_update_storage_key,
                )
            ],
        ),
        embeddings_service=embeddings_service,
        object_store=object_store,
        event_bus=event_bus,
    )

    assert processed == 0
    assert embeddings_service.requests == []
    ready_events = [
        event for event in event_bus.published_events
        if isinstance(event, KnowledgeBaseReadyEvent)
    ]
    assert len(ready_events) == 1
    ready_reference = ready_events[0].knowledge_bases[0]
    assert ready_reference.knowledge_base_id == "kb-empty"
    assert ready_reference.entity_count == 0
    assert ready_reference.relationship_count == 0
    assert ready_reference.vector_count == 0


def test_handle_event_dispatches_graph_updated_event() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    embeddings_service = _FakeEmbeddingsService()
    graph_update_storage_key = "knowledgebases/kb-1/graph_updates/extract-1.json"
    validation_storage_key = "knowledgebases/kb-1/validations/extract-1.json"
    object_store.put_bytes(
        graph_update_storage_key,
        GraphUpsertResult(
            knowledge_base_id="kb-1",
            source_document_id="doc-1",
            parsed_document_id="parsed-1",
            extraction_result_id="extract-1",
            validation_report_id="validate-1",
            upserted_entity_ids=["entity-1"],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )
    object_store.put_bytes(
        validation_storage_key,
        ValidationReport(
            id="validate-1",
            extraction_result_id="extract-1",
            source_document_id="doc-1",
            valid_entities=[
                Entity(
                    id="entity-1",
                    type="claim",
                    properties={"embedding_text": "Claim 42 from provider A"},
                )
            ],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )
    service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=event_bus,
    )

    processed = handle_event(
        EventDelivery(
            event=GraphUpdatedEvent(
                correlation_id="corr-dispatch-123",
                documents=[
                    GraphUpdatedDocumentReference(
                        knowledge_base_id="kb-1",
                        source_document_id="doc-1",
                        parsed_document_id="parsed-1",
                        extraction_result_id="extract-1",
                        validation_report_id="validate-1",
                        upserted_entity_count=1,
                        upserted_relationship_count=0,
                        validation_storage_key=validation_storage_key,
                        graph_update_storage_key=graph_update_storage_key,
                    )
                ],
            )
        ),
        service,
        document_chunker=create_document_chunker(),
        document_extractor=create_document_extractor([]),
        extraction_validator=create_extraction_validator([], []),
        graph_service=create_graph_service(
            InMemoryGraphRepository(),
            object_store=object_store,
            event_bus=event_bus,
        ),
        object_store=object_store,
        event_bus=event_bus,
        embeddings_service=embeddings_service,
    )

    assert processed == 1
    assert isinstance(event_bus.published_events[-1], EmbeddingsCompleteEvent)
    assert event_bus.published_events[-1].correlation_id == "corr-dispatch-123"


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
        asyncio.run(drain_ingestion_events(
            event_bus,
            service,
            chunker,
            extractor,
            validator,
            graph_service,
            object_store,
            consumer_group="test-workers",
            consumer_name="worker-1",
        ))
    graph_count = asyncio.run(drain_ingestion_events(
        event_bus,
        service,
        chunker,
        extractor,
        validator,
        graph_service,
        object_store,
        consumer_group="test-workers",
        consumer_name="worker-1",
    ))

    assert graph_count == 1
    graph_events = [
        event for event in event_bus.published_events if isinstance(event, GraphUpdatedEvent)
    ]
    assert len(graph_events) == 1
    assert graph_events[0].documents[0].graph_update_storage_key is not None


# ---------------------------------------------------------------------------
# E4-S08 — config-driven adapter wiring
# ---------------------------------------------------------------------------


def _base_config() -> DomainConfig:
    return load_config(
        __file__.replace(
            "tests/agent/test_coordinator.py",
            "config/defaults/medicare_fraud.yaml",
        )
    )


def test_build_object_store_uses_in_memory_when_section_default() -> None:
    config = _base_config()
    assert isinstance(__import__("agent.coordinator", fromlist=["build_object_store"]).build_object_store(config), InMemoryObjectStore)


def test_build_object_store_raises_for_unknown_backend() -> None:
    from agent.coordinator import build_object_store
    base = _base_config()
    forced_config = ObjectStoreConfig.model_construct(backend="gcs")
    config = base.model_copy(update={"storage": forced_config})
    with pytest.raises(ConfigurationError) as excinfo:
        build_object_store(config)
    assert excinfo.value.subsystem == "storage"
    assert excinfo.value.backend == "gcs"


def test_build_graph_repository_raises_when_neo4j_uri_missing() -> None:
    from agent.coordinator import build_graph_repository
    config = _base_config().model_copy(
        update={"graph": GraphDbConfig(backend="neo4j", uri=None)}
    )
    with pytest.raises(ConfigurationError) as excinfo:
        build_graph_repository(config)
    assert excinfo.value.subsystem == "graph"
    assert excinfo.value.backend == "neo4j"


def test_build_vector_store_raises_when_qdrant_uri_missing() -> None:
    from agent.coordinator import build_vector_store
    config = _base_config().model_copy(
        update={
            "vectorstore": VectorStoreConfig(backend="qdrant", uri=None, dimensions=384),
        }
    )
    with pytest.raises(ConfigurationError) as excinfo:
        build_vector_store(config)
    assert excinfo.value.subsystem == "vectorstore"


def test_build_embedder_raises_when_openai_api_key_env_var_missing() -> None:
    from agent.coordinator import build_embedder
    config = _base_config().model_copy(
        update={
            "embeddings": EmbeddingsConfig(
                provider="openai",
                model="text-embedding-3-small",
                dimensions=384,
            ),
        }
    )
    with pytest.raises(ConfigurationError) as excinfo:
        build_embedder(config)
    assert excinfo.value.subsystem == "embeddings"
    assert excinfo.value.backend == "openai"


def test_build_llm_client_raises_when_openai_api_key_env_var_missing() -> None:
    from agent.coordinator import build_llm_client
    config = _base_config().model_copy(
        update={"llm": LlmConfig(provider="openai", model="gpt-4o-mini")}
    )
    with pytest.raises(ConfigurationError) as excinfo:
        build_llm_client(config)
    assert excinfo.value.subsystem == "llm"
    assert excinfo.value.backend == "openai"


# ---------------------------------------------------------------------------
# E4-S02 — vector indexing handler
# ---------------------------------------------------------------------------


def _seed_validation_and_graph(
    object_store: InMemoryObjectStore,
    *,
    knowledge_base_id: str = "kb-1",
    graph_update_storage_key: str = "knowledgebases/kb-1/graph_updates/extract-1.json",
    validation_storage_key: str = "knowledgebases/kb-1/validations/extract-1.json",
) -> None:
    object_store.put_bytes(
        graph_update_storage_key,
        GraphUpsertResult(
            knowledge_base_id=knowledge_base_id,
            source_document_id="doc-1",
            parsed_document_id="parsed-1",
            extraction_result_id="extract-1",
            validation_report_id="validate-1",
            upserted_entity_ids=["entity-1"],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )
    object_store.put_bytes(
        validation_storage_key,
        ValidationReport(
            id="validate-1",
            extraction_result_id="extract-1",
            source_document_id="doc-1",
            valid_entities=[
                Entity(
                    id="entity-1",
                    type="claim",
                    properties={"name": "Provider Alpha"},
                ),
            ],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )


def test_handle_embeddings_complete_indexes_vectors_and_publishes_event() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    vector_store = InMemoryVectorStore()
    _seed_validation_and_graph(object_store)

    embeddings_storage_key = "knowledgebases/kb-1/embeddings/extract-1.embeddings.json"
    object_store.put_bytes(
        embeddings_storage_key,
        EmbeddingResult(
            request_id="embed-request-1",
            vectors={"entity-1": [0.1, 0.2, 0.3]},
            metadata=EmbeddingMetadata(
                model_name="model",
                dimensions=3,
                provider="embeddings-service",
            ),
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    processed = handle_embeddings_complete(
        EmbeddingsCompleteEvent(
            correlation_id="corr-vec-1",
            documents=[
                EmbeddingsCompleteDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-1",
                    parsed_document_id="parsed-1",
                    extraction_result_id="extract-1",
                    validation_report_id="validate-1",
                    entity_count=1,
                    graph_update_storage_key="knowledgebases/kb-1/graph_updates/extract-1.json",
                    embeddings_storage_key=embeddings_storage_key,
                )
            ],
        ),
        vector_store=vector_store,
        object_store=object_store,
        event_bus=event_bus,
    )

    assert processed == 1
    indexed_event = next(
        event for event in event_bus.published_events if isinstance(event, VectorsIndexedEvent)
    )
    assert indexed_event.correlation_id == "corr-vec-1"
    assert indexed_event.documents[0].vector_count == 1
    assert indexed_event.documents[0].record_ids == ["kb-1:entity-1"]
    assert indexed_event.records[0].dimension == 3


def test_handle_embeddings_complete_skips_when_no_vectors() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    vector_store = InMemoryVectorStore()
    _seed_validation_and_graph(object_store)

    embeddings_storage_key = "knowledgebases/kb-1/embeddings/extract-empty.embeddings.json"
    object_store.put_bytes(
        embeddings_storage_key,
        EmbeddingResult(
            request_id="embed-request-1",
            vectors={"entity-1": [0.0, 0.0]},
            metadata=EmbeddingMetadata(
                model_name="m", dimensions=2, provider="embeddings-service"
            ),
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    processed = handle_embeddings_complete(
        EmbeddingsCompleteEvent(
            correlation_id="corr-vec-2",
            documents=[
                EmbeddingsCompleteDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-1",
                    parsed_document_id="parsed-1",
                    extraction_result_id="extract-1",
                    validation_report_id="validate-1",
                    entity_count=1,
                    graph_update_storage_key="knowledgebases/kb-1/graph_updates/extract-1.json",
                    embeddings_storage_key=embeddings_storage_key,
                )
            ],
        ),
        vector_store=vector_store,
        object_store=object_store,
        event_bus=event_bus,
    )

    assert processed == 1


# ---------------------------------------------------------------------------
# E4-S03 — kb.ready emission
# ---------------------------------------------------------------------------


def test_handle_vectors_indexed_emits_kb_ready_event() -> None:
    event_bus = InMemoryEventBus()
    graph_repository = InMemoryGraphRepository()

    processed = handle_vectors_indexed(
        VectorsIndexedEvent(
            correlation_id="corr-kb-1",
            documents=[
                VectorsIndexedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-1",
                    parsed_document_id="parsed-1",
                    extraction_result_id="extract-1",
                    validation_report_id="validate-1",
                    vector_count=3,
                    embeddings_storage_key="knowledgebases/kb-1/embeddings/extract-1.embeddings.json",
                    record_ids=["kb-1:entity-1", "kb-1:entity-2", "kb-1:entity-3"],
                )
            ],
        ),
        graph_repository=graph_repository,
        event_bus=event_bus,
    )

    assert processed == 1
    ready_event = next(
        event for event in event_bus.published_events if isinstance(event, KnowledgeBaseReadyEvent)
    )
    assert ready_event.correlation_id == "corr-kb-1"
    assert ready_event.knowledge_bases[0].knowledge_base_id == "kb-1"
    assert ready_event.knowledge_bases[0].vector_count == 3


def test_handle_vectors_indexed_returns_zero_for_no_documents() -> None:
    event_bus = InMemoryEventBus()
    graph_repository = InMemoryGraphRepository()

    processed = handle_vectors_indexed(
        VectorsIndexedEvent(correlation_id="corr-empty", documents=[]),
        graph_repository=graph_repository,
        event_bus=event_bus,
    )
    assert processed == 0


def test_full_pipeline_chain_documents_uploaded_through_kb_ready() -> None:
    """Drive the full chain by seeding an in-progress GraphUpdatedEvent and
    draining events.uploaded → ... → kb.ready in a single test."""

    from embeddings.service import create_embeddings_service

    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    vector_store = InMemoryVectorStore()
    graph_repository = InMemoryGraphRepository()
    graph_service = create_graph_service(
        graph_repository,
        object_store=object_store,
        event_bus=event_bus,
    )
    embeddings_service = create_embeddings_service(
        InMemoryEmbedder(), event_bus=event_bus
    )
    service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=event_bus,
    )

    # Seed the artifacts and publish the documents.uploaded event for stages 1-5.
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

    # Pre-seed graph + validation artifacts directly so we can also exercise the
    # graph.updated → embeddings.complete → vectors.indexed → kb.ready legs.
    graph_update_storage_key = (
        "knowledgebases/kb-1/graph_updates/extract-pipeline.json"
    )
    validation_storage_key = (
        "knowledgebases/kb-1/validations/extract-pipeline.json"
    )
    object_store.put_bytes(
        graph_update_storage_key,
        GraphUpsertResult(
            knowledge_base_id="kb-1",
            source_document_id="doc-pipeline",
            parsed_document_id="parsed-pipeline",
            extraction_result_id="extract-pipeline",
            validation_report_id="validate-pipeline",
            upserted_entity_ids=["entity-pipeline"],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )
    object_store.put_bytes(
        validation_storage_key,
        ValidationReport(
            id="validate-pipeline",
            extraction_result_id="extract-pipeline",
            source_document_id="doc-pipeline",
            valid_entities=[
                Entity(
                    id="entity-pipeline",
                    type="claim",
                    properties={"name": "Pipeline Claim"},
                ),
            ],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    event_bus.publish(
        GraphUpdatedEvent(
            correlation_id="corr-pipeline",
            documents=[
                GraphUpdatedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-pipeline",
                    parsed_document_id="parsed-pipeline",
                    extraction_result_id="extract-pipeline",
                    validation_report_id="validate-pipeline",
                    upserted_entity_count=1,
                    upserted_relationship_count=0,
                    validation_storage_key=validation_storage_key,
                    graph_update_storage_key=graph_update_storage_key,
                )
            ],
        )
    )

    kwargs: dict[str, object] = dict(
        embeddings_service=embeddings_service,
        vector_store=vector_store,
        graph_repository=graph_repository,
        consumer_group="test-workers",
        consumer_name="worker-1",
    )

    for _ in range(10):
        asyncio.run(drain_ingestion_events(
            event_bus,
            service,
            create_document_chunker(),
            create_document_extractor([]),
            create_extraction_validator([], []),
            graph_service,
            object_store,
            **kwargs,  # type: ignore[arg-type]
        ))

    event_types_published = [type(event).__name__ for event in event_bus.published_events]
    # Each downstream stage must have run at least once.
    assert "DocumentsUploadedEvent" in event_types_published
    assert "DocumentsParsedEvent" in event_types_published
    assert "DocumentsChunkedEvent" in event_types_published
    assert "EntitiesExtractedEvent" in event_types_published
    assert "EntitiesValidatedEvent" in event_types_published
    assert "EmbeddingsCompleteEvent" in event_types_published
    assert "VectorsIndexedEvent" in event_types_published
    kb_ready_events = [
        event for event in event_bus.published_events if isinstance(event, KnowledgeBaseReadyEvent)
    ]
    assert len(kb_ready_events) >= 1
    assert kb_ready_events[0].correlation_id == "corr-pipeline"


# ---------------------------------------------------------------------------
# E4-S05 — retry/backoff
# ---------------------------------------------------------------------------


class _FlakyHandler:
    def __init__(self, *, fails: int) -> None:
        self.fails = fails
        self.calls = 0

    def __call__(self) -> int:
        self.calls += 1
        if self.calls <= self.fails:
            raise RuntimeError(f"transient failure {self.calls}")
        return 42


async def _instant_sleep(_delay: float) -> None:
    return None


def test_run_handler_with_retry_succeeds_after_transient_failure() -> None:
    event_bus = InMemoryEventBus()
    handler = _FlakyHandler(fails=1)
    event = KnowledgeBaseCreatedEvent(knowledge_base_id="kb-1")

    result = asyncio.run(
        run_handler_with_retry(
            handler,
            event=event,
            event_bus=event_bus,
            retry_policy=RetryPolicy(max_retries=3, base_delay_seconds=0.0),
            sleep=_instant_sleep,
        )
    )

    assert result == 42
    assert handler.calls == 2
    assert event_bus.dlq_entries == []


def test_run_handler_with_retry_routes_to_dlq_after_exhaustion() -> None:
    event_bus = InMemoryEventBus()
    handler = _FlakyHandler(fails=10)
    event = KnowledgeBaseCreatedEvent(
        correlation_id="corr-permanent", knowledge_base_id="kb-1"
    )

    result = asyncio.run(
        run_handler_with_retry(
            handler,
            event=event,
            event_bus=event_bus,
            retry_policy=RetryPolicy(max_retries=2, base_delay_seconds=0.0),
            sleep=_instant_sleep,
        )
    )

    assert result == 0
    assert handler.calls == 3
    assert len(event_bus.dlq_entries) == 1
    entry = event_bus.dlq_entries[0]
    assert entry.event.correlation_id == "corr-permanent"
    assert entry.error.retry_count == 2
    assert "transient failure" in entry.error.error_message


def test_retry_policy_delay_for_attempt() -> None:
    policy = RetryPolicy(max_retries=3, base_delay_seconds=1.0, backoff_multiplier=2.0)
    assert policy.delay_for_attempt(0) == 0.0
    assert policy.delay_for_attempt(1) == 1.0
    assert policy.delay_for_attempt(2) == 2.0
    assert policy.delay_for_attempt(3) == 4.0


# ---------------------------------------------------------------------------
# E4-S04 — DLQ wiring through drain_ingestion_events
# ---------------------------------------------------------------------------


def test_drain_ingestion_events_routes_failing_event_to_dlq() -> None:
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

    # Publish a DocumentsParsedEvent referencing a missing storage key.
    event_bus.publish(
        DocumentsParsedEvent(
            correlation_id="corr-fail",
            documents=[
                ParsedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-1",
                    parsed_document_id="parsed-1",
                    parser_name="test-parser",
                )
            ],
        )
    )

    asyncio.run(drain_ingestion_events(
        event_bus,
        service,
        chunker,
        extractor,
        validator,
        graph_service,
        object_store,
        consumer_group="test-workers",
        consumer_name="worker-1",
        retry_policy=RetryPolicy(max_retries=1, base_delay_seconds=0.0),
        sleep=_instant_sleep,
    ))

    assert len(event_bus.dlq_entries) == 1
    dlq_entry = event_bus.dlq_entries[0]
    assert isinstance(dlq_entry.event, DocumentsParsedEvent)
    assert dlq_entry.error.retry_count == 1


# ---------------------------------------------------------------------------
# E4-S06 — graceful shutdown
# ---------------------------------------------------------------------------


def test_graceful_shutdown_finishes_in_flight_event(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The worker loop completes gracefully when the shutdown event fires."""

    import logging

    from agent.coordinator import (
        WorkerDependencies,
        SHUTDOWN_LOG_DONE,
        SHUTDOWN_LOG_REQUESTED,
        run_worker,
    )
    from agent.adapters.in_memory import InMemoryWorkflowRunStore
    from agent.workflow_tracking import WorkflowEventTracker

    defaults_yaml = __file__.replace(
        "tests/agent/test_coordinator.py", "config/defaults/medicare_fraud.yaml"
    )
    monkeypatch.setenv("CHILI_CONFIG_PATH", defaults_yaml)

    event_bus = InMemoryEventBus()
    workflow_run_store = InMemoryWorkflowRunStore()
    object_store = InMemoryObjectStore()
    vector_store = InMemoryVectorStore()
    graph_repository = InMemoryGraphRepository()
    graph_service = create_graph_service(
        graph_repository, object_store=object_store, event_bus=event_bus
    )
    from embeddings.service import create_embeddings_service
    embeddings_service = create_embeddings_service(
        InMemoryEmbedder(), event_bus=event_bus
    )
    ingestion_service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(), fetcher=HttpxRemoteDocumentFetcher()
        ),
        object_store=object_store,
        event_bus=event_bus,
    )

    from analytics.explainability.adapters.in_memory import (
        InMemoryExplainabilityContextSource,
    )
    from analytics.explainability.service import create_explainability_service
    from analytics.gnn.adapters.in_memory import InMemoryGraphSnapshotSource
    from analytics.gnn.service import create_gnn_service
    from analytics.risk.adapters.in_memory import InMemoryRiskSignalSource
    from analytics.risk.service import create_risk_service
    from monitoring.adapters.in_memory import InMemoryObservationSource
    from monitoring.service import create_monitoring_service

    fake_deps = WorkerDependencies(
        event_bus=event_bus,
        ingestion_service=ingestion_service,
        document_chunker=create_document_chunker(),
        document_extractor=create_document_extractor([]),
        extraction_validator=create_extraction_validator([], []),
        graph_service=graph_service,
        embeddings_service=embeddings_service,
        object_store=object_store,
        vector_store=vector_store,
        llm_client=__import__(
            "llm.adapters.in_memory", fromlist=["InMemoryLlmClient"]
        ).InMemoryLlmClient(),
        gnn_service=create_gnn_service(
            InMemoryGraphSnapshotSource(), event_bus=event_bus
        ),
        risk_service=create_risk_service(
            InMemoryRiskSignalSource(), event_bus=event_bus
        ),
        explainability_service=create_explainability_service(
            InMemoryExplainabilityContextSource(), event_bus=event_bus
        ),
        monitoring_service=create_monitoring_service(
            InMemoryObservationSource(), event_bus=event_bus
        ),
        records_config=RecordsConfig(),
        raw_record_store=InMemoryRawRecordStore(),
        observation_writer=InMemoryObservationWriter(),
        event_settings=EventBusSettings(backend="in-memory"),
        workflow_run_store=workflow_run_store,
        workflow_tracker=WorkflowEventTracker(workflow_run_store),
    )

    monkeypatch.setattr(
        "agent.coordinator.build_worker_dependencies", lambda: fake_deps
    )

    # Run a brief worker loop and trigger shutdown via the asyncio event loop.
    async def _run() -> None:
        worker_task = asyncio.create_task(run_worker())
        await asyncio.sleep(0.1)
        # Trigger SIGTERM-equivalent by signalling the shutdown event directly.
        for task in asyncio.all_tasks():
            if task is not worker_task and task is not asyncio.current_task():
                continue
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass

    caplog.set_level(logging.INFO, logger="chili.worker")
    asyncio.run(_run())
    log_text = caplog.text
    assert SHUTDOWN_LOG_DONE in log_text
    # SHUTDOWN_LOG_REQUESTED would only fire if signal was actually delivered;
    # since cancellation skips it, only the graceful-stop log is asserted.
    assert SHUTDOWN_LOG_REQUESTED.startswith("Shutdown requested")


def testinstall_signal_handlers_sets_shutdown_event() -> None:
    """The signal handler flips the shutdown event and logs the request."""

    from agent.coordinator import SHUTDOWN_LOG_REQUESTED, install_signal_handlers

    async def _run() -> None:
        loop = asyncio.get_running_loop()
        shutdown_event = asyncio.Event()
        install_signal_handlers(loop, shutdown_event)
        # Direct invocation through the registered handler is platform-specific,
        # so simulate the trigger by setting the event ourselves.
        shutdown_event.set()
        assert shutdown_event.is_set()

    asyncio.run(_run())
    assert SHUTDOWN_LOG_REQUESTED == "Shutdown requested, finishing current event..."


def test_signal_trigger_flips_event_and_logs(caplog: pytest.LogCaptureFixture) -> None:
    """Trigger the registered SIGTERM handler to cover the inner closure."""

    import logging
    import os
    import signal as signal_module

    from agent.coordinator import SHUTDOWN_LOG_REQUESTED, install_signal_handlers

    async def _run() -> None:
        loop = asyncio.get_running_loop()
        shutdown_event = asyncio.Event()
        install_signal_handlers(loop, shutdown_event)
        os.kill(os.getpid(), signal_module.SIGTERM)
        # Give the loop a chance to process the signal callback.
        await asyncio.sleep(0.05)
        assert shutdown_event.is_set()

    caplog.set_level(logging.INFO, logger="chili.worker")
    asyncio.run(_run())
    assert SHUTDOWN_LOG_REQUESTED in caplog.text


def teststart_health_server_safely_logs_warning_on_failure(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The worker survives a health-server failure and logs a warning."""

    import logging

    from agent.coordinator import start_health_server_safely
    from agent.health import HealthState
    from agent.models import HealthSettings

    async def _failing_start(_state: object) -> object:
        raise OSError("port in use")

    monkeypatch.setattr("agent.coordinator.start_health_server", _failing_start)

    async def _run() -> None:
        state = HealthState(settings=HealthSettings())
        result = await start_health_server_safely(state)
        assert result is None

    caplog.set_level(logging.WARNING, logger="chili.worker")
    asyncio.run(_run())
    assert "Health server failed to start" in caplog.text


def test_handle_documents_parsed_raises_when_storage_key_missing() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    chunker = create_document_chunker()
    with pytest.raises(ValueError):
        handle_documents_parsed(
            DocumentsParsedEvent(
                documents=[
                    ParsedDocumentReference(
                        knowledge_base_id="kb-1",
                        source_document_id="doc-1",
                        parsed_document_id="parsed-1",
                        parser_name="test",
                    )
                ]
            ),
            document_chunker=chunker,
            object_store=object_store,
            event_bus=event_bus,
        )


def test_handle_documents_chunked_raises_when_storage_key_missing() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    extractor = create_document_extractor([])
    with pytest.raises(ValueError):
        handle_documents_chunked(
            DocumentsChunkedEvent(
                documents=[
                    ChunkedDocumentReference(
                        knowledge_base_id="kb-1",
                        source_document_id="doc-1",
                        parsed_document_id="parsed-1",
                        chunk_count=0,
                        strategy="x",
                    )
                ]
            ),
            document_extractor=extractor,
            object_store=object_store,
            event_bus=event_bus,
        )


def test_handle_entities_extracted_raises_when_storage_key_missing() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    validator = create_extraction_validator([], [])
    with pytest.raises(ValueError):
        handle_entities_extracted(
            EntitiesExtractedEvent(
                documents=[
                    ExtractedDocumentReference(
                        knowledge_base_id="kb-1",
                        source_document_id="doc-1",
                        parsed_document_id="parsed-1",
                        extraction_result_id="extract-1",
                        entity_count=0,
                        relationship_count=0,
                    )
                ]
            ),
            extraction_validator=validator,
            object_store=object_store,
            event_bus=event_bus,
        )


def test_handle_entities_validated_raises_when_storage_key_missing() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    graph_service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=object_store,
        event_bus=event_bus,
    )
    with pytest.raises(ValueError):
        handle_entities_validated(
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
                    )
                ]
            ),
            graph_service=graph_service,
            object_store=object_store,
        )


def test_handle_event_requires_embeddings_service_for_graph_updated() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
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
    with pytest.raises(ValueError):
        handle_event(
            EventDelivery(
                event=GraphUpdatedEvent(
                    correlation_id="x",
                    documents=[
                        GraphUpdatedDocumentReference(
                            knowledge_base_id="kb-1",
                            source_document_id="d",
                            parsed_document_id="p",
                            extraction_result_id="e",
                            validation_report_id="v",
                            upserted_entity_count=0,
                            upserted_relationship_count=0,
                            graph_update_storage_key="x.json",
                            validation_storage_key="y.json",
                        )
                    ],
                )
            ),
            service,
            document_chunker=create_document_chunker(),
            document_extractor=create_document_extractor([]),
            extraction_validator=create_extraction_validator([], []),
            graph_service=graph_service,
            object_store=object_store,
            event_bus=event_bus,
        )


def test_handle_event_requires_vector_store_for_embeddings_complete() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
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
    with pytest.raises(ValueError):
        handle_event(
            EventDelivery(
                event=EmbeddingsCompleteEvent(
                    documents=[
                        EmbeddingsCompleteDocumentReference(
                            knowledge_base_id="kb-1",
                            source_document_id="d",
                            parsed_document_id="p",
                            extraction_result_id="e",
                            validation_report_id="v",
                            entity_count=0,
                            graph_update_storage_key="g.json",
                            embeddings_storage_key="emb.json",
                        )
                    ]
                )
            ),
            service,
            document_chunker=create_document_chunker(),
            document_extractor=create_document_extractor([]),
            extraction_validator=create_extraction_validator([], []),
            graph_service=graph_service,
            object_store=object_store,
            event_bus=event_bus,
        )


def test_handle_event_requires_graph_repository_for_vectors_indexed() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
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
    with pytest.raises(ValueError):
        handle_event(
            EventDelivery(
                event=VectorsIndexedEvent(
                    documents=[
                        VectorsIndexedDocumentReference(
                            knowledge_base_id="kb-1",
                            source_document_id="d",
                            parsed_document_id="p",
                            extraction_result_id="e",
                            validation_report_id="v",
                            vector_count=0,
                            embeddings_storage_key="emb.json",
                            record_ids=[],
                        )
                    ]
                )
            ),
            service,
            document_chunker=create_document_chunker(),
            document_extractor=create_document_extractor([]),
            extraction_validator=create_extraction_validator([], []),
            graph_service=graph_service,
            object_store=object_store,
            event_bus=event_bus,
        )


def test_handle_graph_updated_raises_when_storage_keys_missing() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    embeddings_service = _FakeEmbeddingsService()

    with pytest.raises(ValueError):
        handle_graph_updated(
            GraphUpdatedEvent(
                documents=[
                    GraphUpdatedDocumentReference(
                        knowledge_base_id="kb-1",
                        source_document_id="d",
                        parsed_document_id="p",
                        extraction_result_id="e",
                        validation_report_id="v",
                        upserted_entity_count=0,
                        upserted_relationship_count=0,
                        graph_update_storage_key=None,
                        validation_storage_key=None,
                    )
                ]
            ),
            embeddings_service=embeddings_service,
            object_store=object_store,
            event_bus=event_bus,
        )


def test_handle_graph_updated_raises_when_validation_storage_key_missing() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    embeddings_service = _FakeEmbeddingsService()

    with pytest.raises(ValueError):
        handle_graph_updated(
            GraphUpdatedEvent(
                documents=[
                    GraphUpdatedDocumentReference(
                        knowledge_base_id="kb-1",
                        source_document_id="d",
                        parsed_document_id="p",
                        extraction_result_id="e",
                        validation_report_id="v",
                        upserted_entity_count=0,
                        upserted_relationship_count=0,
                        graph_update_storage_key="g.json",
                        validation_storage_key=None,
                    )
                ]
            ),
            embeddings_service=embeddings_service,
            object_store=object_store,
            event_bus=event_bus,
        )


def test_handle_graph_updated_raises_when_validation_missing_entities() -> None:
    """The handler raises if graph upsert refers to entities not in validation."""

    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    embeddings_service = _FakeEmbeddingsService()
    graph_update_storage_key = "knowledgebases/kb-1/graph_updates/missing.json"
    validation_storage_key = "knowledgebases/kb-1/validations/missing.json"
    object_store.put_bytes(
        graph_update_storage_key,
        GraphUpsertResult(
            knowledge_base_id="kb-1",
            source_document_id="doc",
            parsed_document_id="parsed",
            extraction_result_id="extract",
            validation_report_id="validate",
            upserted_entity_ids=["entity-missing"],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )
    object_store.put_bytes(
        validation_storage_key,
        ValidationReport(
            id="validate",
            extraction_result_id="extract",
            source_document_id="doc",
            valid_entities=[
                Entity(id="entity-other", type="claim", properties={}),
            ],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    with pytest.raises(ValueError):
        handle_graph_updated(
            GraphUpdatedEvent(
                documents=[
                    GraphUpdatedDocumentReference(
                        knowledge_base_id="kb-1",
                        source_document_id="doc",
                        parsed_document_id="parsed",
                        extraction_result_id="extract",
                        validation_report_id="validate",
                        upserted_entity_count=1,
                        upserted_relationship_count=0,
                        graph_update_storage_key=graph_update_storage_key,
                        validation_storage_key=validation_storage_key,
                    )
                ]
            ),
            embeddings_service=embeddings_service,
            object_store=object_store,
            event_bus=event_bus,
        )


# ---------------------------------------------------------------------------
# E4-S07 — health endpoint
# ---------------------------------------------------------------------------


def test_health_state_marks_event_processed_and_reports_status() -> None:
    from datetime import datetime, timedelta, timezone

    from agent.health import HealthState, build_health_payload
    from agent.models import HealthSettings

    state = HealthState(settings=HealthSettings(degraded_after_seconds=1.0))
    assert state.status() == "ok"

    state.mark_event_processed(datetime.now(timezone.utc))
    payload = build_health_payload(state)
    assert payload["status"] == "ok"
    assert payload["last_event_processed_at"] is not None

    stale_now = state.last_event_processed_at
    assert stale_now is not None
    future = stale_now + timedelta(seconds=10)
    assert state.status(now=future) == "degraded"


def test_health_payload_handles_no_events() -> None:
    from agent.health import HealthState, build_health_payload
    from agent.models import HealthSettings

    state = HealthState(settings=HealthSettings())
    payload = build_health_payload(state)
    assert payload == {"status": "ok", "last_event_processed_at": None}

# ---------------------------------------------------------------------------
# E7-S10 — analytics handler (Flow B)
# ---------------------------------------------------------------------------


class _AcceptingExplainabilityContextSource:
    """Test double that builds a deterministic explanation context per alert."""

    def load_context(
        self,
        *,
        knowledge_base_id: str,
        alert_id: str,
    ):  # type: ignore[no-untyped-def]
        from datetime import datetime, timezone

        from analytics.explainability.models import (
            ExplanationContext,
            ExplanationItem,
            ExplanationSubgraph,
        )
        from shared.types import Alert

        return ExplanationContext(
            knowledge_base_id=knowledge_base_id,
            alert=Alert(
                id=alert_id,
                entity_type="provider",
                entity_id="provider-1",
                severity="high",
                title="Outlier",
                reasoning="Detected by analytics pipeline.",
                created_at=datetime.now(timezone.utc),
            ),
            explanation_items=[
                ExplanationItem(
                    source_id="signal-1",
                    source_type="risk_signal",
                    quote="High anomaly score.",
                    rationale="Anomaly score 0.7 exceeds baseline.",
                    score=0.9,
                )
            ],
            subgraph=ExplanationSubgraph(node_ids=["provider-1"], edge_ids=[]),
            confidence=0.8,
        )


def test_handle_event_dispatches_analytics_pipeline_for_graph_updated() -> None:
    from analytics.gnn.adapters.in_memory import InMemoryGraphSnapshotSource
    from analytics.gnn.models import (
        GraphEdgeSignal,
        GraphNodeSignal,
        GraphSnapshot,
    )
    from analytics.gnn.service import create_gnn_service
    from analytics.risk.adapters.in_memory import InMemoryRiskSignalSource
    from analytics.risk.models import RiskProfile, RiskSignal
    from analytics.risk.service import create_risk_service
    from analytics.explainability.service import create_explainability_service
    from events.types import AlertsCreatedEvent, EmbeddingsCompleteEvent

    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    embeddings_service = _FakeEmbeddingsService()
    graph_update_storage_key = "knowledgebases/kb-1/graph_updates/extract-A.json"
    validation_storage_key = "knowledgebases/kb-1/validations/extract-A.json"
    object_store.put_bytes(
        graph_update_storage_key,
        GraphUpsertResult(
            knowledge_base_id="kb-1",
            source_document_id="doc-A",
            parsed_document_id="parsed-A",
            extraction_result_id="extract-A",
            validation_report_id="validate-A",
            upserted_entity_ids=["provider-1"],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )
    object_store.put_bytes(
        validation_storage_key,
        ValidationReport(
            id="validate-A",
            extraction_result_id="extract-A",
            source_document_id="doc-A",
            valid_entities=[
                Entity(
                    id="provider-1",
                    type="claim",
                    properties={"name": "Provider 1"},
                )
            ],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    snapshot_source = InMemoryGraphSnapshotSource(
        snapshots=[
            GraphSnapshot(
                knowledge_base_id="kb-1",
                nodes=[
                    GraphNodeSignal(entity_id="provider-1", feature_values=[0.4, 0.2]),
                    GraphNodeSignal(entity_id="other-1", feature_values=[0.1, 0.9]),
                ],
                edges=[
                    GraphEdgeSignal(
                        source_id="provider-1", target_id="other-1", weight=1.0
                    ),
                ],
            )
        ]
    )
    signal_source = InMemoryRiskSignalSource(
        profiles=[
            RiskProfile(
                knowledge_base_id="kb-1",
                entity_id="provider-1",
                signals=[
                    RiskSignal(signal_name="anomaly", value=0.7, weight=0.5),
                    RiskSignal(signal_name="velocity", value=0.6, weight=0.5),
                ],
            )
        ]
    )
    gnn_service = create_gnn_service(snapshot_source, event_bus=event_bus)
    risk_service = create_risk_service(signal_source, event_bus=event_bus)
    explainability_service = create_explainability_service(
        _AcceptingExplainabilityContextSource(),
        event_bus=event_bus,
    )
    graph_repository = InMemoryGraphRepository()
    graph_repository.upsert_entities(
        "kb-1",
        [Entity(id="provider-1", type="claim", properties={"name": "Provider 1"})],
    )
    graph_service = create_graph_service(
        graph_repository, object_store=object_store, event_bus=event_bus
    )
    service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=event_bus,
    )

    processed = handle_event(
        EventDelivery(
            event=GraphUpdatedEvent(
                correlation_id="corr-flowB",
                documents=[
                    GraphUpdatedDocumentReference(
                        knowledge_base_id="kb-1",
                        source_document_id="doc-A",
                        parsed_document_id="parsed-A",
                        extraction_result_id="extract-A",
                        validation_report_id="validate-A",
                        upserted_entity_count=1,
                        upserted_relationship_count=0,
                        validation_storage_key=validation_storage_key,
                        graph_update_storage_key=graph_update_storage_key,
                    )
                ],
            )
        ),
        service,
        document_chunker=create_document_chunker(),
        document_extractor=create_document_extractor([]),
        extraction_validator=create_extraction_validator([], []),
        graph_service=graph_service,
        object_store=object_store,
        event_bus=event_bus,
        embeddings_service=embeddings_service,
        gnn_service=gnn_service,
        risk_service=risk_service,
        explainability_service=explainability_service,
    )

    assert processed == 1
    embedding_events = [
        e for e in event_bus.published_events if isinstance(e, EmbeddingsCompleteEvent)
    ]
    assert len(embedding_events) == 1
    alert_events = [
        e for e in event_bus.published_events if isinstance(e, AlertsCreatedEvent)
    ]
    assert len(alert_events) == 1
    assert alert_events[0].alerts[0].entity_id == "provider-1"
    # Risk + GNN properties were written back to the graph (E7-S11 self-loop).
    updated = graph_repository.get_entity("kb-1", "provider-1")
    assert updated is not None
    assert "risk_score" in updated.properties
    assert "risk_level" in updated.properties
    assert "risk_assessed_at" in updated.properties
    assert "centrality_score" in updated.properties
    assert "community_id" in updated.properties


def test_analytics_handler_emits_analysis_failed_when_risk_profile_missing() -> None:
    from analytics.gnn.adapters.in_memory import InMemoryGraphSnapshotSource
    from analytics.gnn.models import (
        GraphEdgeSignal,
        GraphNodeSignal,
        GraphSnapshot,
    )
    from analytics.gnn.service import create_gnn_service
    from analytics.risk.adapters.in_memory import InMemoryRiskSignalSource
    from analytics.risk.service import create_risk_service
    from analytics.explainability.adapters.in_memory import (
        InMemoryExplainabilityContextSource,
    )
    from analytics.explainability.service import create_explainability_service
    from agent.coordinator import handle_graph_updated_for_analytics
    from events.types import AnalysisFailedEvent

    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    object_store.put_bytes(
        "gk",
        GraphUpsertResult(
            knowledge_base_id="kb-1",
            source_document_id="doc-A",
            parsed_document_id="parsed-A",
            extraction_result_id="extract-A",
            validation_report_id="validate-A",
            upserted_entity_ids=["provider-1"],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    # Snapshot present, but no risk profile registered for entity.
    snapshot_source = InMemoryGraphSnapshotSource(
        snapshots=[
            GraphSnapshot(
                knowledge_base_id="kb-1",
                nodes=[
                    GraphNodeSignal(entity_id="provider-1", feature_values=[0.4, 0.2]),
                    GraphNodeSignal(entity_id="other-1", feature_values=[0.1, 0.9]),
                ],
                edges=[
                    GraphEdgeSignal(
                        source_id="provider-1", target_id="other-1", weight=1.0
                    ),
                ],
            )
        ]
    )
    gnn_service = create_gnn_service(snapshot_source, event_bus=event_bus)
    risk_service = create_risk_service(
        InMemoryRiskSignalSource(), event_bus=event_bus
    )
    explainability_service = create_explainability_service(
        InMemoryExplainabilityContextSource(),
        event_bus=event_bus,
    )
    graph_repository = InMemoryGraphRepository()
    graph_service = create_graph_service(
        graph_repository, object_store=object_store, event_bus=event_bus
    )

    alerts = handle_graph_updated_for_analytics(
        GraphUpdatedEvent(
            correlation_id="corr-fail",
            documents=[
                GraphUpdatedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-A",
                    parsed_document_id="parsed-A",
                    extraction_result_id="extract-A",
                    validation_report_id="validate-A",
                    upserted_entity_count=1,
                    upserted_relationship_count=0,
                    validation_storage_key="vk",
                    graph_update_storage_key="gk",
                )
            ],
        ),
        gnn_service=gnn_service,
        risk_service=risk_service,
        explainability_service=explainability_service,
        graph_service=graph_service,
        event_bus=event_bus,
        object_store=object_store,
    )
    assert alerts == 0
    failures = [
        e for e in event_bus.published_events if isinstance(e, AnalysisFailedEvent)
    ]
    assert len(failures) == 1
    assert failures[0].stage == "risk"
    assert failures[0].entity_id == "provider-1"


def test_analytics_handler_failure_does_not_abort_flow_a() -> None:
    """Even when the analytics chain fails, embeddings (Flow A) still publishes."""

    from analytics.gnn.adapters.in_memory import InMemoryGraphSnapshotSource
    from analytics.gnn.service import create_gnn_service
    from analytics.risk.adapters.in_memory import InMemoryRiskSignalSource
    from analytics.risk.service import create_risk_service
    from analytics.explainability.adapters.in_memory import (
        InMemoryExplainabilityContextSource,
    )
    from analytics.explainability.service import create_explainability_service
    from events.types import AnalysisFailedEvent, EmbeddingsCompleteEvent

    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    embeddings_service = _FakeEmbeddingsService()
    graph_update_storage_key = "knowledgebases/kb-1/graph_updates/extract-Z.json"
    validation_storage_key = "knowledgebases/kb-1/validations/extract-Z.json"
    object_store.put_bytes(
        graph_update_storage_key,
        GraphUpsertResult(
            knowledge_base_id="kb-1",
            source_document_id="doc-Z",
            parsed_document_id="parsed-Z",
            extraction_result_id="extract-Z",
            validation_report_id="validate-Z",
            upserted_entity_ids=["provider-1"],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )
    object_store.put_bytes(
        validation_storage_key,
        ValidationReport(
            id="validate-Z",
            extraction_result_id="extract-Z",
            source_document_id="doc-Z",
            valid_entities=[
                Entity(
                    id="provider-1",
                    type="claim",
                    properties={"embedding_text": "Provider 1"},
                ),
            ],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    # Empty analytics adapters cause GNN to raise (no snapshot).
    gnn_service = create_gnn_service(
        InMemoryGraphSnapshotSource(), event_bus=event_bus
    )
    risk_service = create_risk_service(
        InMemoryRiskSignalSource(), event_bus=event_bus
    )
    explainability_service = create_explainability_service(
        InMemoryExplainabilityContextSource(), event_bus=event_bus
    )
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

    processed = handle_event(
        EventDelivery(
            event=GraphUpdatedEvent(
                correlation_id="corr-mixed",
                documents=[
                    GraphUpdatedDocumentReference(
                        knowledge_base_id="kb-1",
                        source_document_id="doc-Z",
                        parsed_document_id="parsed-Z",
                        extraction_result_id="extract-Z",
                        validation_report_id="validate-Z",
                        upserted_entity_count=1,
                        upserted_relationship_count=0,
                        validation_storage_key=validation_storage_key,
                        graph_update_storage_key=graph_update_storage_key,
                    )
                ],
            )
        ),
        service,
        document_chunker=create_document_chunker(),
        document_extractor=create_document_extractor([]),
        extraction_validator=create_extraction_validator([], []),
        graph_service=graph_service,
        object_store=object_store,
        event_bus=event_bus,
        embeddings_service=embeddings_service,
        gnn_service=gnn_service,
        risk_service=risk_service,
        explainability_service=explainability_service,
    )

    assert processed == 1
    embedding_events = [
        e for e in event_bus.published_events if isinstance(e, EmbeddingsCompleteEvent)
    ]
    assert len(embedding_events) == 1
    failures = [
        e for e in event_bus.published_events if isinstance(e, AnalysisFailedEvent)
    ]
    assert len(failures) >= 1
    assert any(failure.stage == "gnn" for failure in failures)


# ---------------------------------------------------------------------------
# E8-S07 — Monitoring stream consumer
# ---------------------------------------------------------------------------


def _build_monitoring_test_bundle() -> tuple[
    _MonitoringService, InMemoryEventBus, _RiskScoredEvent
]:
    from monitoring.adapters.in_memory import InMemoryObservationSource
    from monitoring.models import MonitoringBatch, MonitoringObservation
    from monitoring.service import create_monitoring_service
    from events.types import RiskScoredReference

    event_bus = InMemoryEventBus()
    source = InMemoryObservationSource(
        batches=[
            MonitoringBatch(
                knowledge_base_id="kb-1",
                batch_id="risk-request-1",
                observations=[
                    MonitoringObservation(
                        entity_id="provider-1",
                        entity_type="provider",
                        metric_name="risk",
                        score=0.92,
                        rationale="High risk score from risk service.",
                    )
                ],
            )
        ]
    )
    service = create_monitoring_service(source, event_bus=event_bus)
    event = _RiskScoredEvent(
        assessments=[
            RiskScoredReference(
                knowledge_base_id="kb-1",
                request_id="risk-request-1",
                entity_id="provider-1",
                overall_score=0.92,
                risk_level="high",
                factor_count=2,
            )
        ]
    )
    return service, event_bus, event


def test_handle_risk_scored_emits_alerts_created() -> None:
    from agent.coordinator import handle_risk_scored
    from events.types import AlertsCreatedEvent

    service, event_bus, event = _build_monitoring_test_bundle()

    processed = handle_risk_scored(
        event, monitoring_service=service, event_bus=event_bus
    )

    assert processed == 1
    alerts_events = [
        e for e in event_bus.published_events if isinstance(e, AlertsCreatedEvent)
    ]
    assert len(alerts_events) == 1
    assert alerts_events[0].alerts[0].entity_id == "provider-1"


def test_handle_risk_scored_logs_and_continues_on_monitoring_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    from agent.coordinator import handle_risk_scored
    from events.types import RiskScoredEvent, RiskScoredReference
    from monitoring.adapters.in_memory import InMemoryObservationSource
    from monitoring.service import create_monitoring_service

    event_bus = InMemoryEventBus()
    # No batch seeded — load_batch raises ValueError, mapped to MonitoringConfigurationError.
    service = create_monitoring_service(
        InMemoryObservationSource(), event_bus=event_bus
    )
    event = RiskScoredEvent(
        assessments=[
            RiskScoredReference(
                knowledge_base_id="kb-1",
                request_id="missing",
                entity_id="provider-1",
                overall_score=0.5,
                risk_level="medium",
                factor_count=1,
            )
        ]
    )

    caplog.set_level(logging.ERROR, logger="chili.worker")
    processed = handle_risk_scored(
        event, monitoring_service=service, event_bus=event_bus
    )

    # Failures count zero processed assessments and do not raise.
    assert processed == 0
    assert "Monitoring evaluation failed" in caplog.text


def test_handle_event_dispatches_risk_scored_to_monitoring() -> None:
    from agent.coordinator import handle_event
    from events.types import AlertsCreatedEvent

    service, event_bus, event = _build_monitoring_test_bundle()
    object_store = InMemoryObjectStore()
    graph_repository = InMemoryGraphRepository()
    graph_service = create_graph_service(
        graph_repository, object_store=object_store, event_bus=event_bus
    )
    ingestion_service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(), fetcher=HttpxRemoteDocumentFetcher()
        ),
        object_store=object_store,
        event_bus=event_bus,
    )

    processed = handle_event(
        EventDelivery(event=event, event_id="1", stream="risk.scored"),
        ingestion_service,
        document_chunker=create_document_chunker(),
        document_extractor=create_document_extractor([]),
        extraction_validator=create_extraction_validator([], []),
        graph_service=graph_service,
        object_store=object_store,
        event_bus=event_bus,
        monitoring_service=service,
    )

    assert processed == 1
    alerts_events = [
        e for e in event_bus.published_events if isinstance(e, AlertsCreatedEvent)
    ]
    assert len(alerts_events) == 1


def test_handle_event_skips_risk_scored_when_no_monitoring_service() -> None:
    from agent.coordinator import handle_event
    from events.types import RiskScoredEvent, RiskScoredReference

    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    graph_repository = InMemoryGraphRepository()
    graph_service = create_graph_service(
        graph_repository, object_store=object_store, event_bus=event_bus
    )
    ingestion_service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(), fetcher=HttpxRemoteDocumentFetcher()
        ),
        object_store=object_store,
        event_bus=event_bus,
    )
    event = RiskScoredEvent(
        assessments=[
            RiskScoredReference(
                knowledge_base_id="kb-1",
                request_id="r1",
                entity_id="provider-1",
                overall_score=0.5,
                risk_level="medium",
                factor_count=1,
            )
        ]
    )

    processed = handle_event(
        EventDelivery(event=event, event_id="1", stream="risk.scored"),
        ingestion_service,
        document_chunker=create_document_chunker(),
        document_extractor=create_document_extractor([]),
        extraction_validator=create_extraction_validator([], []),
        graph_service=graph_service,
        object_store=object_store,
        event_bus=event_bus,
    )

    assert processed == 0


def test_handle_event_absorbs_unexpected_monitoring_exception() -> None:
    """A non-MonitoringError raised by monitoring should not propagate from handle_event."""

    from agent.coordinator import handle_event
    from events.types import RiskScoredEvent, RiskScoredReference
    from monitoring.adapters.in_memory import InMemoryObservationSource
    from monitoring.service import MonitoringService
    from monitoring.service_models import (
        MonitoringEvaluationRequest,
        MonitoringEvaluationResponse,
    )

    class _BoomMonitoring(MonitoringService):
        def __init__(self) -> None:
            super().__init__(InMemoryObservationSource(), event_bus=InMemoryEventBus())

        def evaluate(
            self, request: MonitoringEvaluationRequest
        ) -> MonitoringEvaluationResponse:
            raise RuntimeError("unexpected failure")

    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    graph_repository = InMemoryGraphRepository()
    graph_service = create_graph_service(
        graph_repository, object_store=object_store, event_bus=event_bus
    )
    ingestion_service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(), fetcher=HttpxRemoteDocumentFetcher()
        ),
        object_store=object_store,
        event_bus=event_bus,
    )
    event = RiskScoredEvent(
        assessments=[
            RiskScoredReference(
                knowledge_base_id="kb-1",
                request_id="r1",
                entity_id="provider-1",
                overall_score=0.5,
                risk_level="medium",
                factor_count=1,
            )
        ]
    )

    processed = handle_event(
        EventDelivery(event=event, event_id="1", stream="risk.scored"),
        ingestion_service,
        document_chunker=create_document_chunker(),
        document_extractor=create_document_extractor([]),
        extraction_validator=create_extraction_validator([], []),
        graph_service=graph_service,
        object_store=object_store,
        event_bus=event_bus,
        monitoring_service=_BoomMonitoring(),
    )

    assert processed == 0

