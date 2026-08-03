"""Candidate scoring service for SAFE-CMS-012 identity resolution."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from analytics.identity_resolution.models import (
    IdentityCandidateEntity,
    IdentityCandidateScore,
    IdentityMatchConfidence,
    IdentityMatchReason,
    IdentityRelationshipProjectionRequest,
    IdentityResolutionRequest,
    IdentityResolutionResult,
    IdentityReviewState,
)
from shared.types import Entity, Relationship

type Normalizer = Callable[[Any], str]

_NATURAL_KEY_WEIGHT = 0.55
_IDENTIFIER_WEIGHT = 0.30
_ADDRESS_WEIGHT = 0.15

_ADDRESS_ABBREVIATIONS = {
    "ave": "avenue",
    "blvd": "boulevard",
    "cir": "circle",
    "ct": "court",
    "dr": "drive",
    "ln": "lane",
    "pkwy": "parkway",
    "rd": "road",
    "st": "street",
}


class IdentityResolutionService:
    """Score canonical identity candidates from existing graph entities."""

    def score_candidates(
        self, request: IdentityResolutionRequest
    ) -> IdentityResolutionResult:
        """Return deterministic, KB-scoped candidate scores."""

        scores: list[IdentityCandidateScore] = []
        excluded_candidate_ids: list[str] = []
        for candidate in request.candidates:
            if candidate.knowledge_base_id != request.knowledge_base_id:
                excluded_candidate_ids.append(candidate.entity.id)
                continue
            score = self._score_candidate(request.source_entity, candidate, request)
            if score.score > 0.0:
                scores.append(score)

        scores.sort(key=lambda item: (-item.score, item.entity_id))
        return IdentityResolutionResult(
            knowledge_base_id=request.knowledge_base_id,
            source_entity_id=request.source_entity.id,
            candidates=scores,
            excluded_candidate_ids=sorted(excluded_candidate_ids),
        )

    def project_identity_relationships(
        self, request: IdentityRelationshipProjectionRequest
    ) -> list[Relationship]:
        """Project scored candidates into graph-storable identity links."""

        relationships: list[Relationship] = []
        for candidate in request.candidates:
            relationships.append(
                Relationship(
                    id=_identity_relationship_id(
                        request.knowledge_base_id,
                        candidate.entity_id,
                        request.source_entity.id,
                    ),
                    type=request.relationship_type,
                    source_id=candidate.entity_id,
                    target_id=request.source_entity.id,
                    properties={
                        "confidence": candidate.confidence,
                        "score": candidate.score,
                        "review_state": candidate.review_state,
                        "decision_source": request.decision_source,
                    },
                    metadata={
                        "knowledge_base_id": request.knowledge_base_id,
                        "source_entity_type": request.source_entity.type,
                        "candidate_entity_type": candidate.entity_type,
                        "source_refs": list(request.source_refs),
                        "match_reasons": [
                            {
                                "field": reason.field,
                                "reason": reason.reason,
                                "score_contribution": reason.score_contribution,
                            }
                            for reason in candidate.match_reasons
                        ],
                    },
                    weight=candidate.score,
                )
            )
        return relationships

    def _score_candidate(
        self,
        source_entity: Entity,
        candidate: IdentityCandidateEntity,
        request: IdentityResolutionRequest,
    ) -> IdentityCandidateScore:
        reasons: list[IdentityMatchReason] = []
        score = 0.0
        for field in request.natural_key_fields:
            reason = _exact_property_match_reason(
                source_entity,
                candidate.entity,
                field=field,
                reason="natural_key_match",
                contribution=_NATURAL_KEY_WEIGHT,
            )
            if reason is not None:
                reasons.append(reason)
                score += reason.score_contribution
        for field in request.identifier_fields:
            reason = _normalized_property_match_reason(
                source_entity,
                candidate.entity,
                field=field,
                reason="identifier_match",
                contribution=_IDENTIFIER_WEIGHT,
                normalizer=_normalize_identifier,
            )
            if reason is not None:
                reasons.append(reason)
                score += reason.score_contribution
        for field in request.address_fields:
            reason = _normalized_property_match_reason(
                source_entity,
                candidate.entity,
                field=field,
                reason="address_match",
                contribution=_ADDRESS_WEIGHT,
                normalizer=_normalize_address,
            )
            if reason is not None:
                reasons.append(reason)
                score += reason.score_contribution

        bounded_score = _bounded_score(score)
        review_state = _review_state(bounded_score)
        return IdentityCandidateScore(
            knowledge_base_id=candidate.knowledge_base_id,
            entity_id=candidate.entity.id,
            entity_type=candidate.entity.type,
            score=bounded_score,
            confidence=_confidence(bounded_score),
            review_state=review_state,
            match_reasons=reasons,
        )


def _exact_property_match_reason(
    source_entity: Entity,
    candidate_entity: Entity,
    *,
    field: str,
    reason: str,
    contribution: float,
) -> IdentityMatchReason | None:
    return _normalized_property_match_reason(
        source_entity,
        candidate_entity,
        field=field,
        reason=reason,
        contribution=contribution,
        normalizer=_normalize_text,
    )


def _normalized_property_match_reason(
    source_entity: Entity,
    candidate_entity: Entity,
    *,
    field: str,
    reason: str,
    contribution: float,
    normalizer: "Normalizer",
) -> IdentityMatchReason | None:
    source_value = source_entity.properties.get(field)
    candidate_value = candidate_entity.properties.get(field)
    if not _has_value(source_value) or not _has_value(candidate_value):
        return None
    if normalizer(source_value) != normalizer(candidate_value):
        return None
    return IdentityMatchReason(
        field=field,
        reason=reason,
        source_value=str(source_value),
        candidate_value=str(candidate_value),
        score_contribution=contribution,
    )


def _has_value(value: object) -> bool:
    return value is not None and str(value).strip() != ""


def _bounded_score(score: float) -> float:
    return round(min(score, 1.0), 6)


def _identity_relationship_id(
    knowledge_base_id: str, canonical_entity_id: str, source_entity_id: str
) -> str:
    return (
        "identity_link:"
        f"{_relationship_id_part(knowledge_base_id)}:"
        f"{_relationship_id_part(canonical_entity_id)}:"
        f"{_relationship_id_part(source_entity_id)}"
    )


def _relationship_id_part(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-")


def _normalize_identifier(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value).casefold().strip())


def _normalize_address(value: Any) -> str:
    tokens = re.sub(r"[^a-z0-9\s]", " ", str(value).casefold()).split()
    expanded = [_ADDRESS_ABBREVIATIONS.get(token, token) for token in tokens]
    return " ".join(expanded)


def _confidence(score: float) -> IdentityMatchConfidence:
    if score >= 0.85:
        return "high"
    if score >= 0.50:
        return "medium"
    return "low"


def _review_state(score: float) -> IdentityReviewState:
    if score >= 0.85:
        return "auto_linkable"
    if score >= 0.50:
        return "steward_review"
    return "needs_review"


__all__ = ["IdentityResolutionService"]
