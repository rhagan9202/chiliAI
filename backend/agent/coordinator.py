"""Pipeline worker / coordinator entry point.

Consumes events from Redis Streams and executes pipeline steps.
This is a minimal stub that validates the container lifecycle.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from config.loader import load_config
from events.protocols import EventBus, EventDelivery
from events.runtime import EventBusSettings, create_event_bus, load_event_bus_settings
from events.types import (
    ChunkedDocumentReference,
    DocumentsChunkedEvent,
    DocumentsParsedEvent,
    DocumentsUploadedEvent,
    EntitiesExtractedEvent,
    EntitiesValidatedEvent,
    ExtractedDocumentReference,
    ValidatedDocumentReference,
)
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.service import GraphService, create_graph_service
from graph.service_models import GraphBuildTask
from ingestion.chunker import ChunkingResult, DocumentChunker, create_document_chunker
from ingestion.extractor import PatternDocumentExtractor, create_document_extractor
from ingestion.models import ExtractionResult, ParsedDocument, ValidationReport
from ingestion.orchestrators.parser import DocumentParsingOrchestrator
from ingestion.parsers.registry import create_default_registry
from ingestion.parsers.remote import HttpxRemoteDocumentFetcher
from ingestion.service import IngestionService
from ingestion.validator import ExtractionResultValidator, create_extraction_validator
from storage.protocols import ObjectStore
from storage.adapters.in_memory import InMemoryObjectStore

__all__ = [
    "build_worker_dependencies",
    "drain_ingestion_events",
    "handle_documents_chunked",
    "handle_documents_parsed",
    "handle_entities_extracted",
    "handle_entities_validated",
    "handle_event",
    "main",
    "run_worker",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("chili.worker")


def build_worker_dependencies(
) -> tuple[
    EventBus,
    IngestionService,
    DocumentChunker,
    PatternDocumentExtractor,
    ExtractionResultValidator,
    GraphService,
    ObjectStore,
    EventBusSettings,
]:
    """Assemble the worker's ingestion dependencies.

    The event transport is selected at runtime so tests can keep using the
    in-memory adapter while deployed workers consume Redis Streams.
    """
    # TODO(production): Replace hardcoded InMemoryObjectStore/InMemoryGraphRepository
    # with adapter selection from DomainConfig (S3, Neo4j, etc.). Wire embeddings,
    # vectorstore, RAG, LLM, analytics, and monitoring services here for full
    # pipeline support (currently only ingestion→graph stages are wired).
    config = load_config()
    event_settings = load_event_bus_settings()
    event_bus = create_event_bus(event_settings)
    object_store = InMemoryObjectStore()
    orchestrator = DocumentParsingOrchestrator(
        create_default_registry(),
        fetcher=HttpxRemoteDocumentFetcher(),
    )
    service = IngestionService(
        orchestrator,
        object_store=object_store,
        event_bus=event_bus,
    )
    chunker = create_document_chunker(config.ingestion.chunking)
    extractor = create_document_extractor(config.entities, config.relationships)
    validator = create_extraction_validator(config.entities, config.relationships)
    graph_service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=object_store,
        event_bus=event_bus,
    )
    return (
        event_bus,
        service,
        chunker,
        extractor,
        validator,
        graph_service,
        object_store,
        event_settings,
    )


def handle_documents_parsed(
    event: DocumentsParsedEvent,
    *,
    document_chunker: DocumentChunker,
    object_store: ObjectStore,
    event_bus: EventBus,
) -> int:
    """Chunk parsed documents and publish the next workflow event."""
    references: list[ChunkedDocumentReference] = []
    for document in event.documents:
        if document.parsed_document_storage_key is None:
            raise ValueError(
                "DocumentsParsedEvent requires parsed_document_storage_key for chunking."
            )
        stored = object_store.get_bytes(document.parsed_document_storage_key)
        parsed_document = ParsedDocument.model_validate_json(stored.content)
        result = document_chunker.chunk_document(
            parsed_document,
            source_document_id=document.source_document_id,
        )
        chunks_storage_key = _build_chunks_storage_key(
            document.knowledge_base_id,
            document.parsed_document_id,
        )
        object_store.put_bytes(
            chunks_storage_key,
            result.model_dump_json().encode("utf-8"),
            media_type="application/json",
            metadata={
                "knowledge_base_id": document.knowledge_base_id,
                "source_document_id": document.source_document_id,
                "parsed_document_id": document.parsed_document_id,
                "chunk_count": len(result.chunks),
            },
        )
        references.append(
            ChunkedDocumentReference(
                knowledge_base_id=document.knowledge_base_id,
                source_document_id=document.source_document_id,
                parsed_document_id=document.parsed_document_id,
                chunk_count=len(result.chunks),
                strategy=result.strategy_used,
                storage_key=document.storage_key,
                parsed_document_storage_key=document.parsed_document_storage_key,
                chunks_storage_key=chunks_storage_key,
            )
        )
    if references:
        event_bus.publish(
            DocumentsChunkedEvent(
                correlation_id=event.correlation_id,
                documents=references,
            )
        )
    return len(references)


def _build_chunks_storage_key(
    knowledge_base_id: str,
    parsed_document_id: str,
) -> str:
    """Build the object-store path for persisted chunking output."""
    return f"knowledgebases/{knowledge_base_id}/chunks/{parsed_document_id}.json"


def handle_documents_chunked(
    event: DocumentsChunkedEvent,
    *,
    document_extractor: PatternDocumentExtractor,
    object_store: ObjectStore,
    event_bus: EventBus,
) -> int:
    """Extract entity candidates from persisted chunks and publish the next event."""
    references: list[ExtractedDocumentReference] = []
    for document in event.documents:
        if document.chunks_storage_key is None:
            raise ValueError("DocumentsChunkedEvent requires chunks_storage_key for extraction.")
        stored = object_store.get_bytes(document.chunks_storage_key)
        chunking_result = ChunkingResult.model_validate_json(stored.content)
        extraction_result = document_extractor.extract_document(chunking_result)
        extraction_storage_key = _build_extraction_storage_key(
            document.knowledge_base_id,
            extraction_result.id,
        )
        object_store.put_bytes(
            extraction_storage_key,
            extraction_result.model_dump_json().encode("utf-8"),
            media_type="application/json",
            metadata={
                "knowledge_base_id": document.knowledge_base_id,
                "source_document_id": document.source_document_id,
                "parsed_document_id": document.parsed_document_id,
                "extraction_result_id": extraction_result.id,
                "entity_count": len(extraction_result.candidate_entities),
                "relationship_count": len(extraction_result.candidate_relationships),
            },
        )
        references.append(
            ExtractedDocumentReference(
                knowledge_base_id=document.knowledge_base_id,
                source_document_id=document.source_document_id,
                parsed_document_id=document.parsed_document_id,
                extraction_result_id=extraction_result.id,
                entity_count=len(extraction_result.candidate_entities),
                relationship_count=len(extraction_result.candidate_relationships),
                storage_key=document.storage_key,
                parsed_document_storage_key=document.parsed_document_storage_key,
                chunks_storage_key=document.chunks_storage_key,
                extraction_storage_key=extraction_storage_key,
            )
        )
    if references:
        event_bus.publish(
            EntitiesExtractedEvent(
                correlation_id=event.correlation_id,
                documents=references,
            )
        )
    return len(references)


def _build_extraction_storage_key(
    knowledge_base_id: str,
    extraction_result_id: str,
) -> str:
    """Build the object-store path for persisted extraction output."""
    return f"knowledgebases/{knowledge_base_id}/extractions/{extraction_result_id}.json"


def handle_entities_extracted(
    event: EntitiesExtractedEvent,
    *,
    extraction_validator: ExtractionResultValidator,
    object_store: ObjectStore,
    event_bus: EventBus,
) -> int:
    """Validate extracted candidates and publish runtime-ready results."""
    references: list[ValidatedDocumentReference] = []
    for document in event.documents:
        if document.extraction_storage_key is None:
            raise ValueError("EntitiesExtractedEvent requires extraction_storage_key for validation.")
        stored = object_store.get_bytes(document.extraction_storage_key)
        extraction_result = ExtractionResult.model_validate_json(stored.content)
        validation_report = extraction_validator.validate_extraction(extraction_result)
        validation_storage_key = _build_validation_storage_key(
            document.knowledge_base_id,
            extraction_result.id,
        )
        object_store.put_bytes(
            validation_storage_key,
            validation_report.model_dump_json().encode("utf-8"),
            media_type="application/json",
            metadata={
                "knowledge_base_id": document.knowledge_base_id,
                "source_document_id": document.source_document_id,
                "parsed_document_id": document.parsed_document_id,
                "extraction_result_id": extraction_result.id,
                "validation_report_id": validation_report.id,
                "valid_entity_count": len(validation_report.valid_entities),
                "valid_relationship_count": len(validation_report.valid_relationships),
                "entity_error_count": len(validation_report.entity_errors),
                "relationship_error_count": len(validation_report.relationship_errors),
            },
        )
        references.append(
            ValidatedDocumentReference(
                knowledge_base_id=document.knowledge_base_id,
                source_document_id=document.source_document_id,
                parsed_document_id=document.parsed_document_id,
                extraction_result_id=document.extraction_result_id,
                validation_report_id=validation_report.id,
                valid_entity_count=len(validation_report.valid_entities),
                valid_relationship_count=len(validation_report.valid_relationships),
                entity_error_count=len(validation_report.entity_errors),
                relationship_error_count=len(validation_report.relationship_errors),
                storage_key=document.storage_key,
                parsed_document_storage_key=document.parsed_document_storage_key,
                chunks_storage_key=document.chunks_storage_key,
                extraction_storage_key=document.extraction_storage_key,
                validation_storage_key=validation_storage_key,
            )
        )
    if references:
        event_bus.publish(
            EntitiesValidatedEvent(
                correlation_id=event.correlation_id,
                documents=references,
            )
        )
    return len(references)


def _build_validation_storage_key(
    knowledge_base_id: str,
    extraction_result_id: str,
) -> str:
    """Build the object-store path for persisted validation output."""
    return f"knowledgebases/{knowledge_base_id}/validations/{extraction_result_id}.json"


def handle_entities_validated(
    event: EntitiesValidatedEvent,
    *,
    graph_service: GraphService,
    object_store: ObjectStore,
) -> int:
    """Upsert validated runtime objects into the graph and publish graph updates."""
    processed = 0
    for document in event.documents:
        if document.validation_storage_key is None:
            raise ValueError("EntitiesValidatedEvent requires validation_storage_key for graph updates.")
        stored = object_store.get_bytes(document.validation_storage_key)
        validation_report = ValidationReport.model_validate_json(stored.content)
        graph_service.upsert_task(
            GraphBuildTask(
                knowledge_base_id=document.knowledge_base_id,
                source_document_id=document.source_document_id,
                parsed_document_id=document.parsed_document_id,
                extraction_result_id=document.extraction_result_id,
                validation_report_id=document.validation_report_id,
                validation_storage_key=document.validation_storage_key,
                correlation_id=event.correlation_id,
                entities=validation_report.valid_entities,
                relationships=validation_report.valid_relationships,
            )
        )
        processed += 1
    return processed


def handle_event(
    delivery: EventDelivery,
    ingestion_service: IngestionService,
    *,
    document_chunker: DocumentChunker,
    document_extractor: PatternDocumentExtractor,
    extraction_validator: ExtractionResultValidator,
    graph_service: GraphService,
    object_store: ObjectStore,
    event_bus: EventBus,
) -> int:
    """Handle a single event and return the number of processed documents."""
    # TODO(production): Wrap each handler call in try/except to isolate failures
    # per event. Route failed events to a dead-letter queue instead of crashing
    # the worker. Add per-event-type metrics (processed count, error count,
    # latency). Extend to handle post-graph pipeline stages: graph.updated →
    # embeddings, vectors.indexed → analytics, analysis.complete → monitoring.
    event = delivery.event
    if isinstance(event, DocumentsUploadedEvent):
        return len(ingestion_service.process_documents_uploaded(event))
    if isinstance(event, DocumentsParsedEvent):
        return handle_documents_parsed(
            event,
            document_chunker=document_chunker,
            object_store=object_store,
            event_bus=event_bus,
        )
    if isinstance(event, DocumentsChunkedEvent):
        return handle_documents_chunked(
            event,
            document_extractor=document_extractor,
            object_store=object_store,
            event_bus=event_bus,
        )
    if isinstance(event, EntitiesExtractedEvent):
        return handle_entities_extracted(
            event,
            extraction_validator=extraction_validator,
            object_store=object_store,
            event_bus=event_bus,
        )
    if isinstance(event, EntitiesValidatedEvent):
        return handle_entities_validated(
            event,
            graph_service=graph_service,
            object_store=object_store,
        )
    return 0


def drain_ingestion_events(
    event_bus: EventBus,
    ingestion_service: IngestionService,
    document_chunker: DocumentChunker,
    document_extractor: PatternDocumentExtractor,
    extraction_validator: ExtractionResultValidator,
    graph_service: GraphService,
    object_store: ObjectStore,
    *,
    consumer_group: str,
    consumer_name: str,
    limit: int = 10,
    block_ms: int | None = None,
) -> int:
    """Consume and process available ingestion events."""
    processed = 0
    event_types = [
        "documents.uploaded",
        "documents.parsed",
        "documents.chunked",
        "entities.extracted",
        "entities.validated",
    ]
    event_bus.ensure_consumer_group(event_types, consumer_group=consumer_group)
    deliveries = event_bus.consume(
        event_types,
        consumer_group=consumer_group,
        consumer_name=consumer_name,
        limit=limit,
        block_ms=block_ms,
    )
    ackable: list[EventDelivery] = []
    for delivery in deliveries:
        # TODO(production): Wrap handle_event() in try/except to isolate per-event
        # failures. Failed events should be routed to a dead-letter queue rather
        # than blocking the entire batch. Track retry count per event and discard
        # poison messages after N attempts.
        processed += handle_event(
            delivery,
            ingestion_service,
            document_chunker=document_chunker,
            document_extractor=document_extractor,
            extraction_validator=extraction_validator,
            graph_service=graph_service,
            object_store=object_store,
            event_bus=event_bus,
        )
        ackable.append(delivery)
    if ackable:
        event_bus.ack(ackable)
    return processed


async def run_worker() -> None:
    """Main worker loop — connects to Redis and processes events."""
    # TODO(production): Add signal handlers for SIGTERM/SIGHUP for graceful shutdown.
    # Wrap the main loop in try/except to handle transient failures with backoff
    # instead of crashing. Add health check endpoint or heartbeat signal for
    # container orchestrator liveness probes. Add metrics export (events processed,
    # error count, latency per event type).
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    logger.info("Worker starting — REDIS_URL=%s", redis_url)
    (
        event_bus,
        ingestion_service,
        document_chunker,
        document_extractor,
        extraction_validator,
        graph_service,
        object_store,
        event_settings,
    ) = build_worker_dependencies()

    try:
        while True:
            processed = drain_ingestion_events(
                event_bus,
                ingestion_service,
                document_chunker,
                document_extractor,
                extraction_validator,
                graph_service,
                object_store,
                consumer_group=event_settings.consumer_group,
                consumer_name=event_settings.consumer_name(),
                limit=event_settings.batch_size,
                block_ms=event_settings.block_ms,
            )
            if processed:
                logger.info("Processed %s ingestion document(s)", processed)
            if event_settings.backend != "redis":
                await asyncio.sleep(1)
                logger.debug("Worker heartbeat")
    except asyncio.CancelledError:
        logger.info("Worker shutting down")


def main() -> None:
    """Entry point for `python -m agent.coordinator`."""
    logger.info("chiliAI pipeline worker starting")
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Worker interrupted — exiting")
        sys.exit(0)


if __name__ == "__main__":
    main()
