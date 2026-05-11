"""Dependency injection wiring for the FastAPI application."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import NoReturn, cast

from fastapi import Depends, Path, Request

from api.contracts import (
    AlertDetailResponse,
    AlertListResponse,
    AnalyticsOverviewResponse,
    ApiEnvelope,
    CaseCreateRequest,
    CaseDetailResponse,
    CaseFeedbackCreateRequest,
    CaseListResponse,
    CaseUpdateRequest,
    ChatConversationCreateRequest,
    ChatConversationResponse,
    ChatMessageCreateRequest,
    EvidencePackResponse,
    GraphEntityDetailResponse,
    KnowledgeBaseCreateRequest,
    KnowledgeBaseDocumentListResponse,
    KnowledgeBaseListResponse,
    KnowledgeBaseSummaryResponse,
    PolicyBriefCreateRequest,
    PolicyBriefResponse,
    PolicyGapCaseListResponse,
    PolicyGapDetailResponse,
    PolicyGapListResponse,
    RiskScoreResponse,
    TimeseriesResponse,
    WorkflowRunListResponse,
    WorkflowRunResponse,
)
from api.state import ApiState, create_api_state
from config.loader import load_config
from config.schema import (
    DomainConfig,
    EmbeddingsConfig,
    EventBusConfig,
    GraphDbConfig,
    LlmConfig,
    MonitoringConfig,
    ObjectStoreConfig,
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
from monitoring.adapters.protocols import ObservationSourceProtocol
from monitoring.protocols import MonitoringServiceProtocol
from monitoring.service import create_monitoring_service
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
    "get_alert_detail_payload",
    "get_alert_list_payload",
    "get_alert_mutation_payload",
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
    "get_knowledge_base_create_payload",
    "get_knowledge_base_delete_payload",
    "get_knowledge_base_detail_payload",
    "get_knowledge_base_document_delete_payload",
    "get_knowledge_base_documents_payload",
    "get_knowledge_base_list_payload",
    "get_graph_repository",
    "get_graph_service",
    "get_ingestion_service",
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
    "get_workflow_runs_payload",
    "get_session_store",
    "get_vector_store",
    "get_vectorstore_service",
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
        state = create_api_state()
        request.app.state.api_state = state
    return state


def get_alert_list_payload(state: ApiState = Depends(get_api_state)) -> AlertListResponse:
    """Return the alert feed read model."""
    return state.list_alerts()


def get_alert_detail_payload(
    alert_id: str = Path(..., description="Alert identifier."),
    state: ApiState = Depends(get_api_state),
) -> AlertDetailResponse:
    """Return one deterministic alert detail read model."""
    return state.get_alert_detail(alert_id)


def get_alert_mutation_payload(
    alert_id: str = Path(..., description="Alert identifier."),
    state: ApiState = Depends(get_api_state),
) -> ApiEnvelope:
    """Return the scaffold acknowledgement response."""
    updated = state.acknowledge_alert(alert_id)
    return ApiEnvelope(status="accepted", message=f"Alert '{updated.id}' is now {updated.status}.")


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


def get_knowledge_base_list_payload(
    state: ApiState = Depends(get_api_state),
) -> KnowledgeBaseListResponse:
    """Return the knowledge base manager collection payload."""
    return state.list_knowledge_bases()


def get_knowledge_base_detail_payload(
    knowledge_base_id: str = Path(..., description="Knowledge base identifier."),
    state: ApiState = Depends(get_api_state),
) -> KnowledgeBaseSummaryResponse:
    """Return one knowledge base detail payload."""
    return state.get_knowledge_base_detail(knowledge_base_id)


def get_knowledge_base_create_payload(
    payload: KnowledgeBaseCreateRequest,
    state: ApiState = Depends(get_api_state),
) -> KnowledgeBaseSummaryResponse:
    """Create and return a new knowledge base."""
    return state.create_knowledge_base(payload)


def get_knowledge_base_delete_payload(
    knowledge_base_id: str = Path(..., description="Knowledge base identifier."),
    state: ApiState = Depends(get_api_state),
) -> ApiEnvelope:
    """Delete a knowledge base and return an acknowledgement envelope."""
    state.delete_knowledge_base(knowledge_base_id)
    return ApiEnvelope(status="accepted", message=f"Knowledge base '{knowledge_base_id}' queued for deletion.")


def get_knowledge_base_documents_payload(
    knowledge_base_id: str = Path(..., description="Knowledge base identifier."),
    state: ApiState = Depends(get_api_state),
) -> KnowledgeBaseDocumentListResponse:
    """Return the document inventory for one knowledge base."""
    return state.list_knowledge_base_documents(knowledge_base_id)


def get_knowledge_base_document_delete_payload(
    knowledge_base_id: str = Path(..., description="Knowledge base identifier."),
    document_id: str = Path(..., description="Knowledge base document identifier."),
    state: ApiState = Depends(get_api_state),
) -> ApiEnvelope:
    """Delete a document and return an acknowledgement envelope."""
    state.delete_knowledge_base_document(knowledge_base_id, document_id)
    return ApiEnvelope(status="accepted", message=f"Document '{document_id}' removed from knowledge base '{knowledge_base_id}'.")


def get_knowledge_base_rebuild_payload(
    knowledge_base_id: str = Path(..., description="Knowledge base identifier."),
    state: ApiState = Depends(get_api_state),
) -> WorkflowRunResponse:
    """Queue a knowledge base rebuild and return the resulting workflow record."""
    return state.rebuild_knowledge_base(knowledge_base_id)


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


def get_workflow_runs_payload(state: ApiState = Depends(get_api_state)) -> WorkflowRunListResponse:
    """Return recent scaffold workflow runs."""
    return state.list_workflows()


def get_risk_score_payload(
    entity_id: str = Path(..., description="Entity identifier."),
    state: ApiState = Depends(get_api_state),
) -> RiskScoreResponse:
    """Return a deterministic risk-score payload."""
    return state.get_risk_score(entity_id)


def get_timeseries_payload(
    entity_id: str = Path(..., description="Entity identifier."),
    state: ApiState = Depends(get_api_state),
) -> TimeseriesResponse:
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
                auth=_resolve_graph_auth(graph_config),
            )
        except (ImportError, ValueError) as exc:
            raise ConfigurationError(str(exc)) from exc
    _raise_unsupported_backend("graph", backend, ("in_memory", "neo4j"))


def _resolve_graph_auth(config: GraphDbConfig) -> tuple[str, str] | None:
    """Resolve optional graph credentials from the configured environment variable."""

    if config.auth_env_var is None:
        return None
    raw_value = os.environ.get(config.auth_env_var)
    if raw_value is None or raw_value.strip() == "":
        return None
    if ":" in raw_value:
        username, password = raw_value.split(":", 1)
        return username, password
    return "neo4j", raw_value


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
    """Return the monitoring observation source selected by config."""
    _ = get_domain_config().monitoring or MonitoringConfig()
    return InMemoryObservationSource()


@lru_cache(maxsize=1)
def get_monitoring_service() -> MonitoringServiceProtocol:
    """Return the monitoring service assembled from configured dependencies."""
    return create_monitoring_service(get_monitoring_source(), event_bus=get_event_bus())


@lru_cache(maxsize=1)
def get_ingestion_service() -> IngestionService:
    """Return the ingestion service used by API routes and tests."""
    return IngestionService(
        get_parser_orchestrator(),
        object_store=get_object_store(),
        event_bus=get_event_bus(),
    )


# --- Knowledgebases router additions (E5-S11/S12/S13) -------------------------
# Keep this block at the end of the module so parallel router agents can append
# their own DI factories without merge conflicts.

from api._kb_store import (  # noqa: E402  (intentional bottom-of-file import)
    InMemoryKnowledgeBaseRepository,
    KnowledgeBaseRepository,
)
from api.middleware.session_store import (  # noqa: E402  (intentional bottom-of-file import)
    InMemorySessionStore,
    RedisSessionStore,
    SessionStoreProtocol,
)


@lru_cache(maxsize=1)
def get_knowledge_base_repository() -> KnowledgeBaseRepository:
    """Return the knowledge base metadata repository used by the KB router."""
    return InMemoryKnowledgeBaseRepository()
