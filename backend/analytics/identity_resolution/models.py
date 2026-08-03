"""Domain-neutral models for entity identity resolution."""

from __future__ import annotations

from typing import Literal, cast

from pydantic import BaseModel, Field, field_validator

from shared.types import Entity

IdentityMatchConfidence = Literal["high", "medium", "low"]
IdentityReviewState = Literal["auto_linkable", "steward_review", "needs_review"]


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


__all__ = [
    "IdentityCandidateEntity",
    "IdentityCandidateScore",
    "IdentityMatchConfidence",
    "IdentityMatchReason",
    "IdentityRelationshipProjectionRequest",
    "IdentityResolutionRequest",
    "IdentityResolutionResult",
    "IdentityReviewState",
]
