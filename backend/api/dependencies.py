"""Dependency injection wiring for the FastAPI application."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import NoReturn, cast

from fastapi import Depends, Path, Request

from api.contracts import (
    AnalyticsOverviewResponse,
    CaseCreateRequest,
    CaseDetailResponse,
    CaseFeedbackCreateRequest,
    CaseListResponse,
    CaseUpdateRequest,
    ChatConversationCreateRequest,
    ChatConversationResponse,
    ChatMessageCreateRequest,
    EntityTimeseriesResponse,
    EvidencePackResponse,
    GraphEntityDetailResponse,
    PolicyBriefCreateRequest,
    PolicyBriefResponse,
    PolicyGapCaseListResponse,
    PolicyGapDetailResponse,
    PolicyGapListResponse,
    RiskScoreResponse,
)
from api.state import ApiState, create_api_state
from config.loader import load_config
from config.schema import (
    DatabaseConfig,
    DomainConfig,
    EmbeddingsConfig,
    EventBusConfig,
    GraphDbConfig,
    LlmConfig,
    MonitoringConfig,
    ObjectStoreConfig,
    RecordsConfig,
    VectorStoreConfig,
)
from embeddings.adapters.in_memory import InMemoryEmbedder
from embeddings.adapters.protocols import EmbedderProtocol
from embeddings.protocols import EmbeddingsServiceProtocol
from embeddings.service import create_embeddings_service
from events.protocols import EventBus
from events.runtime import EventBusSettings, create_event_bus, load_event_bus_settings
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.adapters.protocols import GraphRepository
from graph.auth import resolve_graph_auth
from graph.protocols import GraphServiceProtocol
from graph.service import create_graph_service
from ingestion.orchestrators.parser import DocumentParsingOrchestrator
from ingestion.parsers.registry import ParserRegistry, create_default_registry
from ingestion.parsers.remote import HttpxRemoteDocumentFetcher
from ingestion.service import IngestionService
from llm.adapters.in_memory import InMemoryLlmClient
from llm.adapters.protocols import LlmClientProtocol
from llm.protocols import LlmServiceProtocol
from llm.service import create_llm_service
from monitoring.adapters.in_memory import InMemoryObservationSource
from monitoring.adapters.postgres import PostgresObservationSource
from monitoring.adapters.protocols import ObservationSourceProtocol
from monitoring.protocols import MonitoringServiceProtocol
from monitoring.service import create_monitoring_service
from database.protocols import ConnectionProvider
from database.runtime import create_connection_provider
from records.adapters.in_memory import InMemoryRawRecordStore
from records.adapters.postgres import PostgresRawRecordStore
from records.adapters.protocols import RawRecordStore
from records.protocols import RecordsServiceProtocol
from records.service import create_records_service
from shared.exceptions import ConfigurationError
from storage.adapters.in_memory import InMemoryObjectStore
from storage.adapters.local_fs_adapter import LocalFsObjectStore
from storage.protocols import ObjectStore
from vectorstore.adapters.in_memory import InMemoryVectorStore
from vectorstore.adapters.protocols import VectorStoreProtocol
from vectorstore.protocols import VectorServiceProtocol
from vectorstore.service import create_vector_service

__all__ = [
    "get_api_state",
    "get_alert_repository",
    "get_agent_service",
    "get_analytics_overview_payload",
    "get_case_create_payload",
    "get_case_detail_payload",
    "get_case_feedback_payload",
    "get_case_list_payload",
    "get_case_update_payload",
    "get_chat_conversation_create_payload",
    "get_chat_conversation_payload",
    "get_chat_message_payload",
    "get_embedder",
    "get_embeddings_service",
    "get_domain_config",
    "get_domain_config_features_payload",
    "get_domain_config_payload",
    "get_domain_config_schema_payload",
    "get_evidence_pack_payload",
    "get_event_bus",
    "get_event_bus_settings",
    "get_graph_entity_detail_payload",
    "get_ingestion_service",
    "get_graph_repository",
    "get_graph_service",
    "get_connection_provider",
    "get_raw_record_store",
    "get_records_service",
    "get_knowledge_base_repository",
    "get_llm_client",
    "get_llm_service",
    "get_monitoring_service",
    "get_monitoring_source",
    "get_object_store",
    "get_parser_orchestrator",
    "get_parser_registry",
    "get_policy_brief_payload",
    "get_policy_gap_cases_payload",
    "get_policy_gap_detail_payload",
    "get_policy_gap_list_payload",
    "get_remote_fetcher",
    "get_risk_score_payload",
    "get_timeseries_payload",
    "get_session_store",
    "get_vector_store",
    "get_vectorstore_service",
    "get_workflow_run_store",
]


def _raise_unsupported_backend(
    subsystem: str,
    backend: str,
    available_backends: tuple[str, ...],
) -> NoReturn:
    available = ", ".join(available_backends)
    raise ConfigurationError(
        f"Unsupported {subsystem} backend '{backend}'. Available backends: {available}."
    )


def get_api_state(request: Request) -> ApiState:
    """Return the per-app seeded mutable API state.

    State is attached to ``app.state`` in :func:`api.app.create_app`, giving
    each TestClient (and each production process) its own ``ApiState``
    instance. Mutations made via one request do not leak into a fresh app
    instance — important for test isolation.
    """
    state = getattr(request.app.state, "api_state", None)
    if state is None:
        state = create_api_state(get_domain_config())
        request.app.state.api_state = state
    return state


def get_graph_entity_detail_payload(
    entity_id: str = Path(..., description="Entity identifier."),
    state: ApiState = Depends(get_api_state),
) -> GraphEntityDetailResponse:
    """Return one deterministic graph entity read model."""
    return state.get_graph_entity_detail(entity_id)


def get_evidence_pack_payload(
    evidence_pack_id: str = Path(..., description="Evidence pack identifier."),
    state: ApiState = Depends(get_api_state),
) -> EvidencePackResponse:
    """Return one deterministic evidence pack read model."""
    return state.get_evidence_pack(evidence_pack_id)


def get_case_list_payload(state: ApiState = Depends(get_api_state)) -> CaseListResponse:
    """Return a deterministic case queue read model."""
    return state.list_cases()


def get_case_detail_payload(
    case_id: str = Path(..., description="Case identifier."),
    state: ApiState = Depends(get_api_state),
) -> CaseDetailResponse:
    """Return one deterministic case detail read model."""
    return state.get_case_detail(case_id)


def get_case_create_payload(
    payload: CaseCreateRequest,
    state: ApiState = Depends(get_api_state),
) -> CaseDetailResponse:
    """Create and return a persisted case."""
    return state.create_case(payload)


def get_case_update_payload(
    payload: CaseUpdateRequest,
    case_id: str = Path(..., description="Case identifier."),
    state: ApiState = Depends(get_api_state),
) -> CaseDetailResponse:
    """Update and return a persisted case."""
    return state.update_case(case_id, payload)


def get_case_feedback_payload(
    payload: CaseFeedbackCreateRequest,
    case_id: str = Path(..., description="Case identifier."),
    state: ApiState = Depends(get_api_state),
) -> CaseDetailResponse:
    """Append feedback and return the updated case detail."""
    return state.add_feedback(case_id, payload)


def get_chat_conversation_payload(
    conversation_id: str = Path(..., description="Conversation identifier."),
    state: ApiState = Depends(get_api_state),
) -> ChatConversationResponse:
    """Return a deterministic chat conversation read model."""
    return state.get_conversation(conversation_id)


def get_chat_conversation_create_payload(
    payload: ChatConversationCreateRequest,
    state: ApiState = Depends(get_api_state),
) -> ChatConversationResponse:
    """Create and return a new conversation."""
    return state.create_conversation(payload)


def get_chat_message_payload(
    payload: ChatMessageCreateRequest,
    conversation_id: str = Path(..., description="Conversation identifier."),
    state: ApiState = Depends(get_api_state),
) -> ChatConversationResponse:
    """Append a message and return the updated conversation."""
    return state.add_message(conversation_id, payload)


def get_policy_gap_list_payload(
    state: ApiState = Depends(get_api_state),
) -> PolicyGapListResponse:
    """Return the policy intelligence gap queue."""
    return state.list_policy_gaps()


def get_policy_gap_detail_payload(
    gap_id: str = Path(..., description="Policy gap identifier."),
    state: ApiState = Depends(get_api_state),
) -> PolicyGapDetailResponse:
    """Return one policy gap detail payload."""
    return state.get_policy_gap_detail(gap_id)


def get_policy_gap_cases_payload(
    gap_id: str = Path(..., description="Policy gap identifier."),
    state: ApiState = Depends(get_api_state),
) -> PolicyGapCaseListResponse:
    """Return the affected cases for one policy gap."""
    return state.list_policy_gap_cases(gap_id)


def get_policy_brief_payload(
    payload: PolicyBriefCreateRequest,
    state: ApiState = Depends(get_api_state),
) -> PolicyBriefResponse:
    """Generate a policy brief for the supplied policy gap."""
    return state.create_policy_brief(payload)


def get_risk_score_payload(
    entity_id: str = Path(..., description="Entity identifier."),
    state: ApiState = Depends(get_api_state),
) -> RiskScoreResponse:
    """Return a deterministic risk-score payload."""
    return state.get_risk_score(entity_id)


def get_timeseries_payload(
    entity_id: str = Path(..., description="Entity identifier."),
    state: ApiState = Depends(get_api_state),
) -> EntityTimeseriesResponse:
    """Return a deterministic timeseries payload."""
    return state.get_timeseries(entity_id)


def get_analytics_overview_payload(
    state: ApiState = Depends(get_api_state),
) -> AnalyticsOverviewResponse:
    """Return a deterministic analytics overview payload."""
    return state.get_analytics_overview()


@lru_cache(maxsize=1)
def get_domain_config() -> DomainConfig:
    """Load and cache the domain configuration (process-singleton).

    The cache is cleared at the start of :func:`api.app.create_app` so each
    test that builds a fresh app picks up the current ``CHILI_CONFIG_PATH``
    or ``api.app.load_config`` patch. Tests that need to inject a specific
    config can also override via ``app.dependency_overrides``.
    """
    return load_config()


def get_domain_config_payload(
    config: DomainConfig = Depends(get_domain_config),
) -> dict[str, object]:
    """Return the active domain configuration as a plain mapping."""
    return cast(dict[str, object], config.model_dump())


def get_domain_config_features_payload(
    config: DomainConfig = Depends(get_domain_config),
) -> dict[str, object]:
    """Return frontend-oriented feature flags derived from the domain config."""
    enabled_pages = [
        page.id
        for page in (config.ui.navigation.pages if config.ui and config.ui.navigation else [])
        if page.capability is None or bool(getattr(config.capabilities, page.capability, False))
    ]
    return {
        "capabilities": config.capabilities.model_dump(),
        "default_entity_type": config.ui.default_entity_type if config.ui else None,
        "default_role": next(iter(config.ui.roles.keys())) if config.ui and config.ui.roles else None,
        "enabled_pages": enabled_pages,
        "roles": config.ui.roles if config.ui else {},
    }


def get_domain_config_schema_payload(
    config: DomainConfig = Depends(get_domain_config),
) -> dict[str, object]:
    """Return the JSON schema for the active domain configuration model."""
    return cast(dict[str, object], config.__class__.model_json_schema())


@lru_cache(maxsize=1)
def get_parser_registry() -> ParserRegistry:
    """Return the default parser registry."""
    return create_default_registry()


@lru_cache(maxsize=1)
def get_remote_fetcher() -> HttpxRemoteDocumentFetcher:
    """Return the default remote fetcher for HTTPS documents."""
    return HttpxRemoteDocumentFetcher()


@lru_cache(maxsize=1)
def get_parser_orchestrator() -> DocumentParsingOrchestrator:
    """Return the parser orchestrator assembled from default dependencies."""
    return DocumentParsingOrchestrator(
        get_parser_registry(),
        fetcher=get_remote_fetcher(),
    )


@lru_cache(maxsize=1)
def get_event_bus_settings() -> EventBusSettings:
    """Return the runtime event transport settings."""
    return load_event_bus_settings()


def _event_bus_section_is_explicit(config: DomainConfig) -> bool:
    return "events" in config.model_fields_set


def _config_section_is_non_default(value: object, default: object) -> bool:
    """Return whether a post-validated config section differs from defaults."""

    return value != default


def _resolve_event_bus_settings(config: DomainConfig) -> EventBusSettings:
    env_settings = get_event_bus_settings()
    if not _event_bus_section_is_explicit(config):
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
    )


@lru_cache(maxsize=1)
def get_event_bus() -> EventBus:
    """Return the event bus implementation for API-triggered workflows."""
    config = get_domain_config()
    settings = _resolve_event_bus_settings(config)
    return create_event_bus(settings)


@lru_cache(maxsize=1)
def get_session_store() -> SessionStoreProtocol:
    """Return the configured session store.

    Uses InMemorySessionStore when AuthConfig.enabled is False, otherwise
    requires REDIS_URL and returns RedisSessionStore.
    """

    config = get_domain_config()
    auth = config.auth
    if auth is None or not auth.enabled:
        return InMemorySessionStore()

    redis_url = os.environ.get("REDIS_URL")
    if redis_url is None:
        raise ConfigurationError(
            "AuthConfig.enabled=True requires REDIS_URL to be set "
            "(e.g. REDIS_URL=redis://redis:6379/0)."
        )
    return RedisSessionStore(redis_url=redis_url)


@lru_cache(maxsize=1)
def get_object_store() -> ObjectStore:
    """Return the object store implementation for raw document content."""
    config = get_domain_config()
    storage_config = config.storage or ObjectStoreConfig()
    backend = storage_config.backend
    if backend == "local":
        if _config_section_is_non_default(storage_config, ObjectStoreConfig()):
            return LocalFsObjectStore(storage_config)
        return InMemoryObjectStore()
    if backend in {"s3", "minio"}:
        try:
            from storage.adapters.s3_adapter import S3ObjectStore
        except ImportError as exc:
            raise ConfigurationError(str(exc)) from exc
        try:
            return S3ObjectStore(storage_config)
        except (ImportError, ValueError) as exc:
            raise ConfigurationError(str(exc)) from exc
    _raise_unsupported_backend("storage", backend, ("local", "s3", "minio"))


@lru_cache(maxsize=1)
def get_graph_repository() -> GraphRepository:
    """Return the graph repository implementation selected by config."""
    graph_config = get_domain_config().graph or GraphDbConfig()
    backend = graph_config.backend
    if backend == "in_memory":
        return InMemoryGraphRepository()
    if backend == "neo4j":
        try:
            from graph.adapters.neo4j_adapter import Neo4jGraphRepository
        except ImportError as exc:
            raise ConfigurationError(str(exc)) from exc
        try:
            return Neo4jGraphRepository(
                graph_config,
                auth=resolve_graph_auth(graph_config),
            )
        except (ImportError, ValueError) as exc:
            raise ConfigurationError(str(exc)) from exc
    _raise_unsupported_backend("graph", backend, ("in_memory", "neo4j"))


@lru_cache(maxsize=1)
def get_graph_service() -> GraphServiceProtocol:
    """Return the graph service assembled from configured dependencies."""
    return create_graph_service(
        get_graph_repository(),
        object_store=get_object_store(),
        event_bus=get_event_bus(),
    )


@lru_cache(maxsize=1)
def get_vector_store() -> VectorStoreProtocol:
    """Return the vector store adapter implementation selected by config."""
    vectorstore_config = get_domain_config().vectorstore or VectorStoreConfig()
    backend = vectorstore_config.backend
    if backend == "in_memory":
        return InMemoryVectorStore()
    if backend == "qdrant":
        try:
            from vectorstore.adapters.qdrant_adapter import QdrantVectorStore
        except ImportError as exc:
            raise ConfigurationError(str(exc)) from exc
        try:
            return QdrantVectorStore(vectorstore_config)
        except (ImportError, ValueError) as exc:
            raise ConfigurationError(str(exc)) from exc
    _raise_unsupported_backend("vectorstore", backend, ("in_memory", "qdrant"))


@lru_cache(maxsize=1)
def get_vectorstore_service() -> VectorServiceProtocol:
    """Return the vectorstore service assembled from configured dependencies."""
    return create_vector_service(get_vector_store(), event_bus=get_event_bus())


@lru_cache(maxsize=1)
def get_embedder() -> EmbedderProtocol:
    """Return the embeddings adapter implementation selected by config."""
    config = get_domain_config()
    embeddings_config = config.embeddings or EmbeddingsConfig()
    provider = embeddings_config.provider
    if embeddings_config == EmbeddingsConfig():
        return InMemoryEmbedder(provider=provider)
    if provider == "local":
        return InMemoryEmbedder(provider=provider)
    if provider == "sentence_transformers":
        try:
            from embeddings.adapters.sentence_transformers_adapter import (
                SentenceTransformersEmbedder,
            )
        except ImportError as exc:
            raise ConfigurationError(str(exc)) from exc
        try:
            return SentenceTransformersEmbedder(embeddings_config)
        except (ImportError, ValueError) as exc:
            raise ConfigurationError(str(exc)) from exc
    if provider == "openai":
        try:
            from embeddings.adapters.openai_adapter import OpenAIEmbedder
            from embeddings.exceptions import EmbeddingConfigurationError
        except ImportError as exc:
            raise ConfigurationError(str(exc)) from exc
        try:
            return OpenAIEmbedder(embeddings_config)
        except (ImportError, ValueError, EmbeddingConfigurationError) as exc:
            raise ConfigurationError(str(exc)) from exc
    _raise_unsupported_backend(
        "embeddings",
        provider,
        ("local", "sentence_transformers", "openai"),
    )


@lru_cache(maxsize=1)
def get_embeddings_service() -> EmbeddingsServiceProtocol:
    """Return the embeddings service assembled from configured dependencies."""
    return create_embeddings_service(get_embedder(), event_bus=get_event_bus())


@lru_cache(maxsize=1)
def get_llm_client() -> LlmClientProtocol:
    """Return the llm client implementation selected by config."""
    llm_config = get_domain_config().llm or LlmConfig()
    provider = llm_config.provider
    if provider == "local":
        return InMemoryLlmClient(provider=provider)
    if provider == "openai":
        try:
            from llm.adapters.openai_adapter import OpenAILlmClient
            from llm.exceptions import LlmConfigurationError
        except ImportError as exc:
            raise ConfigurationError(str(exc)) from exc
        try:
            return OpenAILlmClient(llm_config)
        except (ImportError, ValueError, LlmConfigurationError) as exc:
            raise ConfigurationError(str(exc)) from exc
    if provider == "anthropic":
        try:
            from llm.adapters.anthropic_adapter import AnthropicLlmClient
            from llm.exceptions import LlmConfigurationError
        except ImportError as exc:
            raise ConfigurationError(str(exc)) from exc
        try:
            return AnthropicLlmClient(llm_config)
        except (ImportError, ValueError, LlmConfigurationError) as exc:
            raise ConfigurationError(str(exc)) from exc
    _raise_unsupported_backend("llm", provider, ("local", "openai", "anthropic"))


@lru_cache(maxsize=1)
def get_llm_service() -> LlmServiceProtocol:
    """Return the llm service assembled from configured dependencies."""
    return create_llm_service(get_llm_client(), event_bus=get_event_bus())


@lru_cache(maxsize=1)
def get_monitoring_source() -> ObservationSourceProtocol:
    """Return the monitoring observation source selected by the database backend."""
    provider = get_connection_provider()
    if provider is None:
        return InMemoryObservationSource()
    return PostgresObservationSource(provider)


@lru_cache(maxsize=1)
def get_monitoring_service() -> MonitoringServiceProtocol:
    """Return the monitoring service assembled from configured dependencies."""
    monitoring_config = get_domain_config().monitoring or MonitoringConfig()
    return create_monitoring_service(
        get_monitoring_source(),
        event_bus=get_event_bus(),
        dedup_window_seconds=monitoring_config.dedup_window_seconds,
        max_alerts_per_evaluation=monitoring_config.max_alerts_per_evaluation,
        grouping_window_seconds=monitoring_config.grouping_window_seconds,
    )


@lru_cache(maxsize=1)
def get_ingestion_service() -> IngestionService:
    """Return the ingestion service used by API routes and tests."""
    return IngestionService(
        get_parser_orchestrator(),
        object_store=get_object_store(),
        event_bus=get_event_bus(),
    )


@lru_cache(maxsize=1)
def get_connection_provider() -> ConnectionProvider | None:
    """Return the database connection provider, or None for the in-memory backend."""
    config = get_domain_config()
    return create_connection_provider(config.database or DatabaseConfig())


@lru_cache(maxsize=1)
def get_raw_record_store() -> RawRecordStore:
    """Return the raw record store selected by the configured database backend."""
    provider = get_connection_provider()
    if provider is None:
        return InMemoryRawRecordStore()
    return PostgresRawRecordStore(provider)


def get_records_service(
    event_bus: EventBus = Depends(get_event_bus),
    store: RawRecordStore = Depends(get_raw_record_store),
    config: DomainConfig = Depends(get_domain_config),
) -> RecordsServiceProtocol:
    """Return the records ingestion service assembled from configured dependencies."""
    return create_records_service(
        store,
        event_bus=event_bus,
        records_config=config.records or RecordsConfig(),
    )


from api._alert_store import (  # noqa: E402  (intentional bottom-of-file import)
    AlertProjectionRepository,
    InMemoryAlertProjectionRepository,
    ObjectStoreAlertProjectionRepository,
)
from agent.adapters.protocols import (  # noqa: E402  (intentional bottom-of-file import)
    WorkflowRunStoreProtocol,
)
from agent.adapters.runtime import create_workflow_run_store_from_env  # noqa: E402
from agent.protocols import AgentServiceProtocol  # noqa: E402
from agent.service import create_agent_service  # noqa: E402
from api._kb_store import (  # noqa: E402  (intentional bottom-of-file import)
    InMemoryKnowledgeBaseRepository,
    KnowledgeBaseRepository,
    ObjectStoreKnowledgeBaseRepository,
)
from api.middleware.session_store import (  # noqa: E402  (intentional bottom-of-file import)
    InMemorySessionStore,
    RedisSessionStore,
    SessionStoreProtocol,
)


@lru_cache(maxsize=1)
def get_knowledge_base_repository() -> KnowledgeBaseRepository:
    """Return the knowledge base metadata repository used by the KB router."""
    backend = os.environ.get("CHILI_KB_REPOSITORY_BACKEND", "in_memory").strip().lower()
    if backend in {"in_memory", "memory"}:
        return InMemoryKnowledgeBaseRepository()
    if backend in {"object_store", "object-store", "objectstore"}:
        return ObjectStoreKnowledgeBaseRepository(get_object_store())
    _raise_unsupported_backend(
        "knowledge base repository",
        backend,
        ("in_memory", "object_store"),
    )


def get_alert_repository(request: Request) -> AlertProjectionRepository:
    """Return the per-app alert projection repository used by alert routes."""
    repository = getattr(request.app.state, "alert_repository", None)
    if isinstance(repository, AlertProjectionRepository):
        return repository

    repository = _create_alert_repository()
    request.app.state.alert_repository = repository
    return repository


def _create_alert_repository() -> AlertProjectionRepository:
    """Create the alert projection repository selected by environment."""
    backend = os.environ.get("CHILI_ALERT_REPOSITORY_BACKEND", "in_memory").strip().lower()
    if backend in {"in_memory", "memory"}:
        return InMemoryAlertProjectionRepository()
    if backend in {"object_store", "object-store", "objectstore"}:
        return ObjectStoreAlertProjectionRepository(get_object_store())
    _raise_unsupported_backend(
        "alert repository",
        backend,
        ("in_memory", "object_store"),
    )


def get_workflow_run_store(request: Request) -> WorkflowRunStoreProtocol:
    """Return the per-app workflow run store used by agent services."""
    store = getattr(request.app.state, "workflow_run_store", None)
    if isinstance(store, WorkflowRunStoreProtocol):
        return store

    store = _create_workflow_run_store()
    request.app.state.workflow_run_store = store
    return store


def _create_workflow_run_store() -> WorkflowRunStoreProtocol:
    """Create the workflow run store selected by environment."""
    return create_workflow_run_store_from_env()


def get_agent_service(
    run_store: WorkflowRunStoreProtocol = Depends(get_workflow_run_store),
    event_bus: EventBus = Depends(get_event_bus),
) -> AgentServiceProtocol:
    """Return the agent workflow service assembled from configured dependencies."""
    return create_agent_service(run_store, event_bus=event_bus)
