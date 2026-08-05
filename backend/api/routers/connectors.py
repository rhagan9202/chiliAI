"""KB-scoped connector management API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.contracts import (
    ConnectorCreateRequest,
    ConnectorListResponse,
    ConnectorMappingRefPayload,
    ConnectorQuarantineListResponse,
    ConnectorQuarantineRecordResponse,
    ConnectorResponse,
    ConnectorSchedulePayload,
    ConnectorSyncCountersResponse,
    ConnectorSyncRunListResponse,
    ConnectorSyncRunRequest,
    ConnectorSyncRunResponse,
)
from api.dependencies import (
    get_connector_service,
    get_domain_config,
    get_knowledge_base_repository,
)
from api.middleware.auth import User
from api.middleware.rbac import require_role
from config.schema import DomainConfig
from connectors.models import (
    ConnectorDefinition,
    ConnectorDefinitionCreate,
    ConnectorMappingRef,
    ConnectorQuarantineRecord,
    ConnectorSchedule,
    ConnectorSyncRun,
)
from connectors.service import ConnectorService
from knowledgebases.protocols import KnowledgeBaseRepository
from shared.types import KnowledgeBase

__all__ = ["router"]

router = APIRouter(
    prefix="/knowledgebases/{knowledge_base_id}/connectors",
    tags=["connectors"],
)


def _can_access_knowledge_base(user: User, knowledge_base_id: str) -> bool:
    allowed = user.knowledge_base_ids
    return allowed is None or knowledge_base_id in allowed or "admin" in user.roles


def _require_knowledge_base(
    knowledge_base_id: str,
    repository: KnowledgeBaseRepository,
    user: User,
    domain_config: DomainConfig,
) -> tuple[KnowledgeBase, str]:
    if not _can_access_knowledge_base(user, knowledge_base_id):
        raise _not_found("Knowledge base", knowledge_base_id)
    kb = repository.get(knowledge_base_id)
    if kb is None:
        raise _not_found("Knowledge base", knowledge_base_id)
    domain_name = getattr(kb, "domain_name", None)
    if isinstance(domain_name, str) and domain_name:
        return kb, domain_name
    return kb, kb.domain or domain_config.domain.name


@router.get("", response_model=ConnectorListResponse)
def list_connectors(
    knowledge_base_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    connector_service: ConnectorService = Depends(get_connector_service),
    domain_config: DomainConfig = Depends(get_domain_config),
    user: User = Depends(require_role("viewer")),
) -> ConnectorListResponse:
    """Return connector definitions for one knowledge base."""

    _require_knowledge_base(knowledge_base_id, kb_repository, user, domain_config)
    page = connector_service.list_connectors(
        knowledge_base_id=knowledge_base_id,
        limit=limit,
        offset=offset,
    )
    return ConnectorListResponse(
        items=[_connector_response(item) for item in page.items],
        total=page.total_items,
        limit=page.limit,
        offset=page.offset,
    )


@router.post("", response_model=ConnectorResponse)
def register_connector(
    knowledge_base_id: str,
    payload: ConnectorCreateRequest,
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    connector_service: ConnectorService = Depends(get_connector_service),
    domain_config: DomainConfig = Depends(get_domain_config),
    user: User = Depends(require_role("analyst")),
) -> ConnectorResponse:
    """Register a connector definition for one knowledge base."""

    _, domain_name = _require_knowledge_base(
        knowledge_base_id,
        kb_repository,
        user,
        domain_config,
    )
    try:
        definition = connector_service.register_connector(
            knowledge_base_id,
            ConnectorDefinitionCreate(
                connector_id=payload.connector_id,
                name=payload.name,
                source_type=payload.source_type,
                knowledge_base_id=knowledge_base_id,
                domain_name=payload.domain_name or domain_name,
                credentials_ref=payload.credentials_ref,
                schedule=ConnectorSchedule(**payload.schedule.model_dump()),
                mapping=ConnectorMappingRef(**payload.mapping.model_dump()),
                config=payload.config,
            ),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return _connector_response(definition)


@router.post("/{connector_id}/sync-runs", response_model=ConnectorSyncRunResponse)
def start_sync_run(
    knowledge_base_id: str,
    connector_id: str,
    payload: ConnectorSyncRunRequest,
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    connector_service: ConnectorService = Depends(get_connector_service),
    domain_config: DomainConfig = Depends(get_domain_config),
    user: User = Depends(require_role("analyst")),
) -> ConnectorSyncRunResponse:
    """Create or reuse a manual connector sync run."""

    _require_knowledge_base(knowledge_base_id, kb_repository, user, domain_config)
    try:
        run = connector_service.start_sync(
            knowledge_base_id=knowledge_base_id,
            connector_id=connector_id,
            requested_by=user.user_id,
            idempotency_key=payload.idempotency_key,
        )
    except KeyError as exc:
        raise _not_found("Connector", connector_id) from exc
    return _sync_run_response(run)


@router.get("/{connector_id}/sync-runs", response_model=ConnectorSyncRunListResponse)
def list_sync_runs(
    knowledge_base_id: str,
    connector_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    connector_service: ConnectorService = Depends(get_connector_service),
    domain_config: DomainConfig = Depends(get_domain_config),
    user: User = Depends(require_role("viewer")),
) -> ConnectorSyncRunListResponse:
    """Return sync runs for one connector."""

    _require_knowledge_base(knowledge_base_id, kb_repository, user, domain_config)
    page = connector_service.list_runs(
        knowledge_base_id=knowledge_base_id,
        connector_id=connector_id,
        limit=limit,
        offset=offset,
    )
    return ConnectorSyncRunListResponse(
        items=[_sync_run_response(item) for item in page.items],
        total=page.total_items,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{connector_id}/quarantine", response_model=ConnectorQuarantineListResponse)
def list_quarantine(
    knowledge_base_id: str,
    connector_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    connector_service: ConnectorService = Depends(get_connector_service),
    domain_config: DomainConfig = Depends(get_domain_config),
    user: User = Depends(require_role("viewer")),
) -> ConnectorQuarantineListResponse:
    """Return quarantined records for one connector."""

    _require_knowledge_base(knowledge_base_id, kb_repository, user, domain_config)
    page = connector_service.list_quarantine(
        knowledge_base_id=knowledge_base_id,
        connector_id=connector_id,
        limit=limit,
        offset=offset,
    )
    return ConnectorQuarantineListResponse(
        items=[_quarantine_response(item) for item in page.items],
        total=page.total_items,
        limit=page.limit,
        offset=page.offset,
    )


def _connector_response(definition: ConnectorDefinition) -> ConnectorResponse:
    return ConnectorResponse(
        connector_id=definition.connector_id,
        name=definition.name,
        source_type=definition.source_type,
        knowledge_base_id=definition.knowledge_base_id,
        domain_name=definition.domain_name,
        credentials_display=definition.credentials_display,
        schedule=ConnectorSchedulePayload(
            mode=definition.schedule.mode,
            expression=definition.schedule.expression,
        ),
        mapping=ConnectorMappingRefPayload(
            mapping_id=definition.mapping.mapping_id,
            mapping_version=definition.mapping.mapping_version,
            feed_name=definition.mapping.feed_name,
        ),
        config=dict(definition.config),
        status=definition.status,
        created_at=definition.created_at,
        updated_at=definition.updated_at,
    )


def _sync_run_response(run: ConnectorSyncRun) -> ConnectorSyncRunResponse:
    return ConnectorSyncRunResponse(
        run_id=run.run_id,
        connector_id=run.connector_id,
        knowledge_base_id=run.knowledge_base_id,
        requested_by=run.requested_by,
        status=run.status,
        counters=ConnectorSyncCountersResponse(
            pulled=run.counters.pulled,
            accepted=run.counters.accepted,
            quarantined=run.counters.quarantined,
            failed=run.counters.failed,
        ),
        idempotency_key=run.idempotency_key,
        ingest_correlation_id=run.ingest_correlation_id,
        source_cursor=run.source_cursor,
        error_message=run.error_message,
        started_at=run.started_at,
        completed_at=run.completed_at,
        updated_at=run.updated_at,
    )


def _quarantine_response(
    record: ConnectorQuarantineRecord,
) -> ConnectorQuarantineRecordResponse:
    return ConnectorQuarantineRecordResponse(
        quarantine_id=record.quarantine_id,
        run_id=record.run_id,
        connector_id=record.connector_id,
        knowledge_base_id=record.knowledge_base_id,
        source_record_id=record.source_record_id,
        reason=record.reason,
        raw_ref=record.raw_ref,
        created_at=record.created_at,
    )


def _not_found(resource: str, identifier: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{resource} '{identifier}' not found.",
    )
