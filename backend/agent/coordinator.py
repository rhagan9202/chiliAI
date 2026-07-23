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
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from datetime import datetime, timezone
from typing import cast

from pydantic import ValidationError

from agent.adapters.protocols import WorkflowRunStoreProtocol
from agent.adapters.runtime import create_workflow_run_store_from_env
from agent.embeddings_graph_bridge import GnnGraphEmbeddingProvider
from agent.exceptions import ConfigurationError
from agent.health import HealthState, start_health_server
from agent.models import HealthSettings, RetryPolicy
from agent.policy import (
    StagePolicy,
    StagePolicyRegistry,
    load_stage_policy_registry_from_env,
)
from agent.status_projection import project_document_status
from agent.workflow_tracking import WorkflowEventTracker
from config.loader import load_active_config
from config.schema import (
    AnalyticsConfig,
    DatabaseConfig,
    DomainConfig,
    EmbeddingsConfig,
    EventBusConfig,
    GnnConfig,
    GraphDbConfig,
    LlmConfig,
    ObjectStoreConfig,
    PeerStatsConfig,
    PolicyRulePack,
    RecordFeedConfig,
    RecordsConfig,
    TimeseriesAnalyticsConfig,
    VectorStoreConfig,
)
from database.protocols import ConnectionProvider
from database.runtime import create_connection_provider
from analytics.explainability.adapters.deterministic import (
    DeterministicNarrativeGenerator,
)
from analytics.explainability.adapters.evidence_object_store import (
    ObjectStoreEvidencePackRepository,
)
from analytics.explainability.adapters.in_memory import (
    InMemoryExplainabilityContextSource,
)
from analytics.explainability.adapters.llm_narrative import LlmNarrativeGenerator
from analytics.explainability.adapters.protocols import (
    ExplainabilityContextSourceProtocol,
)
from analytics.explainability.adapters.shap_attribution import (
    NoopFeatureAttributor,
    ShapRiskAttributor,
)
from analytics.explainability.exceptions import ExplainabilityError
from graph.exceptions import (
    BatchUpsertError,
    GraphError,
    GraphIntegrityError,
    GraphVersionConflictError,
)
from analytics.explainability.models import (
    ExplanationContext,
    ExplanationItem,
    ExplanationSubgraph,
)
from analytics.explainability.protocols import (
    FeatureAttributorProtocol,
    NarrativeGeneratorProtocol,
)
from analytics.explainability.repository import EvidencePackRepository
from analytics.explainability.service import (
    ExplainabilityService,
    create_explainability_service,
)
from analytics.gnn.adapters.cluster_store import ObjectStoreClusterSummaryStore
from analytics.gnn.adapters.graph_repository_source import GraphRepositorySnapshotSource
from analytics.gnn.adapters.protocols import (
    ClusterSummaryStoreProtocol,
    GraphSnapshotSourceProtocol,
)
from analytics.gnn.exceptions import (
    GnnDisabledError,
    GnnError,
    GnnInsufficientGraphError,
    GnnSnapshotUnavailableError,
)
from analytics.gnn.models import ClusterSummary
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
from analytics.peerstats.adapters.in_memory import (
    InMemoryDerivedRiskSignalWriter,
    InMemoryRecordColumnSource,
)
from analytics.peerstats.adapters.postgres import (
    PostgresDerivedRiskSignalWriter,
    PostgresRecordColumnSource,
)
from analytics.peerstats.adapters.protocols import (
    DerivedRiskSignalWriterProtocol,
    RecordColumnSourceProtocol,
)
from analytics.peerstats.aggregation import z_to_signal
from analytics.peerstats.models import DerivedRiskSignal
from analytics.peerstats.service import PeerStatsService, create_peerstats_service
from analytics.peerstats.service_models import PeerStatsComputeRequest
from analytics.risk.adapters.in_memory import InMemoryRiskHistoryWriter, InMemoryRiskSignalSource
from analytics.risk.adapters.postgres import PostgresRiskHistoryStore, PostgresRiskSignalSource
from analytics.risk.adapters.protocols import RiskHistoryWriter, RiskSignalSourceProtocol
from analytics.risk.exceptions import (
    RiskConfigurationError,
    RiskError,
    RiskInsufficientSignalsError,
)
from analytics.risk.models import RiskAssessmentRecord, RiskFactor
from analytics.risk.service import RiskService, create_risk_service
from analytics.risk.service_models import (
    RiskAssessmentRequest,
    RiskAssessmentResponse,
)
from analytics.timeseries.adapters.in_memory import (
    InMemoryTimeSeriesHistorySource,
    InMemoryTimeseriesAnomalyStore,
)
from analytics.timeseries.adapters.postgres import PostgresTimeseriesAnomalyStore
from analytics.timeseries.adapters.protocols import TimeseriesAnomalyStoreProtocol
from analytics.timeseries.adapters.record_aggregates import load_entity_series_map
from analytics.timeseries.exceptions import (
    TimeseriesConfigurationError,
    TimeseriesInsufficientHistoryError,
)
from analytics.timeseries.models import TimeseriesAnomalyRecord
from analytics.timeseries.service import create_timeseries_service
from analytics.timeseries.service_models import TimeseriesAnalysisRequest
from embeddings.adapters.cache_in_memory import (
    create_embedding_cache,
    embedding_cache_namespace,
)
from embeddings.adapters.in_memory import InMemoryEmbedder
from embeddings.adapters.protocols import EmbedderProtocol, EmbeddingCacheProtocol
from embeddings.models import EmbeddingMetadata, EmbeddingResult, EmbeddingVector
from embeddings.protocols import EmbeddingsServiceProtocol
from embeddings.service import create_embeddings_service
from embeddings.service_models import EmbedRequest, EmbedSubmission
from events.adapters.dlq_in_memory import InMemoryDlqRecordStore
from events.adapters.dlq_postgres import PostgresDlqRecordStore
from events.codec import encode_event
from events.dlq_models import DlqRecord
from events.protocols import DlqErrorInfo, DlqRecordStore, EventBus, EventDelivery
from events.runtime import EventBusSettings, create_event_bus, load_event_bus_settings
from events.types import (
    AlertCreatedReference,
    AlertsCreatedEvent,
    AnalysisFailedEvent,
    AnyEvent,
    ChunkedDocumentReference,
    ConfigUpdatedEvent,
    DocumentFailureReference,
    DocumentsChunkedEvent,
    DocumentsExtractionWarningEvent,
    DocumentsFailedEvent,
    DocumentsParsedEvent,
    DocumentsUploadedEvent,
    EmbeddingsCompleteDocumentReference,
    EmbeddingsCompleteEvent,
    EntitiesExtractedEvent,
    EntitiesValidatedEvent,
    ExtractedDocumentReference,
    ExtractionWarningReference,
    GraphUpdatedEvent,
    KnowledgeBaseDeletedEvent,
    KnowledgeBaseReadyEvent,
    KnowledgeBaseReadyReference,
    RecordsIngestedEvent,
    RiskScoredEvent,
    ValidatedDocumentReference,
    VectorIndexedReference,
    VectorsIndexedDocumentReference,
    VectorsIndexedEvent,
)
from knowledgebases import (
    InMemoryKnowledgeBaseRepository,
    KnowledgeBaseRepository,
    ObjectStoreKnowledgeBaseRepository,
)
from knowledgebases.cleanup import (
    KbDeletionStores,
    TimeseriesAnomalyPurger,
    kb_deletion_steps,
)
from cases.adapters.in_memory import InMemoryCaseRepository
from cases.adapters.postgres import PostgresCaseRepository
from conversations.adapters.in_memory import InMemoryConversationRepository
from conversations.adapters.postgres import PostgresConversationRepository
from vectorstore.service import create_vector_service
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.adapters.protocols import GraphRepository
from graph.auth import resolve_graph_auth
from graph.models import GraphUpsertResult
from graph.protocols import GraphServiceProtocol
from graph.service import GraphService, create_graph_service
from graph.service_models import GraphBuildTask
from ingestion.adapters.in_memory import InMemorySourceDocumentStatusStore
from ingestion.adapters.postgres import PostgresSourceDocumentStatusStore
from ingestion.adapters.protocols import SourceDocumentStatusStore
from ingestion.chunker import ChunkingResult, DocumentChunker, create_document_chunker
from ingestion.extractor import create_document_extractor
from ingestion.protocols import DocumentExtractorProtocol
from ingestion.models import ExtractionResult, ParsedDocument, ValidationReport
from ingestion.orchestrators.parser import DocumentParsingOrchestrator
from ingestion.parsers.registry import create_default_registry
from ingestion.parsers.remote import HttpxRemoteDocumentFetcher
from ingestion.recovery import ObjectStoreIngestionRecoveryStore
from ingestion.service import IngestionService
from ingestion.validator import ExtractionResultValidator, create_extraction_validator
from llm.adapters.protocols import LlmClientProtocol
from llm.factory import create_llm_client as _create_llm_client
from llm.service import create_llm_service
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
from monitoring.models import AlertHistoryRecord, MonitoringBatch
from monitoring.service import MonitoringService, create_monitoring_service
from monitoring.service_models import MonitoringEvaluationRequest
from monitoring.metrics import observe_pipeline_stage
from records.adapters.in_memory import InMemoryRawRecordStore
from records.adapters.postgres import PostgresRawRecordStore
from records.adapters.protocols import RawRecordStore
from scorecards.adapters.in_memory import InMemoryScorecardRunRepository
from scorecards.adapters.postgres import PostgresScorecardRunRepository
from scorecards.adapters.protocols import ScorecardRunRepository
from records.exceptions import RecordFeedNotFoundError
from records.mappers.feed_mapper import map_batch, map_observations
from policy.adapters.in_memory import InMemoryPolicyItemRepository
from policy.adapters.postgres import PostgresPolicyItemRepository
from policy.adapters.protocols import PolicyItemRepository
from policy.evaluation import PolicyEvalState, evaluate
from policy.service import PolicyService, create_policy_service
from shared.logging import bind_correlation_id, configure_logging, get_logger
from shared.metrics import (
    ingestion_documents_empty_extraction_total,
    ingestion_documents_failed_total,
    log_stage,
)
from shared.provenance import (
    SOURCE_DOCUMENT_ID_KEY,
    SOURCE_ID_KEY,
    SOURCE_KIND_DOCUMENT,
    SOURCE_KIND_KEY,
    SOURCE_KIND_RECORD,
)
from shared.tracing import setup_tracing, start_pipeline_span
from shared.types import Alert, Entity
from shared.utils import generate_id
from storage.adapters.in_memory import InMemoryObjectStore
from storage.protocols import ObjectStore
from vectorstore.adapters.in_memory import InMemoryVectorStore
from vectorstore.adapters.protocols import VectorStoreProtocol
from vectorstore.models import VectorRecord

__all__ = [
    "CONFIG_UPDATED_EVENT_TYPE",
    "WORKER_EVENT_TYPES",
    "ConfigReloadState",
    "WorkerDependencies",
    "apply_pending_config_updates",
    "assess_entities",
    "build_alert_history_writer",
    "build_connection_provider",
    "build_dlq_record_store",
    "build_document_status_store",
    "build_embedder",
    "build_embedding_cache",
    "build_entity_metric_repository",
    "build_explainability_context_source",
    "build_explanation_context",
    "build_feature_attributor",
    "build_graph_repository",
    "build_graph_snapshot_source",
    "build_llm_client",
    "build_monitoring_observation_source",
    "build_narrative_generator",
    "build_object_store",
    "build_observation_writer",
    "build_peerstats_service",
    "build_policy_item_repository",
    "build_policy_service",
    "build_raw_record_store",
    "build_risk_history_writer",
    "build_risk_signal_source",
    "build_scorecard_run_repository",
    "build_timeseries_anomaly_store",
    "build_vector_store",
    "build_worker_dependencies",
    "drain_ingestion_events",
    "handle_alerts_created_for_graph",
    "handle_documents_chunked",
    "handle_documents_parsed",
    "handle_embeddings_complete",
    "handle_entities_extracted",
    "handle_entities_validated",
    "handle_event",
    "handle_graph_updated",
    "handle_graph_updated_for_analytics",
    "handle_knowledge_base_deleted",
    "handle_records_ingested",
    "handle_risk_scored",
    "handle_risk_scored_for_graph",
    "handle_vectors_indexed",
    "main",
    "run_handler_with_retry",
    "run_peerstats_stage",
    "run_timeseries_stage",
    "run_worker",
]

configure_logging()
logger = get_logger("chili.worker")

# Depth of the explanatory subgraph extracted around an alert's seed entity
# when building an evidence pack (BL-005). Bounded per sprint risk R-03.
_EVIDENCE_SUBGRAPH_DEPTH = 2

SHUTDOWN_LOG_REQUESTED = "Shutdown requested, finishing current event..."
SHUTDOWN_LOG_DONE = "Worker stopped gracefully."
DEFAULT_WORKFLOW_STALE_MAX_AGE_SECONDS = 24 * 60 * 60
DEFAULT_WORKFLOW_RECONCILE_INTERVAL_SECONDS = 60
# Backoff after a drain iteration raises (e.g. transient Redis outage) so the
# worker neither dies nor hot-loops while the dependency recovers.
DRAIN_ERROR_BACKOFF_SECONDS = 1.0
WORKER_EVENT_TYPES: tuple[str, ...] = (
    "documents.uploaded",
    "documents.parsed",
    "documents.failed",
    "documents.extraction_warning",
    "documents.chunked",
    "entities.extracted",
    "entities.validated",
    "graph.updated",
    "embeddings.complete",
    "vectors.indexed",
    "kb.ready",
    "risk.scored",
    "records.ingested",
    "alerts.created",
    "kb.delete",
)
# Domain hot-swap (E6): the worker consumes `config.updated` on its own
# non-blocking poll — never through the pipeline drain — so a dependency
# rebuild can only happen *between* drain iterations. An in-flight event
# always completes with the dependencies it started with.
CONFIG_UPDATED_EVENT_TYPE = "config.updated"


