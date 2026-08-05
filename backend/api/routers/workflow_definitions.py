"""KB-scoped workflow definition API endpoints."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

from api._workflow_projection import project_workflow_run
from api.contracts import (
    WorkflowDefinitionCreatePayload,
    WorkflowDefinitionListResponse,
    WorkflowDefinitionResponse,
    WorkflowDefinitionRunRequestPayload,
    WorkflowDefinitionUpdatePayload,
    WorkflowRunResponse,
    WorkflowStepDefinitionResponse,
)
from api.dependencies import (
    get_domain_config,
    get_knowledge_base_repository,
    get_workflow_definition_service,
)
from api.middleware.auth import User
from api.middleware.rbac import require_role
from config.schema import DomainConfig
from knowledgebases.protocols import KnowledgeBaseRepository
from shared.types import KnowledgeBase
from workflow_definitions.models import (
    WorkflowDefinition,
    WorkflowDefinitionCreate,
    WorkflowDefinitionRunRequest,
    WorkflowDefinitionUpdate,
    WorkflowStepDefinition,
)
from workflow_definitions.service import (
    WorkflowDefinitionConflictError,
    WorkflowDefinitionNotFoundError,
    WorkflowDefinitionService,
    WorkflowDefinitionValidationError,
)

__all__ = ["router"]

router = APIRouter(
    prefix="/knowledgebases/{knowledge_base_id}/workflow-definitions",
    tags=["workflow-definitions"],
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
    return kb, _resolve_domain_name(kb, domain_config)


def _resolve_domain_name(kb: KnowledgeBase, domain_config: DomainConfig) -> str:
    domain_name = getattr(kb, "domain_name", None)
    if isinstance(domain_name, str) and domain_name:
        return domain_name
    return kb.domain or domain_config.domain.name


@router.get("", response_model=WorkflowDefinitionListResponse)
def list_workflow_definitions(
    knowledge_base_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    service: WorkflowDefinitionService = Depends(get_workflow_definition_service),
    domain_config: DomainConfig = Depends(get_domain_config),
    user: User = Depends(require_role("viewer")),
) -> WorkflowDefinitionListResponse:
    """Return workflow definitions for one knowledge base."""
    _require_knowledge_base(knowledge_base_id, kb_repository, user, domain_config)
    page = service.list_definitions(
        knowledge_base_id=knowledge_base_id,
        limit=limit,
        offset=offset,
    )
    return WorkflowDefinitionListResponse(
        items=[_definition_response(item) for item in page.items],
        total=page.total_items,
        limit=page.limit,
        offset=page.offset,
    )


@router.post("", response_model=WorkflowDefinitionResponse)
def create_workflow_definition(
    knowledge_base_id: str,
    payload: WorkflowDefinitionCreatePayload,
    request: Request,
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    service: WorkflowDefinitionService = Depends(get_workflow_definition_service),
    domain_config: DomainConfig = Depends(get_domain_config),
    user: User = Depends(require_role("analyst")),
) -> WorkflowDefinitionResponse:
    """Create a draft workflow definition for one knowledge base."""
    _, domain_name = _require_knowledge_base(
        knowledge_base_id,
        kb_repository,
        user,
        domain_config,
    )
    correlation_id = _correlation_id(request)
    try:
        definition = service.create_draft(
            knowledge_base_id,
            _create_model(payload, domain_name=domain_name),
            correlation_id=correlation_id,
            **_actor_kwargs(user),
        )
    except WorkflowDefinitionValidationError as exc:
        raise _validation_error(exc) from exc
    except WorkflowDefinitionConflictError as exc:
        raise _conflict(exc) from exc
    return _definition_response(definition)


@router.get(
    "/{definition_id}/versions/{version}",
    response_model=WorkflowDefinitionResponse,
)
def get_workflow_definition(
    knowledge_base_id: str,
    definition_id: str = Path(...),
    version: str = Path(...),
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    service: WorkflowDefinitionService = Depends(get_workflow_definition_service),
    domain_config: DomainConfig = Depends(get_domain_config),
    user: User = Depends(require_role("viewer")),
) -> WorkflowDefinitionResponse:
    """Return one workflow definition snapshot."""
    _require_knowledge_base(knowledge_base_id, kb_repository, user, domain_config)
    try:
        definition = service.get_definition(knowledge_base_id, definition_id, version)
    except WorkflowDefinitionNotFoundError as exc:
        raise _not_found("Workflow definition", f"{definition_id}:{version}") from exc
    return _definition_response(definition)


@router.put(
    "/{definition_id}/versions/{version}",
    response_model=WorkflowDefinitionResponse,
)
def update_workflow_definition(
    knowledge_base_id: str,
    payload: WorkflowDefinitionUpdatePayload,
    request: Request,
    definition_id: str = Path(...),
    version: str = Path(...),
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    service: WorkflowDefinitionService = Depends(get_workflow_definition_service),
    domain_config: DomainConfig = Depends(get_domain_config),
    user: User = Depends(require_role("analyst")),
) -> WorkflowDefinitionResponse:
    """Update one draft workflow definition snapshot."""
    _, domain_name = _require_knowledge_base(
        knowledge_base_id,
        kb_repository,
        user,
        domain_config,
    )
    correlation_id = _correlation_id(request)
    try:
        definition = service.update_draft(
            knowledge_base_id,
            definition_id,
            version,
            _update_model(payload, domain_name=domain_name),
            correlation_id=correlation_id,
            **_actor_kwargs(user),
        )
    except WorkflowDefinitionNotFoundError as exc:
        raise _not_found("Workflow definition", f"{definition_id}:{version}") from exc
    except WorkflowDefinitionValidationError as exc:
        raise _validation_error(exc) from exc
    except WorkflowDefinitionConflictError as exc:
        raise _conflict(exc) from exc
    return _definition_response(definition)


@router.post(
    "/{definition_id}/versions/{version}/approve",
    response_model=WorkflowDefinitionResponse,
)
def approve_workflow_definition(
    knowledge_base_id: str,
    request: Request,
    definition_id: str = Path(...),
    version: str = Path(...),
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    service: WorkflowDefinitionService = Depends(get_workflow_definition_service),
    domain_config: DomainConfig = Depends(get_domain_config),
    user: User = Depends(require_role("admin")),
) -> WorkflowDefinitionResponse:
    """Approve one draft workflow definition snapshot."""
    _require_knowledge_base(knowledge_base_id, kb_repository, user, domain_config)
    correlation_id = _correlation_id(request)
    try:
        definition = service.approve_definition(
            knowledge_base_id,
            definition_id,
            version,
            correlation_id=correlation_id,
            **_actor_kwargs(user),
        )
    except WorkflowDefinitionNotFoundError as exc:
        raise _not_found("Workflow definition", f"{definition_id}:{version}") from exc
    except WorkflowDefinitionConflictError as exc:
        raise _conflict(exc) from exc
    return _definition_response(definition)


@router.post(
    "/{definition_id}/versions/{version}/retire",
    response_model=WorkflowDefinitionResponse,
)
def retire_workflow_definition(
    knowledge_base_id: str,
    request: Request,
    definition_id: str = Path(...),
    version: str = Path(...),
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    service: WorkflowDefinitionService = Depends(get_workflow_definition_service),
    domain_config: DomainConfig = Depends(get_domain_config),
    user: User = Depends(require_role("admin")),
) -> WorkflowDefinitionResponse:
    """Retire one approved workflow definition snapshot."""
    _require_knowledge_base(knowledge_base_id, kb_repository, user, domain_config)
    correlation_id = _correlation_id(request)
    try:
        definition = service.retire_definition(
            knowledge_base_id,
            definition_id,
            version,
            correlation_id=correlation_id,
            **_actor_kwargs(user),
        )
    except WorkflowDefinitionNotFoundError as exc:
        raise _not_found("Workflow definition", f"{definition_id}:{version}") from exc
    except WorkflowDefinitionConflictError as exc:
        raise _conflict(exc) from exc
    return _definition_response(definition)


@router.post(
    "/{definition_id}/versions/{version}/run",
    response_model=WorkflowRunResponse,
)
def run_workflow_definition(
    knowledge_base_id: str,
    payload: WorkflowDefinitionRunRequestPayload,
    request: Request,
    definition_id: str = Path(...),
    version: str = Path(...),
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    service: WorkflowDefinitionService = Depends(get_workflow_definition_service),
    domain_config: DomainConfig = Depends(get_domain_config),
    user: User = Depends(require_role("analyst")),
) -> WorkflowRunResponse:
    """Queue a run for one approved workflow definition snapshot."""
    _require_knowledge_base(knowledge_base_id, kb_repository, user, domain_config)
    correlation_id = _correlation_id(request)
    try:
        run = service.run_definition(
            knowledge_base_id,
            definition_id,
            version,
            WorkflowDefinitionRunRequest.model_validate(payload.model_dump()),
            correlation_id=correlation_id,
            **_actor_kwargs(user),
        )
    except WorkflowDefinitionNotFoundError as exc:
        raise _not_found("Workflow definition", f"{definition_id}:{version}") from exc
    except WorkflowDefinitionValidationError as exc:
        raise _validation_error(exc) from exc
    except WorkflowDefinitionConflictError as exc:
        raise _conflict(exc) from exc
    return project_workflow_run(run)


def _create_model(
    payload: WorkflowDefinitionCreatePayload,
    *,
    domain_name: str,
) -> WorkflowDefinitionCreate:
    data = payload.model_dump()
    data["domain_name"] = domain_name
    return WorkflowDefinitionCreate.model_validate(data)


def _update_model(
    payload: WorkflowDefinitionUpdatePayload,
    *,
    domain_name: str,
) -> WorkflowDefinitionUpdate:
    data = payload.model_dump(exclude_unset=True)
    data["domain_name"] = domain_name
    return WorkflowDefinitionUpdate.model_validate(data)


def _definition_response(definition: WorkflowDefinition) -> WorkflowDefinitionResponse:
    return WorkflowDefinitionResponse(
        snapshot_id=definition.snapshot_id,
        definition_id=definition.definition_id,
        knowledge_base_id=definition.knowledge_base_id,
        domain_name=definition.domain_name,
        name=definition.name,
        description=definition.description,
        version=definition.version,
        status=definition.status,
        allowed_capability_refs=list(definition.allowed_capability_refs),
        steps=[_step_response(step) for step in definition.steps],
        created_by=definition.created_by,
        approved_by=definition.approved_by,
        created_at=definition.created_at,
        updated_at=definition.updated_at,
        approved_at=definition.approved_at,
        retired_at=definition.retired_at,
    )


def _step_response(step: WorkflowStepDefinition) -> WorkflowStepDefinitionResponse:
    retry_policy = (
        None if step.retry_policy is None else step.retry_policy.model_dump()
    )
    return WorkflowStepDefinitionResponse(
        step_id=step.step_id,
        label=step.label,
        capability_ref=step.capability_ref,
        input_refs=list(step.input_refs),
        output_refs=list(step.output_refs),
        condition=step.condition,
        retry_policy=cast(dict[str, int] | None, retry_policy),
        requires_human_approval=step.requires_human_approval,
        on_failure=step.on_failure.value,
    )


def _actor_kwargs(user: User) -> dict[str, Any]:
    return {
        "actor_user_id": user.user_id,
        "actor_email": user.email,
        "actor_roles": _roles(user.roles),
    }


def _roles(roles: Sequence[str]) -> list[str]:
    return list(roles)


def _correlation_id(request: Request) -> str:
    correlation_id = (
        request.headers.get("x-request-id")
        or request.headers.get("x-correlation-id")
        or "workflow-definition-request"
    )
    request.state.correlation_id = correlation_id
    return correlation_id


def _not_found(resource: str, identifier: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{resource} '{identifier}' not found.",
    )


def _validation_error(exc: WorkflowDefinitionValidationError) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail=exc.errors,
    )


def _conflict(exc: WorkflowDefinitionConflictError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
