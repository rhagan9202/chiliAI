"""Identity resolution API router for SAFE-CMS-012."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from analytics.identity_resolution import (
    IdentityCandidateEntity,
    IdentityDecisionService,
    IdentityLinkDecisionRequest,
    IdentityLinkRecord,
    IdentityLinkRepository,
    IdentityLinkRepositoryQuery,
    IdentityMatchReason,
    IdentityResolutionRequest,
    IdentityResolutionResult,
    IdentityResolutionService,
)
from api.contracts import (
    CanonicalIdentityDetailResponse,
    IdentityCandidateEntityRequest,
    IdentityCandidateScoreResponse,
    IdentityLinkDecisionRecordResponse,
    IdentityLinkDecisionRequestPayload,
    IdentityLinkResponse,
    IdentityMatchReasonResponse,
    IdentityResolutionRequestPayload,
    IdentityResolutionResponse,
)
from api.dependencies import (
    get_identity_decision_service,
    get_identity_link_repository,
    get_identity_resolution_service,
)
from api.middleware.auth import User
from api.middleware.rbac import require_role

__all__ = ["router"]

router = APIRouter(prefix="/identity", tags=["identity"])


def _can_access_knowledge_base(user: User, knowledge_base_id: str) -> bool:
    allowed = user.knowledge_base_ids
    return allowed is None or knowledge_base_id in allowed or "admin" in user.roles


def _require_knowledge_base_access(user: User, knowledge_base_id: str) -> None:
    if not _can_access_knowledge_base(user, knowledge_base_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Knowledge base '{knowledge_base_id}' not found.",
        )


@router.get(
    "/canonical/{entity_id}",
    response_model=CanonicalIdentityDetailResponse,
)
def get_canonical_identity_detail(
    entity_id: str,
    kb_id: str = Query(..., alias="knowledge_base_id", min_length=1),
    limit: int = Query(default=50, gt=0, le=200),
    offset: int = Query(default=0, ge=0),
    repository: IdentityLinkRepository = Depends(get_identity_link_repository),
    user: User = Depends(require_role("viewer")),
) -> CanonicalIdentityDetailResponse:
    """Return source identities linked to a canonical entity."""

    _require_knowledge_base_access(user, kb_id)
    page = repository.list_links(
        IdentityLinkRepositoryQuery(
            knowledge_base_id=kb_id,
            canonical_entity_id=entity_id,
            limit=limit,
            offset=offset,
        )
    )
    return CanonicalIdentityDetailResponse(
        knowledge_base_id=kb_id,
        canonical_entity_id=entity_id,
        links=[_link_response(link) for link in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.post(
    "/resolve-candidates",
    response_model=IdentityResolutionResponse,
)
def resolve_identity_candidates(
    payload: IdentityResolutionRequestPayload,
    service: IdentityResolutionService = Depends(get_identity_resolution_service),
    user: User = Depends(require_role("analyst")),
) -> IdentityResolutionResponse:
    """Score a source identity against connector-provided canonical candidates."""

    _require_knowledge_base_access(user, payload.knowledge_base_id)
    result = service.score_candidates(
        IdentityResolutionRequest(
            knowledge_base_id=payload.knowledge_base_id,
            source_entity=payload.source_entity,
            candidates=[
                _candidate_request(candidate) for candidate in payload.candidates
            ],
            natural_key_fields=list(payload.natural_key_fields),
            identifier_fields=list(payload.identifier_fields),
            address_fields=list(payload.address_fields),
        )
    )
    return _resolution_response(result)


@router.post(
    "/links/{link_id}/decision",
    response_model=IdentityLinkResponse,
)
def record_identity_link_decision(
    link_id: str,
    payload: IdentityLinkDecisionRequestPayload,
    service: IdentityDecisionService = Depends(get_identity_decision_service),
    user: User = Depends(require_role("analyst")),
) -> IdentityLinkResponse:
    """Record a steward decision against one identity link."""

    _require_knowledge_base_access(user, payload.knowledge_base_id)
    try:
        stored = service.record_decision(
            IdentityLinkDecisionRequest(
                knowledge_base_id=payload.knowledge_base_id,
                link_id=link_id,
                decision=payload.decision,
                actor_user_id=user.user_id,
                actor_email=user.email,
                actor_roles=list(user.roles),
                comment=payload.comment,
                **(
                    {"correlation_id": payload.correlation_id}
                    if payload.correlation_id is not None
                    else {}
                ),
            )
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Identity link not found.") from exc
    return _link_response(stored)


def _candidate_request(
    payload: IdentityCandidateEntityRequest,
) -> IdentityCandidateEntity:
    return IdentityCandidateEntity(
        knowledge_base_id=payload.knowledge_base_id,
        entity=payload.entity,
    )


def _resolution_response(
    result: IdentityResolutionResult,
) -> IdentityResolutionResponse:
    return IdentityResolutionResponse(
        knowledge_base_id=result.knowledge_base_id,
        source_entity_id=result.source_entity_id,
        candidates=[
            IdentityCandidateScoreResponse(
                knowledge_base_id=candidate.knowledge_base_id,
                entity_id=candidate.entity_id,
                entity_type=candidate.entity_type,
                score=candidate.score,
                confidence=candidate.confidence,
                review_state=candidate.review_state,
                match_reasons=[
                    _match_reason_response(reason)
                    for reason in candidate.match_reasons
                ],
            )
            for candidate in result.candidates
        ],
        excluded_candidate_ids=list(result.excluded_candidate_ids),
    )


def _match_reason_response(
    reason: IdentityMatchReason,
) -> IdentityMatchReasonResponse:
    return IdentityMatchReasonResponse(
        field=reason.field,
        reason=reason.reason,
        source_value=reason.source_value,
        candidate_value=reason.candidate_value,
        score_contribution=reason.score_contribution,
    )


def _link_response(link: IdentityLinkRecord) -> IdentityLinkResponse:
    return IdentityLinkResponse(
        id=link.id,
        knowledge_base_id=link.knowledge_base_id,
        canonical_entity_id=link.canonical_entity_id,
        source_entity_id=link.source_entity_id,
        relationship_type=link.relationship_type,
        confidence=link.confidence,
        score=link.score,
        review_state=link.review_state,
        decision_source=link.decision_source,
        source_refs=list(link.source_refs),
        match_reasons=[dict(reason) for reason in link.match_reasons],
        decision_history=[
            IdentityLinkDecisionRecordResponse(
                decision=decision.decision,
                actor_user_id=decision.actor_user_id,
                comment=decision.comment,
                created_at=decision.created_at,
            )
            for decision in link.decision_history
        ],
        created_at=link.created_at,
        updated_at=link.updated_at,
    )