@dataclass(slots=True)
class WorkerDependencies:
    """Container for the assembled worker subsystem dependencies."""

    event_bus: EventBus
    ingestion_service: IngestionService
    document_chunker: DocumentChunker
    document_extractor: DocumentExtractorProtocol
    extraction_validator: ExtractionResultValidator
    graph_service: GraphService
    graph_repository: GraphRepository
    embeddings_service: EmbeddingsServiceProtocol
    object_store: ObjectStore
    vector_store: VectorStoreProtocol
    llm_client: LlmClientProtocol
    gnn_service: GnnService
    gnn_cluster_store: ClusterSummaryStoreProtocol
    risk_service: RiskService
    peerstats_service: PeerStatsService
    peer_stats_config: PeerStatsConfig
    peer_stats_enabled: bool
    record_column_source: RecordColumnSourceProtocol
    timeseries_anomaly_store: TimeseriesAnomalyStoreProtocol
    timeseries_config: TimeseriesAnalyticsConfig
    timeseries_enabled: bool
    kb_deletion_stores: KbDeletionStores
    kb_repository: KnowledgeBaseRepository
    explainability_service: ExplainabilityService
    monitoring_service: MonitoringService
    records_config: RecordsConfig
    raw_record_store: RawRecordStore
    derived_signal_store: DerivedRiskSignalWriterProtocol
    observation_writer: ObservationWriter
    policy_service: PolicyService
    policy_rules: list[PolicyRulePack]
    entity_metric_repository: EntityMetricRepository
    metrics_throttle: MetricsRecomputeThrottle
    policy_metrics_throttle: MetricsRecomputeThrottle
    risk_history_writer: RiskHistoryWriter
    alert_history_writer: AlertHistoryWriter
    event_settings: EventBusSettings
    workflow_run_store: WorkflowRunStoreProtocol
    workflow_tracker: WorkflowEventTracker
    document_status_store: SourceDocumentStatusStore
    dlq_record_store: DlqRecordStore
    graph_embeddings_enabled: bool = False


# ---------------------------------------------------------------------------
# Adapter registries (E4-S08)
# ---------------------------------------------------------------------------


_ObjectStoreFactory = Callable[[ObjectStoreConfig], ObjectStore]
_GraphRepositoryFactory = Callable[[GraphDbConfig], GraphRepository]
_VectorStoreFactory = Callable[[VectorStoreConfig], VectorStoreProtocol]
_EmbedderFactory = Callable[[EmbeddingsConfig], EmbedderProtocol]


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




def build_graph_snapshot_source(
    config: DomainConfig,
    *,
    repository: GraphRepository,
    cluster_store: ClusterSummaryStoreProtocol,
) -> GraphSnapshotSourceProtocol:
    """Return the graph-repository-backed GNN snapshot source (B1).

    Bounded by ``config.gnn.snapshot_max_nodes``. ``cluster_store`` is built
    once by the caller (from the worker's shared object store) and passed in
    rather than constructed here, so the persistence step that writes cluster
    summaries and the snapshot source that reads them share one instance.
    """

    gnn_config = config.gnn or GnnConfig()
    return GraphRepositorySnapshotSource(
        repository, cluster_store, max_nodes=gnn_config.snapshot_max_nodes
    )


def build_risk_signal_source(
    provider: ConnectionProvider | None,
) -> RiskSignalSourceProtocol:
    """Return the risk signal source: Postgres-derived when a provider exists."""

    if provider is None:
        return InMemoryRiskSignalSource()
    return PostgresRiskSignalSource(provider)


def build_record_column_source(
    provider: ConnectionProvider | None,
) -> RecordColumnSourceProtocol:
    """Return the peerstats record column source."""

    if provider is None:
        return InMemoryRecordColumnSource()
    return PostgresRecordColumnSource(provider)


def build_derived_signal_writer(
    provider: ConnectionProvider | None,
) -> DerivedRiskSignalWriterProtocol:
    """Return the peerstats derived-signal writer."""

    if provider is None:
        return InMemoryDerivedRiskSignalWriter()
    return PostgresDerivedRiskSignalWriter(provider)


def build_peerstats_service(
    provider: ConnectionProvider | None,
) -> PeerStatsService:
    """Assemble the peerstats service from the configured database backend."""

    return create_peerstats_service(
        build_record_column_source(provider),
        writer=build_derived_signal_writer(provider),
    )


def build_explainability_context_source(
    _config: DomainConfig,
) -> ExplainabilityContextSourceProtocol:
    """Return the configured explainability context source adapter."""

    return InMemoryExplainabilityContextSource()


def build_narrative_generator(
    config: DomainConfig, llm_client: LlmClientProtocol, *, event_bus: EventBus
) -> NarrativeGeneratorProtocol:
    """Select the narrative generator adapter from ``AnalyticsConfig.narrative_backend``.

    ``"llm"`` wraps the already-constructed worker ``llm_client`` in an
    ``LlmService`` (the same composition used for RAG) and degrades to
    ``DeterministicNarrativeGenerator`` per ``LlmNarrativeGenerator``'s own
    never-raise contract; any other value (including the default) uses the
    deterministic generator directly.
    """

    analytics_config = config.analytics or AnalyticsConfig()
    if analytics_config.narrative_backend == "llm":
        llm_config = config.llm or LlmConfig()
        return LlmNarrativeGenerator(
            create_llm_service(llm_client, event_bus=event_bus),
            fallback=DeterministicNarrativeGenerator(),
            model_name=llm_config.model,
            temperature=llm_config.temperature,
            max_tokens=llm_config.max_tokens,
        )
    return DeterministicNarrativeGenerator()


def build_feature_attributor(config: DomainConfig) -> FeatureAttributorProtocol:
    """Select the feature attributor adapter from ``AnalyticsConfig.attribution_backend``."""

    analytics_config = config.analytics or AnalyticsConfig()
    if analytics_config.attribution_backend == "shap":
        return ShapRiskAttributor()
    return NoopFeatureAttributor()


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


def build_document_status_store(
    provider: ConnectionProvider | None,
) -> SourceDocumentStatusStore:
    """Select a document status store: Postgres when a provider exists."""

    if provider is None:
        return InMemorySourceDocumentStatusStore()
    return PostgresSourceDocumentStatusStore(provider)


def build_dlq_record_store(
    provider: ConnectionProvider | None,
) -> DlqRecordStore:
    """Select a durable DLQ record store: Postgres when a provider exists (BL-023)."""

    if provider is None:
        return InMemoryDlqRecordStore()
    return PostgresDlqRecordStore(provider)


def build_observation_writer(
    provider: ConnectionProvider | None,
) -> ObservationWriter:
    """Select an observation writer: Postgres when a provider exists, else in-memory."""

    if provider is None:
        return InMemoryObservationWriter()
    return PostgresObservationStore(provider)


def build_timeseries_anomaly_store(
    provider: ConnectionProvider | None,
) -> TimeseriesAnomalyStoreProtocol:
    """Select the timeseries anomaly store: Postgres when a provider exists."""

    if provider is None:
        return InMemoryTimeseriesAnomalyStore()
    return PostgresTimeseriesAnomalyStore(provider)


def build_policy_item_repository(
    provider: ConnectionProvider | None,
) -> PolicyItemRepository:
    """Select a policy item repository: Postgres when a provider exists, else in-memory."""

    if provider is None:
        return InMemoryPolicyItemRepository()
    return PostgresPolicyItemRepository(provider)


def build_policy_service(provider: ConnectionProvider | None) -> PolicyService:
    """Create the policy service over the selected repository backend."""

    return create_policy_service(build_policy_item_repository(provider))


def build_entity_metric_repository(
    provider: ConnectionProvider | None,
) -> EntityMetricRepository:
    """Select an entity-metric repository: Postgres when a provider exists."""

    if provider is None:
        return InMemoryEntityMetricRepository()
    return PostgresEntityMetricRepository(provider)


def build_scorecard_run_repository(
    provider: ConnectionProvider | None,
) -> ScorecardRunRepository:
    """Select a scorecard-run repository: Postgres when a provider exists."""

    if provider is None:
        return InMemoryScorecardRunRepository()
    return PostgresScorecardRunRepository(provider)


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


def build_kb_repository(object_store: ObjectStore) -> KnowledgeBaseRepository:
    """Select the KB metadata repository, mirroring the API DI selection."""

    backend = os.environ.get("CHILI_KB_REPOSITORY_BACKEND", "in_memory").strip().lower()
    if backend in {"object_store", "object-store", "objectstore"}:
        return ObjectStoreKnowledgeBaseRepository(object_store)
    return InMemoryKnowledgeBaseRepository()


def build_kb_deletion_stores(
    provider: ConnectionProvider | None,
    *,
    graph_service: GraphServiceProtocol,
    vector_store: VectorStoreProtocol,
    object_store: ObjectStore,
    event_bus: EventBus,
    raw_record_store: RawRecordStore,
    derived_signal_store: DerivedRiskSignalWriterProtocol,
    observation_writer: ObservationWriter,
    risk_history_writer: RiskHistoryWriter,
    alert_history_writer: AlertHistoryWriter,
    entity_metric_repository: EntityMetricRepository,
    timeseries_anomaly_store: TimeseriesAnomalyPurger,
) -> KbDeletionStores:
    """Assemble the shared KB-delete cascade bundle for the worker.

    Reuses the already-built worker stores and constructs the few extra stores
    (vector service, conversation/case/policy/evidence repositories, cluster
    summary store) that the worker otherwise needs only for KB-delete retries.
    ``gnn_cluster_store`` is built fresh from ``object_store`` here (it does
    not need to be the same instance as ``WorkerDependencies.gnn_cluster_store``
    — object-store-backed state is shared by construction).

    ``alert_projection_store`` is deliberately left ``None``: the alert read
    projection is API-owned (``api._alert_store``) and this module must not
    import from ``api``. The cascade skips that step here; the API's DELETE
    route always runs it. ``gnn_cluster_store`` is analytics-owned (not
    API-owned), so unlike the alert projection it is always required.
    """

    return KbDeletionStores(
        graph_service=graph_service,
        vector_service=create_vector_service(
            vector_store, event_bus=event_bus, object_store=object_store
        ),
        raw_record_store=raw_record_store,
        derived_signal_store=derived_signal_store,
        risk_history_writer=risk_history_writer,
        observation_writer=observation_writer,
        alert_history_writer=alert_history_writer,
        entity_metric_repository=entity_metric_repository,
        conversation_repository=(
            InMemoryConversationRepository()
            if provider is None
            else PostgresConversationRepository(provider)
        ),
        case_repository=(
            InMemoryCaseRepository()
            if provider is None
            else PostgresCaseRepository(provider)
        ),
        policy_item_repository=build_policy_item_repository(provider),
        evidence_pack_repository=ObjectStoreEvidencePackRepository(object_store),
        scorecard_run_repository=build_scorecard_run_repository(provider),
        document_status_store=build_document_status_store(provider),
        object_store=object_store,
        gnn_cluster_store=ObjectStoreClusterSummaryStore(object_store),
        timeseries_anomaly_store=timeseries_anomaly_store,
    )


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


def build_embedding_cache(
    config: DomainConfig,
) -> tuple[EmbeddingCacheProtocol | None, str]:
    """Build the config-driven embedding cache and its key namespace."""

    embeddings_config = config.embeddings or EmbeddingsConfig()
    return (
        create_embedding_cache(embeddings_config),
        embedding_cache_namespace(embeddings_config),
    )


def build_llm_client(config: DomainConfig) -> LlmClientProtocol:
    """Select an LLM client adapter from the configured provider."""
    from llm.exceptions import LlmConfigurationError

    llm_config = config.llm or LlmConfig()
    try:
        return _create_llm_client(llm_config)
    except LlmConfigurationError as exc:
        raise ConfigurationError(
            subsystem="llm",
            backend=llm_config.provider,
            message=str(exc),
        ) from exc


def build_document_extractor(
    config: DomainConfig,
    llm_client: LlmClientProtocol,
) -> DocumentExtractorProtocol:
    """Select the document extractor for the configured LLM provider.

    The ``local`` provider is the deterministic echo stub
    (llm/adapters/in_memory.py) and cannot produce extraction JSON, so it
    keeps the config-driven ``PatternDocumentExtractor`` baseline. Real
    providers route document extraction through ``LlmDocumentExtractor``.
    """
    provider = (config.llm or LlmConfig()).provider
    if provider == "local":
        return create_document_extractor(config.entities, config.relationships)
    return create_document_extractor(
        config.entities,
        config.relationships,
        llm_client=llm_client,
    )


def _resolve_worker_event_bus_settings(config: DomainConfig) -> EventBusSettings:
    env_settings = load_event_bus_settings()
    if "events" not in config.model_fields_set:
        return env_settings

    event_config = config.events
    if event_config is None or event_config == EventBusConfig():
        return env_settings

    return EventBusSettings(
        backend="redis" if event_config.backend == "redis" else "in-memory",
        redis_url=event_config.uri or env_settings.redis_url,
        stream_prefix=event_config.stream_prefix,
        consumer_group=event_config.consumer_group,
        consumer_name_prefix=env_settings.consumer_name_prefix,
        batch_size=env_settings.batch_size,
        block_ms=env_settings.block_ms,
        stream_maxlen=event_config.stream_maxlen
        if event_config.stream_maxlen is not None
        else env_settings.stream_maxlen,
        reclaim_min_idle_ms=event_config.reclaim_min_idle_ms
        if event_config.reclaim_min_idle_ms is not None
        else env_settings.reclaim_min_idle_ms,
    )


