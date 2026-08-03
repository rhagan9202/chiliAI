"""Dependency injection wiring for the FastAPI application."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from datetime import UTC, date, datetime
from functools import lru_cache
from typing import Literal, NoReturn, Protocol, TypeVar, cast

from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request

from api.contracts import (
    AnalystFeedbackResponse,
    AnalyticsOverviewResponse,
    AlertAssignmentRequest,
    AlertBulkRejection,
    AlertBulkStatusUpdateRequest,
    AlertBulkStatusUpdateResponse,
    AlertDetailResponse,
    AlertListItem,
    AlertListResponse,
    AlertOperationResponse,
    AlertStatusUpdateRequest,
    AlertTriageEventResponse,
    ApiEnvelope,
    CaseCreateRequest,
    CaseDetailResponse,
    CaseFeedbackCreateRequest,
    CaseListResponse,
    CaseAttachAlertRequest,
    CasePromoteRequest,
    CaseSummaryResponse,
    CaseTimelineEventResponse,
    CaseUpdateRequest,
    ChatConversationCreateRequest,
    ChatConversationListResponse,
    ChatConversationResponse,
    ChatConversationSummaryResponse,
    ChatMessageCreateRequest,
    EntityTimeseriesPointResponse,
    EntityTimeseriesResponse,
    EvidenceExportFormat,
    EvidencePackExportResponse,
    EvidencePackResponse,
    EvidenceProvenanceListResponse,
    EvidenceProvenanceReferenceResponse,
    FeatureAttributionResponse,
    GraphEntityDetailResponse,
    NarrativeSectionResponse,
    PageInfo,
    PolicyCitationResponse,
    PolicyDispositionResponse,
    PolicyItemDetailResponse,
    PolicyItemListResponse,
    PolicyItemSummaryResponse,
    PolicyTriageRequest,
    RiskFactorResponse,
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
from conversations.models import Conversation, ConversationMessage
from conversations.service import ConversationService, create_conversation_service
from rag.service_models import RagQueryRequest
from shared.alerts import normalize_severity
from shared.kb_scope import resolve_kb_scope
from cases.exceptions import AlertAlreadyAttachedError, CaseNotFoundError
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
from config.loader import ConfigLoadError, load_config
from config.store import ActivePackStoreError, read_active_pack
from config.schema import (
    AnalyticsConfig,
    AuthConfig,
    DatabaseConfig,
    DomainConfig,
    EmbeddingsConfig,
    EventBusConfig,
    GnnConfig,
    GraphDbConfig,
    LlmConfig,
    MonitoringConfig,
    ObjectStoreConfig,
    RecordsConfig,
    VectorStoreConfig,
)
from analytics.features.service import (
    FeatureCatalogService,
    create_feature_catalog_service,
)
from analytics.gnn.adapters.cluster_store import ObjectStoreClusterSummaryStore
from analytics.gnn.adapters.graph_repository_source import GraphRepositorySnapshotSource
from analytics.gnn.adapters.protocols import GraphSnapshotSourceProtocol
from analytics.gnn.protocols import GnnServiceProtocol
from analytics.gnn.service import create_gnn_service
from analytics.metrics.adapters.in_memory import InMemoryEntityMetricRepository
from analytics.metrics.adapters.postgres import PostgresEntityMetricRepository
from analytics.metrics.adapters.protocols import EntityMetricRepository
from analytics.risk.adapters.in_memory import (
    InMemoryRiskHistoryWriter,
    InMemoryRiskSignalSource,
)
from analytics.risk.adapters.postgres import (
    PostgresRiskHistoryStore,
    PostgresRiskProjectionRebuildSource,
    PostgresRiskProjectionRepository,
    PostgresRiskSignalSource,
)
from analytics.risk.adapters.protocols import RiskHistoryWriter, RiskSignalSourceProtocol
from analytics.risk.exceptions import RiskConfigurationError, RiskInsufficientSignalsError
from analytics.risk.projection_service import (
    RiskProjectionRebuildSourceProtocol,
    RiskProjectionService,
)
from analytics.risk.projections import (
    InMemoryRiskProjectionRepository,
    RiskProjectionRepositoryProtocol,
)
from analytics.risk.protocols import RiskServiceProtocol
from analytics.risk.service import create_risk_service
from analytics.risk.service_models import RiskAssessmentRequest
from analytics.score_runs.adapters.in_memory import InMemoryScoreRunRepository
from analytics.score_runs.protocols import ScoreRunRepositoryProtocol
from analytics.score_runs.service import ScoreRunService, create_score_run_service
from analytics.timeseries.adapters.in_memory import (
    InMemoryTimeSeriesHistorySource,
    InMemoryTimeseriesAnomalyStore,
)
from analytics.timeseries.adapters.postgres import (
    PostgresTimeSeriesHistorySource,
    PostgresTimeseriesAnomalyStore,
)
from analytics.timeseries.adapters.protocols import (
    TimeSeriesHistorySourceProtocol,
    TimeseriesAnomalyStoreProtocol,
)
from analytics.timeseries.adapters.record_aggregates import RecordAggregateTimeSeriesSource
from analytics.timeseries.protocols import TimeseriesServiceProtocol
from analytics.timeseries.service import create_timeseries_service
from embeddings.adapters.cache_in_memory import (
    create_embedding_cache,
    embedding_cache_namespace,
)
from embeddings.adapters.in_memory import InMemoryEmbedder
from embeddings.adapters.protocols import EmbedderProtocol
from embeddings.protocols import EmbeddingsServiceProtocol
from embeddings.service import create_embeddings_service
from events.adapters.dlq_in_memory import InMemoryDlqRecordStore
from events.adapters.dlq_postgres import PostgresDlqRecordStore
from events.protocols import DlqRecordStore, EventBus
from ingestion.adapters.in_memory import InMemorySourceDocumentStatusStore
from ingestion.adapters.postgres import PostgresSourceDocumentStatusStore
from ingestion.adapters.protocols import SourceDocumentStatusStore
from events.runtime import EventBusSettings, create_event_bus, load_event_bus_settings
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.adapters.protocols import GraphRepository
from graph.auth import resolve_graph_auth
from graph.protocols import GraphServiceProtocol
from graph.service import create_graph_service
from ingestion.orchestrators.parser import DocumentParsingOrchestrator
from ingestion.parsers.registry import ParserRegistry, create_default_registry
from ingestion.parsers.remote import HttpxRemoteDocumentFetcher
from ingestion.recovery import IngestionRecoveryStore, ObjectStoreIngestionRecoveryStore
from ingestion.service import IngestionService
from llm.adapters.protocols import LlmClientProtocol
from llm.factory import create_llm_client
from llm.protocols import LlmServiceProtocol
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
    AlertFeedStoreProtocol,
    AlertHistoryWriter,
    ObservationSourceProtocol,
    ObservationWriter,
)
from monitoring.exceptions import AlertLifecycleError
from monitoring.models import AlertHistoryRecord, AlertTriageEvent
from monitoring.protocols import MonitoringServiceProtocol
from monitoring.service import create_monitoring_service
from database.protocols import ConnectionProvider
from database.runtime import create_connection_provider
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
from records.adapters.in_memory import InMemoryRawRecordStore
from records.adapters.postgres import PostgresRawRecordStore
from records.adapters.protocols import RawRecordStore
from scorecards.adapters.in_memory import InMemoryScorecardRunRepository
from scorecards.adapters.postgres import PostgresScorecardRunRepository
from scorecards.adapters.protocols import ScorecardRunRepository
from scorecards.evaluation import SourceRecord, SourceValue
from scorecards.service import ScorecardService, create_scorecard_service
from analytics.explainability.adapters.evidence_object_store import (
    ObjectStoreEvidencePackRepository,
)
from analytics.explainability.export import render_evidence_markdown
from analytics.explainability.repository import EvidencePackRepository
from analytics.explainability.provenance import (
    EvidencePackProvenanceRepository,
    EvidenceProvenanceRepository,
)
from records.protocols import RecordsServiceProtocol
from records.service import create_records_service
from shared.exceptions import ConfigurationError
from shared.logging import get_logger
from shared.types import Alert, EvidencePack
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
    "CONFIG_CACHE_REGISTRY",
    "_apply_policy_triage",
    "build_api_state",
    "enforce_production_guardrail",
    "get_config_generation",
    "load_chili_environment",
    "require_kb_scoped_conversation",
    "reset_domain_config_caches",
    "get_api_state",
    "get_alert_acknowledge_payload",
    "get_alert_detail_payload",
    "get_alert_feed_store",
    "get_alert_list_payload",
    "get_agent_service",
    "get_analytics_overview_payload",
    "get_case_create_payload",
    "get_case_detail_payload",
    "get_case_feedback_payload",
    "get_case_list_payload",
    "get_case_attach_alert_payload",
    "get_case_promote_payload",
    "get_case_repository",
    "get_case_service",
    "get_case_update_payload",
    "get_chat_conversation_create_payload",
    "get_chat_conversation_payload",
    "get_chat_message_payload",
    "get_conversation_repository",
    "get_conversation_service",
    "get_dlq_record_store",
    "get_document_status_store",
    "get_embedder",
    "get_embeddings_service",
    "get_domain_config",
    "get_domain_config_features_payload",
    "get_domain_config_payload",
    "get_domain_config_schema_payload",
    "get_evidence_pack_export_payload",
    "get_evidence_pack_payload",
    "get_evidence_pack_repository",
    "get_evidence_provenance_payload",
    "get_evidence_provenance_repository",
    "get_event_bus",
    "get_event_bus_settings",
    "get_feature_catalog_service",
    "get_graph_entity_detail_payload",
    "get_ingestion_recovery_store",
    "get_ingestion_service",
    "get_graph_repository",
    "get_graph_service",
    "get_connection_provider",
    "get_raw_record_store",
    "get_records_service",
    "get_score_run_repository",
    "get_score_run_service",
    "get_scorecard_run_repository",
    "get_scorecard_service",
    "get_source_record_loader",
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
    "get_risk_projection_repository",
    "get_risk_projection_rebuild_source",
    "get_risk_projection_service",
    "get_risk_score_payload",
    "get_timeseries_payload",
    "get_session_store",
    "get_vector_service",
    "get_vector_store",
    "get_vectorstore_service",
    "get_workflow_run_store",
    "get_workflow_tracker",
    "resolve_event_bus_settings",
]

logger = get_logger("chili.api.dependencies")


def _raise_unsupported_backend(
    subsystem: str,
    backend: str,
    available_backends: tuple[str, ...],
) -> NoReturn:
    available = ", ".join(available_backends)
    raise ConfigurationError(
        f"Unsupported {subsystem} backend '{backend}'. Available backends: {available}."
    )


# ---------------------------------------------------------------------------
# Environment + production auth guardrail.
#
# Public (moved here from api.app) so the config hot-swap routes can enforce
# the same guardrail on a candidate pack BEFORE activating it — a domain
# switch under CHILI_ENV=staging/production must never disable auth
# platform-wide. api.app.create_app applies it at boot; POST /config/apply |
# /config/switch (T3) must apply it to the candidate's ``auth`` section as
# part of step 1 of swap-once-success (validate; nothing mutated on failure).
# ---------------------------------------------------------------------------

_ALLOWED_ENVIRONMENTS = frozenset({"local", "dev", "staging", "production"})
_AUTH_REQUIRED_ENVIRONMENTS = frozenset({"staging", "production"})


def load_chili_environment() -> str:
    """Return the validated runtime environment name from ``CHILI_ENV``."""

    raw_environment = os.environ.get("CHILI_ENV")
    if raw_environment is None or raw_environment.strip() == "":
        allowed = ", ".join(sorted(_ALLOWED_ENVIRONMENTS))
        raise RuntimeError(
            "CHILI_ENV must be set to one of "
            f"{allowed}; use CHILI_ENV=local for local development."
        )

    environment = raw_environment.strip().lower()
    if environment not in _ALLOWED_ENVIRONMENTS:
        allowed = ", ".join(sorted(_ALLOWED_ENVIRONMENTS))
        raise RuntimeError(
            f"Unknown CHILI_ENV '{raw_environment}'. Expected one of {allowed}."
        )
    return environment


def enforce_production_guardrail(auth: AuthConfig | None) -> None:
    """Reject an ``auth`` section that would disable auth under staging/production.

    No-op under ``CHILI_ENV=local|dev``. Raises ``RuntimeError`` when auth is
    absent, disabled, or missing required OIDC fields under
    ``CHILI_ENV=staging|production``. Applied at boot (``api.app.create_app``)
    and to every candidate pack before a domain hot-swap activates it.
    """
    environment = load_chili_environment()
    if environment not in _AUTH_REQUIRED_ENVIRONMENTS:
        return
    if auth is None or not auth.enabled:
        raise RuntimeError(
            "AuthConfig.enabled must be True under "
            f"CHILI_ENV={environment}."
        )
    required = (
        ("issuer_url", auth.issuer_url),
        ("audience", auth.audience),
        ("jwks_uri", auth.jwks_uri),
        ("client_id", auth.client_id),
        ("client_secret_env_var", auth.client_secret_env_var),
        ("authorize_endpoint", auth.authorize_endpoint),
        ("token_endpoint", auth.token_endpoint),
        ("redirect_uri", auth.redirect_uri),
    )
    missing = [name for name, value in required if value is None]
    if missing:
        raise RuntimeError(
            "AuthConfig is missing required fields under "
            f"CHILI_ENV={environment}: {missing}"
        )


def get_api_state(request: Request) -> ApiState:
    """Return the per-app seeded mutable API state.

    State is attached to ``app.state`` in :func:`api.app.create_app`, giving
    each TestClient (and each production process) its own ``ApiState``
    instance. Mutations made via one request do not leak into a fresh app
    instance — important for test isolation.

    The lazy rebuild (bare ``FastAPI()`` in tests, or first request after a
    swap purge) is memoized through :func:`_memoize_config_derived` so a
    build that raced a domain swap can never poison ``app.state`` — see M2 in
    the swap-core section.
    """
    return _memoize_config_derived(
        request.app,
        "api_state",
        lambda: create_api_state(get_domain_config()),
        guard=lambda value: isinstance(value, ApiState),
    )


def get_evidence_pack_repository(request: Request) -> EvidencePackRepository:
    """Return the per-app evidence-pack repository used by the evidence route.

    Reads packs the worker persisted to the shared object store (BL-005).
    """
    return _memoize_config_derived(
        request.app,
        "evidence_pack_repository",
        lambda: ObjectStoreEvidencePackRepository(get_object_store()),
        guard=lambda value: isinstance(value, EvidencePackRepository),
    )


def get_evidence_provenance_repository(
    request: Request,
) -> EvidenceProvenanceRepository:
    """Return the provenance query seam backed by persisted evidence packs."""

    return EvidencePackProvenanceRepository(get_evidence_pack_repository(request))


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


def get_evidence_provenance_payload(
    evidence_pack_id: str = Path(..., description="Evidence pack identifier."),
    knowledge_base_id: str = Query(
        ..., min_length=1, description="Knowledge base the evidence pack belongs to."
    ),
    repository: EvidenceProvenanceRepository = Depends(
        get_evidence_provenance_repository
    ),
) -> EvidenceProvenanceListResponse:
    """Return structured provenance references for one evidence pack."""

    return build_evidence_provenance_response(
        knowledge_base_id=knowledge_base_id,
        evidence_pack_id=evidence_pack_id,
        repository=repository,
    )


def get_evidence_pack_export_payload(
    evidence_pack_id: str = Path(..., description="Evidence pack identifier."),
    knowledge_base_id: str = Query(
        ..., min_length=1, description="Knowledge base the evidence pack belongs to."
    ),
    export_format: EvidenceExportFormat = Query(
        default="markdown",
        alias="format",
        description="Rendering to return: machine-readable JSON or readable Markdown.",
    ),
    repository: EvidencePackRepository = Depends(get_evidence_pack_repository),
) -> EvidencePackExportResponse:
    """Render one persisted evidence pack for download (UXA-405)."""
    pack = repository.get(knowledge_base_id, evidence_pack_id)
    if pack is None:
        raise HTTPException(status_code=404, detail="Evidence pack not found.")
    if export_format == "json":
        content = pack.model_dump_json(indent=2)
        suffix = "json"
    else:
        content = render_evidence_markdown(pack)
        suffix = "md"
    return EvidencePackExportResponse(
        evidence_pack_id=pack.id,
        format=export_format,
        filename=f"evidence-{pack.id}.{suffix}",
        content=content,
    )


def build_evidence_provenance_response(
    *,
    knowledge_base_id: str,
    evidence_pack_id: str,
    repository: EvidenceProvenanceRepository,
) -> EvidenceProvenanceListResponse:
    refs = repository.list_for_evidence_pack(knowledge_base_id, evidence_pack_id)
    if refs is None:
        raise HTTPException(status_code=404, detail="Evidence pack not found.")
    return EvidenceProvenanceListResponse(
        knowledge_base_id=knowledge_base_id,
        evidence_pack_id=evidence_pack_id,
        items=[
            EvidenceProvenanceReferenceResponse(
                reference_type=reference.reference_type,
                reference_id=reference.reference_id,
                label=reference.label,
                source_system=reference.source_system,
                source_version=reference.source_version,
                transformation_version=reference.transformation_version,
                confidence=reference.confidence,
                route_target=reference.route_target,
                metadata=dict(reference.metadata),
            )
            for reference in refs
        ],
    )


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
        attribution=[
            FeatureAttributionResponse(
                feature_name=attribution.feature_name,
                contribution=attribution.contribution,
                rationale=attribution.rationale,
            )
            for attribution in pack.attribution
        ],
        narrative_sections=[
            NarrativeSectionResponse(
                heading=section.heading,
                body=section.body,
                evidence_refs=list(section.evidence_refs),
            )
            for section in pack.narrative_sections
        ],
        provenance=[
            EvidenceProvenanceReferenceResponse(
                reference_type=reference.reference_type,
                reference_id=reference.reference_id,
                label=reference.label,
                source_system=reference.source_system,
                source_version=reference.source_version,
                transformation_version=reference.transformation_version,
                confidence=reference.confidence,
                route_target=reference.route_target,
                metadata=dict(reference.metadata),
            )
            for reference in pack.provenance
        ],
        created_at=pack.created_at,
        source_documents=list(pack.source_documents),
    )


def get_case_repository(request: Request) -> CaseRepository:
    """Return the per-app durable case repository selected by config (BL-010).

    Postgres when a connection provider is configured, otherwise a per-app
    in-memory repository (so each app instance is isolated).
    """
    def build() -> CaseRepository:
        provider = get_connection_provider()
        return (
            InMemoryCaseRepository() if provider is None else PostgresCaseRepository(provider)
        )

    return _memoize_config_derived(
        request.app,
        "case_repository",
        build,
        guard=lambda value: isinstance(value, CaseRepository),
    )


def get_case_service(
    repository: CaseRepository = Depends(get_case_repository),
) -> CaseService:
    """Return the case service over the configured repository."""
    return create_case_service(repository)


@lru_cache(maxsize=1)
def get_alert_feed_store() -> AlertFeedStoreProtocol:
    """Return the durable alert feed store (Postgres when a DB is configured).

    Serves the alert list/detail/acknowledge routes and the SSE active-alert
    count directly from the ``alert_history`` table (alerts.36) — the API no
    longer keeps a separate, non-authoritative projection blob.
    """
    provider = get_connection_provider()
    if provider is None:
        return InMemoryAlertHistoryWriter()
    return PostgresAlertHistoryStore(provider)


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


_ALERT_STATUS_LITERALS = frozenset(
    {"open", "acknowledged", "investigating", "resolved", "dismissed"}
)


def _alert_record_to_list_item(record: AlertHistoryRecord) -> AlertListItem:
    status = record.status if record.status in _ALERT_STATUS_LITERALS else "open"
    return AlertListItem(
        id=record.alert_id,
        knowledge_base_id=record.knowledge_base_id,
        entity_id=record.entity_id,
        entity_type=record.entity_type,
        entity_label=record.entity_label or record.entity_id,
        severity=normalize_severity(record.severity, record.confidence),
        status=cast(
            Literal["open", "acknowledged", "investigating", "resolved", "dismissed"],
            status,
        ),
        title=record.title,
        reasoning=record.reasoning,
        confidence=record.confidence,
        evidence_pack_id=record.evidence_pack_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
        tags=list(record.tags),
        assignee=record.assignee,
    )


def _alert_triage_event_to_response(
    event: AlertTriageEvent,
) -> AlertTriageEventResponse:
    return AlertTriageEventResponse(
        event_type=event.event_type,
        actor=event.actor,
        occurred_at=event.occurred_at,
        assignee=event.assignee,
        from_status=event.from_status,
        to_status=event.to_status,
        reason=event.reason,
    )


def _linked_case_alerts(
    case: Case,
    *,
    alert_store: AlertFeedStoreProtocol,
) -> list[AlertListItem]:
    linked_alerts: list[AlertListItem] = []
    for alert_id in case.alert_ids:
        record = alert_store.get_alert(alert_id)
        if record is None or record.knowledge_base_id != case.knowledge_base_id:
            continue
        linked_alerts.append(_alert_record_to_list_item(record))
    return linked_alerts


def _case_feedback_to_response(case: Case) -> list[AnalystFeedbackResponse]:
    return [
        AnalystFeedbackResponse(
            case_id=feedback.case_id,
            label=feedback.label,
            evidence_adequacy=feedback.evidence_adequacy,
            missing_evidence=list(feedback.missing_evidence),
            notes=feedback.notes,
            submitted_at=feedback.submitted_at,
        )
        for feedback in case.feedback_history
    ]


def _assemble_case_detail(
    case: Case,
    *,
    evidence_repository: EvidencePackRepository,
    alert_store: AlertFeedStoreProtocol,
) -> CaseDetailResponse:
    evidence_pack: EvidencePackResponse | None = None
    if case.evidence_pack_id:
        pack = evidence_repository.get(case.knowledge_base_id, case.evidence_pack_id)
        if pack is not None:
            evidence_pack = _evidence_pack_to_response(pack)
    return CaseDetailResponse(
        case=_case_to_summary(case),
        alerts=_linked_case_alerts(case, alert_store=alert_store),
        evidence_pack=evidence_pack,
        entity_timeline=[
            CaseTimelineEventResponse(
                occurred_at=event.occurred_at, label=event.label, detail=event.detail
            )
            for event in case.timeline
        ],
        feedback_history=_case_feedback_to_response(case),
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
    alert_store: AlertFeedStoreProtocol = Depends(get_alert_feed_store),
) -> CaseDetailResponse:
    """Return one KB-scoped case detail read model."""
    case = service.get(knowledge_base_id=knowledge_base_id, case_id=case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found.")
    return _assemble_case_detail(
        case, evidence_repository=evidence_repository, alert_store=alert_store
    )


def get_case_create_payload(
    payload: CaseCreateRequest,
    knowledge_base_id: str = Query(..., min_length=1, description="Knowledge base scope."),
    service: CaseService = Depends(get_case_service),
    evidence_repository: EvidencePackRepository = Depends(get_evidence_pack_repository),
    alert_store: AlertFeedStoreProtocol = Depends(get_alert_feed_store),
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
        case, evidence_repository=evidence_repository, alert_store=alert_store
    )


def get_case_update_payload(
    payload: CaseUpdateRequest,
    case_id: str = Path(..., description="Case identifier."),
    knowledge_base_id: str = Query(..., min_length=1, description="Knowledge base scope."),
    service: CaseService = Depends(get_case_service),
    evidence_repository: EvidencePackRepository = Depends(get_evidence_pack_repository),
    alert_store: AlertFeedStoreProtocol = Depends(get_alert_feed_store),
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
        case, evidence_repository=evidence_repository, alert_store=alert_store
    )


def get_case_feedback_payload(
    payload: CaseFeedbackCreateRequest,
    case_id: str = Path(..., description="Case identifier."),
    knowledge_base_id: str = Query(..., min_length=1, description="Knowledge base scope."),
    service: CaseService = Depends(get_case_service),
    evidence_repository: EvidencePackRepository = Depends(get_evidence_pack_repository),
    alert_store: AlertFeedStoreProtocol = Depends(get_alert_feed_store),
) -> CaseDetailResponse:
    """Append analyst feedback to a case and return the updated detail."""
    try:
        case = service.add_feedback(
            knowledge_base_id=knowledge_base_id,
            case_id=case_id,
            label=payload.label,
            evidence_adequacy=payload.evidence_adequacy,
            missing_evidence=list(payload.missing_evidence),
            notes=payload.notes,
        )
    except CaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Case not found.") from exc
    return _assemble_case_detail(
        case, evidence_repository=evidence_repository, alert_store=alert_store
    )


def get_conversation_repository(request: Request) -> ConversationRepository:
    """Return the per-app durable conversation repository selected by config (BL-012).

    Postgres when a connection provider is configured, otherwise a per-app
    in-memory repository (so each app instance is isolated).
    """
    def build() -> ConversationRepository:
        provider = get_connection_provider()
        return (
            InMemoryConversationRepository()
            if provider is None
            else PostgresConversationRepository(provider)
        )

    return _memoize_config_derived(
        request.app,
        "conversation_repository",
        build,
        guard=lambda value: isinstance(value, ConversationRepository),
    )


def get_conversation_service(
    repository: ConversationRepository = Depends(get_conversation_repository),
) -> ConversationService:
    """Return the conversation service over the configured repository."""
    return create_conversation_service(repository)


def require_kb_scoped_conversation(
    service: ConversationService, conversation_id: str, knowledge_base_id: str
) -> Conversation:
    """Load one conversation within a KB scope, or 404.

    The listing route has always required a KB scope, but the detail and
    message-append routes took none — so a full transcript was readable, and
    retrieval drivable, by id alone from outside the owning knowledge base.
    """
    conversation = service.get(conversation_id)
    if conversation is None or conversation.knowledge_base_id != knowledge_base_id:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return conversation


def get_chat_conversation_payload(
    conversation_id: str = Path(..., description="Conversation identifier."),
    knowledge_base_id: str = Query(
        ..., min_length=1, description="Knowledge base identifier."
    ),
    service: ConversationService = Depends(get_conversation_service),
) -> ChatConversationResponse:
    """Return a chat conversation read model from the durable repository."""
    conversation = require_kb_scoped_conversation(
        service, conversation_id, knowledge_base_id
    )
    return project_conversation(conversation)


def get_chat_conversation_list_payload(
    knowledge_base_id: str = Query(
        ..., min_length=1, description="Knowledge base scope."
    ),
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: ConversationService = Depends(get_conversation_service),
) -> ChatConversationListResponse:
    """Return a knowledge base's conversations, most recently updated first."""
    conversations, total = service.list(
        knowledge_base_id=knowledge_base_id, limit=limit, offset=offset
    )
    return ChatConversationListResponse(
        items=[
            ChatConversationSummaryResponse(
                id=conversation.id,
                title=conversation.title,
                knowledge_base_id=conversation.knowledge_base_id,
                message_count=len(conversation.messages),
                last_message=_conversation_preview(conversation.messages),
                updated_at=conversation.updated_at,
            )
            for conversation in conversations
        ],
        page=PageInfo(page=(offset // limit) + 1, page_size=limit, total_items=total),
    )


def _conversation_preview(messages: list[ConversationMessage]) -> str | None:
    """Pick a compact preview line for a conversation summary.

    Prefers the analyst's most recent question over the assistant's most recent
    reply because RAG replies interleave citation dumps and, when the LLM
    adapter falls back to echo mode, are largely context payload — the question
    is what the analyst remembers the thread by (surfaced in the ChatGPT-style
    conversation list). Falls back to the final assistant reply for threads
    that begin with a system or assistant seed.
    """
    if not messages:
        return None
    for message in reversed(messages):
        if message.role == "user":
            return message.content
    return messages[-1].content


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
    knowledge_base_id: str = Query(
        ..., min_length=1, description="Knowledge base identifier."
    ),
    state: ApiState = Depends(get_api_state),
    service: ConversationService = Depends(get_conversation_service),
    config: DomainConfig | None = None,
) -> ChatConversationResponse:
    """Append a user message + generated assistant reply to a durable conversation."""
    resolved_config = config if config is not None else get_domain_config()
    conversation = require_kb_scoped_conversation(
        service, conversation_id, knowledge_base_id
    )

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
    def build() -> PolicyItemRepository:
        provider = get_connection_provider()
        return (
            InMemoryPolicyItemRepository()
            if provider is None
            else PostgresPolicyItemRepository(provider)
        )

    return _memoize_config_derived(
        request.app,
        "policy_repository",
        build,
        guard=lambda value: isinstance(value, PolicyItemRepository),
    )


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
    status: list[str] | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: PolicyService = Depends(get_policy_service),
) -> PolicyItemListResponse:
    """Return a KB-scoped page of policy items, narrowed by status and title.

    ``status`` repeats (``?status=open&status=escalated``) so "open **or**
    escalated" — the working set an analyst actually wants — is expressible in
    one request. A single ``?status=open`` still parses to a one-element list,
    so the pre-multi-select wire form keeps working (UXA-401).
    """
    items, total = service.list(
        knowledge_base_id=knowledge_base_id,
        limit=limit,
        offset=offset,
        statuses=status,
        query=q,
    )
    return PolicyItemListResponse(
        items=[_policy_item_to_summary(item) for item in items],
        total=total,
        status_counts=service.count_by_status(knowledge_base_id=knowledge_base_id),
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


# get_risk_score_payload is defined further below (after get_risk_service)
# since it takes the DI risk service as a FastAPI ``Depends(...)`` default
# argument, which is resolved at module import time.


# get_timeseries_payload is defined further below (after get_entity_series_source
# and get_timeseries_anomaly_store) since it depends on those factories as
# FastAPI ``Depends(...)`` default arguments, which are resolved at module
# import time and so require the factories to already exist.




@lru_cache(maxsize=1)
def get_domain_config() -> DomainConfig:
    """Load and cache the domain configuration (process-singleton).

    Resolution precedence: active-pack pointer (``config.store``, written by
    the config hot-swap routes) > ``CHILI_CONFIG_PATH`` env. When no pointer
    has been written the historical zero-arg ``load_config()`` call is kept so
    tests that monkeypatch ``api.dependencies.load_config`` still take effect.

    The cache is cleared by :func:`reset_domain_config_caches` (called at the
    start of :func:`api.app.create_app` and on every domain hot-swap), so each
    fresh app or swap picks up the currently active pack. Tests that need to
    inject a specific config can also override via ``app.dependency_overrides``.
    """
    try:
        pointer = read_active_pack()
    except ActivePackStoreError as exc:
        raise ConfigLoadError(str(exc)) from exc
    if pointer is not None:
        return load_config(pointer.config_path)
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


def get_feature_catalog_service(
    config: DomainConfig = Depends(get_domain_config),
) -> FeatureCatalogService:
    """Return the feature catalog service for the active domain config."""

    return create_feature_catalog_service(config)


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


def resolve_event_bus_settings(config: DomainConfig) -> EventBusSettings:
    """Return the event transport a pack would actually run on.

    A pack's ``events`` section is only half the answer: the environment wins
    when that section is absent, ``None``, or equal to the default
    ``EventBusConfig()``, so only an explicitly pinned, non-default block
    overrides it. Public because ``/config/packs`` and ``/config/validate``
    report this to operators before a hot-swap — the declared section would
    mis-report any pack that omits it (UXA-404).
    """
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
    settings = resolve_event_bus_settings(config)
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
    embeddings_config = get_domain_config().embeddings or EmbeddingsConfig()
    return create_embeddings_service(
        get_embedder(),
        event_bus=get_event_bus(),
        cache=create_embedding_cache(embeddings_config),
        cache_namespace=embedding_cache_namespace(embeddings_config),
    )


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


def _normalize_risk_level(
    risk_level: str, overall_score: float
) -> Literal["low", "medium", "high", "critical"]:
    if overall_score >= 0.9:
        return "critical"
    if risk_level in {"high", "medium", "low", "critical"}:
        return cast(Literal["low", "medium", "high", "critical"], risk_level)
    return "medium"


def get_risk_score_payload(
    entity_id: str = Path(..., description="Entity identifier."),
    kb_id: str = Query(
        ..., alias="knowledge_base_id", min_length=1, description="Knowledge base identifier."
    ),
    risk_service: RiskServiceProtocol = Depends(get_risk_service),
) -> RiskScoreResponse:
    """Return a KB-scoped risk-score payload from the DI risk service (B2).

    Configuration and insufficient-signal conditions surface as an
    "unavailable" payload; infrastructure failures propagate so they are not
    misreported as an entity without a risk profile.
    """
    try:
        response = risk_service.assess(
            RiskAssessmentRequest(knowledge_base_id=kb_id, entity_id=entity_id)
        )
    except (RiskConfigurationError, RiskInsufficientSignalsError, ValueError):
        return RiskScoreResponse(
            entity_id=entity_id,
            overall_score=0.0,
            risk_level="low",
            factors=[],
            availability_status="unavailable",
            unavailable_reason="No risk profile has been generated for this entity.",
        )
    return RiskScoreResponse(
        entity_id=response.entity_id,
        overall_score=response.overall_score,
        risk_level=_normalize_risk_level(response.risk_level, response.overall_score),
        factors=[
            RiskFactorResponse(
                factor_name=factor.factor_name,
                contribution=factor.contribution,
                rationale=factor.rationale,
            )
            for factor in response.factors
        ],
        availability_status="available",
        unavailable_reason=None,
    )


@lru_cache(maxsize=1)
def get_timeseries_history_source() -> TimeSeriesHistorySourceProtocol:
    """Return the graph-scope timeseries source: Postgres when a DB is configured."""
    provider = get_connection_provider()
    if provider is None:
        return InMemoryTimeSeriesHistorySource()
    return PostgresTimeSeriesHistorySource(provider)


@lru_cache(maxsize=1)
def get_timeseries_service() -> TimeseriesServiceProtocol:
    """Return the timeseries service assembled from DomainConfig."""
    return create_timeseries_service(
        get_timeseries_history_source(),
        event_bus=get_event_bus(),
    )


@lru_cache(maxsize=1)
def get_timeseries_anomaly_store() -> TimeseriesAnomalyStoreProtocol:
    """Return the timeseries anomaly store selected by the database backend."""
    provider = get_connection_provider()
    if provider is None:
        return InMemoryTimeseriesAnomalyStore()
    return PostgresTimeseriesAnomalyStore(provider)


@lru_cache(maxsize=1)
def get_record_column_source() -> RecordColumnSourceProtocol:
    """Return the record-aggregate column source selected by the database backend."""
    provider = get_connection_provider()
    if provider is None:
        return InMemoryRecordColumnSource()
    return PostgresRecordColumnSource(provider)


@lru_cache(maxsize=1)
def get_entity_series_source() -> RecordAggregateTimeSeriesSource:
    """Return the per-entity record-aggregate series source."""
    config = get_domain_config()
    specs = list(config.timeseries.metrics) if config.timeseries is not None else []
    return RecordAggregateTimeSeriesSource(get_record_column_source(), specs=specs)


def get_timeseries_payload(
    entity_id: str = Path(..., description="Entity identifier."),
    kb_id: str = Query(
        ..., alias="knowledge_base_id", min_length=1, description="Knowledge base identifier."
    ),
    source: RecordAggregateTimeSeriesSource = Depends(get_entity_series_source),
    anomaly_store: TimeseriesAnomalyStoreProtocol = Depends(get_timeseries_anomaly_store),
) -> EntityTimeseriesResponse:
    """Return a KB-scoped entity timeseries built from record aggregates."""
    metric_names = source.metric_names()
    for metric_name in metric_names:
        try:
            series = source.load_series(
                knowledge_base_id=kb_id, entity_id=entity_id, metric_name=metric_name
            )
        except ValueError:
            continue  # this spec has no data for the entity; try the next
        anomalies = anomaly_store.load_anomalies(
            knowledge_base_id=kb_id, entity_id=entity_id, metric_name=metric_name
        )
        anomaly_timestamps = {record.observed_at for record in anomalies}
        return EntityTimeseriesResponse(
            entity_id=entity_id,
            metric_name=metric_name,
            points=[
                EntityTimeseriesPointResponse(
                    timestamp=observation.observed_at,
                    value=observation.value,
                    label=observation.observed_at.strftime("%b %d"),
                    is_anomaly=observation.observed_at in anomaly_timestamps,
                )
                for observation in series.observations
            ],
            availability_status="available",
            unavailable_reason=None,
        )
    return EntityTimeseriesResponse(
        entity_id=entity_id,
        metric_name=metric_names[0] if metric_names else "timeseries",
        points=[],
        availability_status="unavailable",
        unavailable_reason="No time series is configured or populated for this entity.",
    )


@lru_cache(maxsize=1)
def get_graph_snapshot_source() -> GraphSnapshotSourceProtocol:
    """Return the GNN graph snapshot source, repository-backed (B1).

    Mirrors the worker's ``build_graph_snapshot_source`` wiring: bounded by
    ``DomainConfig.gnn.snapshot_max_nodes`` with cluster summaries served from
    an object-store-backed cluster store over the configured object store.
    """
    gnn_config = get_domain_config().gnn or GnnConfig()
    return GraphRepositorySnapshotSource(
        get_graph_repository(),
        ObjectStoreClusterSummaryStore(get_object_store()),
        max_nodes=gnn_config.snapshot_max_nodes,
    )


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
def get_ingestion_recovery_store() -> IngestionRecoveryStore:
    """Return the recovery marker store for ingestion publish failures."""
    return ObjectStoreIngestionRecoveryStore(get_object_store())


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
def get_document_status_store() -> SourceDocumentStatusStore:
    """Return the durable document status store (Postgres when configured)."""
    provider = get_connection_provider()
    if provider is None:
        return InMemorySourceDocumentStatusStore()
    return PostgresSourceDocumentStatusStore(provider)


@lru_cache(maxsize=1)
def get_dlq_record_store() -> DlqRecordStore:
    """Return the durable DLQ record store (Postgres when configured)."""
    provider = get_connection_provider()
    if provider is None:
        return InMemoryDlqRecordStore()
    return PostgresDlqRecordStore(provider)


@lru_cache(maxsize=1)
def get_derived_signal_store() -> DerivedRiskSignalWriterProtocol:
    """Return the peerstats derived-signal store (Postgres when a DB is configured).

    Used by the KB-delete cascade to purge ``entity_derived_signals``.
    """
    provider = get_connection_provider()
    if provider is None:
        return InMemoryDerivedRiskSignalWriter()
    return PostgresDerivedRiskSignalWriter(provider)


# Analytics/monitoring write stores — used by the KB-delete cascade to purge the
# per-consumer durable tables (Postgres when a DB is configured, else in-memory).


@lru_cache(maxsize=1)
def get_risk_history_writer() -> RiskHistoryWriter:
    """Return the risk-history store (purges ``risk_score_history`` on KB delete)."""
    provider = get_connection_provider()
    if provider is None:
        return InMemoryRiskHistoryWriter()
    return PostgresRiskHistoryStore(provider)


@lru_cache(maxsize=1)
def get_observation_writer() -> ObservationWriter:
    """Return the observation store (purges ``observations`` on KB delete)."""
    provider = get_connection_provider()
    if provider is None:
        return InMemoryObservationWriter()
    return PostgresObservationStore(provider)


@lru_cache(maxsize=1)
def get_alert_history_writer() -> AlertHistoryWriter:
    """Return the alert-history store (purges ``alert_history`` on KB delete)."""
    provider = get_connection_provider()
    if provider is None:
        return InMemoryAlertHistoryWriter()
    return PostgresAlertHistoryStore(provider)


@lru_cache(maxsize=1)
def get_entity_metric_repository() -> EntityMetricRepository:
    """Return the entity-metric repository (purges metric tables on KB delete)."""
    provider = get_connection_provider()
    if provider is None:
        return InMemoryEntityMetricRepository()
    return PostgresEntityMetricRepository(provider)


def get_scorecard_run_repository(request: Request) -> ScorecardRunRepository:
    """Return the scorecard-run repository selected by config."""

    def build() -> ScorecardRunRepository:
        provider = get_connection_provider()
        return (
            InMemoryScorecardRunRepository()
            if provider is None
            else PostgresScorecardRunRepository(provider)
        )

    return _memoize_config_derived(
        request.app,
        "scorecard_run_repository",
        build,
        guard=lambda value: isinstance(value, ScorecardRunRepository),
    )


def get_score_run_repository(request: Request) -> ScoreRunRepositoryProtocol:
    """Return the score-run repository for score-all workflow state."""

    return _memoize_config_derived(
        request.app,
        "score_run_repository",
        lambda: InMemoryScoreRunRepository(),
        guard=lambda value: isinstance(value, ScoreRunRepositoryProtocol),
    )


def get_score_run_service(
    repository: ScoreRunRepositoryProtocol = Depends(get_score_run_repository),
    event_bus: EventBus = Depends(get_event_bus),
) -> ScoreRunService:
    """Return the score-run service for KB-scoped score-all operations."""

    return create_score_run_service(repository, event_bus=event_bus)


def get_risk_projection_repository(request: Request) -> RiskProjectionRepositoryProtocol:
    """Return the configured risk projection repository."""

    def build() -> RiskProjectionRepositoryProtocol:
        provider = get_connection_provider()
        if provider is None:
            return InMemoryRiskProjectionRepository()
        return PostgresRiskProjectionRepository(provider)

    return _memoize_config_derived(
        request.app,
        "risk_projection_repository",
        build,
        guard=lambda value: isinstance(value, RiskProjectionRepositoryProtocol),
    )


def get_risk_projection_rebuild_source() -> RiskProjectionRebuildSourceProtocol | None:
    """Return the authoritative source for rebuilding risk projections, if configured."""

    provider = get_connection_provider()
    if provider is None:
        return None
    return PostgresRiskProjectionRebuildSource(
        provider,
        feature_typology_index=_feature_typology_index(get_domain_config()),
    )


def _feature_typology_index(config: DomainConfig) -> dict[str, list[str]]:
    return {
        feature.id: list(feature.typology_ids)
        for feature in config.feature_catalog.features
    }


def get_risk_projection_service(
    repository: RiskProjectionRepositoryProtocol = Depends(get_risk_projection_repository),
) -> RiskProjectionService:
    """Return the risk projection writer/rebuild service."""

    return RiskProjectionService(repository)


class RecordFeedSourceLoader:
    """Bridge the raw-records store into the scorecard evaluator's read model.

    Implements :class:`scorecards.service.ScorecardSourceRecordLoader` at the
    gateway layer, so scorecards (and the housing read models) consume ingested
    feed data without importing the records module directly. Stored rows are
    keyed by ``record_type``; the active config's feed declarations map each
    row back to the feed name that scorecard metric inputs reference. Rows are
    dated from their ``snapshot_date`` column (every housing feed carries one)
    so the evaluator's freshness checks operate on real observation dates.
    """

    def __init__(self, store: RawRecordStore, records_config: RecordsConfig) -> None:
        self._store = store
        self._feed_names_by_record_type: dict[str, list[str]] = {}
        for feed in records_config.feeds:
            self._feed_names_by_record_type.setdefault(feed.record_type, []).append(
                feed.name
            )

    def load_source_records(self, knowledge_base_id: str) -> list[SourceRecord]:
        """Return every ingested record for the KB as evaluator source records."""
        source_records: list[SourceRecord] = []
        for record in self._store.load_for_kb(knowledge_base_id=knowledge_base_id):
            feed_names = self._feed_names_by_record_type.get(record.record_type, [])
            if not feed_names:
                continue
            values = _scalar_payload_values(record.payload)
            observed_at = _parse_observed_at(record.payload.get("snapshot_date"))
            source_records.extend(
                SourceRecord(
                    feed_name=feed_name,
                    record_id=record.record_id,
                    values=values,
                    observed_at=observed_at,
                )
                for feed_name in feed_names
            )
        return source_records


def _scalar_payload_values(payload: dict[str, object]) -> dict[str, SourceValue]:
    """Keep the scalar payload columns the evaluator understands."""
    return {
        key: value
        for key, value in payload.items()
        if value is None or isinstance(value, str | int | float | bool)
    }


def _parse_observed_at(raw: object) -> datetime | None:
    """Parse a payload ``snapshot_date`` into a timezone-aware datetime."""
    if isinstance(raw, datetime):
        return raw if raw.tzinfo is not None else raw.replace(tzinfo=UTC)
    if isinstance(raw, date):
        return datetime(raw.year, raw.month, raw.day, tzinfo=UTC)
    if isinstance(raw, str):
        try:
            parsed = date.fromisoformat(raw.strip())
        except ValueError:
            return None
        return datetime(parsed.year, parsed.month, parsed.day, tzinfo=UTC)
    return None


def get_source_record_loader(
    config: DomainConfig = Depends(get_domain_config),
) -> RecordFeedSourceLoader:
    """Return the feed-record loader over the configured raw-record store."""
    return RecordFeedSourceLoader(
        get_raw_record_store(), config.records or RecordsConfig()
    )


def get_scorecard_service(
    config: DomainConfig = Depends(get_domain_config),
    repository: ScorecardRunRepository = Depends(get_scorecard_run_repository),
    record_source: RecordFeedSourceLoader = Depends(get_source_record_loader),
) -> ScorecardService:
    """Return the scorecard service assembled from config, records, and persistence."""
    return create_scorecard_service(config, repository, record_source)


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


from agent.adapters.protocols import (  # noqa: E402  (intentional bottom-of-file import)
    WorkflowRunStoreProtocol,
)
from agent.adapters.runtime import create_workflow_run_store_from_env  # noqa: E402
from agent.protocols import AgentServiceProtocol  # noqa: E402
from agent.service import create_agent_service  # noqa: E402
from agent.workflow_tracking import WorkflowEventTracker  # noqa: E402
from knowledgebases.adapters.in_memory import (  # noqa: E402  (intentional bottom-of-file import)
    InMemoryKnowledgeBaseRepository,
)
from knowledgebases.adapters.object_store import (  # noqa: E402  (intentional bottom-of-file import)
    ObjectStoreKnowledgeBaseRepository,
)
from knowledgebases.protocols import (  # noqa: E402  (intentional bottom-of-file import)
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


def get_graph_entity_detail_payload(
    entity_id: str = Path(..., description="Entity identifier."),
    alert_store: AlertFeedStoreProtocol = Depends(get_alert_feed_store),
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
        alert_store=alert_store,
        kb_repository=kb_repository,
        domain_config=domain_config,
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="Entity not found.")
    return detail


def get_analytics_overview_payload(
    knowledge_base_id: str | None = Query(
        default=None,
        description="Restrict every figure to one knowledge base. Omit for workspace-wide totals.",
    ),
    alert_store: AlertFeedStoreProtocol = Depends(get_alert_feed_store),
    case_service: CaseService = Depends(get_case_service),
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
) -> AnalyticsOverviewResponse:
    """Return the analytics overview computed from durable stores (BL-012).

    The ``kb`` alias matches ``GET /alerts`` (UXA-408). Omitting it preserves
    the workspace-wide behaviour existing consumers depend on.
    """
    return build_analytics_overview(
        alert_store=alert_store,
        case_service=case_service,
        kb_repository=kb_repository,
        knowledge_base_id=knowledge_base_id,
    )


def _resolve_kb_scoped_alert(
    alert_store: AlertFeedStoreProtocol, alert_id: str, knowledge_base_id: str
) -> Alert:
    """Load one alert within a KB scope, or 404.

    Shared by promote and attach so the two paths cannot disagree about what an
    ``Alert`` built from a feed record looks like.
    """
    record = alert_store.get_alert(alert_id)
    if record is None or record.knowledge_base_id != knowledge_base_id:
        raise HTTPException(status_code=404, detail="Alert not found.")
    return Alert(
        id=record.alert_id,
        entity_type=record.entity_type,
        entity_id=record.entity_id,
        severity=record.severity,
        title=record.title,
        reasoning=record.reasoning,
        evidence_pack_id=record.evidence_pack_id,
        created_at=record.created_at,
        status=cast(
            Literal["open", "acknowledged", "investigating", "resolved", "dismissed"],
            record.status if record.status in _ALERT_STATUS_LITERALS else "open",
        ),
        updated_at=record.updated_at,
        acknowledged=record.status == "acknowledged",
    )


def get_case_attach_alert_payload(
    payload: CaseAttachAlertRequest,
    case_id: str = Path(..., description="Case the alert is attached to."),
    knowledge_base_id: str = Query(..., min_length=1, description="Knowledge base scope."),
    service: CaseService = Depends(get_case_service),
    alert_store: AlertFeedStoreProtocol = Depends(get_alert_feed_store),
    evidence_repository: EvidencePackRepository = Depends(get_evidence_pack_repository),
) -> CaseDetailResponse:
    """Attach an alert to a case that already exists (UXA-405).

    Distinct from promote, which opens a *new* case: this is "I already have a
    case, this belongs to it". 409 on a re-attach mirrors the promote-twice
    guard the alert feed already enforces.
    """
    alert = _resolve_kb_scoped_alert(alert_store, payload.alert_id, knowledge_base_id)
    try:
        case = service.attach_alert(
            knowledge_base_id=knowledge_base_id,
            case_id=case_id,
            alert=alert,
            notes=payload.notes,
        )
    except CaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AlertAlreadyAttachedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _assemble_case_detail(
        case, evidence_repository=evidence_repository, alert_store=alert_store
    )


def get_case_promote_payload(
    payload: CasePromoteRequest,
    knowledge_base_id: str = Query(..., min_length=1, description="Knowledge base scope."),
    service: CaseService = Depends(get_case_service),
    alert_store: AlertFeedStoreProtocol = Depends(get_alert_feed_store),
    evidence_repository: EvidencePackRepository = Depends(get_evidence_pack_repository),
) -> CaseDetailResponse:
    """Promote an alert into a durable, KB-scoped case capturing its evidence."""
    alert = _resolve_kb_scoped_alert(alert_store, payload.alert_id, knowledge_base_id)
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
        case, evidence_repository=evidence_repository, alert_store=alert_store
    )


def get_alert_list_payload(
    knowledge_base_id: str | None = Query(default=None),
    status_filter: list[str] | None = Query(default=None, alias="status"),
    severity_filter: list[str] | None = Query(default=None, alias="severity"),
    typology_filter: list[str] | None = Query(default=None, alias="typology"),
    created_from: str | None = Query(default=None, alias="from"),
    created_to: str | None = Query(default=None, alias="to"),
    evidence: str | None = Query(default=None),
    freshness: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    store: AlertFeedStoreProtocol = Depends(get_alert_feed_store),
) -> AlertListResponse:
    """Return the paginated alert feed from the durable ``alert_history`` store."""
    # The store owns the predicate (UXA-408). This used to fetch a first page
    # to learn the total, re-fetch the *entire* alert_history table, then
    # filter and paginate in Python — so reading one KB's queue cost grew with
    # every other KB's alert volume.
    records, total = store.list_alerts(
        knowledge_base_id=knowledge_base_id,
        statuses=status_filter,
        severities=severity_filter,
        tags=typology_filter,
        created_from=created_from,
        created_to=created_to,
        evidence=evidence,
        freshness=freshness,
        limit=limit,
        offset=offset,
    )

    page = (offset // limit) + 1 if limit else 1
    return AlertListResponse(
        items=[_alert_record_to_list_item(record) for record in records],
        page=PageInfo(page=page, page_size=max(limit, 1), total_items=total),
    )


def _require_kb_scoped_alert_record(
    store: AlertFeedStoreProtocol, alert_id: str, knowledge_base_id: str
) -> AlertHistoryRecord:
    """Load one alert row within a KB scope, or 404.

    ``alert_id`` is a globally unique UUID, so an id-only lookup is never
    *ambiguous* — but that is an argument about lookup, not about
    authorisation. Without this check the detail and acknowledge routes served
    and mutated any knowledge base's alert to any caller, while their siblings
    ``/cases/{id}`` and ``/evidence-packs/{id}`` already 404 on a mismatch.

    The 404 (rather than 403) matches those siblings: a caller outside the KB
    is not told the alert exists.
    """
    record = store.get_alert(alert_id)
    if record is None or record.knowledge_base_id != knowledge_base_id:
        raise HTTPException(
            status_code=404, detail=f"Alert '{alert_id}' was not found."
        )
    return record


def get_alert_detail_payload(
    alert_id: str = Path(..., description="Alert identifier."),
    knowledge_base_id: str = Query(
        ..., min_length=1, description="Knowledge base identifier."
    ),
    store: AlertFeedStoreProtocol = Depends(get_alert_feed_store),
) -> AlertDetailResponse:
    """Return one alert detail with related entities and policy citations.

    ``alert_history`` does not carry related-entity or policy-citation columns
    (BL-005/BL-012 keep those on the evidence pack / policy item read models),
    so this defaults to the alert's own entity and an empty citation list.
    """
    record = _require_kb_scoped_alert_record(store, alert_id, knowledge_base_id)
    return AlertDetailResponse(
        alert=_alert_record_to_list_item(record),
        related_entity_ids=[record.entity_id],
        policy_citations=[],
    )


def get_alert_acknowledge_payload(
    alert_id: str = Path(..., description="Alert identifier."),
    knowledge_base_id: str = Query(
        ..., min_length=1, description="Knowledge base identifier."
    ),
    store: AlertFeedStoreProtocol = Depends(get_alert_feed_store),
) -> ApiEnvelope:
    """Acknowledge an alert in the durable store; returns a status receipt."""
    # Ownership is settled before the mutation: an alert never changes KB, so
    # the checked record cannot drift out from under the update.
    _require_kb_scoped_alert_record(store, alert_id, knowledge_base_id)
    updated = store.acknowledge(alert_id)
    if updated is None:
        raise HTTPException(
            status_code=404, detail=f"Alert '{alert_id}' was not found."
        )
    return ApiEnvelope(
        status="accepted",
        message=f"Alert '{updated.alert_id}' is now {updated.status}.",
    )


def _latest_alert_triage_event(record: AlertHistoryRecord) -> AlertTriageEvent:
    if not record.triage_history:
        raise HTTPException(
            status_code=500,
            detail=f"Alert '{record.alert_id}' mutation did not record an audit event.",
        )
    return record.triage_history[-1]


def build_alert_assignment_payload(
    *,
    alert_id: str,
    payload: AlertAssignmentRequest,
    store: AlertFeedStoreProtocol,
    actor: str,
) -> AlertOperationResponse:
    """Assign one scoped alert and return its updated row plus audit receipt."""
    _require_kb_scoped_alert_record(store, alert_id, payload.knowledge_base_id)
    updated = store.assign(
        alert_id,
        knowledge_base_id=payload.knowledge_base_id,
        assignee=payload.assignee,
        actor=actor,
    )
    if updated is None:
        raise HTTPException(
            status_code=404, detail=f"Alert '{alert_id}' was not found."
        )
    event = _latest_alert_triage_event(updated)
    return AlertOperationResponse(
        status="accepted",
        message=f"Alert '{updated.alert_id}' is assigned.",
        alert=_alert_record_to_list_item(updated),
        audit_event=_alert_triage_event_to_response(event),
    )


def build_alert_status_update_payload(
    *,
    alert_id: str,
    payload: AlertStatusUpdateRequest,
    store: AlertFeedStoreProtocol,
    actor: str,
) -> AlertOperationResponse:
    """Transition one scoped alert and return its updated row plus audit receipt."""
    _require_kb_scoped_alert_record(store, alert_id, payload.knowledge_base_id)
    try:
        updated = store.transition_status(
            alert_id,
            knowledge_base_id=payload.knowledge_base_id,
            status=payload.status,
            actor=actor,
            reason=payload.reason,
        )
    except AlertLifecycleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(
            status_code=404, detail=f"Alert '{alert_id}' was not found."
        )
    event = _latest_alert_triage_event(updated)
    return AlertOperationResponse(
        status="accepted",
        message=f"Alert '{updated.alert_id}' is now {updated.status}.",
        alert=_alert_record_to_list_item(updated),
        audit_event=_alert_triage_event_to_response(event),
    )


def build_alert_bulk_status_update_payload(
    *,
    payload: AlertBulkStatusUpdateRequest,
    store: AlertFeedStoreProtocol,
    actor: str,
) -> AlertBulkStatusUpdateResponse:
    """Transition each selected scoped alert where the lifecycle allows it."""
    updated_alerts: list[AlertListItem] = []
    rejected_alerts: list[AlertBulkRejection] = []
    for alert_id in payload.alert_ids:
        record = store.get_alert(alert_id)
        if record is None or record.knowledge_base_id != payload.knowledge_base_id:
            rejected_alerts.append(
                AlertBulkRejection(alert_id=alert_id, reason="not_found")
            )
            continue
        try:
            updated = store.transition_status(
                alert_id,
                knowledge_base_id=payload.knowledge_base_id,
                status=payload.status,
                actor=actor,
                reason=payload.reason,
            )
        except AlertLifecycleError:
            rejected_alerts.append(
                AlertBulkRejection(alert_id=alert_id, reason="invalid_transition")
            )
            continue
        if updated is None:
            rejected_alerts.append(
                AlertBulkRejection(alert_id=alert_id, reason="not_found")
            )
            continue
        updated_alerts.append(_alert_record_to_list_item(updated))
    return AlertBulkStatusUpdateResponse(
        status="accepted",
        message=(
            f"Updated {len(updated_alerts)} alert"
            f"{'' if len(updated_alerts) == 1 else 's'}."
        ),
        updated_alerts=updated_alerts,
        rejected_alerts=rejected_alerts,
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


# ---------------------------------------------------------------------------
# Domain hot-swap core (config.05 / E3+E5).
#
# Every ``@lru_cache`` singleton in this module is derived (directly or
# transitively) from the active ``DomainConfig``, so a domain swap must clear
# them all together. The registry below is the single authoritative list; the
# regression test in ``tests/api/test_dependency_swap.py`` fails if a new
# ``@lru_cache`` site is added to this module without being registered here.
# ---------------------------------------------------------------------------


class _ClearableCache(Protocol):
    """Structural type for an ``functools.lru_cache`` wrapper we can clear."""

    def cache_clear(self) -> None: ...


CONFIG_CACHE_REGISTRY: dict[str, _ClearableCache] = {
    "get_domain_config": get_domain_config,
    "get_parser_registry": get_parser_registry,
    "get_remote_fetcher": get_remote_fetcher,
    "get_parser_orchestrator": get_parser_orchestrator,
    "get_event_bus_settings": get_event_bus_settings,
    "get_event_bus": get_event_bus,
    "get_session_store": get_session_store,
    "get_object_store": get_object_store,
    "get_graph_repository": get_graph_repository,
    "get_graph_service": get_graph_service,
    "get_vector_store": get_vector_store,
    "get_vectorstore_service": get_vectorstore_service,
    "get_embedder": get_embedder,
    "get_embeddings_service": get_embeddings_service,
    "get_llm_client": get_llm_client,
    "get_llm_service": get_llm_service,
    "get_monitoring_source": get_monitoring_source,
    "get_monitoring_service": get_monitoring_service,
    "get_risk_signal_source": get_risk_signal_source,
    "get_risk_service": get_risk_service,
    "get_timeseries_history_source": get_timeseries_history_source,
    "get_timeseries_service": get_timeseries_service,
    "get_timeseries_anomaly_store": get_timeseries_anomaly_store,
    "get_record_column_source": get_record_column_source,
    "get_entity_series_source": get_entity_series_source,
    "get_graph_snapshot_source": get_graph_snapshot_source,
    "get_gnn_service": get_gnn_service,
    "get_ingestion_recovery_store": get_ingestion_recovery_store,
    "get_ingestion_service": get_ingestion_service,
    "get_connection_provider": get_connection_provider,
    "get_raw_record_store": get_raw_record_store,
    "get_document_status_store": get_document_status_store,
    "get_dlq_record_store": get_dlq_record_store,
    "get_derived_signal_store": get_derived_signal_store,
    "get_risk_history_writer": get_risk_history_writer,
    "get_observation_writer": get_observation_writer,
    "get_alert_history_writer": get_alert_history_writer,
    "get_alert_feed_store": get_alert_feed_store,
    "get_entity_metric_repository": get_entity_metric_repository,
    "get_knowledge_base_repository": get_knowledge_base_repository,
    "get_rag_service": get_rag_service,
}
"""All ``@lru_cache`` singletons in this module, cleared together on swap."""


# Config-derived objects memoized on ``app.state`` by the per-app dependency
# helpers above. Purged (and ``api_state`` eagerly rebuilt) on swap so the next
# request lazily reconstructs them against the new pack's backends.
_CONFIG_DERIVED_APP_STATE_ATTRS: tuple[str, ...] = (
    "api_state",
    "evidence_pack_repository",
    "case_repository",
    "conversation_repository",
    "policy_repository",
    "scorecard_run_repository",
    "score_run_repository",
    "risk_projection_repository",
)

_CONFIG_SWAP_LOCK = threading.Lock()
_config_generation = 0

_T = TypeVar("_T")


def _memoize_config_derived(
    app: FastAPI,
    attr: str,
    factory: Callable[[], _T],
    *,
    guard: Callable[[object], bool],
) -> _T:
    """Memoize a config-derived object onto ``app.state`` swap-safely (M2).

    A naive unlocked check-then-act memoizer races the swap: a threadpool
    request can build an object against the *old* pack, the locked reset
    completes (purging ``app.state``), and the thread then memoizes the stale
    object — served until the next swap (for ``api_state`` this can clobber
    live-RAG state with the seeded fallback). This helper makes post-reset
    memoization of a pre-reset build impossible:

    1. Snapshot the swap generation under the lock, build outside the lock
       (builds may be slow; the factory itself must never take the lock).
    2. Write under the lock only if the generation is unchanged; otherwise a
       swap completed mid-build — discard the stale candidate and rebuild
       against the new pack.

    Note the ``@lru_cache`` singletons themselves retain the documented miss
    race (m4): a lookup that misses concurrently with a reset may construct
    and transiently *use* an instance that loses the cache-fill race and is
    discarded — never torn, and never re-served after the swap.
    """
    existing = getattr(app.state, attr, None)
    if guard(existing):
        return cast("_T", existing)
    while True:
        with _CONFIG_SWAP_LOCK:
            generation = _config_generation
        candidate = factory()
        with _CONFIG_SWAP_LOCK:
            if _config_generation != generation:
                # A swap completed while we were building: the candidate was
                # derived from the previous pack. Never memoize it.
                continue
            existing = getattr(app.state, attr, None)
            if guard(existing):
                return cast("_T", existing)
            setattr(app.state, attr, candidate)
            return candidate


def get_config_generation() -> int:
    """Return the monotonic swap generation token (0 until the first reset).

    Bumped exactly once per :func:`reset_domain_config_caches`. A request that
    records the generation when it starts can detect that a swap happened
    mid-request by comparing against the current value.
    """
    with _CONFIG_SWAP_LOCK:
        return _config_generation


def build_api_state() -> ApiState:
    """Build a fresh :class:`ApiState` from the active domain configuration.

    Composes the live RAG service (embeddings → vectorstore → graph → LLM,
    BL-001); on composition failure it logs the exception and falls back to
    the seeded in-memory pipeline so the API still serves.
    """
    domain_config = get_domain_config()
    try:
        live_rag_service: RagServiceProtocol | None = get_rag_service()
    except Exception:
        logger.exception(
            "Failed to compose live RAG service; falling back to seeded in-memory pipeline."
        )
        live_rag_service = None
    return create_api_state(domain_config, rag_service=live_rag_service)


def reset_domain_config_caches(app: FastAPI | None = None) -> int:
    """Atomically swap every config-derived singleton to the active pack.

    Clears every ``@lru_cache`` wrapper in :data:`CONFIG_CACHE_REGISTRY`; when
    ``app`` is given, also purges the config-derived per-app state attributes
    (:data:`_CONFIG_DERIVED_APP_STATE_ATTRS`) and eagerly rebuilds
    ``app.state.api_state`` via :func:`build_api_state`. Returns the new
    swap generation (see :func:`get_config_generation`).

    Callers MUST follow swap-once-success discipline: fully load + validate
    the candidate pack (``load_config(path)``) and persist the pointer
    (``config.store.write_active_pack``) *before* calling this — a failure in
    either step leaves every cache untouched and the old pack keeps serving.

    Atomicity guarantee:

    - Swaps are **serialized** by a module-level lock; no two resets interleave.
    - The reset is **all-or-nothing at the registry level**: within one
      critical section every registered singleton is cleared and
      ``app.state.api_state`` is rebuilt — after this function returns, any
      new dependency resolution observes only new-pack singletons.
    - In-flight requests that resolved singletons **before** the reset keep
      those (old-pack) objects for the rest of that resolution; requests
      resolving **concurrently** with the reset may observe a mix across
      *separate* singleton lookups, but each individual singleton is either
      wholly old or wholly new — never torn. Use :func:`get_config_generation`
      to detect a swap mid-request if needed.

    Accepted limitations (red-cell m2/m3, by design):

    - The reset runs synchronously and holds the lock while rebuilding
      ``api_state`` (adapter composition included), blocking the event loop
      for that duration. Swaps are rare, operator-initiated actions; do not
      call this from a hot path.
    - If the pack file becomes unreadable *after* the pointer was persisted
      but before/while caches rebuild, subsequent resolutions fail loudly
      (``ConfigLoadError`` → 500) with caches cleared rather than silently
      serving a stale pack. Recover by activating a valid pack (or
      ``config.store.clear_active_pack()`` to revert to ``CHILI_CONFIG_PATH``).
    """
    global _config_generation
    with _CONFIG_SWAP_LOCK:
        for wrapper in CONFIG_CACHE_REGISTRY.values():
            wrapper.cache_clear()
        if app is not None:
            for attr in _CONFIG_DERIVED_APP_STATE_ATTRS:
                if hasattr(app.state, attr):
                    delattr(app.state, attr)
            app.state.api_state = build_api_state()
        _config_generation += 1
        return _config_generation
