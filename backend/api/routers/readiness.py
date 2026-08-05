"""KB-scoped readiness API endpoints."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, HTTPException, status

from api.contracts import (
    KnowledgeBaseReadinessResponse,
    ReadinessComponentResponse,
    ReadinessIssueResponse,
    ReadinessKnowledgeBaseSummaryResponse,
)
from api.dependencies import get_knowledge_base_repository, get_readiness_service
from api.middleware.auth import User
from api.middleware.rbac import require_role
from knowledgebases.protocols import KnowledgeBaseRepository
from readiness.models import ReadinessComponent, ReadinessIssue, ReadinessResponse
from readiness.service import ReadinessService

__all__ = ["router"]

router = APIRouter(
    prefix="/knowledgebases/{knowledge_base_id}/readiness",
    tags=["readiness"],
)


def _can_access_knowledge_base(user: User, knowledge_base_id: str) -> bool:
    allowed = user.knowledge_base_ids
    return allowed is None or knowledge_base_id in allowed or "admin" in user.roles


@router.get("", response_model=KnowledgeBaseReadinessResponse)
def get_knowledge_base_readiness(
    knowledge_base_id: str,
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    service: ReadinessService = Depends(get_readiness_service),
    user: User = Depends(require_role("viewer")),
) -> KnowledgeBaseReadinessResponse:
    """Return aggregated readiness for one knowledge base."""

    if not _can_access_knowledge_base(user, knowledge_base_id):
        raise _not_found("Knowledge base", knowledge_base_id)
    if kb_repository.get(knowledge_base_id) is None:
        raise _not_found("Knowledge base", knowledge_base_id)
    try:
        readiness = service.get_readiness(knowledge_base_id)
    except KeyError as exc:
        raise _not_found("Knowledge base", knowledge_base_id) from exc
    return _readiness_response(readiness)


def _readiness_response(readiness: ReadinessResponse) -> KnowledgeBaseReadinessResponse:
    return KnowledgeBaseReadinessResponse(
        knowledge_base=ReadinessKnowledgeBaseSummaryResponse(
            id=readiness.knowledge_base.id,
            name=readiness.knowledge_base.name,
            domain=readiness.knowledge_base.domain,
            status=readiness.knowledge_base.status,
            document_count=readiness.knowledge_base.document_count,
            entity_count=readiness.knowledge_base.entity_count,
            relationship_count=readiness.knowledge_base.relationship_count,
            updated_at=readiness.knowledge_base.updated_at,
            created_at=readiness.knowledge_base.created_at,
        ),
        active_domain_name=readiness.active_domain_name,
        ready=readiness.ready,
        components={
            key: _component_response(component)
            for key, component in readiness.components.items()
        },
        blockers=[_issue_response(issue) for issue in readiness.blockers],
        warnings=[_issue_response(issue) for issue in readiness.warnings],
    )


def _component_response(component: ReadinessComponent) -> ReadinessComponentResponse:
    return ReadinessComponentResponse(
        status=component.status,
        label=component.label,
        summary=component.summary,
        blockers=[_issue_response(issue) for issue in component.blockers],
        warnings=[_issue_response(issue) for issue in component.warnings],
        details=cast(dict[str, object], dict(component.details)),
    )


def _issue_response(issue: ReadinessIssue) -> ReadinessIssueResponse:
    return ReadinessIssueResponse(
        component=issue.component,
        code=issue.code,
        message=issue.message,
        action=issue.action,
    )


def _not_found(resource: str, identifier: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{resource} '{identifier}' not found.",
    )