def _load_worker_config() -> DomainConfig:
    """Resolve the active :class:`DomainConfig` for the worker.

    Uses the store-aware ``load_active_config()`` resolver (active-pack
    pointer > ``CHILI_CONFIG_PATH``) so the worker and the API always agree
    on the active domain pack across hot-swaps.
    """

    return load_active_config()


def build_worker_dependencies() -> WorkerDependencies:
    """Assemble the worker's runtime dependencies from configuration.

    Adapter selection is driven by ``DomainConfig`` subsystem sections; absent
    sections silently fall back to the in-memory adapters used by tests.
    """

    config = _load_worker_config()
    event_settings = _resolve_worker_event_bus_settings(config)
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
        recovery_store=ObjectStoreIngestionRecoveryStore(object_store),
    )
    chunker = create_document_chunker(config.ingestion.chunking)
    extractor = build_document_extractor(config, llm_client)
    validator = create_extraction_validator(config.entities, config.relationships)
    graph_service = create_graph_service(
        graph_repository,
        object_store=object_store,
        event_bus=event_bus,
    )
    gnn_cluster_store = ObjectStoreClusterSummaryStore(object_store)
    gnn_service = create_gnn_service(
        build_graph_snapshot_source(
            config, repository=graph_repository, cluster_store=gnn_cluster_store
        ),
        event_bus=event_bus,
        gnn_enabled=lambda: config.capabilities.gnn,
    )
    embedding_cache, embedding_cache_ns = build_embedding_cache(config)
    embeddings_service = create_embeddings_service(
        embedder,
        event_bus=event_bus,
        graph_embedding_provider=(
            GnnGraphEmbeddingProvider(gnn_service)
            if config.capabilities.gnn
            else None
        ),
        cache=embedding_cache,
        cache_namespace=embedding_cache_ns,
    )
    connection_provider = build_connection_provider(config)
    risk_service = create_risk_service(
        build_risk_signal_source(connection_provider),
        event_bus=event_bus,
    )
    explainability_service = create_explainability_service(
        build_explainability_context_source(config),
        event_bus=event_bus,
        narrative_generator=build_narrative_generator(
            config, llm_client, event_bus=event_bus
        ),
        feature_attributor=build_feature_attributor(config),
    )
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
    document_status_store = build_document_status_store(connection_provider)
    dlq_record_store = build_dlq_record_store(connection_provider)
    derived_signal_store = build_derived_signal_writer(connection_provider)
    observation_writer = build_observation_writer(connection_provider)
    policy_service = build_policy_service(connection_provider)
    policy_rules = list(config.policy_rules)
    entity_metric_repository = build_entity_metric_repository(connection_provider)
    risk_history_writer = build_risk_history_writer(connection_provider)
    alert_history_writer = build_alert_history_writer(connection_provider)
    analytics_config = config.analytics or AnalyticsConfig()
    metrics_throttle = MetricsRecomputeThrottle(
        min_interval_seconds=analytics_config.metrics_recompute_min_interval_seconds
    )
    policy_metrics_throttle = MetricsRecomputeThrottle(
        min_interval_seconds=analytics_config.metrics_recompute_min_interval_seconds
    )
    records_config = config.records or RecordsConfig()
    peer_stats_config = config.peer_stats or PeerStatsConfig()
    peerstats_service = build_peerstats_service(connection_provider)
    timeseries_config = config.timeseries or TimeseriesAnalyticsConfig()
    record_column_source = build_record_column_source(connection_provider)
    timeseries_anomaly_store = build_timeseries_anomaly_store(connection_provider)
    kb_repository = build_kb_repository(object_store)
    kb_deletion_stores = build_kb_deletion_stores(
        connection_provider,
        graph_service=graph_service,
        vector_store=vector_store,
        object_store=object_store,
        event_bus=event_bus,
        raw_record_store=raw_record_store,
        derived_signal_store=derived_signal_store,
        observation_writer=observation_writer,
        risk_history_writer=risk_history_writer,
        alert_history_writer=alert_history_writer,
        entity_metric_repository=entity_metric_repository,
        timeseries_anomaly_store=timeseries_anomaly_store,
    )

    return WorkerDependencies(
        event_bus=event_bus,
        ingestion_service=ingestion_service,
        document_chunker=chunker,
        document_extractor=extractor,
        extraction_validator=validator,
        graph_service=graph_service,
        graph_repository=graph_repository,
        embeddings_service=embeddings_service,
        object_store=object_store,
        vector_store=vector_store,
        llm_client=llm_client,
        gnn_service=gnn_service,
        gnn_cluster_store=gnn_cluster_store,
        risk_service=risk_service,
        peerstats_service=peerstats_service,
        peer_stats_config=peer_stats_config,
        peer_stats_enabled=config.capabilities.peer_stats,
        record_column_source=record_column_source,
        timeseries_anomaly_store=timeseries_anomaly_store,
        timeseries_config=timeseries_config,
        timeseries_enabled=config.capabilities.timeseries,
        kb_deletion_stores=kb_deletion_stores,
        kb_repository=kb_repository,
        explainability_service=explainability_service,
        monitoring_service=monitoring_service,
        records_config=records_config,
        raw_record_store=raw_record_store,
        derived_signal_store=derived_signal_store,
        observation_writer=observation_writer,
        policy_service=policy_service,
        policy_rules=policy_rules,
        entity_metric_repository=entity_metric_repository,
        metrics_throttle=metrics_throttle,
        policy_metrics_throttle=policy_metrics_throttle,
        risk_history_writer=risk_history_writer,
        alert_history_writer=alert_history_writer,
        event_settings=event_settings,
        workflow_run_store=workflow_run_store,
        workflow_tracker=workflow_tracker,
        document_status_store=document_status_store,
        dlq_record_store=dlq_record_store,
        graph_embeddings_enabled=config.capabilities.gnn,
    )


# ---------------------------------------------------------------------------
# Domain hot-swap (E6) — config.updated consumption
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ConfigReloadState:
    """Tracks the last applied ``config.updated`` delivery.

    Used to make event redelivery idempotent: rebuilding twice for the same
    delivery would be harmless (the factory re-reads the active config) but
    wasteful, so redeliveries of an already-applied ``correlation_id`` skip
    the rebuild.
    """

    last_applied_correlation_id: str | None = None


def apply_pending_config_updates(
    deps: WorkerDependencies,
    *,
    state: ConfigReloadState,
    deps_factory: Callable[[], WorkerDependencies] | None = None,
) -> WorkerDependencies:
    """Consume pending ``config.updated`` events and rebuild worker deps.

    Atomicity contract: ``run_worker`` calls this strictly *between* drain
    iterations, so a rebuild never interleaves with event handling — the
    in-flight event finished with the old dependencies before this runs, and
    the next dispatch reads the swapped reference.

    Multiple pending updates collapse into a single rebuild: the factory
    re-reads the *active* configuration, so only the newest event matters.
    On reload failure the previous dependencies are kept (the worker is never
    left deps-less) and the deliveries are still acked — the next successful
    config apply/switch publishes a fresh event.
    """

    event_types = [CONFIG_UPDATED_EVENT_TYPE]
    consumer_group = deps.event_settings.consumer_group
    deps.event_bus.ensure_consumer_group(event_types, consumer_group=consumer_group)
    deliveries = deps.event_bus.consume(
        event_types,
        consumer_group=consumer_group,
        consumer_name=deps.event_settings.consumer_name(),
        limit=deps.event_settings.batch_size,
        block_ms=None,
    )
    if not deliveries:
        return deps

    current = deps
    latest = next(
        (
            delivery.event
            for delivery in reversed(deliveries)
            if isinstance(delivery.event, ConfigUpdatedEvent)
        ),
        None,
    )
    if latest is None:
        deps.event_bus.ack(deliveries)
        return current

    if latest.correlation_id == state.last_applied_correlation_id:
        logger.info(
            "config.updated redelivered for pack '%s' (correlation_id=%s); "
            "dependencies already rebuilt — skipping.",
            latest.pack_name,
            latest.correlation_id,
        )
    else:
        factory = deps_factory if deps_factory is not None else build_worker_dependencies
        try:
            rebuilt = factory()
        except Exception:  # noqa: BLE001 - never leave the worker deps-less
            logger.exception(
                "CONFIG RELOAD FAILED for pack '%s' (reason=%s correlation_id=%s); "
                "keeping previous worker dependencies.",
                latest.pack_name,
                latest.reason,
                latest.correlation_id,
            )
        else:
            current = rebuilt
            state.last_applied_correlation_id = latest.correlation_id
            logger.info(
                "Worker dependencies rebuilt for domain pack '%s' "
                "(reason=%s previous_pack=%s correlation_id=%s).",
                latest.pack_name,
                latest.reason,
                latest.previous_pack_name,
                latest.correlation_id,
            )
    # Ack on the bus the deliveries came from (the *old* deps' bus).
    deps.event_bus.ack(deliveries)
    return current


# ---------------------------------------------------------------------------
# Pipeline handlers
# ---------------------------------------------------------------------------


