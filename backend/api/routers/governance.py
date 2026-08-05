"""KB-scoped SAFE-CMS-020 governance API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from analytics.explainability.reviews import (
    ExplanationReviewQuery,
    ExplanationReviewService,
)
from api.contracts import (
    GovernanceEvalApprovalRequest,
    GovernanceEvalRunCreateRequest,
    GovernanceEvalRunListResponse,
    GovernanceEvalRunResponse,
    GovernanceFeedbackTrendResponse,
    GovernancePendingApprovalResponse,
    GovernanceReleaseBlockerResponse,
    GovernanceReportResponse,
    GovernanceVersionSummaryResponse,
)
from api.dependencies import (
    get_domain_config,
    get_explanation_review_service,
    get_governance_eval_service,
    get_governance_report_service,
    get_knowledge_base_repository,
)
from api.middleware.auth import User
from api.middleware.rbac import require_role
from config.schema import DomainConfig
from governance.models import (
    GovernanceEvalRun,
    GovernanceEvalRunCreate,
    GovernanceMetricInput,
    GovernanceReport,
)
from governance.service import (
    CHALLENGED_REVIEW_STATES,
    GovernanceEvalApprovalError,
    GovernanceEvalNotFoundError,
    GovernanceEvalService,
    GovernanceReportService,
)
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


@router.get("/eval-runs", response_model=GovernanceEvalRunListResponse)
def list_governance_eval_runs(
    knowledge_base_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    service: GovernanceEvalService = Depends(get_governance_eval_service),
    domain_config: DomainConfig = Depends(get_domain_config),
    user: User = Depends(require_role("viewer")),
) -> GovernanceEvalRunListResponse:
    """Return governance evaluation runs for one knowledge base."""

    _require_knowledge_base(knowledge_base_id, kb_repository, user, domain_config)
    page = service.list_eval_runs(
        knowledge_base_id=knowledge_base_id,
        limit=limit,
        offset=offset,
    )
    return GovernanceEvalRunListResponse(
        items=[_eval_run_response(item) for item in page.items],
        total_items=page.total_items,
    )


@router.post(
    "/eval-runs",
    response_model=GovernanceEvalRunResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_governance_eval_run(
    knowledge_base_id: str,
    payload: GovernanceEvalRunCreateRequest,
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    service: GovernanceEvalService = Depends(get_governance_eval_service),
    explanation_review_service: ExplanationReviewService = Depends(
        get_explanation_review_service
    ),
    domain_config: DomainConfig = Depends(get_domain_config),
    user: User = Depends(require_role("analyst")),
) -> GovernanceEvalRunResponse:
    """Register a candidate evaluation run for release governance."""

    _require_knowledge_base(knowledge_base_id, kb_repository, user, domain_config)
    try:
        run = service.record_eval_run(
            GovernanceEvalRunCreate(
                knowledge_base_id=knowledge_base_id,
                artifact_kind=payload.artifact_kind,
                artifact_id=payload.artifact_id,
                artifact_version=payload.artifact_version,
                baseline_version=payload.baseline_version,
                dataset_id=payload.dataset_id,
                metrics=[
                    GovernanceMetricInput.model_validate(metric.model_dump())
                    for metric in payload.metrics
                ],
                dataset_source_refs=_dataset_source_refs(
                    knowledge_base_id=knowledge_base_id,
                    requested_refs=payload.dataset_source_refs,
                    explanation_review_service=explanation_review_service,
                ),
                affected_alert_ids=list(payload.affected_alert_ids),
                affected_case_ids=list(payload.affected_case_ids),
                created_by=user.user_id,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _eval_run_response(run)


@router.post(
    "/eval-runs/{run_id}/approve",
    response_model=GovernanceEvalRunResponse,
)
def approve_governance_eval_run(
    knowledge_base_id: str,
    run_id: str,
    payload: GovernanceEvalApprovalRequest,
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    service: GovernanceEvalService = Depends(get_governance_eval_service),
    domain_config: DomainConfig = Depends(get_domain_config),
    user: User = Depends(require_role("admin")),
) -> GovernanceEvalRunResponse:
    """Approve a passing candidate eval run before release promotion."""

    _require_knowledge_base(knowledge_base_id, kb_repository, user, domain_config)
    try:
        existing = service.get_eval_run(run_id)
        if existing.knowledge_base_id != knowledge_base_id:
            raise GovernanceEvalNotFoundError(
                f"Governance eval run '{run_id}' not found."
            )
        run = service.approve_baseline(
            run_id=run_id,
            approved_by=user.user_id,
            rationale=payload.rationale,
        )
    except GovernanceEvalNotFoundError as exc:
        raise _not_found("Governance eval run", run_id) from exc
    except GovernanceEvalApprovalError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if run.knowledge_base_id != knowledge_base_id:
        raise _not_found("Governance eval run", run_id)
    return _eval_run_response(run)


@router.post(
    "/eval-runs/{run_id}/reject",
    response_model=GovernanceEvalRunResponse,
)
def reject_governance_eval_run(
    knowledge_base_id: str,
    run_id: str,
    payload: GovernanceEvalApprovalRequest,
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    service: GovernanceEvalService = Depends(get_governance_eval_service),
    domain_config: DomainConfig = Depends(get_domain_config),
    user: User = Depends(require_role("admin")),
) -> GovernanceEvalRunResponse:
    """Reject a candidate eval run and retain the decision as release evidence."""

    _require_knowledge_base(knowledge_base_id, kb_repository, user, domain_config)
    try:
        existing = service.get_eval_run(run_id)
        if existing.knowledge_base_id != knowledge_base_id:
            raise GovernanceEvalNotFoundError(
                f"Governance eval run '{run_id}' not found."
            )
        run = service.reject_baseline(
            run_id=run_id,
            rejected_by=user.user_id,
            rationale=payload.rationale,
        )
    except GovernanceEvalNotFoundError as exc:
        raise _not_found("Governance eval run", run_id) from exc
    except GovernanceEvalApprovalError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if run.knowledge_base_id != knowledge_base_id:
        raise _not_found("Governance eval run", run_id)
    return _eval_run_response(run)


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
        eval_runs=[_eval_run_response(item) for item in report.eval_runs],
        release_blockers=[
            GovernanceReleaseBlockerResponse.model_validate(item.model_dump())
            for item in report.release_blockers
        ],
        release_ready=report.release_ready,
    )


def _eval_run_response(run: GovernanceEvalRun) -> GovernanceEvalRunResponse:
    return GovernanceEvalRunResponse.model_validate(run.model_dump())


def _dataset_source_refs(
    *,
    knowledge_base_id: str,
    requested_refs: list[str],
    explanation_review_service: ExplanationReviewService,
) -> list[str]:
    refs = list(requested_refs)
    offset = 0
    while True:
        page = explanation_review_service.list_reviews(
            ExplanationReviewQuery(
                knowledge_base_id=knowledge_base_id,
                limit=200,
                offset=offset,
            )
        )
        refs.extend(
            (
                "explanation_review:"
                f"{review.evidence_pack_id}:"
                f"{review.target.target_type}:"
                f"{review.target.target_id}"
            )
            for review in page.items
            if review.state in CHALLENGED_REVIEW_STATES
        )
        offset += len(page.items)
        if offset >= page.total or not page.items:
            return list(dict.fromkeys(refs))


def _not_found(resource: str, identifier: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{resource} '{identifier}' not found.",
    )
