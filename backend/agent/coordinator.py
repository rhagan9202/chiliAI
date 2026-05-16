"""Pipeline worker / coordinator entry point.

Consumes events from Redis Streams and executes pipeline steps. The
coordinator is the composition root of the worker: it selects adapters from
``DomainConfig``, wraps handlers in retry/dead-letter logic, runs an optional
health-check HTTP endpoint, and exits gracefully on SIGTERM/SIGINT.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
import sys
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import cast

from agent.adapters.protocols import WorkflowRunStoreProtocol
from agent.adapters.runtime import create_workflow_run_store_from_env
from agent.exceptions import ConfigurationError
from agent.health import HealthState, start_health_server
from agent.models import HealthSettings, RetryPolicy
from agent.workflow_tracking import WorkflowEventTracker
from config.loader import load_config
from config.schema import (
    AnalyticsConfig,
    DatabaseConfig,
    DomainConfig,
    EmbeddingsConfig,
    GraphDbConfig,
    LlmConfig,
    ObjectStoreConfig,
    RecordFeedConfig,
    RecordsConfig,
    VectorStoreConfig,
)
from database.protocols import ConnectionProvider
from database.runtime import create_connection_provider
from analytics.explainability.adapters.in_memory import (
    InMemoryExplainabilityContextSource,
)
from analytics.explainability.adapters.protocols import (
    ExplainabilityContextSourceProtocol,
)
from analytics.explainability.exceptions import ExplainabilityError
from analytics.explainability.service import (
    ExplainabilityService,
    create_explainability_service,
)
from analytics.explainability.service_models import ExplainabilityRequest
from analytics.gnn.adapters.in_memory import InMemoryGraphSnapshotSource
from analytics.gnn.adapters.protocols import GraphSnapshotSourceProtocol
from analytics.gnn.exceptions import GnnError
from analytics.gnn.service import GnnService, create_gnn_service
from analytics.gnn.service_models import GnnAnalysisRequest, GnnAnalysisResponse
from analytics.metrics.adapters.in_memory import InMemoryEntityMetricRepository
from analytics.metrics.adapters.postgres import PostgresEntityMetricRepository
from analytics.metrics.adapters.protocols import EntityMetricRepository
from analytics.metrics.models import (
    GRAPH_SCOPE_ENTITY_ID,
    METRIC_AVG_DEGREE,
    METRIC_ENTITY_COUNT,
    METRIC_RELATIONSHIP_COUNT,
    EntityMetricSample,
)
from analytics.metrics.throttle import MetricsRecomputeThrottle
from analytics.risk.adapters.in_memory import InMemoryRiskHistoryWriter, InMemoryRiskSignalSource
from analytics.risk.adapters.postgres import PostgresRiskHistoryStore
from analytics.risk.adapters.protocols import RiskHistoryWriter, RiskSignalSourceProtocol
from analytics.risk.exceptions import RiskError
from analytics.risk.models import RiskAssessmentRecord, RiskFactor
from analytics.risk.service import RiskService, create_risk_service
from analytics.risk.service_models import (
    RiskAssessmentRequest,
    RiskAssessmentResponse,
)
from embeddings.adapters.in_memory import InMemoryEmbedder
from embeddings.adapters.protocols import EmbedderProtocol
from embeddings.models import EmbeddingMetadata, EmbeddingResult
from embeddings.protocols import EmbeddingsServiceProtocol
from embeddings.service import create_embeddings_service
from embeddings.service_models import EmbedRequest, EmbedSubmission
from events.protocols import DlqErrorInfo, EventBus, EventDelivery
from events.runtime import EventBusSettings, create_event_bus, load_event_bus_settings
from events.types import (
    AlertCreatedReference,
    AlertsCreatedEvent,
    AnalysisFailedEvent,
    AnyEvent,
    ChunkedDocumentReference,
    DocumentsChunkedEvent,
    DocumentsParsedEvent,
    DocumentsUploadedEvent,
    EmbeddingsCompleteDocumentReference,
    EmbeddingsCompleteEvent,
    EntitiesExtractedEvent,
    EntitiesValidatedEvent,
    ExtractedDocumentReference,
    GraphUpdatedEvent,
    KnowledgeBaseReadyEvent,
    KnowledgeBaseReadyReference,
    RecordsIngestedEvent,
    RiskScoredEvent,
    ValidatedDocumentReference,
    VectorIndexedReference,
    VectorsIndexedDocumentReference,
    VectorsIndexedEvent,
)
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.adapters.protocols import GraphRepository
from graph.auth import resolve_graph_auth
from graph.models import GraphUpsertResult
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
from llm.adapters.in_memory import InMemoryLlmClient
from llm.adapters.protocols import LlmClientProtocol
from monitoring.adapters.in_memory import (
    InMemoryAlertHistoryWriter,
    InMemoryObservationSource,
    InMemoryObservationWriter,
)
from monitoring.adapters.postgres import (
    PostgresAlertHistoryStore,
    PostgresObservationSource,
    PostgresObservationStore,
)
from monitoring.adapters.protocols import (
    AlertHistoryWriter,
    ObservationSourceProtocol,
    ObservationWriter,
)
from monitoring.exceptions import MonitoringError
from monitoring.models import MonitoringBatch
from monitoring.service import MonitoringService, create_monitoring_service
from monitoring.service_models import MonitoringEvaluationRequest
from monitoring.metrics import observe_pipeline_stage
from records.adapters.in_memory import InMemoryRawRecordStore
from records.adapters.postgres import PostgresRawRecordStore
from records.adapters.protocols import RawRecordStore
from records.exceptions import RecordFeedNotFoundError
from records.mappers.feed_mapper import map_batch, map_observations
from shared.logging import bind_correlation_id, configure_logging, get_logger
from shared.tracing import setup_tracing, start_pipeline_span
from shared.types import Entity
from storage.adapters.in_memory import InMemoryObjectStore
from storage.protocols import ObjectStore
from vectorstore.adapters.in_memory import InMemoryVectorStore
from vectorstore.adapters.protocols import VectorStoreProtocol
from vectorstore.models import VectorRecord

__all__ = [
    "WorkerDependencies",
    "build_alert_history_writer",
    "build_connection_provider",
    "build_embedder",
    "build_entity_metric_repository",
    "build_explainability_context_source",
    "build_graph_repository",
    "build_graph_snapshot_source",
    "build_llm_client",
    "build_monitoring_observation_source",
    "build_object_store",
    "build_observation_writer",
    "build_raw_record_store",
    "build_risk_history_writer",
    "build_risk_signal_source",
    "build_vector_store",
    "build_worker_dependencies",
    "drain_ingestion_events",
    "handle_documents_chunked",
    "handle_documents_parsed",
    "handle_embeddings_complete",
    "handle_entities_extracted",
    "handle_entities_validated",
    "handle_event",
    "handle_graph_updated",
    "handle_graph_updated_for_analytics",
    "handle_records_ingested",
    "handle_risk_scored",
    "handle_risk_scored_for_graph",
    "handle_vectors_indexed",
    "main",
    "run_handler_with_retry",
    "run_worker",
]

configure_logging()
logger = get_logger("chili.worker")

SHUTDOWN_LOG_REQUESTED = "Shutdown requested, finishing current event..."
SHUTDOWN_LOG_DONE = "Worker stopped gracefully."


@dataclass(slots=True)
class WorkerDependencies:
    """Container for the assembled worker subsystem dependencies."""

    event_bus: EventBus
    ingestion_service: IngestionService
    document_chunker: DocumentChunker
    document_extractor: PatternDocumentExtractor
    extraction_validator: ExtractionResultValidator
    graph_service: GraphService
    embeddings_service: EmbeddingsServiceProtocol
    object_store: ObjectStore
    vector_store: VectorStoreProtocol
    llm_client: LlmClientProtocol
    gnn_service: GnnService
    risk_service: RiskService
    explainability_service: ExplainabilityService
    monitoring_service: MonitoringService
    records_config: RecordsConfig
    raw_record_store: RawRecordStore
    observation_writer: ObservationWriter
    entity_metric_repository: EntityMetricRepository
    metrics_throttle: MetricsRecomputeThrottle
    risk_history_writer: RiskHistoryWriter
    alert_history_writer: AlertHistoryWriter
    event_settings: EventBusSettings
    workflow_run_store: WorkflowRunStoreProtocol
    workflow_tracker: WorkflowEventTracker


# ---------------------------------------------------------------------------
# Adapter registries (E4-S08)
# ---------------------------------------------------------------------------


_ObjectStoreFactory = Callable[[ObjectStoreConfig], ObjectStore]
_GraphRepositoryFactory = Callable[[GraphDbConfig], GraphRepository]
_VectorStoreFactory = Callable[[VectorStoreConfig], VectorStoreProtocol]
_EmbedderFactory = Callable[[EmbeddingsConfig], EmbedderProtocol]
_LlmClientFactory = Callable[[LlmConfig], LlmClientProtocol]


def _build_in_memory_object_store(_: ObjectStoreConfig) -> ObjectStore:
    return InMemoryObjectStore()


def _build_local_fs_object_store(config: ObjectStoreConfig) -> ObjectStore:
    try:
        from storage.adapters.local_fs_adapter import LocalFsObjectStore
    except ImportError as exc:  # pragma: no cover - stdlib only
        raise ConfigurationError(
            subsystem="storage",
            backend="local",
            message=str(exc),
        ) from exc
    return LocalFsObjectStore(config)


def _build_s3_object_store(config: ObjectStoreConfig) -> ObjectStore:
    try:
        from storage.adapters.s3_adapter import S3ObjectStore
    except ImportError as exc:
        raise ConfigurationError(
            subsystem="storage",
            backend=config.backend,
            message=str(exc),
        ) from exc
    try:
        return S3ObjectStore(config)
    except (ImportError, ValueError) as exc:
        raise ConfigurationError(
            subsystem="storage",
            backend=config.backend,
            message=str(exc),
        ) from exc


_OBJECT_STORE_REGISTRY: dict[str, _ObjectStoreFactory] = {
    "in_memory": _build_in_memory_object_store,
    "local": _build_local_fs_object_store,
    "s3": _build_s3_object_store,
    "minio": _build_s3_object_store,
}


def _build_in_memory_graph_repository(_: GraphDbConfig) -> GraphRepository:
    return InMemoryGraphRepository()


def _build_neo4j_graph_repository(config: GraphDbConfig) -> GraphRepository:
    try:
        from graph.adapters.neo4j_adapter import Neo4jGraphRepository
    except ImportError as exc:
        raise ConfigurationError(
            subsystem="graph",
            backend=config.backend,
            message=str(exc),
        ) from exc
    try:
        return Neo4jGraphRepository(config, auth=resolve_graph_auth(config))
    except (ImportError, ValueError) as exc:
        raise ConfigurationError(
            subsystem="graph",
            backend=config.backend,
            message=str(exc),
        ) from exc


_GRAPH_REGISTRY: dict[str, _GraphRepositoryFactory] = {
    "in_memory": _build_in_memory_graph_repository,
    "neo4j": _build_neo4j_graph_repository,
}


def _build_in_memory_vector_store(_: VectorStoreConfig) -> VectorStoreProtocol:
    return InMemoryVectorStore()


def _build_qdrant_vector_store(config: VectorStoreConfig) -> VectorStoreProtocol:
    try:
        from vectorstore.adapters.qdrant_adapter import QdrantVectorStore
    except ImportError as exc:
        raise ConfigurationError(
            subsystem="vectorstore",
            backend=config.backend,
            message=str(exc),
        ) from exc
    try:
        return QdrantVectorStore(config)
    except (ImportError, ValueError) as exc:
        raise ConfigurationError(
            subsystem="vectorstore",
            backend=config.backend,
            message=str(exc),
        ) from exc


_VECTOR_STORE_REGISTRY: dict[str, _VectorStoreFactory] = {
    "in_memory": _build_in_memory_vector_store,
    "qdrant": _build_qdrant_vector_store,
}


def _build_in_memory_embedder(config: EmbeddingsConfig) -> EmbedderProtocol:
    return InMemoryEmbedder(provider=config.provider, dimensions=config.dimensions)


def _build_openai_embedder(config: EmbeddingsConfig) -> EmbedderProtocol:
    try:
        from embeddings.adapters.openai_adapter import OpenAIEmbedder
        from embeddings.exceptions import EmbeddingConfigurationError
    except ImportError as exc:
        raise ConfigurationError(
            subsystem="embeddings",
            backend=config.provider,
            message=str(exc),
        ) from exc
    try:
        return OpenAIEmbedder(config)
    except (ImportError, ValueError, EmbeddingConfigurationError) as exc:
        raise ConfigurationError(
            subsystem="embeddings",
            backend=config.provider,
            message=str(exc),
        ) from exc


def _build_sentence_transformers_embedder(
    config: EmbeddingsConfig,
) -> EmbedderProtocol:
    try:
        from embeddings.adapters.sentence_transformers_adapter import (
            SentenceTransformersEmbedder,
        )
    except ImportError as exc:
        raise ConfigurationError(
            subsystem="embeddings",
            backend=config.provider,
            message=str(exc),
        ) from exc
    try:
        return SentenceTransformersEmbedder(config)
    except (ImportError, ValueError) as exc:
        raise ConfigurationError(
            subsystem="embeddings",
            backend=config.provider,
            message=str(exc),
        ) from exc


_EMBEDDING_REGISTRY: dict[str, _EmbedderFactory] = {
    "local": _build_in_memory_embedder,
    "sentence_transformers": _build_sentence_transformers_embedder,
    "openai": _build_openai_embedder,
}


def _build_in_memory_llm_client(config: LlmConfig) -> LlmClientProtocol:
    return InMemoryLlmClient(provider=config.provider)


def _build_openai_llm_client(config: LlmConfig) -> LlmClientProtocol:
    try:
        from llm.adapters.openai_adapter import OpenAILlmClient
        from llm.exceptions import LlmConfigurationError
    except ImportError as exc:
        raise ConfigurationError(
            subsystem="llm",
            backend=config.provider,
            message=str(exc),
        ) from exc
    try:
        return OpenAILlmClient(config)
    except (ImportError, ValueError, LlmConfigurationError) as exc:
        raise ConfigurationError(
            subsystem="llm",
            backend=config.provider,
            message=str(exc),
        ) from exc


def _build_anthropic_llm_client(config: LlmConfig) -> LlmClientProtocol:
    try:
        from llm.adapters.anthropic_adapter import AnthropicLlmClient
        from llm.exceptions import LlmConfigurationError
    except ImportError as exc:
        raise ConfigurationError(
            subsystem="llm",
            backend=config.provider,
            message=str(exc),
        ) from exc
    try:
        return AnthropicLlmClient(config)
    except (ImportError, ValueError, LlmConfigurationError) as exc:
        raise ConfigurationError(
            subsystem="llm",
            backend=config.provider,
            message=str(exc),
        ) from exc


_LLM_REGISTRY: dict[str, _LlmClientFactory] = {
    "local": _build_in_memory_llm_client,
    "openai": _build_openai_llm_client,
    "anthropic": _build_anthropic_llm_client,
}


def build_graph_snapshot_source(
    _config: DomainConfig,
) -> GraphSnapshotSourceProtocol:
    """Return the configured GNN snapshot source adapter.

    The platform currently ships an in-memory adapter for tests; production
    adapters can later be wired through ``DomainConfig`` once an analytics
    section exists.
    """

    return InMemoryGraphSnapshotSource()


def build_risk_signal_source(_config: DomainConfig) -> RiskSignalSourceProtocol:
    """Return the configured risk signal source adapter."""

    return InMemoryRiskSignalSource()


def build_explainability_context_source(
    _config: DomainConfig,
) -> ExplainabilityContextSourceProtocol:
    """Return the configured explainability context source adapter."""

    return InMemoryExplainabilityContextSource()


def build_monitoring_observation_source(
    provider: ConnectionProvider | None,
) -> ObservationSourceProtocol:
    """Select a monitoring observation source: Postgres when a provider exists."""

    if provider is None:
        return InMemoryObservationSource()
    return PostgresObservationSource(provider)


def build_connection_provider(config: DomainConfig) -> ConnectionProvider | None:
    """Return a database connection provider, or None for the in-memory backend."""

    return create_connection_provider(config.database or DatabaseConfig())


def build_raw_record_store(
    provider: ConnectionProvider | None,
) -> RawRecordStore:
    """Select a raw record store: Postgres when a provider exists, else in-memory."""

    if provider is None:
        return InMemoryRawRecordStore()
    return PostgresRawRecordStore(provider)


def build_observation_writer(
    provider: ConnectionProvider | None,
) -> ObservationWriter:
    """Select an observation writer: Postgres when a provider exists, else in-memory."""

    if provider is None:
        return InMemoryObservationWriter()
    return PostgresObservationStore(provider)


def build_entity_metric_repository(
    provider: ConnectionProvider | None,
) -> EntityMetricRepository:
    """Select an entity-metric repository: Postgres when a provider exists."""

    if provider is None:
        return InMemoryEntityMetricRepository()
    return PostgresEntityMetricRepository(provider)


def build_risk_history_writer(
    provider: ConnectionProvider | None,
) -> RiskHistoryWriter:
    """Select a risk-history writer: Postgres when a provider exists."""

    if provider is None:
        return InMemoryRiskHistoryWriter()
    return PostgresRiskHistoryStore(provider)


def build_alert_history_writer(
    provider: ConnectionProvider | None,
) -> AlertHistoryWriter:
    """Select an alert-history writer: Postgres when a provider exists."""

    if provider is None:
        return InMemoryAlertHistoryWriter()
    return PostgresAlertHistoryStore(provider)


def _section_is_default(value: object, default: object) -> bool:
    """Return True when a config subsystem section equals its post-validator default.

    The :class:`DomainConfig` post-validator sets each subsystem section to its
    default model when the user omits it from the YAML, so an absent section is
    indistinguishable from an all-defaults section. Equality with the default
    is the contract the existing API DI layer uses, and we follow that pattern
    here so the worker behaves consistently with API-side wiring.
    """

    return value == default


def build_object_store(config: DomainConfig) -> ObjectStore:
    """Select an object store adapter from the configured backend."""

    storage_config = config.storage or ObjectStoreConfig()
    if _section_is_default(storage_config, ObjectStoreConfig()):
        return InMemoryObjectStore()
    factory = _OBJECT_STORE_REGISTRY.get(storage_config.backend)
    if factory is None:
        raise ConfigurationError(
            subsystem="storage",
            backend=storage_config.backend,
            message=(
                "Available backends: "
                + ", ".join(sorted(_OBJECT_STORE_REGISTRY))
            ),
        )
    return factory(storage_config)


def build_graph_repository(config: DomainConfig) -> GraphRepository:
    """Select a graph repository adapter from the configured backend."""

    graph_config = config.graph or GraphDbConfig()
    if _section_is_default(graph_config, GraphDbConfig()):
        return InMemoryGraphRepository()
    factory = _GRAPH_REGISTRY.get(graph_config.backend)
    if factory is None:
        raise ConfigurationError(
            subsystem="graph",
            backend=graph_config.backend,
            message="Available backends: " + ", ".join(sorted(_GRAPH_REGISTRY)),
        )
    return factory(graph_config)


def build_vector_store(config: DomainConfig) -> VectorStoreProtocol:
    """Select a vector store adapter from the configured backend."""

    vector_config = config.vectorstore or VectorStoreConfig()
    if _section_is_default(vector_config, VectorStoreConfig()):
        return InMemoryVectorStore()
    factory = _VECTOR_STORE_REGISTRY.get(vector_config.backend)
    if factory is None:
        raise ConfigurationError(
            subsystem="vectorstore",
            backend=vector_config.backend,
            message="Available backends: " + ", ".join(sorted(_VECTOR_STORE_REGISTRY)),
        )
    return factory(vector_config)


def build_embedder(config: DomainConfig) -> EmbedderProtocol:
    """Select an embedder adapter from the configured provider."""

    embeddings_config = config.embeddings or EmbeddingsConfig()
    if _section_is_default(embeddings_config, EmbeddingsConfig()):
        return InMemoryEmbedder()
    factory = _EMBEDDING_REGISTRY.get(embeddings_config.provider)
    if factory is None:
        raise ConfigurationError(
            subsystem="embeddings",
            backend=embeddings_config.provider,
            message="Available backends: " + ", ".join(sorted(_EMBEDDING_REGISTRY)),
        )
    return factory(embeddings_config)


def build_llm_client(config: DomainConfig) -> LlmClientProtocol:
    """Select an LLM client adapter from the configured provider."""

    llm_config = config.llm or LlmConfig()
    if _section_is_default(llm_config, LlmConfig()):
        return InMemoryLlmClient()
    factory = _LLM_REGISTRY.get(llm_config.provider)
    if factory is None:
        raise ConfigurationError(
            subsystem="llm",
            backend=llm_config.provider,
            message="Available backends: " + ", ".join(sorted(_LLM_REGISTRY)),
        )
    return factory(llm_config)


def build_worker_dependencies() -> WorkerDependencies:
    """Assemble the worker's runtime dependencies from configuration.

    Adapter selection is driven by ``DomainConfig`` subsystem sections; absent
    sections silently fall back to the in-memory adapters used by tests.
    """

    config = load_config()
    event_settings = load_event_bus_settings()
    event_bus = create_event_bus(event_settings)
    workflow_run_store = create_workflow_run_store_from_env()
    workflow_tracker = WorkflowEventTracker(workflow_run_store)

    object_store = build_object_store(config)
    graph_repository = build_graph_repository(config)
    vector_store = build_vector_store(config)
    embedder = build_embedder(config)
    llm_client = build_llm_client(config)

    orchestrator = DocumentParsingOrchestrator(
        create_default_registry(),
        fetcher=HttpxRemoteDocumentFetcher(),
    )
    ingestion_service = IngestionService(
        orchestrator,
        object_store=object_store,
        event_bus=event_bus,
    )
    chunker = create_document_chunker(config.ingestion.chunking)
    extractor = create_document_extractor(config.entities, config.relationships)
    validator = create_extraction_validator(config.entities, config.relationships)
    graph_service = create_graph_service(
        graph_repository,
        object_store=object_store,
        event_bus=event_bus,
    )
    embeddings_service = create_embeddings_service(embedder, event_bus=event_bus)
    gnn_service = create_gnn_service(
        build_graph_snapshot_source(config),
        event_bus=event_bus,
    )
    risk_service = create_risk_service(
        build_risk_signal_source(config),
        event_bus=event_bus,
    )
    explainability_service = create_explainability_service(
        build_explainability_context_source(config),
        event_bus=event_bus,
    )
    connection_provider = build_connection_provider(config)
    monitoring_config = config.monitoring
    monitoring_service = create_monitoring_service(
        build_monitoring_observation_source(connection_provider),
        event_bus=event_bus,
        dedup_window_seconds=(
            monitoring_config.dedup_window_seconds
            if monitoring_config is not None
            else 3600
        ),
        max_alerts_per_evaluation=(
            monitoring_config.max_alerts_per_evaluation
            if monitoring_config is not None
            else 100
        ),
        grouping_window_seconds=(
            monitoring_config.grouping_window_seconds
            if monitoring_config is not None
            else 300
        ),
    )
    raw_record_store = build_raw_record_store(connection_provider)
    observation_writer = build_observation_writer(connection_provider)
    entity_metric_repository = build_entity_metric_repository(connection_provider)
    risk_history_writer = build_risk_history_writer(connection_provider)
    alert_history_writer = build_alert_history_writer(connection_provider)
    analytics_config = config.analytics or AnalyticsConfig()
    metrics_throttle = MetricsRecomputeThrottle(
        min_interval_seconds=analytics_config.metrics_recompute_min_interval_seconds
    )
    records_config = config.records or RecordsConfig()

    return WorkerDependencies(
        event_bus=event_bus,
        ingestion_service=ingestion_service,
        document_chunker=chunker,
        document_extractor=extractor,
        extraction_validator=validator,
        graph_service=graph_service,
        embeddings_service=embeddings_service,
        object_store=object_store,
        vector_store=vector_store,
        llm_client=llm_client,
        gnn_service=gnn_service,
        risk_service=risk_service,
        explainability_service=explainability_service,
        monitoring_service=monitoring_service,
        records_config=records_config,
        raw_record_store=raw_record_store,
        observation_writer=observation_writer,
        entity_metric_repository=entity_metric_repository,
        metrics_throttle=metrics_throttle,
        risk_history_writer=risk_history_writer,
        alert_history_writer=alert_history_writer,
        event_settings=event_settings,
        workflow_run_store=workflow_run_store,
        workflow_tracker=workflow_tracker,
    )


# ---------------------------------------------------------------------------
# Pipeline handlers
# ---------------------------------------------------------------------------


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


def handle_graph_updated(
    event: GraphUpdatedEvent,
    *,
    embeddings_service: EmbeddingsServiceProtocol,
    object_store: ObjectStore,
    event_bus: EventBus,
) -> int:
    """Generate and persist embeddings for entities upserted into the graph."""
    references: list[EmbeddingsCompleteDocumentReference] = []
    ready_references: list[KnowledgeBaseReadyReference] = []
    for document in event.documents:
        if document.graph_update_storage_key is None:
            raise ValueError(
                "GraphUpdatedEvent requires graph_update_storage_key for embeddings."
            )
        if document.validation_storage_key is None:
            raise ValueError(
                "GraphUpdatedEvent requires validation_storage_key for embeddings."
            )

        graph_update = _load_graph_update(
            object_store,
            document.graph_update_storage_key,
        )
        validation_report = _load_validation_report(
            object_store,
            document.validation_storage_key,
        )
        entities = _select_upserted_entities(
            graph_update.upserted_entity_ids,
            validation_report.valid_entities,
        )

        if not entities:
            ready_references.append(
                KnowledgeBaseReadyReference(
                    knowledge_base_id=document.knowledge_base_id,
                    entity_count=document.upserted_entity_count,
                    relationship_count=document.upserted_relationship_count,
                    vector_count=0,
                )
            )
            continue

        response = embeddings_service.embed(
            EmbedRequest(
                knowledge_base_id=document.knowledge_base_id,
                submissions=[
                    EmbedSubmission(
                        content_id=entity.id,
                        content=_build_entity_embedding_text(entity),
                    )
                    for entity in entities
                ],
            )
        )
        embeddings_result = EmbeddingResult(
            request_id=response.request_id,
            vectors={item.content_id: item.vector for item in response.items},
            metadata=EmbeddingMetadata(
                model_name=response.model_name,
                dimensions=response.dimensions,
                provider="embeddings-service",
            ),
        )
        embeddings_storage_key = _build_embeddings_storage_key(
            document.graph_update_storage_key,
        )
        object_store.put_bytes(
            embeddings_storage_key,
            embeddings_result.model_dump_json().encode("utf-8"),
            media_type="application/json",
            metadata={
                "knowledge_base_id": document.knowledge_base_id,
                "source_document_id": document.source_document_id,
                "parsed_document_id": document.parsed_document_id,
                "extraction_result_id": document.extraction_result_id,
                "validation_report_id": document.validation_report_id,
                "graph_update_storage_key": document.graph_update_storage_key,
                "entity_count": len(entities),
                "embedding_request_id": embeddings_result.request_id,
                "embedding_model_name": embeddings_result.metadata.model_name,
                "embedding_dimensions": embeddings_result.metadata.dimensions,
            },
        )
        references.append(
            EmbeddingsCompleteDocumentReference(
                knowledge_base_id=document.knowledge_base_id,
                source_document_id=document.source_document_id,
                parsed_document_id=document.parsed_document_id,
                extraction_result_id=document.extraction_result_id,
                validation_report_id=document.validation_report_id,
                entity_count=len(entities),
                graph_update_storage_key=document.graph_update_storage_key,
                embeddings_storage_key=embeddings_storage_key,
            )
        )

    if references:
        event_bus.publish(
            EmbeddingsCompleteEvent(
                correlation_id=event.correlation_id,
                documents=references,
            )
        )
    if ready_references:
        event_bus.publish(
            KnowledgeBaseReadyEvent(
                correlation_id=event.correlation_id,
                knowledge_bases=ready_references,
            )
        )
    return len(references)


def handle_graph_updated_for_analytics(
    event: GraphUpdatedEvent,
    *,
    gnn_service: GnnService,
    risk_service: RiskService,
    explainability_service: ExplainabilityService,
    graph_service: GraphService,
    event_bus: EventBus,
    object_store: ObjectStore | None = None,
    entity_metric_repository: EntityMetricRepository | None = None,
    metrics_throttle: MetricsRecomputeThrottle | None = None,
) -> int:
    """Run Flow B (GNN -> risk -> explainability -> alerts.created).

    Each upserted entity is processed independently. Failures are caught and
    surfaced as ``analysis.failed`` events without aborting the pipeline.
    Successful runs additionally write analytics-derived properties back to
    the graph (E7-S11) before publishing the ``alerts.created`` aggregate.
    """

    alerts: list[AlertCreatedReference] = []
    for document in event.documents:
        knowledge_base_id = document.knowledge_base_id
        upserted_entity_ids = _resolve_upserted_entity_ids(
            document, object_store=object_store
        )
        if not upserted_entity_ids:
            continue

        gnn_response = _run_gnn_stage(
            event=event,
            gnn_service=gnn_service,
            knowledge_base_id=knowledge_base_id,
            event_bus=event_bus,
        )
        if gnn_response is None:
            continue

        for entity_id in upserted_entity_ids:
            risk_response = _run_risk_stage(
                event=event,
                risk_service=risk_service,
                knowledge_base_id=knowledge_base_id,
                entity_id=entity_id,
                event_bus=event_bus,
            )
            if risk_response is None:
                continue

            _write_analytics_properties_to_graph(
                graph_service=graph_service,
                knowledge_base_id=knowledge_base_id,
                entity_id=entity_id,
                gnn_response=gnn_response,
                risk_response=risk_response,
            )

            alert_reference = _run_explainability_stage(
                event=event,
                explainability_service=explainability_service,
                knowledge_base_id=knowledge_base_id,
                entity_id=entity_id,
                risk_response=risk_response,
                event_bus=event_bus,
            )
            if alert_reference is not None:
                alerts.append(alert_reference)

    _persist_graph_metrics_for_event(
        event=event,
        graph_service=graph_service,
        entity_metric_repository=entity_metric_repository,
        metrics_throttle=metrics_throttle,
    )

    if alerts:
        event_bus.publish(
            AlertsCreatedEvent(
                correlation_id=event.correlation_id,
                alerts=alerts,
            )
        )
    return len(alerts)


def _resolve_upserted_entity_ids(
    document: object,
    *,
    object_store: ObjectStore | None,
) -> list[str]:
    upserted_ids: object = getattr(document, "upserted_entity_ids", None)
    if isinstance(upserted_ids, list):
        typed_ids = cast("list[object]", upserted_ids)
        return [str(entity_id) for entity_id in typed_ids]
    storage_key = getattr(document, "graph_update_storage_key", None)
    if (
        object_store is not None
        and isinstance(storage_key, str)
        and storage_key
    ):
        try:
            graph_update = _load_graph_update(object_store, storage_key)
        except Exception:  # noqa: BLE001 - tolerate missing artifacts
            return []
        return list(graph_update.upserted_entity_ids)
    return []


def _run_gnn_stage(
    *,
    event: GraphUpdatedEvent,
    gnn_service: GnnService,
    knowledge_base_id: str,
    event_bus: EventBus,
) -> GnnAnalysisResponse | None:
    try:
        return gnn_service.analyze(
            GnnAnalysisRequest(knowledge_base_id=knowledge_base_id),
        )
    except GnnError as exc:
        _publish_analysis_failed(
            event_bus=event_bus,
            correlation_id=event.correlation_id,
            knowledge_base_id=knowledge_base_id,
            entity_id="",
            stage="gnn",
            error_message=str(exc),
        )
        return None


def _run_risk_stage(
    *,
    event: GraphUpdatedEvent,
    risk_service: RiskService,
    knowledge_base_id: str,
    entity_id: str,
    event_bus: EventBus,
) -> RiskAssessmentResponse | None:
    try:
        return risk_service.assess(
            RiskAssessmentRequest(
                knowledge_base_id=knowledge_base_id,
                entity_id=entity_id,
            )
        )
    except RiskError as exc:
        _publish_analysis_failed(
            event_bus=event_bus,
            correlation_id=event.correlation_id,
            knowledge_base_id=knowledge_base_id,
            entity_id=entity_id,
            stage="risk",
            error_message=str(exc),
        )
        return None


def _run_explainability_stage(
    *,
    event: GraphUpdatedEvent,
    explainability_service: ExplainabilityService,
    knowledge_base_id: str,
    entity_id: str,
    risk_response: RiskAssessmentResponse,
    event_bus: EventBus,
) -> AlertCreatedReference | None:
    alert_id = f"alert-{entity_id}-{risk_response.request_id}"
    try:
        response = explainability_service.generate(
            ExplainabilityRequest(
                knowledge_base_id=knowledge_base_id,
                alert_id=alert_id,
            )
        )
    except ExplainabilityError as exc:
        _publish_analysis_failed(
            event_bus=event_bus,
            correlation_id=event.correlation_id,
            knowledge_base_id=knowledge_base_id,
            entity_id=entity_id,
            stage="explainability",
            error_message=str(exc),
        )
        return None
    return AlertCreatedReference(
        knowledge_base_id=knowledge_base_id,
        alert_id=response.alert_id,
        entity_id=entity_id,
        severity=risk_response.risk_level,
        evidence_pack_id=response.evidence_pack.id,
        status="open",
        title=f"{risk_response.risk_level.title()} risk: {entity_id}",
        reasoning=response.evidence_pack.reasoning,
    )


def _persist_graph_metrics_for_event(
    *,
    event: GraphUpdatedEvent,
    graph_service: GraphService,
    entity_metric_repository: EntityMetricRepository | None,
    metrics_throttle: MetricsRecomputeThrottle | None,
) -> None:
    """Flow 2 — persist graph metrics per KB, throttled to avoid recompute storms.

    Best-effort: a failure here is logged but never aborts Flow B. The throttle
    drops recomputes that arrive within the configured per-KB interval so a
    burst of graph updates cannot thrash the system.
    """

    if entity_metric_repository is None or metrics_throttle is None:
        return
    now = __datetime__.now(tz=__timezone__.utc)
    seen: set[str] = set()
    for document in event.documents:
        knowledge_base_id = document.knowledge_base_id
        if knowledge_base_id in seen:
            continue
        seen.add(knowledge_base_id)
        if not metrics_throttle.should_recompute(knowledge_base_id, now=now):
            logger.debug(
                "Skipping throttled graph-metric recompute for kb=%s",
                knowledge_base_id,
            )
            continue
        try:
            metrics = graph_service.compute_metrics(knowledge_base_id)
            entity_metric_repository.record_metrics(
                [
                    EntityMetricSample(
                        knowledge_base_id=knowledge_base_id,
                        entity_id=GRAPH_SCOPE_ENTITY_ID,
                        metric_name=METRIC_ENTITY_COUNT,
                        value=float(metrics.entity_count),
                        observed_at=now,
                        correlation_id=event.correlation_id,
                    ),
                    EntityMetricSample(
                        knowledge_base_id=knowledge_base_id,
                        entity_id=GRAPH_SCOPE_ENTITY_ID,
                        metric_name=METRIC_RELATIONSHIP_COUNT,
                        value=float(metrics.relationship_count),
                        observed_at=now,
                        correlation_id=event.correlation_id,
                    ),
                    EntityMetricSample(
                        knowledge_base_id=knowledge_base_id,
                        entity_id=GRAPH_SCOPE_ENTITY_ID,
                        metric_name=METRIC_AVG_DEGREE,
                        value=metrics.avg_degree,
                        observed_at=now,
                        correlation_id=event.correlation_id,
                    ),
                ]
            )
        except Exception as exc:  # noqa: BLE001 - metrics must not block Flow B
            logger.warning(
                "Failed to persist graph metrics for kb=%s: %s",
                knowledge_base_id,
                exc,
            )


def _write_analytics_properties_to_graph(
    *,
    graph_service: GraphService,
    knowledge_base_id: str,
    entity_id: str,
    gnn_response: GnnAnalysisResponse,
    risk_response: RiskAssessmentResponse,
) -> None:
    properties: dict[str, object] = {
        "risk_score": float(risk_response.overall_score),
        "risk_level": risk_response.risk_level,
        "risk_assessed_at": __datetime__.now(tz=__timezone__.utc).isoformat(),
    }
    centrality_score = _resolve_centrality_score(gnn_response, entity_id)
    if centrality_score is not None:
        properties["centrality_score"] = centrality_score
    community_id = _resolve_community_id(gnn_response, entity_id)
    if community_id is not None:
        properties["community_id"] = community_id
    try:
        graph_service.update_entity_properties(
            knowledge_base_id, entity_id, properties
        )
    except Exception as exc:  # noqa: BLE001 - graph backend may be unavailable
        logger.warning(
            "Failed to write analytics properties to graph kb=%s entity=%s: %s",
            knowledge_base_id,
            entity_id,
            exc,
        )


def _resolve_centrality_score(
    gnn_response: GnnAnalysisResponse,
    entity_id: str,
) -> float | None:
    for node in gnn_response.scored_nodes:
        if node.entity_id == entity_id:
            return float(node.score)
    return None


def _resolve_community_id(
    gnn_response: GnnAnalysisResponse,
    entity_id: str,
) -> str | None:
    for node in gnn_response.scored_nodes:
        if node.entity_id == entity_id:
            return node.cluster_id
    for community in gnn_response.communities:
        if entity_id in community.member_entity_ids:
            return community.community_id
    return None


def handle_risk_scored(
    event: RiskScoredEvent,
    *,
    monitoring_service: MonitoringService,
    event_bus: EventBus,
) -> int:
    """Trigger continuous monitoring evaluation in response to risk scores.

    Each ``RiskScoredReference`` in the event is mapped to a monitoring batch
    derived from the risk assessment's request id. ``MonitoringService.evaluate``
    is responsible for emitting ``alerts.created`` when alerts are generated.
    Failures are logged and absorbed so the broader pipeline does not stall.
    """

    processed = 0
    for assessment in event.assessments:
        try:
            response = monitoring_service.evaluate(
                MonitoringEvaluationRequest(
                    knowledge_base_id=assessment.knowledge_base_id,
                    batch_id=assessment.request_id,
                )
            )
        except MonitoringError as exc:
            logger.error(
                "Monitoring evaluation failed kb=%s request=%s entity=%s: %s",
                assessment.knowledge_base_id,
                assessment.request_id,
                assessment.entity_id,
                exc,
            )
            continue
        except Exception as exc:  # noqa: BLE001 - monitoring must not abort pipeline
            logger.error(
                "Monitoring evaluation crashed kb=%s request=%s entity=%s: %s",
                assessment.knowledge_base_id,
                assessment.request_id,
                assessment.entity_id,
                exc,
            )
            continue

        # MonitoringService.evaluate() publishes AlertsCreatedEvent itself when
        # alerts > 0; the coordinator only counts processed assessments here.
        if response.alert_count >= 0:
            processed += 1
    return processed


def handle_risk_scored_for_graph(
    event: RiskScoredEvent,
    *,
    risk_history_writer: RiskHistoryWriter,
    graph_service: GraphService,
) -> int:
    """Flow 3 — persist risk assessments and snapshot risk onto the graph entity.

    Idempotent: ``risk_score_history`` is keyed by request_id and
    ``update_entity_properties`` is a property merge, so the worker's retry/DLQ
    wrapper can safely re-run this handler. The graph write publishes no event,
    so it cannot re-trigger the analytics pipeline.
    """

    assessed_at = __datetime__.now(tz=__timezone__.utc)
    processed = 0
    for assessment in event.assessments:
        record = RiskAssessmentRecord(
            knowledge_base_id=assessment.knowledge_base_id,
            entity_id=assessment.entity_id,
            request_id=assessment.request_id,
            overall_score=assessment.overall_score,
            risk_level=assessment.risk_level,
            factors=[
                RiskFactor(
                    factor_name=factor.factor_name,
                    raw_value=factor.raw_value,
                    weight=factor.weight,
                    contribution=factor.contribution,
                    rationale=factor.rationale,
                )
                for factor in assessment.factors
            ],
            assessed_at=assessed_at,
        )
        risk_history_writer.write_assessment(record)
        try:
            graph_service.update_entity_properties(
                assessment.knowledge_base_id,
                assessment.entity_id,
                {
                    "risk_score": float(assessment.overall_score),
                    "risk_level": assessment.risk_level,
                    "risk_assessed_at": assessed_at.isoformat(),
                },
            )
        except Exception as exc:  # noqa: BLE001 - graph backend may be unavailable
            logger.warning(
                "Failed to snapshot risk to graph kb=%s entity=%s: %s",
                assessment.knowledge_base_id,
                assessment.entity_id,
                exc,
            )
        processed += 1
    return processed


def handle_records_ingested(
    event: RecordsIngestedEvent,
    *,
    records_config: RecordsConfig,
    raw_record_store: RawRecordStore,
    graph_service: GraphService,
    observation_writer: ObservationWriter,
) -> int:
    """Flow 1 — fan a structured-records batch out to the graph and observations.

    A single handler: map rows to graph entities/relationships and upsert them,
    then derive observations and persist them. Every write is idempotent so the
    worker's retry/DLQ wrapper can safely re-run this handler.
    """

    feed = _resolve_records_feed(records_config, event.feed_name)
    records = raw_record_store.load_batch(
        knowledge_base_id=event.knowledge_base_id,
        correlation_id=event.correlation_id,
    )
    if not records:
        logger.info(
            "No raw records found for feed=%s kb=%s correlation=%s",
            event.feed_name,
            event.knowledge_base_id,
            event.correlation_id,
        )
        return 0

    mapped = map_batch(feed, records)
    graph_service.upsert_records_graph(
        event.knowledge_base_id, mapped.entities, mapped.relationships
    )

    observations = map_observations(feed, records)
    if observations:
        observation_writer.write_observations(
            MonitoringBatch(
                knowledge_base_id=event.knowledge_base_id,
                batch_id=event.correlation_id,
                observations=observations,
            ),
            correlation_id=event.correlation_id,
        )
    return len(records)


def _resolve_records_feed(
    records_config: RecordsConfig, feed_name: str
) -> RecordFeedConfig:
    for feed in records_config.feeds:
        if feed.name == feed_name:
            return feed
    raise RecordFeedNotFoundError(feed_name)


def _publish_analysis_failed(
    *,
    event_bus: EventBus,
    correlation_id: str,
    knowledge_base_id: str,
    entity_id: str,
    stage: str,
    error_message: str,
) -> None:
    event_bus.publish(
        AnalysisFailedEvent(
            correlation_id=correlation_id,
            knowledge_base_id=knowledge_base_id,
            entity_id=entity_id,
            stage=stage,
            error_message=error_message,
        )
    )
    logger.warning(
        "Analytics stage failed: stage=%s kb=%s entity=%s error=%s",
        stage,
        knowledge_base_id,
        entity_id,
        error_message,
    )


def handle_embeddings_complete(
    event: EmbeddingsCompleteEvent,
    *,
    vector_store: VectorStoreProtocol,
    object_store: ObjectStore,
    event_bus: EventBus,
) -> int:
    """Index embeddings into the vector store and publish ``vectors.indexed``."""

    document_references: list[VectorsIndexedDocumentReference] = []
    record_references: list[VectorIndexedReference] = []

    for document in event.documents:
        embeddings_result = _load_embeddings_result(
            object_store,
            document.embeddings_storage_key,
        )
        validation_report = _load_validation_report_from_graph_artifact(
            object_store,
            document.graph_update_storage_key,
        )
        entities_by_id = {entity.id: entity for entity in validation_report.valid_entities}

        records: list[VectorRecord] = []
        for content_id in sorted(embeddings_result.vectors):
            embedding = embeddings_result.vectors[content_id]
            entity = entities_by_id.get(content_id)
            metadata: dict[str, str | int | float | bool] = {
                "knowledge_base_id": document.knowledge_base_id,
                "entity_id": content_id,
                "source_document_id": document.source_document_id,
                "extraction_result_id": document.extraction_result_id,
                "validation_report_id": document.validation_report_id,
            }
            if entity is not None:
                metadata["entity_type"] = entity.type
            records.append(
                VectorRecord(
                    id=f"{document.knowledge_base_id}:{content_id}",
                    knowledge_base_id=document.knowledge_base_id,
                    content_id=content_id,
                    embedding=list(embedding),
                    metadata=metadata,
                )
            )

        if not records:
            continue

        stored_records = vector_store.upsert_records(
            document.knowledge_base_id,
            records,
        )

        document_references.append(
            VectorsIndexedDocumentReference(
                knowledge_base_id=document.knowledge_base_id,
                source_document_id=document.source_document_id,
                parsed_document_id=document.parsed_document_id,
                extraction_result_id=document.extraction_result_id,
                validation_report_id=document.validation_report_id,
                vector_count=len(stored_records),
                embeddings_storage_key=document.embeddings_storage_key,
                record_ids=[record.id for record in stored_records],
            )
        )
        record_references.extend(
            VectorIndexedReference(
                knowledge_base_id=record.knowledge_base_id,
                record_id=record.id,
                content_id=record.content_id,
                dimension=len(record.embedding),
            )
            for record in stored_records
        )

    if document_references:
        event_bus.publish(
            VectorsIndexedEvent(
                correlation_id=event.correlation_id,
                records=record_references,
                documents=document_references,
            )
        )
    return len(document_references)


def handle_vectors_indexed(
    event: VectorsIndexedEvent,
    *,
    graph_repository: GraphRepository,
    event_bus: EventBus,
) -> int:
    """Publish a ``kb.ready`` event summarizing pipeline counts per KB."""

    if not event.documents:
        return 0

    grouped: dict[str, dict[str, int]] = {}
    for document in event.documents:
        bucket = grouped.setdefault(
            document.knowledge_base_id,
            {"vector_count": 0},
        )
        bucket["vector_count"] += document.vector_count

    references: list[KnowledgeBaseReadyReference] = []
    for knowledge_base_id, totals in grouped.items():
        entity_count = _count_entities(graph_repository, knowledge_base_id)
        relationship_count = _count_relationships(graph_repository, knowledge_base_id)
        references.append(
            KnowledgeBaseReadyReference(
                knowledge_base_id=knowledge_base_id,
                entity_count=entity_count,
                relationship_count=relationship_count,
                vector_count=totals["vector_count"],
            )
        )

    if references:
        event_bus.publish(
            KnowledgeBaseReadyEvent(
                correlation_id=event.correlation_id,
                knowledge_bases=references,
            )
        )
    return len(references)


def _count_entities(graph_repository: GraphRepository, knowledge_base_id: str) -> int:
    try:
        return graph_repository.count_entities(knowledge_base_id)
    except Exception:  # noqa: BLE001 - graph backend may be unavailable in tests
        logger.debug("Graph entity count unavailable for kb=%s", knowledge_base_id)
        return 0


def _count_relationships(graph_repository: GraphRepository, knowledge_base_id: str) -> int:
    try:
        return graph_repository.count_relationships(knowledge_base_id)
    except Exception:  # noqa: BLE001 - graph backend may be unavailable in tests
        logger.debug("Graph relationship count unavailable for kb=%s", knowledge_base_id)
        return 0


def _load_graph_update(
    object_store: ObjectStore,
    graph_update_storage_key: str,
) -> GraphUpsertResult:
    """Decode a persisted graph update artifact with a typed schema."""
    stored = object_store.get_bytes(graph_update_storage_key)
    return GraphUpsertResult.model_validate_json(stored.content)


def _load_validation_report(
    object_store: ObjectStore,
    validation_storage_key: str,
) -> ValidationReport:
    """Decode the validation artifact that contains runtime entities."""
    stored = object_store.get_bytes(validation_storage_key)
    return ValidationReport.model_validate_json(stored.content)


def _load_validation_report_from_graph_artifact(
    object_store: ObjectStore,
    graph_update_storage_key: str,
) -> ValidationReport:
    """Resolve the validation artifact referenced by a graph update artifact."""

    graph_update = _load_graph_update(object_store, graph_update_storage_key)
    validation_storage_key = (
        graph_update_storage_key.replace("/graph_updates/", "/validations/")
    )
    try:
        return _load_validation_report(object_store, validation_storage_key)
    except KeyError:
        # Fall back to an empty report; downstream consumers tolerate missing
        # entity-type metadata. The graph_update payload is still authoritative
        # for IDs so we synthesize empty placeholders.
        return ValidationReport(
            id=graph_update.validation_report_id,
            extraction_result_id=graph_update.extraction_result_id,
            source_document_id=graph_update.source_document_id,
            valid_entities=[],
        )


def _load_embeddings_result(
    object_store: ObjectStore,
    embeddings_storage_key: str,
) -> EmbeddingResult:
    """Decode a persisted embeddings result artifact."""
    stored = object_store.get_bytes(embeddings_storage_key)
    return EmbeddingResult.model_validate_json(stored.content)


def _select_upserted_entities(
    upserted_entity_ids: list[str],
    valid_entities: list[Entity],
) -> list[Entity]:
    """Return upserted entities in deterministic ID order."""
    entities_by_id = {entity.id: entity for entity in valid_entities}
    missing_ids = sorted(
        entity_id
        for entity_id in set(upserted_entity_ids)
        if entity_id not in entities_by_id
    )
    if missing_ids:
        raise ValueError(
            "Graph update references entities missing from validation artifact: "
            f"{missing_ids}"
        )
    return [entities_by_id[entity_id] for entity_id in sorted(set(upserted_entity_ids))]


def _build_entity_embedding_text(entity: Entity) -> str:
    """Build stable entity text from explicit fields and sorted properties."""
    preferred_text = _preferred_entity_text(entity)
    if preferred_text is not None:
        return preferred_text

    property_fragments = [
        f"{key}={_stringify_embedding_value(entity.properties[key])}"
        for key in sorted(entity.properties)
    ]
    if property_fragments:
        return f"id={entity.id}\ntype={entity.type}\n" + "\n".join(property_fragments)
    return f"id={entity.id}\ntype={entity.type}"


def _preferred_entity_text(entity: Entity) -> str | None:
    """Return the first non-empty explicit embedding text property if present."""
    for key in ("embedding_text", "text", "name", "display_label"):
        value = entity.properties.get(key)
        if isinstance(value, str) and value.strip() != "":
            return value.strip()
    return None


def _stringify_embedding_value(value: object) -> str:
    """Serialize property values deterministically for embedding text."""
    return json.dumps(
        value,
        default=str,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _build_embeddings_storage_key(graph_update_storage_key: str) -> str:
    """Derive the embeddings artifact key from the source graph artifact key."""
    without_suffix = (
        graph_update_storage_key[:-5]
        if graph_update_storage_key.endswith(".json")
        else graph_update_storage_key
    )
    embedding_base = without_suffix.replace("/graph_updates/", "/embeddings/")
    return f"{embedding_base}.embeddings.json"


# ---------------------------------------------------------------------------
# Dispatch + retry/DLQ
# ---------------------------------------------------------------------------


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
    embeddings_service: EmbeddingsServiceProtocol | None = None,
    vector_store: VectorStoreProtocol | None = None,
    graph_repository: GraphRepository | None = None,
    gnn_service: GnnService | None = None,
    risk_service: RiskService | None = None,
    explainability_service: ExplainabilityService | None = None,
    monitoring_service: MonitoringService | None = None,
    records_config: RecordsConfig | None = None,
    raw_record_store: RawRecordStore | None = None,
    observation_writer: ObservationWriter | None = None,
    entity_metric_repository: EntityMetricRepository | None = None,
    metrics_throttle: MetricsRecomputeThrottle | None = None,
    risk_history_writer: RiskHistoryWriter | None = None,
    alert_history_writer: AlertHistoryWriter | None = None,
    workflow_tracker: WorkflowEventTracker | None = None,
) -> int:
    """Handle a single event and return the number of processed documents."""

    event = delivery.event
    bind_correlation_id(event.correlation_id)
    stage_name = f"pipeline.{event.event_type}"
    with start_pipeline_span(
        stage_name, correlation_id=event.correlation_id
    ), observe_pipeline_stage(event.event_type):
        if workflow_tracker is not None and not workflow_tracker.begin_event(event):
            logger.info(
                "Skipping terminal workflow event. event_type=%s correlation_id=%s",
                event.event_type,
                event.correlation_id,
            )
            return 0
        processed = _dispatch_event(
            event=event,
            delivery=delivery,
            ingestion_service=ingestion_service,
            document_chunker=document_chunker,
            document_extractor=document_extractor,
            extraction_validator=extraction_validator,
            graph_service=graph_service,
            object_store=object_store,
            event_bus=event_bus,
            embeddings_service=embeddings_service,
            vector_store=vector_store,
            graph_repository=graph_repository,
            gnn_service=gnn_service,
            risk_service=risk_service,
            explainability_service=explainability_service,
            monitoring_service=monitoring_service,
            records_config=records_config,
            raw_record_store=raw_record_store,
            observation_writer=observation_writer,
            entity_metric_repository=entity_metric_repository,
            metrics_throttle=metrics_throttle,
            risk_history_writer=risk_history_writer,
            alert_history_writer=alert_history_writer,
        )
        if workflow_tracker is not None:
            workflow_tracker.complete_event(event)
        return processed


def _dispatch_event(
    *,
    event: AnyEvent,
    delivery: EventDelivery,
    ingestion_service: IngestionService,
    document_chunker: DocumentChunker,
    document_extractor: PatternDocumentExtractor,
    extraction_validator: ExtractionResultValidator,
    graph_service: GraphService,
    object_store: ObjectStore,
    event_bus: EventBus,
    embeddings_service: EmbeddingsServiceProtocol | None,
    vector_store: VectorStoreProtocol | None,
    graph_repository: GraphRepository | None,
    gnn_service: GnnService | None,
    risk_service: RiskService | None,
    explainability_service: ExplainabilityService | None,
    monitoring_service: MonitoringService | None,
    records_config: RecordsConfig | None,
    raw_record_store: RawRecordStore | None,
    observation_writer: ObservationWriter | None,
    entity_metric_repository: EntityMetricRepository | None,
    metrics_throttle: MetricsRecomputeThrottle | None,
    risk_history_writer: RiskHistoryWriter | None,
    alert_history_writer: AlertHistoryWriter | None,
) -> int:
    del delivery  # reserved for future stream offsets / dlq metadata
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
    if isinstance(event, GraphUpdatedEvent):
        if embeddings_service is None:
            raise ValueError("GraphUpdatedEvent requires an embeddings_service.")
        processed = handle_graph_updated(
            event,
            embeddings_service=embeddings_service,
            object_store=object_store,
            event_bus=event_bus,
        )
        if (
            gnn_service is not None
            and risk_service is not None
            and explainability_service is not None
        ):
            try:
                handle_graph_updated_for_analytics(
                    event,
                    gnn_service=gnn_service,
                    risk_service=risk_service,
                    explainability_service=explainability_service,
                    graph_service=graph_service,
                    event_bus=event_bus,
                    object_store=object_store,
                    entity_metric_repository=entity_metric_repository,
                    metrics_throttle=metrics_throttle,
                )
            except Exception as exc:  # noqa: BLE001 - analytics must not block Flow A
                logger.warning(
                    "Flow B analytics handler raised; Flow A already completed. error=%s",
                    exc,
                )
        return processed
    if isinstance(event, EmbeddingsCompleteEvent):
        if vector_store is None:
            raise ValueError("EmbeddingsCompleteEvent requires a vector_store.")
        return handle_embeddings_complete(
            event,
            vector_store=vector_store,
            object_store=object_store,
            event_bus=event_bus,
        )
    if isinstance(event, VectorsIndexedEvent):
        if graph_repository is None:
            raise ValueError("VectorsIndexedEvent requires a graph_repository.")
        return handle_vectors_indexed(
            event,
            graph_repository=graph_repository,
            event_bus=event_bus,
        )
    if isinstance(event, RiskScoredEvent):
        processed = 0
        if monitoring_service is not None:
            try:
                processed = handle_risk_scored(
                    event,
                    monitoring_service=monitoring_service,
                    event_bus=event_bus,
                )
            except Exception as exc:  # noqa: BLE001 - monitoring must not abort pipeline
                logger.warning(
                    "Monitoring stream consumer raised; continuing. error=%s",
                    exc,
                )
        if risk_history_writer is not None:
            try:
                handle_risk_scored_for_graph(
                    event,
                    risk_history_writer=risk_history_writer,
                    graph_service=graph_service,
                )
            except Exception as exc:  # noqa: BLE001 - write-back must not abort pipeline
                logger.warning(
                    "Risk graph write-back raised; continuing. error=%s",
                    exc,
                )
        return processed
    if isinstance(event, RecordsIngestedEvent):
        if (
            records_config is None
            or raw_record_store is None
            or observation_writer is None
        ):
            logger.warning(
                "RecordsIngestedEvent received but records dependencies are not wired."
            )
            return 0
        return handle_records_ingested(
            event,
            records_config=records_config,
            raw_record_store=raw_record_store,
            graph_service=graph_service,
            observation_writer=observation_writer,
        )
    return 0


async def run_handler_with_retry(
    handler: Callable[[], int],
    *,
    event: AnyEvent,
    event_bus: EventBus,
    retry_policy: RetryPolicy,
    sleep: Callable[[float], "asyncio.Future[None] | object"] = asyncio.sleep,
    on_failure: Callable[[BaseException], None] | None = None,
) -> int:
    """Run ``handler`` with exponential-backoff retry and DLQ on exhaustion.

    ``sleep`` is injected so unit tests can avoid waiting on the event loop.
    """

    last_exc: BaseException | None = None
    for attempt in range(retry_policy.max_retries + 1):
        try:
            return handler()
        except Exception as exc:  # noqa: BLE001 - we route to DLQ
            last_exc = exc
            if attempt >= retry_policy.max_retries:
                break
            delay = retry_policy.delay_for_attempt(attempt + 1)
            logger.warning(
                "Handler failed; will retry. event_type=%s correlation_id=%s "
                "attempt=%d delay=%.2fs error=%s",
                event.event_type,
                event.correlation_id,
                attempt + 1,
                delay,
                str(exc),
            )
            await cast("asyncio.Future[None]", sleep(delay))

    assert last_exc is not None  # noqa: S101 - retry loop guarantees this
    error_info = DlqErrorInfo(
        error_message=str(last_exc),
        traceback="".join(
            traceback.format_exception(type(last_exc), last_exc, last_exc.__traceback__)
        ),
        retry_count=retry_policy.max_retries,
    )
    logger.error(
        "Handler exhausted retries; routing to DLQ. event_type=%s correlation_id=%s "
        "max_retries=%d error=%s",
        event.event_type,
        event.correlation_id,
        retry_policy.max_retries,
        str(last_exc),
    )
    if on_failure is not None:
        on_failure(last_exc)
    event_bus.publish_to_dlq(event, error_info)
    return 0


async def drain_ingestion_events(
    event_bus: EventBus,
    ingestion_service: IngestionService,
    document_chunker: DocumentChunker,
    document_extractor: PatternDocumentExtractor,
    extraction_validator: ExtractionResultValidator,
    graph_service: GraphService,
    object_store: ObjectStore,
    *,
    embeddings_service: EmbeddingsServiceProtocol | None = None,
    vector_store: VectorStoreProtocol | None = None,
    graph_repository: GraphRepository | None = None,
    gnn_service: GnnService | None = None,
    risk_service: RiskService | None = None,
    explainability_service: ExplainabilityService | None = None,
    monitoring_service: MonitoringService | None = None,
    records_config: RecordsConfig | None = None,
    raw_record_store: RawRecordStore | None = None,
    observation_writer: ObservationWriter | None = None,
    entity_metric_repository: EntityMetricRepository | None = None,
    metrics_throttle: MetricsRecomputeThrottle | None = None,
    risk_history_writer: RiskHistoryWriter | None = None,
    alert_history_writer: AlertHistoryWriter | None = None,
    consumer_group: str,
    consumer_name: str,
    limit: int = 10,
    block_ms: int | None = None,
    retry_policy: RetryPolicy | None = None,
    health_state: HealthState | None = None,
    workflow_tracker: WorkflowEventTracker | None = None,
    sleep: Callable[[float], "asyncio.Future[None] | object"] = asyncio.sleep,
) -> int:
    """Consume and process available ingestion events with retry/DLQ semantics."""

    policy = retry_policy or RetryPolicy()
    processed = 0
    event_types = [
        "documents.uploaded",
        "documents.parsed",
        "documents.chunked",
        "entities.extracted",
        "entities.validated",
        "graph.updated",
        "embeddings.complete",
        "vectors.indexed",
        "risk.scored",
        "records.ingested",
        "alerts.created",
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

        def _run_handler(captured: EventDelivery = delivery) -> int:
            return handle_event(
                captured,
                ingestion_service,
                document_chunker=document_chunker,
                document_extractor=document_extractor,
                extraction_validator=extraction_validator,
                graph_service=graph_service,
                object_store=object_store,
                event_bus=event_bus,
                embeddings_service=embeddings_service,
                vector_store=vector_store,
                graph_repository=graph_repository,
                gnn_service=gnn_service,
                risk_service=risk_service,
                explainability_service=explainability_service,
                monitoring_service=monitoring_service,
                records_config=records_config,
                raw_record_store=raw_record_store,
                observation_writer=observation_writer,
                entity_metric_repository=entity_metric_repository,
                metrics_throttle=metrics_throttle,
                risk_history_writer=risk_history_writer,
                alert_history_writer=alert_history_writer,
                workflow_tracker=workflow_tracker,
            )

        def _record_failure(
            error: BaseException,
            captured: EventDelivery = delivery,
        ) -> None:
            if workflow_tracker is not None:
                workflow_tracker.fail_event(captured.event, error)

        processed += await run_handler_with_retry(
            _run_handler,
            event=delivery.event,
            event_bus=event_bus,
            retry_policy=policy,
            sleep=sleep,
            on_failure=_record_failure,
        )
        ackable.append(delivery)
        if health_state is not None:
            health_state.mark_event_processed()
    if ackable:
        event_bus.ack(ackable)
    return processed


# ---------------------------------------------------------------------------
# Worker lifecycle (E4-S06, E4-S07)
# ---------------------------------------------------------------------------


def install_signal_handlers(
    loop: asyncio.AbstractEventLoop,
    shutdown_event: asyncio.Event,
) -> None:
    """Register SIGTERM/SIGINT handlers that flip the shutdown event."""

    def _trigger_shutdown() -> None:
        if not shutdown_event.is_set():
            logger.info(SHUTDOWN_LOG_REQUESTED)
            shutdown_event.set()

    def _signal_callback(_sig: int, _frame: object | None) -> None:  # pragma: no cover - Windows
        _trigger_shutdown()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _trigger_shutdown)
        except NotImplementedError:  # pragma: no cover - Windows
            signal.signal(sig, _signal_callback)


async def start_health_server_safely(
    state: HealthState,
) -> asyncio.AbstractServer | None:
    """Start the health server while keeping the worker alive on failure."""

    try:
        return await start_health_server(state)
    except OSError as exc:
        logger.warning("Health server failed to start: %s", exc)
        return None


async def run_worker(
    *,
    retry_policy: RetryPolicy | None = None,
    health_settings: HealthSettings | None = None,
) -> None:
    """Main worker loop — wires adapters and processes events with retry/DLQ."""

    setup_tracing()
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    logger.info("Worker starting — REDIS_URL=%s", redis_url)
    deps = build_worker_dependencies()

    policy = retry_policy or RetryPolicy()
    settings = health_settings or HealthSettings()
    health_state = HealthState(settings=settings)

    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()
    install_signal_handlers(loop, shutdown_event)

    health_server = await start_health_server_safely(health_state)

    try:
        while not shutdown_event.is_set():
            processed = await drain_ingestion_events(
                deps.event_bus,
                deps.ingestion_service,
                deps.document_chunker,
                deps.document_extractor,
                deps.extraction_validator,
                deps.graph_service,
                deps.object_store,
                embeddings_service=deps.embeddings_service,
                vector_store=deps.vector_store,
                graph_repository=_resolve_graph_repository(deps.graph_service),
                gnn_service=deps.gnn_service,
                risk_service=deps.risk_service,
                explainability_service=deps.explainability_service,
                monitoring_service=deps.monitoring_service,
                records_config=deps.records_config,
                raw_record_store=deps.raw_record_store,
                observation_writer=deps.observation_writer,
                entity_metric_repository=deps.entity_metric_repository,
                metrics_throttle=deps.metrics_throttle,
                risk_history_writer=deps.risk_history_writer,
                alert_history_writer=deps.alert_history_writer,
                consumer_group=deps.event_settings.consumer_group,
                consumer_name=deps.event_settings.consumer_name(),
                limit=deps.event_settings.batch_size,
                block_ms=deps.event_settings.block_ms,
                retry_policy=policy,
                health_state=health_state,
                workflow_tracker=deps.workflow_tracker,
            )
            if processed:
                logger.info("Processed %s ingestion document(s)", processed)
                await asyncio.sleep(0)
            elif deps.event_settings.backend == "redis":
                await asyncio.sleep(0.05)
            else:
                await asyncio.sleep(1)
                logger.debug("Worker heartbeat")
    except asyncio.CancelledError:
        logger.info("Worker shutting down")
    finally:
        if health_server is not None:
            health_server.close()
            with contextlib.suppress(Exception):
                await health_server.wait_closed()
        logger.info(SHUTDOWN_LOG_DONE)


def _resolve_graph_repository(graph_service: GraphService) -> GraphRepository:
    """Return the underlying graph repository used by the graph service."""

    repository = getattr(graph_service, "_repository", None)
    if not isinstance(repository, GraphRepository):  # pragma: no cover - defensive
        raise TypeError("GraphService is missing a GraphRepository instance.")
    return repository


def main() -> None:
    """Entry point for `python -m agent.coordinator`."""
    logger.info("chiliAI pipeline worker starting")
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Worker interrupted — exiting")
        sys.exit(0)


# Re-export ``datetime`` for tests that monkeypatch via this module.
__datetime__ = datetime
__timezone__ = timezone

if __name__ == "__main__":
    main()
