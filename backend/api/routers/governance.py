"""KB-scoped SAFE-CMS-020 governance API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from api.contracts import (
    GovernanceFeedbackTrendResponse,
    GovernancePendingApprovalResponse,
    GovernanceReleaseBlockerResponse,
    GovernanceReportResponse,
    GovernanceVersionSummaryResponse,
)
from api.dependencies import (
    get_domain_config,
    get_governance_report_service,
    get_knowledge_base_repository,
)
from api.middleware.auth import User
from api.middleware.rbac import require_role
from config.schema import DomainConfig
from governance.models import GovernanceReport
from governance.service import GovernanceReportService
from knowledgebases.protocols import KnowledgeBaseRepository
from shared.types import KnowledgeBase

__all__ = ["router"]

router = APIRouter(
    prefix="/knowledgebases/{knowledge_base_id}/governance",
    tags=["governance"],
)


@router.get("/report", response_model=GovernanceReportResponse)
def get_governance_report(
    knowledge_base_id: str,
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    service: GovernanceReportService = Depends(get_governance_report_service),
    domain_config: DomainConfig = Depends(get_domain_config),
    user: User = Depends(require_role("viewer")),
) -> GovernanceReportResponse:
    """Return release-readiness evidence for one knowledge base."""

    _, domain_name = _require_knowledge_base(
        knowledge_base_id,
        kb_repository,
        user,
        domain_config,
    )
    report = service.build_report(
        knowledge_base_id=knowledge_base_id,
        domain_name=domain_name,
    )
    return _report_response(report)


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


def _report_response(report: GovernanceReport) -> GovernanceReportResponse:
    return GovernanceReportResponse(
        knowledge_base_id=report.knowledge_base_id,
        domain_name=report.domain_name,
        generated_at=report.generated_at,
        production_versions=[
            GovernanceVersionSummaryResponse.model_validate(item.model_dump())
            for item in report.production_versions
        ],
        pending_approvals=[
            GovernancePendingApprovalResponse.model_validate(item.model_dump())
            for item in report.pending_approvals
        ],
        feedback_trends=GovernanceFeedbackTrendResponse.model_validate(
            report.feedback_trends.model_dump()
        ),
        release_blockers=[
            GovernanceReleaseBlockerResponse.model_validate(item.model_dump())
            for item in report.release_blockers
        ],
        release_ready=report.release_ready,
    )


def _not_found(resource: str, identifier: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{resource} '{identifier}' not found.",
    )
