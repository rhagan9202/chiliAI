"""Dependency injection wiring for the FastAPI application."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import NoReturn, cast

from fastapi import Depends, HTTPException, Path, Query, Request

from api.contracts import (
    AnalystFeedbackResponse,
    AnalyticsOverviewResponse,
    CaseCreateRequest,
    CaseDetailResponse,
    CaseFeedbackCreateRequest,
    CaseListResponse,
    CasePromoteRequest,
    CaseSummaryResponse,
    CaseTimelineEventResponse,
    CaseUpdateRequest,
    ChatConversationCreateRequest,
    ChatConversationResponse,
    ChatMessageCreateRequest,
    EntityTimeseriesResponse,
    EvidencePackResponse,
    GraphEntityDetailResponse,
    PageInfo,
    PolicyCitationResponse,
    PolicyDispositionResponse,
    PolicyItemDetailResponse,
    PolicyItemListResponse,
    PolicyItemSummaryResponse,
    PolicyTriageRequest,
    RiskScoreResponse,
)
from api._analytics_overview import build_analytics_overview
from api._graph_entity_payload import build_graph_entity_detail
from api._conversation_payloads import (
    build_assistant_message,
    build_user_message,
    project_conversation,
)
from cases.adapters.in_memory import InMemoryCaseRepository
from cases.adapters.postgres import PostgresCaseRepository
from cases.adapters.protocols import CaseRepository
from conversations.adapters.in_memory import InMemoryConversationRepository
from conversations.adapters.postgres import PostgresConversationRepository
from conversations.adapters.protocols import ConversationRepository
from conversations.service import ConversationService, create_conversation_service
from rag.service_models import RagQueryRequest
from shared.kb_scope import resolve_kb_scope
from cases.exceptions import CaseNotFoundError
from cases.models import Case, CasePriority, CaseTimelineEvent
from cases.service import CaseService, create_case_service
from policy.adapters.in_memory import InMemoryPolicyItemRepository
from policy.adapters.postgres import PostgresPolicyItemRepository
from policy.adapters.protocols import PolicyItemRepository
from policy.exceptions import (
    PolicyItemAlreadyTriagedError,
    PolicyItemNotFoundError,
)
from policy.models import PolicyItem
from policy.service import PolicyService, create_policy_service
from shared.utils import utc_now
from api.state import ApiState, create_api_state
from config.loader import load_config
from config.schema import (
    AnalyticsConfig,
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
from analytics.gnn.adapters.in_memory import InMemoryGraphSnapshotSource
from analytics.gnn.adapters.protocols import GraphSnapshotSourceProtocol
from analytics.gnn.protocols import GnnServiceProtocol
from analytics.gnn.service import create_gnn_service
from analytics.risk.adapters.in_memory import InMemoryRiskSignalSource
from analytics.risk.adapters.postgres import PostgresRiskSignalSource
from analytics.risk.adapters.protocols import RiskSignalSourceProtocol
from analytics.risk.protocols import RiskServiceProtocol
from analytics.risk.service import create_risk_service
from analytics.timeseries.adapters.in_memory import InMemoryTimeSeriesHistorySource
from analytics.timeseries.adapters.protocols import TimeSeriesHistorySourceProtocol
from analytics.timeseries.protocols import TimeseriesServiceProtocol
from analytics.timeseries.service import create_timeseries_service
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
from ingestion.recovery import InMemoryIngestionRecoveryStore
from ingestion.service import IngestionService
from llm.adapters.protocols import LlmClientProtocol
from llm.factory import create_llm_client
from llm.protocols import LlmServiceProtocol
from llm.service import create_llm_service
from monitoring.adapters.in_memory import InMemoryObservationSource
from monitoring.adapters.postgres import PostgresObservationSource
from monitoring.adapters.protocols import ObservationSourceProtocol
from monitoring.protocols import MonitoringServiceProtocol
from monitoring.service import create_monitoring_service
from database.protocols import ConnectionProvider
from database.runtime import create_connection_provider
from analytics.peerstats.adapters.in_memory import InMemoryDerivedRiskSignalWriter
from analytics.peerstats.adapters.postgres import PostgresDerivedRiskSignalWriter
from analytics.peerstats.adapters.protocols import DerivedRiskSignalWriterProtocol
from records.adapters.in_memory import InMemoryRawRecordStore
from records.adapters.postgres import PostgresRawRecordStore
from records.adapters.protocols import RawRecordStore
from analytics.explainability.adapters.evidence_object_store import (
    ObjectStoreEvidencePackRepository,
)
from analytics.explainability.repository import EvidencePackRepository
from records.protocols import RecordsServiceProtocol
from records.service import create_records_service
from shared.exceptions import ConfigurationError
from shared.types import EvidencePack
from storage.adapters.in_memory import InMemoryObjectStore
from storage.adapters.local_fs_adapter import LocalFsObjectStore
from storage.protocols import ObjectStore
from vectorstore.adapters.in_memory import InMemoryVectorStore
from vectorstore.adapters.protocols import VectorStoreProtocol
from vectorstore.protocols import VectorServiceProtocol
from vectorstore.service import create_vector_service

from api._rag_bridges import (
    ServiceAnswerGenerator,
    ServiceContextRetriever,
    ServiceGraphContextExpander,
    ServiceQueryEmbedder,
)
from rag.protocols import RagServiceProtocol
from rag.service import create_rag_service

__all__ = [
    "get_api_state",
    "get_alert_repository",
    "get_agent_service",
    "get_analytics_overview_payload",
    "get_case_create_payload",
    "get_case_detail_payload",
    "get_case_feedback_payload",
    "get_case_list_payload",
    "get_case_promote_payload",
    "get_case_repository",
    "get_case_service",
    "get_case_update_payload",
    "get_chat_conversation_create_payload",
    "get_chat_conversation_payload",
    "get_chat_message_payload",
    "get_conversation_repository",
    "get_conversation_service",
    "get_embedder",
    "get_embeddings_service",
    "get_domain_config",
    "get_domain_config_features_payload",
    "get_domain_config_payload",
    "get_domain_config_schema_payload",
    "get_evidence_pack_payload",
    "get_evidence_pack_repository",
    "get_event_bus",
    "get_event_bus_settings",
    "get_graph_entity_detail_payload",
    "get_ingestion_recovery_store",
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
    "get_policy_item_detail_payload",
    "get_policy_item_list_payload",
    "get_policy_repository",
    "get_policy_service",
    "get_remote_fetcher",
    "get_risk_score_payload",
    "get_timeseries_payload",
    "get_session_store",
    "get_vector_service",
    "get_vector_store",
    "get_vectorstore_service",
    "get_workflow_run_store",
    "get_workflow_tracker",
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


def get_evidence_pack_repository(request: Request) -> EvidencePackRepository:
    """Return the per-app evidence-pack repository used by the evidence route.

    Reads packs the worker persisted to the shared object store (BL-005).
    """
    repository = getattr(request.app.state, "evidence_pack_repository", None)
    if isinstance(repository, EvidencePackRepository):
        return repository

    repository = ObjectStoreEvidencePackRepository(get_object_store())
    request.app.state.evidence_pack_repository = repository
    return repository


def get_evidence_pack_payload(
    evidence_pack_id: str = Path(..., description="Evidence pack identifier."),
    knowledge_base_id: str = Query(
        ..., min_length=1, description="Knowledge base the evidence pack belongs to."
    ),
    repository: EvidencePackRepository = Depends(get_evidence_pack_repository),
) -> EvidencePackResponse:
    """Return one evidence pack read model from the persisted repository (BL-005)."""
    pack = repository.get(knowledge_base_id, evidence_pack_id)
    if pack is None:
        raise HTTPException(status_code=404, detail="Evidence pack not found.")
    return _evidence_pack_to_response(pack)


def _evidence_pack_to_response(pack: EvidencePack) -> EvidencePackResponse:
    """Map a persisted EvidencePack to the frontend read model.

    The persisted pack stores subgraph id-lists + a score snapshot; ``items`` and
    ``policy_citations`` are not persisted on the pack and default to empty.
    """
    return EvidencePackResponse(
        id=pack.id,
        alert_id=pack.alert_id,
        reasoning=pack.reasoning,
        confidence=pack.confidence,
        scores=dict(pack.scores),
        subgraph_node_ids=list(pack.subgraph_nodes),
        subgraph_edge_ids=list(pack.subgraph_edges),
    )


def get_case_repository(request: Request) -> CaseRepository:
    """Return the per-app durable case repository selected by config (BL-010).

    Postgres when a connection provider is configured, otherwise a per-app
    in-memory repository (so each app instance is isolated).
    """
    repository = getattr(request.app.state, "case_repository", None)
    if isinstance(repository, CaseRepository):
        return repository

    provider = get_connection_provider()
    repository = (
        InMemoryCaseRepository() if provider is None else PostgresCaseRepository(provider)
    )
    request.app.state.case_repository = repository
    return repository


def get_case_service(
    repository: CaseRepository = Depends(get_case_repository),
) -> CaseService:
    """Return the case service over the configured repository."""
    return create_case_service(repository)


def get_case_feedback_store(request: Request) -> dict[str, list[AnalystFeedbackResponse]]:
    """Return the per-app, in-memory analyst-feedback store.

    Feedback durability is out of scope for BL-010; it is kept ephemeral per app
    instance, decoupled from the durable case repository.
    """
    store = getattr(request.app.state, "case_feedback", None)
    if isinstance(store, dict):
        return cast(dict[str, list[AnalystFeedbackResponse]], store)
    new_store: dict[str, list[AnalystFeedbackResponse]] = {}
    request.app.state.case_feedback = new_store
    return new_store


def _case_to_summary(case: Case) -> CaseSummaryResponse:
    return CaseSummaryResponse(
        id=case.id,
        knowledge_base_id=case.knowledge_base_id,
        title=case.title,
        status=case.status,
        priority=case.priority,
        assignee=case.assignee,
        originating_alert_id=case.originating_alert_id,
        evidence_pack_id=case.evidence_pack_id,
        alert_ids=list(case.alert_ids),
        updated_at=case.updated_at,
    )


def _assemble_case_detail(
    case: Case,
    *,
    evidence_repository: EvidencePackRepository,
    feedback_store: dict[str, list[AnalystFeedbackResponse]],
) -> CaseDetailResponse:
    evidence_pack: EvidencePackResponse | None = None
    if case.evidence_pack_id:
        pack = evidence_repository.get(case.knowledge_base_id, case.evidence_pack_id)
        if pack is not None:
            evidence_pack = _evidence_pack_to_response(pack)
    return CaseDetailResponse(
        case=_case_to_summary(case),
        # Rich alert resolution on case detail is a follow-on; alert linkage is
        # preserved via CaseSummaryResponse.alert_ids.
        alerts=[],
        evidence_pack=evidence_pack,
        entity_timeline=[
            CaseTimelineEventResponse(
                occurred_at=event.occurred_at, label=event.label, detail=event.detail
            )
            for event in case.timeline
        ],
        feedback_history=list(feedback_store.get(case.id, [])),
    )


def get_case_list_payload(
    knowledge_base_id: str = Query(..., min_length=1, description="Knowledge base scope."),
    status: str | None = Query(default=None, description="Filter by case status."),
    priority: str | None = Query(default=None, description="Filter by case priority."),
    service: CaseService = Depends(get_case_service),
) -> CaseListResponse:
    """Return the KB-scoped case queue from the durable repository."""
    cases, total = service.list(
        knowledge_base_id=knowledge_base_id,
        limit=200,
        offset=0,
        status=status,
        priority=priority,
    )
    return CaseListResponse(
        items=[_case_to_summary(case) for case in cases],
        page=PageInfo(page=1, page_size=max(len(cases), 1), total_items=total),
    )


def get_case_detail_payload(
    case_id: str = Path(..., description="Case identifier."),
    knowledge_base_id: str = Query(..., min_length=1, description="Knowledge base scope."),
    service: CaseService = Depends(get_case_service),
    evidence_repository: EvidencePackRepository = Depends(get_evidence_pack_repository),
    feedback_store: dict[str, list[AnalystFeedbackResponse]] = Depends(get_case_feedback_store),
) -> CaseDetailResponse:
    """Return one KB-scoped case detail read model."""
    case = service.get(knowledge_base_id=knowledge_base_id, case_id=case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found.")
    return _assemble_case_detail(
        case, evidence_repository=evidence_repository, feedback_store=feedback_store
    )


def get_case_create_payload(
    payload: CaseCreateRequest,
    knowledge_base_id: str = Query(..., min_length=1, description="Knowledge base scope."),
    service: CaseService = Depends(get_case_service),
    evidence_repository: EvidencePackRepository = Depends(get_evidence_pack_repository),
    feedback_store: dict[str, list[AnalystFeedbackResponse]] = Depends(get_case_feedback_store),
) -> CaseDetailResponse:
    """Create and return a durable, KB-scoped case."""
    case = service.create(
        knowledge_base_id=knowledge_base_id,
        title=payload.title,
        priority=payload.priority,
        assignee=payload.assignee,
        alert_ids=list(payload.alert_ids),
    )
    return _assemble_case_detail(
        case, evidence_repository=evidence_repository, feedback_store=feedback_store
    )


def get_case_update_payload(
    payload: CaseUpdateRequest,
    case_id: str = Path(..., description="Case identifier."),
    knowledge_base_id: str = Query(..., min_length=1, description="Knowledge base scope."),
    service: CaseService = Depends(get_case_service),
    evidence_repository: EvidencePackRepository = Depends(get_evidence_pack_repository),
    feedback_store: dict[str, list[AnalystFeedbackResponse]] = Depends(get_case_feedback_store),
) -> CaseDetailResponse:
    """Patch and return a durable, KB-scoped case."""
    try:
        case = service.update(
            knowledge_base_id=knowledge_base_id,
            case_id=case_id,
            title=payload.title,
            status=payload.status,
            priority=payload.priority,
            assignee=payload.assignee,
        )
    except CaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Case not found.") from exc
    return _assemble_case_detail(
        case, evidence_repository=evidence_repository, feedback_store=feedback_store
    )


def get_case_feedback_payload(
    payload: CaseFeedbackCreateRequest,
    case_id: str = Path(..., description="Case identifier."),
    knowledge_base_id: str = Query(..., min_length=1, description="Knowledge base scope."),
    service: CaseService = Depends(get_case_service),
    evidence_repository: EvidencePackRepository = Depends(get_evidence_pack_repository),
    feedback_store: dict[str, list[AnalystFeedbackResponse]] = Depends(get_case_feedback_store),
) -> CaseDetailResponse:
    """Append analyst feedback to a case and return the updated detail."""
    case = service.get(knowledge_base_id=knowledge_base_id, case_id=case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found.")
    feedback = AnalystFeedbackResponse(
        case_id=case_id,
        label=payload.label,
        evidence_adequacy=payload.evidence_adequacy,
        missing_evidence=list(payload.missing_evidence),
        notes=payload.notes,
        submitted_at=utc_now(),
    )
    feedback_store.setdefault(case_id, []).append(feedback)
    return _assemble_case_detail(
        case, evidence_repository=evidence_repository, feedback_store=feedback_store
    )


def get_conversation_repository(request: Request) -> ConversationRepository:
    """Return the per-app durable conversation repository selected by config (BL-012).

    Postgres when a connection provider is configured, otherwise a per-app
    in-memory repository (so each app instance is isolated).
    """
    repository = getattr(request.app.state, "conversation_repository", None)
    if isinstance(repository, ConversationRepository):
        return repository

    provider = get_connection_provider()
    repository = (
        InMemoryConversationRepository()
        if provider is None
        else PostgresConversationRepository(provider)
    )
    request.app.state.conversation_repository = repository
    return repository


def get_conversation_service(
    repository: ConversationRepository = Depends(get_conversation_repository),
) -> ConversationService:
    """Return the conversation service over the configured repository."""
    return create_conversation_service(repository)


def get_chat_conversation_payload(
    conversation_id: str = Path(..., description="Conversation identifier."),
    service: ConversationService = Depends(get_conversation_service),
) -> ChatConversationResponse:
    """Return a chat conversation read model from the durable repository."""
    conversation = service.get(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return project_conversation(conversation)


def get_chat_conversation_create_payload(
    payload: ChatConversationCreateRequest,
    service: ConversationService = Depends(get_conversation_service),
) -> ChatConversationResponse:
    """Create and return a new durable conversation."""
    conversation = service.create(
        knowledge_base_id=payload.knowledge_base_id, title=payload.title
    )
    return project_conversation(conversation)


def get_chat_message_payload(
    payload: ChatMessageCreateRequest,
    conversation_id: str = Path(..., description="Conversation identifier."),
    state: ApiState = Depends(get_api_state),
    service: ConversationService = Depends(get_conversation_service),
    config: DomainConfig | None = None,
) -> ChatConversationResponse:
    """Append a user message + generated assistant reply to a durable conversation."""
    resolved_config = config if config is not None else get_domain_config()
    conversation = service.get(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    kb_ids = resolve_kb_scope(
        conversation.knowledge_base_id, resolved_config, get_knowledge_base_repository()
    )
    rag_response = state.rag_service.answer(
        RagQueryRequest(
            knowledge_base_ids=kb_ids,
            question=payload.content,
            include_graph_context=payload.include_graph_context,
            filters=payload.filters,
        )
    )
    updated = service.append_messages(
        conversation_id,
        [
            build_user_message(payload.content),
            build_assistant_message(rag_response),
        ],
    )
    return project_conversation(updated)


def get_policy_repository(request: Request) -> PolicyItemRepository:
    """Return the per-app durable policy item repository selected by config.

    Postgres when a connection provider is configured, otherwise a per-app
    in-memory repository (so each app instance is isolated).
    """
    repository = getattr(request.app.state, "policy_repository", None)
    if isinstance(repository, PolicyItemRepository):
        return repository

    provider = get_connection_provider()
    repository = (
        InMemoryPolicyItemRepository()
        if provider is None
        else PostgresPolicyItemRepository(provider)
    )
    request.app.state.policy_repository = repository
    return repository


def get_policy_service(
    repository: PolicyItemRepository = Depends(get_policy_repository),
) -> PolicyService:
    """Return the policy service over the configured repository."""
    return create_policy_service(repository)


def _policy_item_to_summary(item: PolicyItem) -> PolicyItemSummaryResponse:
    return PolicyItemSummaryResponse(
        id=item.id,
        knowledge_base_id=item.knowledge_base_id,
        rule_id=item.rule_id,
        rule_pack_id=item.rule_pack_id,
        target_kind=item.target_kind,
        target_ref=item.target_ref,
        title=item.title,
        severity=item.severity,
        status=item.status,
        updated_at=item.updated_at,
    )


def _policy_item_to_detail(item: PolicyItem) -> PolicyItemDetailResponse:
    disposition = (
        None
        if item.disposition is None
        else PolicyDispositionResponse(**item.disposition.model_dump())
    )
    return PolicyItemDetailResponse(
        item=_policy_item_to_summary(item),
        matched_fields=dict(item.matched_fields),
        citations=[PolicyCitationResponse(**c.model_dump()) for c in item.citations],
        disposition=disposition,
    )


_POLICY_SEVERITY_TO_PRIORITY: dict[str, CasePriority] = {
    "medium": "medium",
    "high": "high",
    "critical": "critical",
}


def _apply_policy_triage(
    *,
    policy_service: PolicyService,
    case_service: CaseService,
    knowledge_base_id: str,
    item_id: str,
    payload: PolicyTriageRequest,
    actor: str,
) -> PolicyItemDetailResponse:
    # Triage first so the item's open-check + disposition commit atomically.
    # Only after that succeeds do we create the case for escalate, so a 404/409
    # (concurrent delete or double-triage) can never leave an orphaned case.
    try:
        updated = policy_service.triage(
            knowledge_base_id=knowledge_base_id,
            item_id=item_id,
            action=payload.action,
            actor=actor,
            note=payload.note,
        )
    except PolicyItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PolicyItemAlreadyTriagedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if payload.action == "escalate":
        case = case_service.create(
            knowledge_base_id=knowledge_base_id,
            title=f"Policy escalation: {updated.title}",
            priority=_POLICY_SEVERITY_TO_PRIORITY.get(updated.severity, "medium"),
            timeline=[
                CaseTimelineEvent(
                    occurred_at=utc_now(),
                    label=f"Escalated from policy rule {updated.rule_id}",
                    detail=(
                        f"target={updated.target_ref}; matched={updated.matched_fields}"
                    ),
                )
            ],
        )
        updated = policy_service.link_case(
            knowledge_base_id=knowledge_base_id, item_id=item_id, case_id=case.id
        )
    return _policy_item_to_detail(updated)


def get_policy_item_list_payload(
    knowledge_base_id: str = Query(...),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: PolicyService = Depends(get_policy_service),
) -> PolicyItemListResponse:
    """Return a KB-scoped page of policy items, optionally filtered by status."""
    items, total = service.list(
        knowledge_base_id=knowledge_base_id, limit=limit, offset=offset, status=status
    )
    return PolicyItemListResponse(
        items=[_policy_item_to_summary(item) for item in items], total=total
    )


def get_policy_item_detail_payload(
    item_id: str = Path(...),
    knowledge_base_id: str = Query(...),
    service: PolicyService = Depends(get_policy_service),
) -> PolicyItemDetailResponse:
    """Return one policy item detail payload."""
    item = service.get(knowledge_base_id=knowledge_base_id, item_id=item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Policy item not found.")
    return _policy_item_to_detail(item)


def get_risk_score_payload(
    entity_id: str = Path(..., description="Entity identifier."),
    kb_id: str = Query(..., min_length=1, description="Knowledge base identifier."),
    state: ApiState = Depends(get_api_state),
) -> RiskScoreResponse:
    """Return a KB-scoped risk-score payload."""
    return state.get_risk_score(entity_id, knowledge_base_id=kb_id)


def get_timeseries_payload(
    entity_id: str = Path(..., description="Entity identifier."),
    kb_id: str = Query(..., min_length=1, description="Knowledge base identifier."),
    state: ApiState = Depends(get_api_state),
) -> EntityTimeseriesResponse:
    """Return a KB-scoped timeseries payload."""
    return state.get_timeseries(entity_id, knowledge_base_id=kb_id)




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
        stream_maxlen=event_config.stream_maxlen
        if event_config.stream_maxlen is not None
        else env_settings.stream_maxlen,
        reclaim_min_idle_ms=event_config.reclaim_min_idle_ms
        if event_config.reclaim_min_idle_ms is not None
        else env_settings.reclaim_min_idle_ms,
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
    return create_vector_service(
        get_vector_store(),
        event_bus=get_event_bus(),
        object_store=get_object_store(),
    )


def get_vector_service() -> VectorServiceProtocol:
    """Alias for ``get_vectorstore_service`` used by the KB delete cascade."""
    return get_vectorstore_service()


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
    from llm.exceptions import LlmConfigurationError

    llm_config = get_domain_config().llm or LlmConfig()
    try:
        return create_llm_client(llm_config)
    except LlmConfigurationError as exc:
        raise ConfigurationError(str(exc)) from exc


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
        default_medium_threshold=monitoring_config.medium_threshold,
        default_high_threshold=monitoring_config.high_threshold,
    )


# ---------------------------------------------------------------------------
# Analytics services (risk / timeseries / GNN).
#
# Built from DomainConfig like monitoring is. Sources are in-memory by
# default and empty; persistence is layered on by the worker once
# Postgres-backed risk/timeseries history exists.
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_risk_signal_source() -> RiskSignalSourceProtocol:
    """Return the risk signal source: Postgres-derived signals when a DB is configured."""
    provider = get_connection_provider()
    if provider is None:
        return InMemoryRiskSignalSource()
    return PostgresRiskSignalSource(provider)


@lru_cache(maxsize=1)
def get_risk_service() -> RiskServiceProtocol:
    """Return the risk service assembled from DomainConfig."""
    analytics_config = get_domain_config().analytics or AnalyticsConfig()
    return create_risk_service(
        get_risk_signal_source(),
        event_bus=get_event_bus(),
        default_medium_risk_threshold=analytics_config.medium_risk_threshold,
        default_high_risk_threshold=analytics_config.high_risk_threshold,
    )


@lru_cache(maxsize=1)
def get_timeseries_history_source() -> TimeSeriesHistorySourceProtocol:
    """Return the timeseries history source. In-memory by default."""
    return InMemoryTimeSeriesHistorySource()


@lru_cache(maxsize=1)
def get_timeseries_service() -> TimeseriesServiceProtocol:
    """Return the timeseries service assembled from DomainConfig."""
    return create_timeseries_service(
        get_timeseries_history_source(),
        event_bus=get_event_bus(),
    )


@lru_cache(maxsize=1)
def get_graph_snapshot_source() -> GraphSnapshotSourceProtocol:
    """Return the GNN graph snapshot source. In-memory by default."""
    return InMemoryGraphSnapshotSource()


def _gnn_capability_enabled() -> bool:
    """Read the GNN capability flag from the active DomainConfig."""
    return bool(get_domain_config().capabilities.gnn)


@lru_cache(maxsize=1)
def get_gnn_service() -> GnnServiceProtocol:
    """Return the GNN service assembled from DomainConfig.

    Honors the gnn capability flag — when disabled in config, the service
    returns empty results on every endpoint.
    """
    return create_gnn_service(
        get_graph_snapshot_source(),
        event_bus=get_event_bus(),
        gnn_enabled=_gnn_capability_enabled,
    )


@lru_cache(maxsize=1)
def get_ingestion_recovery_store() -> InMemoryIngestionRecoveryStore:
    """Return the recovery marker store for ingestion publish failures."""
    return InMemoryIngestionRecoveryStore()


@lru_cache(maxsize=1)
def get_ingestion_service() -> IngestionService:
    """Return the ingestion service used by API routes and tests."""
    return IngestionService(
        get_parser_orchestrator(),
        object_store=get_object_store(),
        event_bus=get_event_bus(),
        recovery_store=get_ingestion_recovery_store(),
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


@lru_cache(maxsize=1)
def get_derived_signal_store() -> DerivedRiskSignalWriterProtocol:
    """Return the peerstats derived-signal store (Postgres when a DB is configured).

    Used by the KB-delete cascade to purge ``entity_derived_signals``.
    """
    provider = get_connection_provider()
    if provider is None:
        return InMemoryDerivedRiskSignalWriter()
    return PostgresDerivedRiskSignalWriter(provider)


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
from agent.workflow_tracking import WorkflowEventTracker  # noqa: E402
from knowledgebases import (  # noqa: E402  (intentional bottom-of-file import)
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


def get_graph_entity_detail_payload(
    entity_id: str = Path(..., description="Entity identifier."),
    alert_repository: AlertProjectionRepository = Depends(get_alert_repository),
    graph_service: GraphServiceProtocol = Depends(get_graph_service),
    risk_service: RiskServiceProtocol = Depends(get_risk_service),
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    domain_config: DomainConfig = Depends(get_domain_config),
) -> GraphEntityDetailResponse:
    """Return one graph entity read model from the durable graph service (BL-012)."""
    detail = build_graph_entity_detail(
        entity_id,
        graph_service=graph_service,
        risk_service=risk_service,
        alert_repository=alert_repository,
        kb_repository=kb_repository,
        domain_config=domain_config,
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="Entity not found.")
    return detail


def get_analytics_overview_payload(
    alert_repository: AlertProjectionRepository = Depends(get_alert_repository),
    case_service: CaseService = Depends(get_case_service),
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
) -> AnalyticsOverviewResponse:
    """Return the analytics overview computed from durable stores (BL-012)."""
    return build_analytics_overview(
        alert_repository=alert_repository,
        case_service=case_service,
        kb_repository=kb_repository,
    )


def get_case_promote_payload(
    payload: CasePromoteRequest,
    knowledge_base_id: str = Query(..., min_length=1, description="Knowledge base scope."),
    service: CaseService = Depends(get_case_service),
    alert_repository: AlertProjectionRepository = Depends(get_alert_repository),
    evidence_repository: EvidencePackRepository = Depends(get_evidence_pack_repository),
    feedback_store: dict[str, list[AnalystFeedbackResponse]] = Depends(get_case_feedback_store),
) -> CaseDetailResponse:
    """Promote an alert into a durable, KB-scoped case capturing its evidence."""
    record = alert_repository.get(payload.alert_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Alert not found.")
    alert = record.alert
    timeline = [
        CaseTimelineEvent(
            occurred_at=alert.created_at,
            label="alert_raised",
            detail=alert.title,
        )
    ]
    case = service.promote_from_alert(
        knowledge_base_id=knowledge_base_id,
        alert=alert,
        timeline=timeline,
        notes=payload.notes,
    )
    return _assemble_case_detail(
        case, evidence_repository=evidence_repository, feedback_store=feedback_store
    )


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


def get_workflow_tracker(
    run_store: WorkflowRunStoreProtocol = Depends(get_workflow_run_store),
) -> WorkflowEventTracker:
    """Return a WorkflowEventTracker that satisfies the WorkflowBusyTracker protocol."""
    return WorkflowEventTracker(run_store)


@lru_cache(maxsize=1)
def get_rag_service() -> RagServiceProtocol:
    """Return the live RAG service composed from configured dependencies.

    Wires the production embeddings → vectorstore → graph → LLM pipeline
    (see BL-001). Bridges in :mod:`api._rag_bridges` adapt the per-module
    service contracts to the :class:`rag.protocols.RagServiceProtocol`
    inputs.
    """
    domain_config = get_domain_config()
    llm_cfg = domain_config.llm or LlmConfig()
    return create_rag_service(
        ServiceQueryEmbedder(get_embeddings_service()),
        ServiceContextRetriever(get_vector_service()),
        ServiceAnswerGenerator(
            get_llm_service(),
            max_tokens=llm_cfg.max_tokens,
            model_name=llm_cfg.model,
            temperature=llm_cfg.temperature,
        ),
        event_bus=get_event_bus(),
        graph_context_expander=ServiceGraphContextExpander(get_graph_service()),
        domain_config=domain_config,
    )
