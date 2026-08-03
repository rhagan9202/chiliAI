"""Evidence pack router exposing investigation evidence read models."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path

from api.contracts import (
    EvidencePackExportResponse,
    EvidencePackResponse,
    EvidenceProvenanceListResponse,
    ExplanationReviewCreateRequest,
    ExplanationReviewListResponse,
    ExplanationReviewResponse,
)
from api.dependencies import (
    build_evidence_provenance_response,
    create_evidence_review_payload,
    get_audit_log_service,
    get_evidence_pack_export_payload,
    get_evidence_pack_payload,
    get_evidence_provenance_payload,
    get_evidence_provenance_repository,
    get_evidence_review_list_payload,
    get_evidence_pack_repository,
    get_explanation_review_service,
    record_explanation_review_audit_event,
)
from analytics.explainability.provenance import EvidenceProvenanceRepository
from analytics.explainability.repository import EvidencePackRepository
from analytics.explainability.reviews import ExplanationReviewService
from api.middleware.auth import User
from api.middleware.rbac import require_role
from auditlog.service import AuditLogService

__all__ = ["kb_router", "router"]

router = APIRouter(prefix="/evidence-packs", tags=["evidence"])
kb_router = APIRouter(
    prefix="/knowledgebases/{knowledge_base_id}/evidence-packs",
    tags=["evidence"],
)


@router.get(
    "/{evidence_pack_id}",
    response_model=EvidencePackResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def get_evidence_pack(
    evidence_pack: EvidencePackResponse = Depends(get_evidence_pack_payload),
) -> EvidencePackResponse:
    """Return one evidence pack read model."""
    return evidence_pack


@router.get(
    "/{evidence_pack_id}/provenance",
    response_model=EvidenceProvenanceListResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def get_evidence_pack_provenance(
    provenance: EvidenceProvenanceListResponse = Depends(
        get_evidence_provenance_payload
    ),
) -> EvidenceProvenanceListResponse:
    """Return structured provenance references for one evidence pack."""
    return provenance


@router.get(
    "/{evidence_pack_id}/reviews",
    response_model=ExplanationReviewListResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def list_evidence_pack_reviews(
    reviews: ExplanationReviewListResponse = Depends(get_evidence_review_list_payload),
) -> ExplanationReviewListResponse:
    """Return analyst review state for one evidence pack."""
    return reviews


@router.post(
    "/{evidence_pack_id}/reviews",
    response_model=ExplanationReviewResponse,
)
async def create_evidence_pack_review(
    payload: ExplanationReviewCreateRequest,
    evidence_pack_id: str,
    knowledge_base_id: str,
    evidence_repository: EvidencePackRepository = Depends(get_evidence_pack_repository),
    review_service: ExplanationReviewService = Depends(get_explanation_review_service),
    audit_service: AuditLogService = Depends(get_audit_log_service),
    user: User = Depends(require_role("analyst")),
) -> ExplanationReviewResponse:
    """Create or update one analyst review of an explanation target."""

    review, was_update = create_evidence_review_payload(
        evidence_pack_id=evidence_pack_id,
        knowledge_base_id=knowledge_base_id,
        payload=payload,
        actor_user_id=user.user_id,
        actor_email=user.email,
        evidence_repository=evidence_repository,
        review_service=review_service,
    )
    record_explanation_review_audit_event(
        audit_service,
        knowledge_base_id=knowledge_base_id,
        actor_user_id=user.user_id,
        actor_email=user.email,
        actor_roles=user.roles,
        action="explanation.review.update" if was_update else "explanation.review.create",
        evidence_pack_id=evidence_pack_id,
        review=review,
    )
    return review


@kb_router.get(
    "/{evidence_pack_id}/provenance",
    response_model=EvidenceProvenanceListResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def get_kb_evidence_pack_provenance(
    knowledge_base_id: str = Path(..., min_length=1),
    evidence_pack_id: str = Path(..., description="Evidence pack identifier."),
    repository: EvidenceProvenanceRepository = Depends(
        get_evidence_provenance_repository
    ),
) -> EvidenceProvenanceListResponse:
    """Return structured provenance references for one KB-scoped evidence pack."""

    return build_evidence_provenance_response(
        knowledge_base_id=knowledge_base_id,
        evidence_pack_id=evidence_pack_id,
        repository=repository,
    )


@router.get(
    "/{evidence_pack_id}/export",
    response_model=EvidencePackExportResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def export_evidence_pack(
    export: EvidencePackExportResponse = Depends(get_evidence_pack_export_payload),
) -> EvidencePackExportResponse:
    """Return a downloadable JSON or Markdown rendering of one evidence pack.

    Same gate as reading the pack: an export is a projection of what the caller
    can already see, not a new disclosure.
    """
    return export
