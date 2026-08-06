"""KB-scoped capability registry API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.contracts import (
    CapabilityDomainCompatibilityResponse,
    CapabilityExampleResponse,
    CapabilityHealthResponse,
    CapabilityListResponse,
    CapabilityManifestResponse,
    CapabilityPermissionResponse,
    CapabilitySideEffectClassValue,
)
from api.dependencies import (
    get_capability_registry_service,
    get_domain_config,
    get_knowledge_base_repository,
)
from api.middleware.auth import User
from api.middleware.rbac import require_role
from capabilities.models import CapabilityManifest, CapabilityQuery
from capabilities.service import CapabilityRegistryService
from config.schema import DomainConfig
from knowledgebases.protocols import KnowledgeBaseRepository
from shared.types import KnowledgeBase

__all__ = ["router"]

router = APIRouter(
    prefix="/knowledgebases/{knowledge_base_id}/capabilities",
    tags=["capabilities"],
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


@router.get("", response_model=CapabilityListResponse)
def list_capabilities(
    knowledge_base_id: str,
    role: str | None = Query(default=None, min_length=1),
    module: str | None = Query(default=None, min_length=1),
    side_effect_class: CapabilitySideEffectClassValue | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    registry: CapabilityRegistryService = Depends(get_capability_registry_service),
    domain_config: DomainConfig = Depends(get_domain_config),
    user: User = Depends(require_role("viewer")),
) -> CapabilityListResponse:
    """Return registered capabilities available to one knowledge base."""

    _, domain_name = _require_knowledge_base(
        knowledge_base_id,
        kb_repository,
        user,
        domain_config,
    )
    page = registry.list_capabilities(
        CapabilityQuery(
            domain_name=domain_name,
            role=role,
            module=module,
            side_effect_class=side_effect_class,
            limit=limit,
            offset=offset,
        )
    )
    return CapabilityListResponse(
        items=[_capability_response(item) for item in page.items],
        total=page.total_items,
        limit=page.limit,
        offset=page.offset,
    )


def _capability_response(manifest: CapabilityManifest) -> CapabilityManifestResponse:
    return CapabilityManifestResponse(
        capability_id=manifest.capability_id,
        version=manifest.version,
        module=manifest.module,
        label=manifest.label,
        description=manifest.description,
        input_schema=dict(manifest.input_schema),
        output_schema=dict(manifest.output_schema),
        side_effect_class=manifest.side_effect_class,
        permission=CapabilityPermissionResponse(
            required_roles=list(manifest.permission.required_roles),
            requires_audit=manifest.permission.requires_audit,
            required_scopes=list(manifest.permission.required_scopes),
        ),
        domain_compatibility=CapabilityDomainCompatibilityResponse(
            supported_domains=list(manifest.domain_compatibility.supported_domains),
            unsupported_domains=list(manifest.domain_compatibility.unsupported_domains),
            environment_tags=list(manifest.domain_compatibility.environment_tags),
        ),
        health=CapabilityHealthResponse(
            status=manifest.health.status,
            last_checked_at=manifest.health.last_checked_at,
            details=manifest.health.details,
        ),
        examples=[
            CapabilityExampleResponse(
                name=example.name,
                input=dict(example.input),
                output=dict(example.output),
            )
            for example in manifest.examples
        ],
    )


def _not_found(resource: str, identifier: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{resource} '{identifier}' not found.",
    )