def handle_documents_parsed(
    event: DocumentsParsedEvent,
    *,
    document_chunker: DocumentChunker,
    object_store: ObjectStore,
    event_bus: EventBus,
    kb_repository: KnowledgeBaseRepository | None = None,
) -> int:
    """Chunk parsed documents and publish the next workflow event.

    Per-document isolation (BL-041): a missing ``parsed_document_storage_key``,
    a not-found parsed artifact (``KeyError`` from the object store), or a
    corrupt/invalid parsed artifact (``pydantic.ValidationError``) fails only
    that document (a ``DocumentsFailedEvent`` is published) instead of
    poisoning the batch and burning retries to the DLQ. These are the only
    two permanent failure classes for this read; any other exception (e.g. a
    transient object-store error) propagates to the retry/DLQ wrapper.
    Chunker and object-store *write* errors also still propagate — they may
    be transient.
    """
    references: list[ChunkedDocumentReference] = []
    failures: list[DocumentFailureReference] = []
    for document in event.documents:
        started_at = time.perf_counter()
        if kb_repository is not None and document.warning_count > 0:
            kb_repository.record_document_warnings(
                document.knowledge_base_id,
                document.source_document_id,
                additional_count=document.warning_count,
                reasons=list(document.warning_samples),
            )
        if document.parsed_document_storage_key is None:
            failures.append(
                DocumentFailureReference(
                    knowledge_base_id=document.knowledge_base_id,
                    source_document_id=document.source_document_id,
                    error_message=(
                        "DocumentsParsedEvent reference is missing "
                        "parsed_document_storage_key; cannot chunk."
                    ),
                    storage_key=document.storage_key,
                )
            )
            # BL-043: count adjacent to the (batched) DocumentsFailedEvent
            # publish below, at the point each failure is committed to it.
            ingestion_documents_failed_total.labels(
                stage="chunk", error_class="MissingStorageKey"
            ).inc()
            log_stage(
                stage="chunk",
                kb_id=document.knowledge_base_id,
                source_document_id=document.source_document_id,
                started_at=started_at,
                outcome="failed",
            )
            continue
        try:
            stored = object_store.get_bytes(document.parsed_document_storage_key)
            parsed_document = ParsedDocument.model_validate_json(stored.content)
        except (KeyError, ValidationError) as exc:
            # Per-document isolation (BL-041) covers only the two permanent
            # failure classes here: a missing object-store key (KeyError) and
            # a corrupt/invalid parsed artifact (pydantic.ValidationError).
            # Any other exception (e.g. a transient object-store error) must
            # propagate so run_handler_with_retry's retry/DLQ policy applies.
            logger.error(
                "Failed to load parsed artifact. source_document_id=%s "
                "storage_key=%s error_class=%s: %s",
                document.source_document_id,
                document.parsed_document_storage_key,
                type(exc).__name__,
                exc,
            )
            failures.append(
                DocumentFailureReference(
                    knowledge_base_id=document.knowledge_base_id,
                    source_document_id=document.source_document_id,
                    error_message=(
                        f"Failed to load parsed artifact "
                        f"'{document.parsed_document_storage_key}': {exc}"
                    ),
                    storage_key=document.storage_key,
                )
            )
            ingestion_documents_failed_total.labels(
                stage="chunk", error_class=type(exc).__name__
            ).inc()
            log_stage(
                stage="chunk",
                kb_id=document.knowledge_base_id,
                source_document_id=document.source_document_id,
                started_at=started_at,
                outcome="failed",
            )
            continue
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
                SOURCE_DOCUMENT_ID_KEY: document.source_document_id,
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
        log_stage(
            stage="chunk",
            kb_id=document.knowledge_base_id,
            source_document_id=document.source_document_id,
            started_at=started_at,
            outcome="success" if result.chunks else "empty",
        )
    if failures:
        event_bus.publish(
            DocumentsFailedEvent(
                correlation_id=event.correlation_id,
                documents=failures,
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
    document_extractor: DocumentExtractorProtocol,
    object_store: ObjectStore,
    event_bus: EventBus,
) -> int:
    """Extract entity candidates from persisted chunks and publish the next event.

    Per-document isolation (BL-041): a missing ``chunks_storage_key``, a
    not-found chunks artifact (``KeyError`` from the object store), or a
    corrupt/invalid chunks artifact (``pydantic.ValidationError``) fails only
    that document via a ``DocumentsFailedEvent`` instead of poisoning the
    batch. These are the only two permanent failure classes for this read;
    any other exception (e.g. a transient object-store error) propagates to
    the retry/DLQ wrapper.
    """
    references: list[ExtractedDocumentReference] = []
    failures: list[DocumentFailureReference] = []
    for document in event.documents:
        started_at = time.perf_counter()
        if document.chunks_storage_key is None:
            failures.append(
                DocumentFailureReference(
                    knowledge_base_id=document.knowledge_base_id,
                    source_document_id=document.source_document_id,
                    error_message=(
                        "DocumentsChunkedEvent reference is missing "
                        "chunks_storage_key; cannot extract."
                    ),
                    storage_key=document.storage_key,
                )
            )
            # BL-043: count adjacent to the (batched) DocumentsFailedEvent
            # publish below, at the point each failure is committed to it.
            ingestion_documents_failed_total.labels(
                stage="extract", error_class="MissingStorageKey"
            ).inc()
            log_stage(
                stage="extract",
                kb_id=document.knowledge_base_id,
                source_document_id=document.source_document_id,
                started_at=started_at,
                outcome="failed",
            )
            continue
        try:
            stored = object_store.get_bytes(document.chunks_storage_key)
            chunking_result = ChunkingResult.model_validate_json(stored.content)
        except (KeyError, ValidationError) as exc:
            # Per-document isolation (BL-041) covers only the two permanent
            # failure classes here: a missing object-store key (KeyError) and
            # a corrupt/invalid chunks artifact (pydantic.ValidationError).
            # Any other exception (e.g. a transient object-store error) must
            # propagate so run_handler_with_retry's retry/DLQ policy applies.
            logger.error(
                "Failed to load chunks artifact. source_document_id=%s "
                "storage_key=%s error_class=%s: %s",
                document.source_document_id,
                document.chunks_storage_key,
                type(exc).__name__,
                exc,
            )
            failures.append(
                DocumentFailureReference(
                    knowledge_base_id=document.knowledge_base_id,
                    source_document_id=document.source_document_id,
                    error_message=(
                        f"Failed to load chunks artifact "
                        f"'{document.chunks_storage_key}': {exc}"
                    ),
                    storage_key=document.storage_key,
                )
            )
            ingestion_documents_failed_total.labels(
                stage="extract", error_class=type(exc).__name__
            ).inc()
            log_stage(
                stage="extract",
                kb_id=document.knowledge_base_id,
                source_document_id=document.source_document_id,
                started_at=started_at,
                outcome="failed",
            )
            continue
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
                SOURCE_DOCUMENT_ID_KEY: document.source_document_id,
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
        log_stage(
            stage="extract",
            kb_id=document.knowledge_base_id,
            source_document_id=document.source_document_id,
            started_at=started_at,
            outcome=(
                "success"
                if extraction_result.candidate_entities
                or extraction_result.candidate_relationships
                else "empty"
            ),
        )
    if failures:
        event_bus.publish(
            DocumentsFailedEvent(
                correlation_id=event.correlation_id,
                documents=failures,
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


_MAX_EXTRACTION_WARNING_SAMPLE = 10


def _collect_extraction_warning_reasons(
    report: ValidationReport,
    extraction_warnings: list[str],
) -> list[str]:
    """Flatten extraction-stage warnings, validation drops, and stripped-property notices into a bounded sample."""
    reasons: list[str] = list(extraction_warnings)
    for candidate_id, errors in report.entity_errors.items():
        reasons.extend(f"entity {candidate_id}: {error}" for error in errors)
    for candidate_id, errors in report.relationship_errors.items():
        reasons.extend(f"relationship {candidate_id}: {error}" for error in errors)
    reasons.extend(report.warnings)
    return reasons[:_MAX_EXTRACTION_WARNING_SAMPLE]


def handle_entities_extracted(
    event: EntitiesExtractedEvent,
    *,
    extraction_validator: ExtractionResultValidator,
    object_store: ObjectStore,
    event_bus: EventBus,
    kb_repository: KnowledgeBaseRepository | None = None,
) -> int:
    """Validate extracted candidates and publish runtime-ready results."""
    references: list[ValidatedDocumentReference] = []
    warning_references: list[ExtractionWarningReference] = []
    for document in event.documents:
        started_at = time.perf_counter()
        try:
            if document.extraction_storage_key is None:
                raise ValueError(
                    "EntitiesExtractedEvent requires extraction_storage_key for validation."
                )
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
                    SOURCE_DOCUMENT_ID_KEY: document.source_document_id,
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

            valid_entity_count = len(validation_report.valid_entities)
            dropped_entity_count = len(validation_report.entity_errors)
            dropped_relationship_count = len(validation_report.relationship_errors)
            stripped_property_count = len(validation_report.warnings)
            extraction_stage_warnings = list(extraction_result.warnings)
            empty_extraction = valid_entity_count == 0
            if empty_extraction:
                ingestion_documents_empty_extraction_total.inc()
            if (
                empty_extraction
                or dropped_entity_count
                or dropped_relationship_count
                or stripped_property_count
                or extraction_stage_warnings
            ):
                logger.warning(
                    "ingestion extraction warning stage=validate knowledge_base_id=%s "
                    "source_document_id=%s valid_entities=%d dropped_entities=%d "
                    "dropped_relationships=%d stripped_properties=%d empty=%s",
                    document.knowledge_base_id,
                    document.source_document_id,
                    valid_entity_count,
                    dropped_entity_count,
                    dropped_relationship_count,
                    stripped_property_count,
                    empty_extraction,
                )
                sample_reasons = _collect_extraction_warning_reasons(
                    validation_report, extraction_stage_warnings
                )
                warning_references.append(
                    ExtractionWarningReference(
                        knowledge_base_id=document.knowledge_base_id,
                        source_document_id=document.source_document_id,
                        valid_entity_count=valid_entity_count,
                        valid_relationship_count=len(validation_report.valid_relationships),
                        dropped_entity_count=dropped_entity_count,
                        dropped_relationship_count=dropped_relationship_count,
                        stripped_property_count=stripped_property_count,
                        empty_extraction=empty_extraction,
                        sample_reasons=sample_reasons,
                        validation_storage_key=validation_storage_key,
                    )
                )
                if kb_repository is not None:
                    warning_total = (
                        dropped_entity_count
                        + dropped_relationship_count
                        + stripped_property_count
                        + len(extraction_stage_warnings)
                    ) or 1  # an unexplained empty extraction still counts once
                    kb_repository.record_document_warnings(
                        document.knowledge_base_id,
                        document.source_document_id,
                        additional_count=warning_total,
                        reasons=sample_reasons,
                    )
        except Exception:
            log_stage(
                stage="validate",
                kb_id=document.knowledge_base_id,
                source_document_id=document.source_document_id,
                started_at=started_at,
                outcome="failed",
            )
            raise
        log_stage(
            stage="validate",
            kb_id=document.knowledge_base_id,
            source_document_id=document.source_document_id,
            started_at=started_at,
            outcome="empty" if empty_extraction else "success",
        )
    if references:
        event_bus.publish(
            EntitiesValidatedEvent(
                correlation_id=event.correlation_id,
                documents=references,
            )
        )
    if warning_references:
        event_bus.publish(
            DocumentsExtractionWarningEvent(
                correlation_id=event.correlation_id,
                documents=warning_references,
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
    event_bus: EventBus,
) -> int:
    """Upsert validated runtime objects into the graph and publish graph updates.

    Per-document isolation (BL-017): a ``GraphIntegrityError`` or
    ``GraphVersionConflictError`` chained inside ``BatchUpsertError`` is a
    permanent failure — the document's relationships reference endpoints that
    do not exist in the graph, or its upsert lost an optimistic-concurrency
    race — so it fails only that document via ``DocumentsFailedEvent``. Any
    other upsert failure (e.g. a transient Neo4j error) propagates to the
    retry/DLQ wrapper.
    """
    processed = 0
    failures: list[DocumentFailureReference] = []
    for document in event.documents:
        started_at = time.perf_counter()
        if document.validation_storage_key is None:
            raise ValueError("EntitiesValidatedEvent requires validation_storage_key for graph updates.")
        stored = object_store.get_bytes(document.validation_storage_key)
        validation_report = ValidationReport.model_validate_json(stored.content)
        try:
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
        except BatchUpsertError as exc:
            cause = exc.__cause__
            if not isinstance(cause, (GraphIntegrityError, GraphVersionConflictError)):
                raise
            if isinstance(cause, GraphIntegrityError):
                error_message = (
                    "Graph integrity violation: relationships reference "
                    f"missing entities {cause.missing_entity_ids} "
                    f"(relationships: {cause.relationship_ids})."
                )
            else:
                error_message = f"Graph version conflict: {cause}"
            failures.append(
                DocumentFailureReference(
                    knowledge_base_id=document.knowledge_base_id,
                    source_document_id=document.source_document_id,
                    error_message=error_message,
                    storage_key=document.storage_key,
                )
            )
            ingestion_documents_failed_total.labels(
                stage="graph", error_class=type(cause).__name__
            ).inc()
            log_stage(
                stage="graph",
                kb_id=document.knowledge_base_id,
                source_document_id=document.source_document_id,
                started_at=started_at,
                outcome="failed",
            )
            continue
        log_stage(
            stage="graph",
            kb_id=document.knowledge_base_id,
            source_document_id=document.source_document_id,
            started_at=started_at,
            outcome="success",
        )
        processed += 1
    if failures:
        event_bus.publish(
            DocumentsFailedEvent(
                correlation_id=event.correlation_id,
                documents=failures,
            )
        )
    return processed


def handle_graph_updated(
    event: GraphUpdatedEvent,
    *,
    embeddings_service: EmbeddingsServiceProtocol,
    object_store: ObjectStore,
    event_bus: EventBus,
    include_graph_embeddings: bool = False,
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
                    source_document_id=document.source_document_id,
                    empty_extraction=True,
                )
            )
            continue

        response = embeddings_service.embed(
            EmbedRequest(
                knowledge_base_id=document.knowledge_base_id,
                include_graph_embeddings=include_graph_embeddings,
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
            vectors={
                item.content_id: item.vector
                for item in response.items
                if item.channel == "text"
            },
            metadata=EmbeddingMetadata(
                model_name=response.model_name,
                dimensions=response.dimensions,
                provider="embeddings-service",
            ),
            items=[
                EmbeddingVector(
                    content_id=item.content_id,
                    channel=item.channel,
                    vector=list(item.vector),
                    model_name=item.model_name or response.model_name,
                    provider=item.provider or "embeddings-service",
                    dimensions=item.dimensions or len(item.vector),
                )
                for item in response.items
            ],
            graph_status=response.graph_status,
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
                SOURCE_DOCUMENT_ID_KEY: document.source_document_id,
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
    gnn_cluster_store: ClusterSummaryStoreProtocol | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> int:
    """Run Flow B (GNN -> risk -> explainability -> alerts.created).

    Each upserted entity is processed independently. Failures are caught and
    surfaced as ``analysis.failed`` events without aborting the pipeline.
    Successful runs additionally write analytics-derived properties back to
    the graph (E7-S11) before publishing the ``alerts.created`` aggregate.
    When a ``gnn_cluster_store`` is supplied, each successful GNN stage also
    persists its community summaries so ``/analytics/gnn/clusters`` serves
    real, up-to-date data (B1); with no store configured, persistence is
    skipped (e.g. unit scaffolding).
    """

    # Evidence packs are persisted to the shared object store so the API can
    # serve them; with no object store configured (e.g. unit scaffolding),
    # persistence is skipped and the pack id remains a forward reference.
    evidence_pack_repository: EvidencePackRepository | None = (
        ObjectStoreEvidencePackRepository(object_store) if object_store is not None else None
    )

    alerts: list[AlertCreatedReference] = []
    for document in event.documents:
        if is_cancelled is not None and is_cancelled():
            logger.info(
                "Analytics flow cancelled; stopping. correlation_id=%s",
                event.correlation_id,
            )
            break
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

        if gnn_cluster_store is not None:
            _persist_gnn_clusters(
                cluster_store=gnn_cluster_store,
                knowledge_base_id=knowledge_base_id,
                gnn_response=gnn_response,
            )

        for entity_id in upserted_entity_ids:
            if is_cancelled is not None and is_cancelled():
                logger.info(
                    "Analytics flow cancelled mid-fan-out; stopping. correlation_id=%s",
                    event.correlation_id,
                )
                break
            risk_response = _run_risk_stage(
                event=event,
                risk_service=risk_service,
                knowledge_base_id=knowledge_base_id,
                entity_id=entity_id,
                event_bus=event_bus,
            )

            # GNN-derived properties (community_id/centrality_score) don't
            # depend on risk, so this write-back runs regardless of the risk
            # stage's outcome — a KB with no derived risk signals is a
            # legitimate, common state, not a reason to drop them.
            _write_analytics_properties_to_graph(
                graph_service=graph_service,
                knowledge_base_id=knowledge_base_id,
                entity_id=entity_id,
                gnn_response=gnn_response,
                risk_response=risk_response,
            )

            if risk_response is None:
                continue

            alert_reference = _run_explainability_stage(
                event=event,
                explainability_service=explainability_service,
                graph_service=graph_service,
                knowledge_base_id=knowledge_base_id,
                entity_id=entity_id,
                risk_response=risk_response,
                evidence_pack_repository=evidence_pack_repository,
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
    except GnnDisabledError:
        logger.info(
            "Skipping GNN analytics because the capability is disabled. kb=%s",
            knowledge_base_id,
        )
        return None
    except GnnSnapshotUnavailableError as exc:
        logger.info(
            "Skipping GNN analytics because no graph snapshot is available yet. "
            "kb=%s error=%s",
            knowledge_base_id,
            exc,
        )
        return None
    except GnnInsufficientGraphError as exc:
        logger.info(
            "Skipping GNN analytics because the graph snapshot has insufficient nodes. "
            "kb=%s error=%s",
            knowledge_base_id,
            exc,
        )
        return None
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


def _persist_gnn_clusters(
    *,
    cluster_store: ClusterSummaryStoreProtocol,
    knowledge_base_id: str,
    gnn_response: GnnAnalysisResponse,
) -> None:
    """Persist pipeline community results so /analytics/gnn/clusters serves real data."""
    score_by_entity = {node.entity_id: node.score for node in gnn_response.scored_nodes}
    try:
        summaries = [
            ClusterSummary(
                cluster_id=community.community_id,
                entity_ids=list(community.member_entity_ids),
                anomaly_score=max(
                    (score_by_entity.get(member, 0.0) for member in community.member_entity_ids),
                    default=0.0,
                ),
            )
            for community in gnn_response.communities
        ]
        cluster_store.put_clusters(knowledge_base_id, summaries)
    except Exception as exc:  # noqa: BLE001 - persistence must not fail the pipeline
        logger.warning(
            "Failed to persist GNN cluster summaries kb=%s: %s", knowledge_base_id, exc
        )


def _risk_request_id(
    *, correlation_id: str, knowledge_base_id: str, entity_id: str
) -> str:
    """Deterministic risk request id for one entity assessment of one event.

    Stable across retries of the same triggering event so risk_score_history,
    the monitoring batch, and the derived alert id all dedup on retry, while a
    genuinely new event (new correlation_id) still appends a new history row.
    """

    return f"risk:{correlation_id}:{knowledge_base_id}:{entity_id}"


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
                request_id=_risk_request_id(
                    correlation_id=event.correlation_id,
                    knowledge_base_id=knowledge_base_id,
                    entity_id=entity_id,
                ),
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
    graph_service: GraphService,
    knowledge_base_id: str,
    entity_id: str,
    risk_response: RiskAssessmentResponse,
    event_bus: EventBus,
    evidence_pack_repository: EvidencePackRepository | None = None,
) -> AlertCreatedReference | None:
    alert_id = f"alert-{entity_id}-{risk_response.request_id}"
    try:
        context = build_explanation_context(
            graph_service=graph_service,
            knowledge_base_id=knowledge_base_id,
            entity_id=entity_id,
            alert_id=alert_id,
            risk_response=risk_response,
        )
        response = explainability_service.generate_from_context(context)
    except (ExplainabilityError, GraphError) as exc:
        # Expected per-entity failures (explainability, or a graph read in
        # build_explanation_context) are isolated to this entity; unexpected
        # exceptions (programming errors) propagate instead of being hidden.
        _publish_analysis_failed(
            event_bus=event_bus,
            correlation_id=event.correlation_id,
            knowledge_base_id=knowledge_base_id,
            entity_id=entity_id,
            stage="explainability",
            error_message=str(exc),
        )
        return None

    if evidence_pack_repository is not None:
        try:
            evidence_pack_repository.put(knowledge_base_id, response.evidence_pack)
        except Exception as exc:  # noqa: BLE001 - persistence is best-effort
            logger.warning(
                "Failed to persist evidence pack %s for entity %s: %s",
                response.evidence_pack.id,
                entity_id,
                exc,
            )

    return AlertCreatedReference(
        knowledge_base_id=knowledge_base_id,
        alert_id=response.alert_id,
        entity_id=entity_id,
        entity_type=context.alert.entity_type,
        severity=risk_response.risk_level,
        evidence_pack_id=response.evidence_pack.id,
        status="open",
        title=f"{risk_response.risk_level.title()} risk: {entity_id}",
        reasoning=response.evidence_pack.reasoning,
        # entity_label: no display value is cheaply in scope here. The only
        # entity read happens inside build_explanation_context (a private
        # local `focal_entity`, not surfaced on ExplanationContext/Alert), so
        # threading a real label through would require either widening the
        # ExplanationContext/Alert public contract or a second graph read —
        # both out of scope for this task. Falls back to entity_id.
        entity_label=entity_id,
        confidence=risk_response.overall_score,
        tags=[factor.factor_name.replace("_", "-") for factor in risk_response.factors[:3]],
    )


def build_explanation_context(
    *,
    graph_service: GraphService,
    knowledge_base_id: str,
    entity_id: str,
    alert_id: str,
    risk_response: RiskAssessmentResponse,
) -> ExplanationContext:
    """Assemble a real explanation context from the graph subgraph + risk assessment.

    Replaces the seeded/in-memory explainability context: the explanatory
    subgraph comes from ``graph.get_subgraph`` and the evidence items + score
    snapshot come from the risk factors.
    """

    subgraph = graph_service.get_subgraph(
        knowledge_base_id, [entity_id], depth=_EVIDENCE_SUBGRAPH_DEPTH
    )
    node_ids = [entity.id for entity in subgraph.entities] or [entity_id]
    edge_ids = [relationship.id for relationship in subgraph.relationships]

    focal_entity = graph_service.get_entity([knowledge_base_id], entity_id)
    entity_type = focal_entity.type if focal_entity is not None else "entity"

    items = [
        ExplanationItem(
            source_id=entity_id,
            source_type="risk_factor",
            quote=factor.factor_name,
            rationale=(
                factor.rationale
                or f"{factor.factor_name} contributed {factor.contribution:.2f} to the risk score."
            ),
            score=factor.contribution,
        )
        for factor in risk_response.factors
    ]
    if not items:
        items = [
            ExplanationItem(
                source_id=entity_id,
                source_type="risk_summary",
                quote=risk_response.risk_level,
                rationale=f"Overall risk score {risk_response.overall_score:.2f}.",
                score=risk_response.overall_score,
            )
        ]

    scores: dict[str, float] = {
        factor.factor_name: factor.contribution for factor in risk_response.factors
    }
    scores["overall"] = risk_response.overall_score

    alert = Alert(
        id=alert_id,
        entity_type=entity_type,
        entity_id=entity_id,
        severity=risk_response.risk_level,
        title=f"{risk_response.risk_level.title()} risk: {entity_id}",
        reasoning=f"{risk_response.risk_level.title()} risk identified for {entity_id}.",
        created_at=datetime.now(tz=timezone.utc),
    )
    return ExplanationContext(
        knowledge_base_id=knowledge_base_id,
        alert=alert,
        explanation_items=items,
        subgraph=ExplanationSubgraph(node_ids=node_ids, edge_ids=edge_ids),
        confidence=risk_response.overall_score,
        scores=scores,
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
    now = datetime.now(tz=timezone.utc)
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
    risk_response: RiskAssessmentResponse | None,
) -> None:
    properties: dict[str, object] = {}
    if risk_response is not None:
        properties["risk_score"] = float(risk_response.overall_score)
        properties["risk_level"] = risk_response.risk_level
        properties["risk_assessed_at"] = datetime.now(tz=timezone.utc).isoformat()
    centrality_score = _resolve_centrality_score(gnn_response, entity_id)
    if centrality_score is not None:
        properties["centrality_score"] = centrality_score
    community_id = _resolve_community_id(gnn_response, entity_id)
    if community_id is not None:
        properties["community_id"] = community_id
    if not properties:
        return
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
            monitoring_service.evaluate(
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

    assessed_at = datetime.now(tz=timezone.utc)
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


def handle_alerts_created_for_graph(
    event: AlertsCreatedEvent,
    *,
    alert_history_writer: AlertHistoryWriter,
    graph_service: GraphService,
) -> int:
    """Flow 4 — persist alerts to the alert-history log and snapshot onto the graph.

    Idempotent: ``alert_history`` is keyed by alert_id; the entity's
    ``active_alert_count`` is derived from a count of open alerts (never blindly
    incremented), so retry/DLQ replay is safe. The graph write publishes no
    event, so it cannot re-trigger the analytics pipeline.
    """

    created_at = datetime.now(tz=timezone.utc)
    records: list[AlertHistoryRecord] = []
    severity_by_entity: dict[tuple[str, str], str] = {}
    for alert in event.alerts:
        records.append(
            AlertHistoryRecord(
                knowledge_base_id=alert.knowledge_base_id,
                alert_id=alert.alert_id,
                entity_id=alert.entity_id,
                entity_type=alert.entity_type,
                severity=alert.severity,
                status=alert.status,
                title=alert.title,
                reasoning=alert.reasoning,
                metric_name=alert.metric_name,
                evidence_pack_id=alert.evidence_pack_id,
                created_at=created_at,
                updated_at=created_at,
                entity_label=alert.entity_label,
                confidence=alert.confidence,
                tags=alert.tags,
            )
        )
        severity_by_entity[(alert.knowledge_base_id, alert.entity_id)] = alert.severity

    alert_history_writer.write_alerts(records)

    for (knowledge_base_id, entity_id), severity in severity_by_entity.items():
        try:
            open_count = alert_history_writer.count_open_alerts(
                knowledge_base_id=knowledge_base_id, entity_id=entity_id
            )
            graph_service.update_entity_properties(
                knowledge_base_id,
                entity_id,
                {
                    "active_alert_count": open_count,
                    "last_alert_at": created_at.isoformat(),
                    "last_alert_severity": severity,
                },
            )
        except Exception as exc:  # noqa: BLE001 - graph backend may be unavailable
            logger.warning(
                "Failed to snapshot alerts to graph kb=%s entity=%s: %s",
                knowledge_base_id,
                entity_id,
                exc,
            )
    return len(records)


def run_peerstats_stage(
    *,
    peerstats_service: PeerStatsService,
    peer_stats_config: PeerStatsConfig,
    knowledge_base_id: str,
    record_type: str,
    correlation_id: str,
) -> list[str]:
    """Compute peer z-scores for every spec matching this feed's record type.

    Computes over all intervals (``interval_starts=[]``) — recompute-all is
    idempotent (upsert) and avoids a time-basis mismatch when a spec uses a
    ``time_column`` that differs from ``ingested_at``. Returns the deduped,
    sorted entity ids that received signals so the caller assesses each once.
    """

    affected: set[str] = set()
    for spec in peer_stats_config.metrics:
        if spec.record_type != record_type:
            continue
        response = peerstats_service.compute(
            PeerStatsComputeRequest(
                knowledge_base_id=knowledge_base_id,
                spec=spec,
                interval_starts=[],
                correlation_id=correlation_id,
            )
        )
        affected.update(response.affected_entity_ids)
    return sorted(affected)


_TIMESERIES_Z_CLAMP = 1.0e6  # flat-baseline jumps yield z=inf; keep stored floats JSON-safe


def run_timeseries_stage(
    *,
    column_source: RecordColumnSourceProtocol,
    anomaly_store: TimeseriesAnomalyStoreProtocol,
    signal_writer: DerivedRiskSignalWriterProtocol,
    event_bus: EventBus,
    timeseries_config: TimeseriesAnalyticsConfig,
    knowledge_base_id: str,
    record_type: str,
    correlation_id: str,
) -> list[str]:
    """Detect self-history anomalies for every spec matching this feed.

    One aggregate query per spec (not per entity); detection runs over a
    batch-local in-memory source. Insufficient history and missing optional
    detection dependencies are controlled skips. Returns the sorted entity
    ids that received an anomaly-derived risk signal so the caller assesses
    each once alongside peerstats-affected ids.
    """

    affected: set[str] = set()
    for spec in timeseries_config.metrics:
        if spec.record_type != record_type:
            continue
        series_map = load_entity_series_map(
            column_source, knowledge_base_id=knowledge_base_id, spec=spec
        )
        if not series_map:
            logger.info(
                "Timeseries stage found no series for metric=%s kb=%s",
                spec.name,
                knowledge_base_id,
            )
            continue
        service = create_timeseries_service(
            InMemoryTimeSeriesHistorySource(series=list(series_map.values())),
            event_bus=event_bus,
        )
        anomaly_records: list[TimeseriesAnomalyRecord] = []
        signals: list[DerivedRiskSignal] = []
        for entity_id in sorted(series_map):
            try:
                response = service.analyze(
                    TimeseriesAnalysisRequest(
                        knowledge_base_id=knowledge_base_id,
                        entity_id=entity_id,
                        metric_name=spec.name,
                        baseline_window=spec.baseline_window,
                        min_history=spec.min_history,
                        z_threshold=spec.z_threshold,
                        detection_strategy=spec.detection_strategy,
                    )
                )
            except TimeseriesInsufficientHistoryError:
                continue  # controlled skip: this entity lacks buckets, others may not
            except TimeseriesConfigurationError as exc:
                logger.info(
                    "Timeseries stage skipped metric=%s: %s", spec.name, exc
                )
                break  # configuration problems (e.g. missing extra) repeat per entity
            if not response.anomalies:
                continue
            for anomaly in response.anomalies:
                bounded_z = min(anomaly.z_score, _TIMESERIES_Z_CLAMP)
                anomaly_records.append(
                    TimeseriesAnomalyRecord(
                        knowledge_base_id=knowledge_base_id,
                        entity_id=entity_id,
                        metric_name=spec.name,
                        observed_at=anomaly.observed_at,
                        observed_value=anomaly.observed_value,
                        expected_value=anomaly.expected_value,
                        z_score=bounded_z,
                        severity=z_to_signal(
                            bounded_z, direction="high", z_cap=spec.z_cap
                        ),
                        detection_strategy=spec.detection_strategy,
                        correlation_id=correlation_id,
                    )
                )
            latest = max(response.anomalies, key=lambda anomaly: anomaly.observed_at)
            latest_z = min(latest.z_score, _TIMESERIES_Z_CLAMP)
            signals.append(
                DerivedRiskSignal(
                    knowledge_base_id=knowledge_base_id,
                    entity_id=entity_id,
                    entity_type=spec.entity_type,
                    metric_name=f"timeseries_anomaly:{spec.name}",
                    interval_start=latest.observed_at,
                    peer_group_key="__self_history__",
                    aggregate_value=latest.observed_value,
                    peer_mean=latest.expected_value,
                    peer_std=(latest.deviation / latest_z if latest_z > 0.0 else 0.0),
                    z_score=latest_z,
                    signal_value=z_to_signal(
                        latest_z, direction="high", z_cap=spec.z_cap
                    ),
                    weight=spec.signal_weight,
                    rationale=(
                        f"{spec.name}: self-history anomaly z={latest_z:.2f} "
                        f"({spec.detection_strategy}, {len(response.anomalies)} "
                        f"anomalous {spec.interval} buckets)"
                    ),
                    correlation_id=correlation_id,
                )
            )
            affected.add(entity_id)
        if anomaly_records:
            anomaly_store.write_anomalies(anomaly_records)
        if signals:
            signal_writer.write_signals(signals)
    return sorted(affected)


def assess_entities(
    *,
    risk_service: RiskService,
    knowledge_base_id: str,
    entity_ids: list[str],
    correlation_id: str,
) -> int:
    """Assess each entity once; tolerate entities with insufficient signals.

    Each successful assess publishes one RiskScoredEvent (existing Flow 3),
    persisted to risk_score_history under a deterministic request id derived from
    ``correlation_id`` + entity, so a retried ingest re-assesses idempotently
    instead of accumulating duplicate history rows. Only *expected* per-entity
    conditions are swallowed (an entity below the >=2-signal floor, or a
    per-entity threshold misconfiguration) so one such entity never aborts the
    batch. Infrastructure failures (``RiskSourceError``/``RiskHistoryError``)
    deliberately propagate so a transient DB/source outage surfaces (logged with
    a traceback by the caller's best-effort wrapper) rather than being silently
    swallowed at INFO.
    """

    assessed = 0
    for entity_id in entity_ids:
        try:
            risk_service.assess(
                RiskAssessmentRequest(
                    knowledge_base_id=knowledge_base_id,
                    entity_id=entity_id,
                    request_id=_risk_request_id(
                        correlation_id=correlation_id,
                        knowledge_base_id=knowledge_base_id,
                        entity_id=entity_id,
                    ),
                )
            )
            assessed += 1
        except (RiskInsufficientSignalsError, RiskConfigurationError) as exc:
            logger.info("Skipping risk assess for entity=%s: %s", entity_id, exc)
    return assessed


def handle_records_ingested(
    event: RecordsIngestedEvent,
    *,
    records_config: RecordsConfig,
    raw_record_store: RawRecordStore,
    graph_service: GraphService,
    observation_writer: ObservationWriter,
    embeddings_service: EmbeddingsServiceProtocol | None = None,
    vector_store: VectorStoreProtocol | None = None,
    policy_rules: list[PolicyRulePack] | None = None,
    policy_service: PolicyService | None = None,
    metrics_throttle: MetricsRecomputeThrottle | None = None,
    peerstats_service: PeerStatsService | None = None,
    peer_stats_config: PeerStatsConfig | None = None,
    risk_service: RiskService | None = None,
    peer_stats_enabled: bool = False,
    record_column_source: RecordColumnSourceProtocol | None = None,
    timeseries_anomaly_store: TimeseriesAnomalyStoreProtocol | None = None,
    timeseries_config: TimeseriesAnalyticsConfig | None = None,
    timeseries_enabled: bool = False,
    derived_signal_store: DerivedRiskSignalWriterProtocol | None = None,
    event_bus: EventBus | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> int:
    """Flow 1 — fan a structured-records batch out to the graph and observations.

    A single handler: map rows to graph entities/relationships and upsert them,
    then derive observations and persist them.  When ``embeddings_service`` and
    ``vector_store`` are both provided, each stored entity is also embedded and
    indexed into the vector store so the KB becomes RAG-searchable.  Both
    parameters default to ``None`` so the handler is backward-compatible with
    callers that do not yet wire the embedding path.

    Every write is idempotent so the worker's retry/DLQ wrapper can safely
    re-run this handler.
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
    stored_entities, _stored_relationships = graph_service.upsert_records_graph(
        event.knowledge_base_id, mapped.entities, mapped.relationships
    )

    if embeddings_service is not None and vector_store is not None and stored_entities:
        texts = [_build_entity_embedding_text(entity) for entity in stored_entities]
        embed_response = embeddings_service.embed(
            EmbedRequest(
                knowledge_base_id=event.knowledge_base_id,
                submissions=[
                    EmbedSubmission(content_id=entity.id, content=text)
                    for entity, text in zip(stored_entities, texts, strict=True)
                ],
            )
        )
        # Build a lookup so we can match vectors to their entity regardless of
        # the order the embedder returns them.
        vector_by_id = {item.content_id: item.vector for item in embed_response.items}
        missing = [e.id for e in stored_entities if e.id not in vector_by_id]
        if missing:
            logger.warning(
                "embed response missing vectors for %d entity ids; skipping. ids=%s",
                len(missing), missing,
            )
        vector_records = [
            VectorRecord(
                id=f"record:{event.knowledge_base_id}:{entity.id}",
                knowledge_base_id=event.knowledge_base_id,
                content_id=entity.id,
                embedding=vector_by_id[entity.id],
                content=text,
                metadata={
                    SOURCE_KIND_KEY: SOURCE_KIND_RECORD,
                    SOURCE_ID_KEY: entity.id,
                    "entity_type": entity.type,
                },
            )
            for entity, text in zip(stored_entities, texts, strict=True)
            if entity.id in vector_by_id
        ]
        if vector_records:
            vector_store.upsert_records(event.knowledge_base_id, vector_records)
            # We intentionally do not publish VectorsIndexedEvent here because
            # handle_vectors_indexed is documents-only and would no-op for records.

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

    if policy_service is not None and policy_rules:
        _evaluate_policy_rules(
            event=event,
            policy_rules=policy_rules,
            policy_service=policy_service,
            entities=stored_entities,
            graph_service=graph_service,
            metrics_throttle=metrics_throttle,
        )

    if is_cancelled is not None and is_cancelled():
        logger.info(
            "Records ingest cancelled before peerstats stage; correlation_id=%s",
            event.correlation_id,
        )
        return len(records)

    affected: set[str] = set()
    if (
        peer_stats_enabled
        and peerstats_service is not None
        and peer_stats_config is not None
        and peer_stats_config.metrics
    ):
        try:
            affected.update(
                run_peerstats_stage(
                    peerstats_service=peerstats_service,
                    peer_stats_config=peer_stats_config,
                    knowledge_base_id=event.knowledge_base_id,
                    record_type=feed.record_type,
                    correlation_id=event.correlation_id,
                )
            )
        except Exception:  # noqa: BLE001 - best-effort: never break ingest
            logger.exception(
                "Peerstats stage failed for kb=%s correlation=%s",
                event.knowledge_base_id,
                event.correlation_id,
            )
    if (
        timeseries_enabled
        and timeseries_config is not None
        and timeseries_config.metrics
        and record_column_source is not None
        and timeseries_anomaly_store is not None
        and derived_signal_store is not None
        and event_bus is not None
    ):
        try:
            affected.update(
                run_timeseries_stage(
                    column_source=record_column_source,
                    anomaly_store=timeseries_anomaly_store,
                    signal_writer=derived_signal_store,
                    event_bus=event_bus,
                    timeseries_config=timeseries_config,
                    knowledge_base_id=event.knowledge_base_id,
                    record_type=feed.record_type,
                    correlation_id=event.correlation_id,
                )
            )
        except Exception:  # noqa: BLE001 - best-effort: never break ingest
            logger.exception(
                "Timeseries stage failed for kb=%s correlation=%s",
                event.knowledge_base_id,
                event.correlation_id,
            )
    if risk_service is not None and affected:
        try:
            assess_entities(
                risk_service=risk_service,
                knowledge_base_id=event.knowledge_base_id,
                entity_ids=sorted(affected),
                correlation_id=event.correlation_id,
            )
        except Exception:  # noqa: BLE001 - best-effort: never break ingest
            logger.exception(
                "Risk assess stage failed for kb=%s correlation=%s",
                event.knowledge_base_id,
                event.correlation_id,
            )
    return len(records)


def _evaluate_policy_rules(
    *,
    event: RecordsIngestedEvent,
    policy_rules: list[PolicyRulePack],
    policy_service: PolicyService,
    entities: list[Entity],
    graph_service: GraphService,
    metrics_throttle: MetricsRecomputeThrottle | None,
) -> None:
    """Flow P — evaluate configured rules over the freshly-stored entities and
    (throttled) graph metrics; upsert a durable item per match. Best-effort:
    a failure here is logged but never aborts records ingestion."""

    try:
        metrics: dict[str, float] = {}
        now = datetime.now(tz=timezone.utc)
        if metrics_throttle is None or metrics_throttle.should_recompute(
            event.knowledge_base_id, now=now
        ):
            graph_metrics = graph_service.compute_metrics(event.knowledge_base_id)
            metrics = {
                "entity_count": float(graph_metrics.entity_count),
                "relationship_count": float(graph_metrics.relationship_count),
                "avg_degree": graph_metrics.avg_degree,
            }
        matches = evaluate(
            policy_rules,
            PolicyEvalState(entities=entities, alerts=[], metrics=metrics),
        )
        for match in matches:
            policy_service.record_match(
                knowledge_base_id=event.knowledge_base_id,
                rule_id=match.rule_id,
                rule_pack_id=match.rule_pack_id,
                target_kind=match.target_kind,
                target_ref=match.target_ref,
                title=match.title,
                severity=match.severity,
                matched_fields=match.matched_fields,
                citations=match.citations,
            )
    except Exception as exc:  # noqa: BLE001 - policy eval must not block ingestion
        logger.warning(
            "Policy evaluation failed for kb=%s: %s", event.knowledge_base_id, exc
        )


def _resolve_records_feed(
    records_config: RecordsConfig, feed_name: str
) -> RecordFeedConfig:
    for feed in records_config.feeds:
        if feed.name == feed_name:
            return feed
    raise RecordFeedNotFoundError(feed_name)


def handle_knowledge_base_deleted(
    event: KnowledgeBaseDeletedEvent,
    *,
    kb_deletion_stores: KbDeletionStores,
    kb_repository: KnowledgeBaseRepository,
) -> None:
    """Retry the FULL KB cleanup cascade when the API DELETE returned a partial cleanup.

    When the API DELETE endpoint returns 207 with ``cleanup_pending=True`` it
    means one or more downstream stores could not be cleaned up synchronously.
    The worker picks up the ``KnowledgeBaseDeletedEvent`` and replays the same
    cascade as the API — the single authoritative step list in
    ``knowledgebases.cleanup.kb_deletion_steps`` (graph/vector/raw_records/derived
    signals/risk history/observations/alert history/metrics/conversations/cases/
    policy/evidence/scorecards/object store) — then deletes the KB metadata.

    Every step is idempotent. Exceptions propagate so the coordinator's retry/DLQ
    wrapper re-runs the whole (idempotent) cascade; KB metadata is deleted only
    after every store has been purged.
    """

    if not event.cleanup_pending:
        return
    logger.info("retrying KB cleanup", extra={"knowledge_base_id": event.knowledge_base_id})
    # Exceptions bubble to the coordinator's DLQ flow; the cascade is idempotent.
    for _step_name, deletion in kb_deletion_steps(
        kb_deletion_stores, event.knowledge_base_id
    ):
        deletion()
    kb_repository.delete(event.knowledge_base_id)


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


def _publish_analytics_fanout_failed(
    *,
    event: GraphUpdatedEvent,
    event_bus: EventBus,
    object_store: ObjectStore,
    error_message: str,
) -> None:
    published = False
    for document in event.documents:
        entity_ids: list[str] = []
        if document.graph_update_storage_key:
            try:
                graph_update = _load_graph_update(
                    object_store, document.graph_update_storage_key
                )
                entity_ids = graph_update.upserted_entity_ids
            except Exception as exc:  # noqa: BLE001 - fallback keeps failure visible
                logger.warning(
                    "Could not resolve analytics fan-out failure entity ids "
                    "for kb=%s document=%s: %s",
                    document.knowledge_base_id,
                    document.source_document_id,
                    exc,
                )
        if not entity_ids:
            entity_ids = [document.source_document_id]
        for entity_id in entity_ids:
            _publish_analysis_failed(
                event_bus=event_bus,
                correlation_id=event.correlation_id,
                knowledge_base_id=document.knowledge_base_id,
                entity_id=entity_id,
                stage="analytics_fanout",
                error_message=error_message,
            )
            published = True

    if not published:
        _publish_analysis_failed(
            event_bus=event_bus,
            correlation_id=event.correlation_id,
            knowledge_base_id="unknown",
            entity_id="unknown",
            stage="analytics_fanout",
            error_message=error_message,
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

        records_by_namespace: dict[str, list[VectorRecord]] = {}
        embedding_items = _embedding_items_for_indexing(embeddings_result)
        for embedding_item in sorted(
            embedding_items,
            key=lambda item: (item.channel, item.content_id),
        ):
            content_id = embedding_item.content_id
            channel = embedding_item.channel
            entity = entities_by_id.get(content_id)
            metadata: dict[str, str | int | float | bool] = {
                "knowledge_base_id": document.knowledge_base_id,
                "entity_id": content_id,
                "embedding_channel": channel,
                "embedding_model_name": embedding_item.model_name,
                "embedding_provider": embedding_item.provider,
                "embedding_dimensions": embedding_item.dimensions,
                SOURCE_KIND_KEY: SOURCE_KIND_DOCUMENT,
                SOURCE_DOCUMENT_ID_KEY: document.source_document_id,
                "extraction_result_id": document.extraction_result_id,
                "validation_report_id": document.validation_report_id,
            }
            if entity is not None:
                metadata["entity_type"] = entity.type
            namespace = _embedding_namespace(document.knowledge_base_id, channel)
            records_by_namespace.setdefault(namespace, []).append(
                VectorRecord(
                    id=_embedding_record_id(
                        document.knowledge_base_id,
                        content_id,
                        channel,
                    ),
                    knowledge_base_id=document.knowledge_base_id,
                    content_id=content_id,
                    embedding=list(embedding_item.vector),
                    metadata=metadata,
                )
            )

        if not records_by_namespace:
            continue

        stored_records: list[VectorRecord] = []
        for namespace in sorted(records_by_namespace):
            stored_records.extend(
                vector_store.upsert_records(
                    namespace,
                    records_by_namespace[namespace],
                )
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
                knowledge_base_id=document.knowledge_base_id,
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


def _embedding_namespace(knowledge_base_id: str, channel: str) -> str:
    if channel == "graph":
        return f"{knowledge_base_id}__graph"
    return knowledge_base_id


def _embedding_record_id(knowledge_base_id: str, content_id: str, channel: str) -> str:
    return f"{knowledge_base_id}:{content_id}:{channel}"


def _embedding_items_for_indexing(
    embeddings_result: EmbeddingResult,
) -> list[EmbeddingVector]:
    if embeddings_result.items:
        return list(embeddings_result.items)

    return [
        EmbeddingVector(
            content_id=content_id,
            channel="text",
            vector=list(vector),
            model_name=embeddings_result.metadata.model_name,
            provider=embeddings_result.metadata.provider,
            dimensions=embeddings_result.metadata.dimensions,
            created_at=embeddings_result.metadata.created_at,
        )
        for content_id, vector in embeddings_result.vectors.items()
    ]


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
    except Exception as exc:  # noqa: BLE001 - kb.ready count is best-effort, not fatal
        # Visible at WARNING: a graph-backend failure here publishes a count of 0,
        # which a consumer would read as an empty KB — surface it rather than hide.
        logger.warning(
            "Graph entity count unavailable for kb=%s (publishing 0): %s",
            knowledge_base_id,
            exc,
        )
        return 0


def _count_relationships(graph_repository: GraphRepository, knowledge_base_id: str) -> int:
    try:
        return graph_repository.count_relationships(knowledge_base_id)
    except Exception as exc:  # noqa: BLE001 - kb.ready count is best-effort, not fatal
        logger.warning(
            "Graph relationship count unavailable for kb=%s (publishing 0): %s",
            knowledge_base_id,
            exc,
        )
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
        # A missing object is ``KeyError`` for every ObjectStore adapter
        # (contract documented on ObjectStoreProtocol.get_bytes), so this
        # fallback is portable across in-memory / local FS / S3 backends.
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
    document_extractor: DocumentExtractorProtocol,
    extraction_validator: ExtractionResultValidator,
    graph_service: GraphService,
    object_store: ObjectStore,
    event_bus: EventBus,
    embeddings_service: EmbeddingsServiceProtocol | None = None,
    vector_store: VectorStoreProtocol | None = None,
    graph_repository: GraphRepository | None = None,
    gnn_service: GnnService | None = None,
    gnn_cluster_store: ClusterSummaryStoreProtocol | None = None,
    risk_service: RiskService | None = None,
    explainability_service: ExplainabilityService | None = None,
    monitoring_service: MonitoringService | None = None,
    records_config: RecordsConfig | None = None,
    raw_record_store: RawRecordStore | None = None,
    observation_writer: ObservationWriter | None = None,
    policy_service: PolicyService | None = None,
    policy_rules: list[PolicyRulePack] | None = None,
    entity_metric_repository: EntityMetricRepository | None = None,
    metrics_throttle: MetricsRecomputeThrottle | None = None,
    policy_metrics_throttle: MetricsRecomputeThrottle | None = None,
    risk_history_writer: RiskHistoryWriter | None = None,
    alert_history_writer: AlertHistoryWriter | None = None,
    workflow_tracker: WorkflowEventTracker | None = None,
    graph_embeddings_enabled: bool = False,
    peerstats_service: PeerStatsService | None = None,
    peer_stats_config: PeerStatsConfig | None = None,
    peer_stats_enabled: bool = False,
    record_column_source: RecordColumnSourceProtocol | None = None,
    timeseries_anomaly_store: TimeseriesAnomalyStoreProtocol | None = None,
    timeseries_config: TimeseriesAnalyticsConfig | None = None,
    timeseries_enabled: bool = False,
    derived_signal_store: DerivedRiskSignalWriterProtocol | None = None,
    kb_repository: KnowledgeBaseRepository | None = None,
    kb_deletion_stores: KbDeletionStores | None = None,
    document_status_store: SourceDocumentStatusStore | None = None,
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
        # Cooperative cancellation probe for long handlers: re-reads run status
        # by correlation so a cancel that lands mid-stage stops further work.
        is_cancelled: Callable[[], bool] | None = (
            partial(workflow_tracker.is_run_cancelled, event.correlation_id)
            if workflow_tracker is not None
            else None
        )
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
            gnn_cluster_store=gnn_cluster_store,
            risk_service=risk_service,
            explainability_service=explainability_service,
            monitoring_service=monitoring_service,
            records_config=records_config,
            raw_record_store=raw_record_store,
            observation_writer=observation_writer,
            policy_service=policy_service,
            policy_rules=policy_rules,
            entity_metric_repository=entity_metric_repository,
            metrics_throttle=metrics_throttle,
            policy_metrics_throttle=policy_metrics_throttle,
            risk_history_writer=risk_history_writer,
            alert_history_writer=alert_history_writer,
            graph_embeddings_enabled=graph_embeddings_enabled,
            peerstats_service=peerstats_service,
            peer_stats_config=peer_stats_config,
            peer_stats_enabled=peer_stats_enabled,
            record_column_source=record_column_source,
            timeseries_anomaly_store=timeseries_anomaly_store,
            timeseries_config=timeseries_config,
            timeseries_enabled=timeseries_enabled,
            derived_signal_store=derived_signal_store,
            kb_repository=kb_repository,
            kb_deletion_stores=kb_deletion_stores,
            document_status_store=document_status_store,
            is_cancelled=is_cancelled,
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
    document_extractor: DocumentExtractorProtocol,
    extraction_validator: ExtractionResultValidator,
    graph_service: GraphService,
    object_store: ObjectStore,
    event_bus: EventBus,
    embeddings_service: EmbeddingsServiceProtocol | None,
    vector_store: VectorStoreProtocol | None,
    graph_repository: GraphRepository | None,
    gnn_service: GnnService | None,
    gnn_cluster_store: ClusterSummaryStoreProtocol | None,
    risk_service: RiskService | None,
    explainability_service: ExplainabilityService | None,
    monitoring_service: MonitoringService | None,
    records_config: RecordsConfig | None,
    raw_record_store: RawRecordStore | None,
    observation_writer: ObservationWriter | None,
    policy_service: PolicyService | None,
    policy_rules: list[PolicyRulePack] | None,
    entity_metric_repository: EntityMetricRepository | None,
    metrics_throttle: MetricsRecomputeThrottle | None,
    policy_metrics_throttle: MetricsRecomputeThrottle | None,
    risk_history_writer: RiskHistoryWriter | None,
    alert_history_writer: AlertHistoryWriter | None,
    graph_embeddings_enabled: bool,
    peerstats_service: PeerStatsService | None = None,
    peer_stats_config: PeerStatsConfig | None = None,
    peer_stats_enabled: bool = False,
    record_column_source: RecordColumnSourceProtocol | None = None,
    timeseries_anomaly_store: TimeseriesAnomalyStoreProtocol | None = None,
    timeseries_config: TimeseriesAnalyticsConfig | None = None,
    timeseries_enabled: bool = False,
    derived_signal_store: DerivedRiskSignalWriterProtocol | None = None,
    kb_repository: KnowledgeBaseRepository | None = None,
    kb_deletion_stores: KbDeletionStores | None = None,
    document_status_store: SourceDocumentStatusStore | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> int:
    del delivery  # reserved for future stream offsets / dlq metadata
    # BL-041: durable per-document status projection. Runs inside the retry/DLQ
    # wrapper; transitions are monotonic + idempotent so replays are no-ops.
    if document_status_store is not None:
        project_document_status(event, document_status_store)
    if isinstance(event, DocumentsExtractionWarningEvent):
        return 0  # projection-only event; no pipeline stage follows
    if isinstance(event, DocumentsUploadedEvent):
        return len(ingestion_service.process_documents_uploaded(event))
    if isinstance(event, DocumentsParsedEvent):
        return handle_documents_parsed(
            event,
            document_chunker=document_chunker,
            object_store=object_store,
            event_bus=event_bus,
            kb_repository=kb_repository,
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
            kb_repository=kb_repository,
        )
    if isinstance(event, EntitiesValidatedEvent):
        return handle_entities_validated(
            event,
            graph_service=graph_service,
            object_store=object_store,
            event_bus=event_bus,
        )
    if isinstance(event, GraphUpdatedEvent):
        if embeddings_service is None:
            raise ValueError("GraphUpdatedEvent requires an embeddings_service.")
        processed = handle_graph_updated(
            event,
            embeddings_service=embeddings_service,
            object_store=object_store,
            event_bus=event_bus,
            include_graph_embeddings=graph_embeddings_enabled,
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
                    gnn_cluster_store=gnn_cluster_store,
                    is_cancelled=is_cancelled,
                )
            except Exception as exc:  # noqa: BLE001 - analytics must not re-run Flow A
                # Kept best-effort intentionally: GraphUpdatedEvent already ran
                # Flow A (embeddings) in this same dispatch, so propagating a Flow B
                # failure would re-run the expensive embedding pipeline on retry.
                # Publishing this visibility event is intentionally not swallowed:
                # if it fails too, the retry/DLQ wrapper must see that failure.
                logger.warning(
                    "Flow B analytics handler raised; Flow A already completed. error=%s",
                    exc,
                )
                _publish_analytics_fanout_failed(
                    event=event,
                    event_bus=event_bus,
                    object_store=object_store,
                    error_message=str(exc),
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
    if isinstance(event, KnowledgeBaseReadyEvent):
        return 0
    if isinstance(event, RiskScoredEvent):
        # RiskScoredEvent is the sole path for monitoring + the risk_score_history
        # write-back. Both are idempotent (the deterministic request_id keys the
        # monitoring batch, the history row, and the derived alert id), so a
        # failure must PROPAGATE to the retry/DLQ wrapper rather than be silently
        # dropped — a transient DB/event-bus outage retries instead of vanishing.
        processed = 0
        if monitoring_service is not None:
            processed = handle_risk_scored(
                event,
                monitoring_service=monitoring_service,
                event_bus=event_bus,
            )
        if risk_history_writer is not None:
            handle_risk_scored_for_graph(
                event,
                risk_history_writer=risk_history_writer,
                graph_service=graph_service,
            )
        return processed
    if isinstance(event, AlertsCreatedEvent):
        if alert_history_writer is None:
            return 0
        # Sole path for the alert_history write; idempotent on alert_id, so a
        # failure propagates to retry/DLQ rather than being silently dropped.
        return handle_alerts_created_for_graph(
            event,
            alert_history_writer=alert_history_writer,
            graph_service=graph_service,
        )
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
            embeddings_service=embeddings_service,
            vector_store=vector_store,
            policy_rules=policy_rules,
            policy_service=policy_service,
            metrics_throttle=policy_metrics_throttle,
            peerstats_service=peerstats_service,
            peer_stats_config=peer_stats_config,
            risk_service=risk_service,
            peer_stats_enabled=peer_stats_enabled,
            record_column_source=record_column_source,
            timeseries_anomaly_store=timeseries_anomaly_store,
            timeseries_config=timeseries_config,
            timeseries_enabled=timeseries_enabled,
            derived_signal_store=derived_signal_store,
            event_bus=event_bus,
            is_cancelled=is_cancelled,
        )
    if isinstance(event, KnowledgeBaseDeletedEvent):
        if kb_deletion_stores is None or kb_repository is None:
            logger.warning(
                "KnowledgeBaseDeletedEvent received but KB cleanup dependencies are not wired."
            )
            return 0
        handle_knowledge_base_deleted(
            event,
            kb_deletion_stores=kb_deletion_stores,
            kb_repository=kb_repository,
        )
        return 1
    return 0


async def run_handler_with_retry(
    handler: Callable[[], int],
    *,
    event: AnyEvent,
    event_bus: EventBus,
    retry_policy: RetryPolicy | None = None,
    stage_policy: StagePolicy | None = None,
    sleep: Callable[[float], "asyncio.Future[None] | object"] = asyncio.sleep,
    on_failure: Callable[[BaseException], None] | None = None,
    dlq_record_store: DlqRecordStore | None = None,
) -> int:
    """Run ``handler`` with exponential-backoff retry and DLQ on exhaustion.

    ``sleep`` is injected so unit tests can avoid waiting on the event loop.

    ACK contract
    ------------
    This function returns the handler's processed-count when the handler
    succeeded OR when retries are exhausted AND ``publish_to_dlq``
    succeeded (returning ``0``). If ``publish_to_dlq`` itself raises
    (e.g., the event bus is unreachable), the exception propagates to
    the caller — the caller therefore does NOT ACK the delivery and the
    event remains pending in the underlying stream for the next
    delivery attempt.

    Callers that unconditionally ACK after this function returns are
    safe. Callers that ACK inside a broad ``except`` MUST NOT catch and
    swallow DLQ publish failures; doing so would silently drop events.
    See ``drain_ingestion_events`` for the canonical caller pattern.

    Durable DLQ record (BL-023)
    ---------------------------
    After ``publish_to_dlq`` succeeds, if ``dlq_record_store`` is provided
    this also persists a durable :class:`~events.dlq_models.DlqRecord` for
    operator visibility/replay. This is best-effort: a failure to persist
    is logged and swallowed rather than propagated, so a durable-store
    outage never masks the original handler error or affects the ACK
    contract above — the Redis Streams DLQ entry (used for the ACK
    contract) is written independently and is unaffected by a persist
    failure.

    Execution thread
    ----------------
    ``handler`` is synchronous and may be CPU-heavy (GNN/embeddings) or do
    blocking I/O (graph/object-store/DB). Each attempt is therefore run in a
    worker thread via ``asyncio.to_thread`` so the event loop — and with it
    the ``/health`` server and SIGTERM/SIGINT handlers — stays responsive
    while a long stage runs. ``drain_ingestion_events`` still awaits each
    delivery in turn, so this changes the execution thread, not the
    one-handler-at-a-time ordering.
    """

    policy = stage_policy or StagePolicy(retry_policy=retry_policy or RetryPolicy())
    retry_policy = policy.retry_policy
    last_exc: BaseException | None = None
    retries_attempted = 0
    for attempt in range(retry_policy.max_retries + 1):
        try:
            handler_task = asyncio.to_thread(handler)
            if policy.timeout_seconds is not None:
                return await asyncio.wait_for(
                    handler_task, timeout=policy.timeout_seconds
                )
            return await handler_task
        except asyncio.TimeoutError as exc:
            last_exc = exc
            retries_attempted = attempt
            break
        except Exception as exc:  # noqa: BLE001 - we route to DLQ
            last_exc = exc
            retries_attempted = attempt
            if policy.fatal_exception_types and isinstance(
                exc, policy.fatal_exception_types
            ):
                break
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
        retry_count=retries_attempted,
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
    if dlq_record_store is not None:
        try:
            dlq_record_store.persist(
                DlqRecord(
                    dlq_id=generate_id(),
                    event_type=event.event_type,
                    correlation_id=event.correlation_id,
                    payload=encode_event(event),
                    error_message=error_info.error_message,
                    error_traceback=error_info.traceback,
                    retry_count=error_info.retry_count,
                    failed_at=error_info.failed_at,
                )
            )
        except Exception:  # noqa: BLE001 - never mask the original handler error
            logger.exception(
                "Failed to persist durable DLQ record; the Redis DLQ entry "
                "still exists. event_type=%s correlation_id=%s",
                event.event_type,
                event.correlation_id,
            )
    return 0


async def drain_ingestion_events(
    event_bus: EventBus,
    ingestion_service: IngestionService,
    document_chunker: DocumentChunker,
    document_extractor: DocumentExtractorProtocol,
    extraction_validator: ExtractionResultValidator,
    graph_service: GraphService,
    object_store: ObjectStore,
    *,
    embeddings_service: EmbeddingsServiceProtocol | None = None,
    vector_store: VectorStoreProtocol | None = None,
    graph_repository: GraphRepository | None = None,
    gnn_service: GnnService | None = None,
    gnn_cluster_store: ClusterSummaryStoreProtocol | None = None,
    risk_service: RiskService | None = None,
    explainability_service: ExplainabilityService | None = None,
    monitoring_service: MonitoringService | None = None,
    records_config: RecordsConfig | None = None,
    raw_record_store: RawRecordStore | None = None,
    observation_writer: ObservationWriter | None = None,
    policy_service: PolicyService | None = None,
    policy_rules: list[PolicyRulePack] | None = None,
    entity_metric_repository: EntityMetricRepository | None = None,
    metrics_throttle: MetricsRecomputeThrottle | None = None,
    policy_metrics_throttle: MetricsRecomputeThrottle | None = None,
    risk_history_writer: RiskHistoryWriter | None = None,
    alert_history_writer: AlertHistoryWriter | None = None,
    peerstats_service: PeerStatsService | None = None,
    peer_stats_config: PeerStatsConfig | None = None,
    peer_stats_enabled: bool = False,
    record_column_source: RecordColumnSourceProtocol | None = None,
    timeseries_anomaly_store: TimeseriesAnomalyStoreProtocol | None = None,
    timeseries_config: TimeseriesAnalyticsConfig | None = None,
    timeseries_enabled: bool = False,
    derived_signal_store: DerivedRiskSignalWriterProtocol | None = None,
    consumer_group: str,
    consumer_name: str,
    limit: int = 10,
    block_ms: int | None = None,
    reclaim_min_idle_ms: int | None = None,
    retry_policy: RetryPolicy | None = None,
    stage_policy_registry: StagePolicyRegistry | None = None,
    health_state: HealthState | None = None,
    workflow_tracker: WorkflowEventTracker | None = None,
    graph_embeddings_enabled: bool = False,
    kb_repository: KnowledgeBaseRepository | None = None,
    kb_deletion_stores: KbDeletionStores | None = None,
    document_status_store: SourceDocumentStatusStore | None = None,
    dlq_record_store: DlqRecordStore | None = None,
    sleep: Callable[[float], "asyncio.Future[None] | object"] = asyncio.sleep,
) -> int:
    """Consume and process available ingestion events with retry/DLQ semantics."""

    policy = retry_policy or RetryPolicy()
    policies = stage_policy_registry or StagePolicyRegistry(default_retry_policy=policy)
    processed = 0
    event_types = list(WORKER_EVENT_TYPES)
    event_bus.ensure_consumer_group(event_types, consumer_group=consumer_group)
    deliveries: list[EventDelivery] = []
    if reclaim_min_idle_ms is not None and reclaim_min_idle_ms > 0 and limit > 0:
        deliveries.extend(
            event_bus.reclaim_stale_pending(
                event_types,
                consumer_group=consumer_group,
                consumer_name=consumer_name,
                min_idle_ms=reclaim_min_idle_ms,
                limit=limit,
            )
        )
    remaining_limit = limit - len(deliveries)
    if remaining_limit > 0:
        deliveries.extend(
            event_bus.consume(
                event_types,
                consumer_group=consumer_group,
                consumer_name=consumer_name,
                limit=remaining_limit,
                block_ms=block_ms,
            )
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
                gnn_cluster_store=gnn_cluster_store,
                risk_service=risk_service,
                explainability_service=explainability_service,
                monitoring_service=monitoring_service,
                records_config=records_config,
                raw_record_store=raw_record_store,
                observation_writer=observation_writer,
                policy_service=policy_service,
                policy_rules=policy_rules,
                entity_metric_repository=entity_metric_repository,
                metrics_throttle=metrics_throttle,
                policy_metrics_throttle=policy_metrics_throttle,
                risk_history_writer=risk_history_writer,
                alert_history_writer=alert_history_writer,
                workflow_tracker=workflow_tracker,
                graph_embeddings_enabled=graph_embeddings_enabled,
                peerstats_service=peerstats_service,
                peer_stats_config=peer_stats_config,
                peer_stats_enabled=peer_stats_enabled,
                record_column_source=record_column_source,
                timeseries_anomaly_store=timeseries_anomaly_store,
                timeseries_config=timeseries_config,
                timeseries_enabled=timeseries_enabled,
                derived_signal_store=derived_signal_store,
                kb_repository=kb_repository,
                kb_deletion_stores=kb_deletion_stores,
                document_status_store=document_status_store,
            )

        dead_lettered = False

        def _record_failure(
            error: BaseException,
            captured: EventDelivery = delivery,
        ) -> None:
            nonlocal dead_lettered
            dead_lettered = True
            if workflow_tracker is not None:
                workflow_tracker.fail_event(captured.event, error)

        processed += await run_handler_with_retry(
            _run_handler,
            event=delivery.event,
            event_bus=event_bus,
            retry_policy=policy,
            stage_policy=policies.get(delivery.event.event_type),
            sleep=sleep,
            on_failure=_record_failure,
            dlq_record_store=dlq_record_store,
        )
        ackable.append(delivery)
        if health_state is not None:
            # Honest health: a dead-lettered delivery is NOT a success. Marking
            # it processed (the old behaviour) made a worker dead-lettering 100%
            # of events look healthy.
            if dead_lettered:
                health_state.mark_event_dead_lettered()
            else:
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


async def _drain_once(
    deps: WorkerDependencies,
    *,
    policy: RetryPolicy,
    stage_policy_registry: StagePolicyRegistry,
    health_state: HealthState,
) -> int:
    """Run one drain iteration with the full worker dependency set.

    Extracted from ``run_worker`` so the loop body stays small enough to wrap in
    the resilience guard that keeps a transient drain error from killing the
    worker process.
    """

    return await drain_ingestion_events(
        deps.event_bus,
        deps.ingestion_service,
        deps.document_chunker,
        deps.document_extractor,
        deps.extraction_validator,
        deps.graph_service,
        deps.object_store,
        embeddings_service=deps.embeddings_service,
        vector_store=deps.vector_store,
        graph_repository=deps.graph_repository,
        gnn_service=deps.gnn_service,
        gnn_cluster_store=deps.gnn_cluster_store,
        risk_service=deps.risk_service,
        explainability_service=deps.explainability_service,
        monitoring_service=deps.monitoring_service,
        records_config=deps.records_config,
        raw_record_store=deps.raw_record_store,
        kb_deletion_stores=deps.kb_deletion_stores,
        kb_repository=deps.kb_repository,
        document_status_store=deps.document_status_store,
        dlq_record_store=deps.dlq_record_store,
        observation_writer=deps.observation_writer,
        policy_service=deps.policy_service,
        policy_rules=deps.policy_rules,
        entity_metric_repository=deps.entity_metric_repository,
        metrics_throttle=deps.metrics_throttle,
        policy_metrics_throttle=deps.policy_metrics_throttle,
        risk_history_writer=deps.risk_history_writer,
        alert_history_writer=deps.alert_history_writer,
        peerstats_service=deps.peerstats_service,
        peer_stats_config=deps.peer_stats_config,
        peer_stats_enabled=deps.peer_stats_enabled,
        record_column_source=deps.record_column_source,
        timeseries_anomaly_store=deps.timeseries_anomaly_store,
        timeseries_config=deps.timeseries_config,
        timeseries_enabled=deps.timeseries_enabled,
        derived_signal_store=deps.derived_signal_store,
        consumer_group=deps.event_settings.consumer_group,
        consumer_name=deps.event_settings.consumer_name(),
        limit=deps.event_settings.batch_size,
        block_ms=deps.event_settings.block_ms,
        reclaim_min_idle_ms=deps.event_settings.reclaim_min_idle_ms,
        retry_policy=policy,
        stage_policy_registry=stage_policy_registry,
        health_state=health_state,
        workflow_tracker=deps.workflow_tracker,
        graph_embeddings_enabled=deps.graph_embeddings_enabled,
    )


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
    config_reload_state = ConfigReloadState()

    policy = retry_policy or RetryPolicy()
    stage_policy_registry = load_stage_policy_registry_from_env(
        default_retry_policy=policy
    )
    settings = health_settings or HealthSettings()
    health_state = HealthState(settings=settings)

    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()
    install_signal_handlers(loop, shutdown_event)

    health_server = await start_health_server_safely(health_state)
    stale_workflow_max_age_seconds = _positive_int_from_env(
        "CHILI_WORKFLOW_STALE_MAX_AGE_SECONDS",
        DEFAULT_WORKFLOW_STALE_MAX_AGE_SECONDS,
    )
    workflow_reconcile_interval_seconds = _positive_int_from_env(
        "CHILI_WORKFLOW_RECONCILE_INTERVAL_SECONDS",
        DEFAULT_WORKFLOW_RECONCILE_INTERVAL_SECONDS,
    )
    last_workflow_reconcile_at: float | None = None
    recovery_replay_complete = False

    try:
        while not shutdown_event.is_set():
            try:
                if not recovery_replay_complete:
                    replayed_recovery_markers = (
                        deps.ingestion_service.replay_recovery_markers()
                    )
                    recovery_replay_complete = True
                    if replayed_recovery_markers:
                        logger.info(
                            "Replayed %s ingestion recovery marker(s)",
                            replayed_recovery_markers,
                        )
                now_monotonic = time.monotonic()
                should_reconcile_workflows = (
                    stale_workflow_max_age_seconds > 0
                    and workflow_reconcile_interval_seconds > 0
                    and (
                        last_workflow_reconcile_at is None
                        or now_monotonic - last_workflow_reconcile_at
                        >= workflow_reconcile_interval_seconds
                    )
                )
                if should_reconcile_workflows:
                    reconciled = deps.workflow_tracker.reconcile_stale_runs(
                        max_age_seconds=stale_workflow_max_age_seconds
                    )
                    last_workflow_reconcile_at = now_monotonic
                    if reconciled:
                        logger.warning(
                            "Reconciled %s stale workflow run(s)", reconciled
                        )
                # Domain hot-swap: poll config.updated and, if the active
                # config changed, atomically swap the dependency set here —
                # between drain iterations, never mid-event.
                deps = apply_pending_config_updates(deps, state=config_reload_state)
                processed = await _drain_once(
                    deps,
                    policy=policy,
                    stage_policy_registry=stage_policy_registry,
                    health_state=health_state,
                )
                health_state.record_drain_success()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - resilience: never kill the worker
                # A transient error (e.g. Redis outage in consume/ack, or the
                # workflow reconcile) must not crash the worker process. Record
                # it for /health, back off so we don't hot-loop, and continue.
                health_state.record_drain_error(exc)
                logger.exception(
                    "Worker drain iteration failed; backing off %.1fs and continuing",
                    DRAIN_ERROR_BACKOFF_SECONDS,
                )
                await asyncio.sleep(DRAIN_ERROR_BACKOFF_SECONDS)
                continue
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


def _positive_int_from_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    value = int(raw)
    return value if value > 0 else 0


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
