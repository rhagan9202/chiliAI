"""Domain-neutral models for entity identity resolution."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, cast

from pydantic import BaseModel, Field, field_validator

from shared.types import Entity
from shared.utils import generate_id, utc_now

IdentityMatchConfidence = Literal["high", "medium", "low"]
IdentityReviewState = Literal["auto_linkable", "steward_review", "needs_review"]
IdentityLinkReviewState = Literal[
    "auto_linkable",
    "steward_review",
    "needs_review",
    "merged",
    "rejected",
    "split",
]
IdentityLinkDecision = Literal["approve_merge", "reject_merge", "split_identity"]


class IdentityCandidateEntity(BaseModel):
    """A canonical candidate entity scoped to one knowledge base."""

    knowledge_base_id: str = Field(min_length=1)
    entity: Entity


class IdentityResolutionRequest(BaseModel):
    """Request to score one source entity against canonical candidates."""

    knowledge_base_id: str = Field(min_length=1)
    source_entity: Entity
    candidates: list[IdentityCandidateEntity] = Field(
        default_factory=lambda: cast(list[IdentityCandidateEntity], [])
    )
    natural_key_fields: list[str] = Field(default_factory=lambda: cast(list[str], []))
    identifier_fields: list[str] = Field(default_factory=lambda: cast(list[str], []))
    address_fields: list[str] = Field(default_factory=lambda: cast(list[str], []))

    @field_validator("natural_key_fields", "identifier_fields", "address_fields")
    @classmethod
    def normalize_fields(cls, fields: list[str]) -> list[str]:
        """Keep configured field lists deterministic and non-empty."""

        return [field.strip() for field in fields if field.strip()]


class IdentityMatchReason(BaseModel):
    """One auditable reason contributing to an identity candidate score."""

    field: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    source_value: str
    candidate_value: str
    score_contribution: float = Field(ge=0.0, le=1.0)


class IdentityCandidateScore(BaseModel):
    """Score and review state for one candidate canonical entity."""

    knowledge_base_id: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    entity_type: str = Field(min_length=1)
    score: float = Field(ge=0.0, le=1.0)
    confidence: IdentityMatchConfidence
    review_state: IdentityReviewState
    match_reasons: list[IdentityMatchReason] = Field(
        default_factory=lambda: cast(list[IdentityMatchReason], [])
    )


class IdentityResolutionResult(BaseModel):
    """Ranked identity-resolution candidates for one source entity."""

    knowledge_base_id: str = Field(min_length=1)
    source_entity_id: str = Field(min_length=1)
    candidates: list[IdentityCandidateScore] = Field(
        default_factory=lambda: cast(list[IdentityCandidateScore], [])
    )
    excluded_candidate_ids: list[str] = Field(default_factory=lambda: cast(list[str], []))


class IdentityRelationshipProjectionRequest(BaseModel):
    """Request to project identity candidates into graph relationships."""

    knowledge_base_id: str = Field(min_length=1)
    source_entity: Entity
    candidates: list[IdentityCandidateScore] = Field(
        default_factory=lambda: cast(list[IdentityCandidateScore], [])
    )
    relationship_type: str = Field(min_length=1)
    decision_source: str = Field(min_length=1)
    source_refs: list[str] = Field(default_factory=lambda: cast(list[str], []))

    @field_validator("relationship_type", "decision_source")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        """Normalize required projection strings at the service boundary."""

        return value.strip()


class IdentityLinkDecisionRecord(BaseModel):
    """One steward decision recorded against an identity link."""

    decision: IdentityLinkDecision
    actor_user_id: str = Field(min_length=1)
    comment: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class IdentityLinkRecord(BaseModel):
    """Stored identity link between a canonical entity and source identity."""

    id: str = Field(min_length=1)
    knowledge_base_id: str = Field(min_length=1)
    canonical_entity_id: str = Field(min_length=1)
    source_entity_id: str = Field(min_length=1)
    relationship_type: str = Field(min_length=1)
    confidence: IdentityMatchConfidence
    score: float = Field(ge=0.0, le=1.0)
    review_state: IdentityLinkReviewState
    decision_source: str = Field(min_length=1)
    source_refs: list[str] = Field(default_factory=lambda: cast(list[str], []))
    match_reasons: list[dict[str, Any]] = Field(
        default_factory=lambda: cast(list[dict[str, Any]], [])
    )
    decision_history: list[IdentityLinkDecisionRecord] = Field(
        default_factory=lambda: cast(list[IdentityLinkDecisionRecord], [])
    )
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class IdentityLinkRepositoryQuery(BaseModel):
    """Filters for listing stored identity links."""

    knowledge_base_id: str = Field(min_length=1)
    canonical_entity_id: str | None = None
    source_entity_id: str | None = None
    review_state: IdentityLinkReviewState | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class IdentityLinkPage(BaseModel):
    """A page of stored identity links."""

    items: list[IdentityLinkRecord] = Field(
        default_factory=lambda: cast(list[IdentityLinkRecord], [])
    )
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class IdentityLinkDecisionRequest(BaseModel):
    """Request to record a steward decision against an identity link."""

    tenant_id: str = Field(default="platform", min_length=1)
    knowledge_base_id: str = Field(min_length=1)
    link_id: str = Field(min_length=1)
    decision: IdentityLinkDecision
    actor_user_id: str = Field(min_length=1)
    actor_email: str | None = None
    actor_roles: list[str] = Field(default_factory=lambda: cast(list[str], []))
    comment: str | None = None
    correlation_id: str = Field(default_factory=generate_id, min_length=1)


__all__ = [
    "IdentityCandidateEntity",
    "IdentityCandidateScore",
    "IdentityLinkDecision",
    "IdentityLinkDecisionRecord",
    "IdentityLinkDecisionRequest",
    "IdentityLinkPage",
    "IdentityLinkRecord",
    "IdentityLinkRepositoryQuery",
    "IdentityLinkReviewState",
    "IdentityMatchConfidence",
    "IdentityMatchReason",
    "IdentityRelationshipProjectionRequest",
    "IdentityResolutionRequest",
    "IdentityResolutionResult",
    "IdentityReviewState",
]
