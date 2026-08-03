"""Contestable explainability review domain models and service.

Reviews are human annotations on generated evidence-pack subtargets. They live
beside the immutable generated evidence so analysts can challenge an explanation
without rewriting the source artifact.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable, Literal, Protocol, cast, runtime_checkable

from pydantic import BaseModel, Field, model_validator

from shared.utils import generate_id, utc_now

ExplanationReviewTargetType = Literal[
    "narrative",
    "narrative_section",
    "feature_attribution",
    "evidence_item",
    "provenance_reference",
]
ExplanationReviewState = Literal[
    "useful",
    "incomplete",
    "misleading",
    "unsupported",
    "approved",
    "rejected",
    "regeneration_requested",
]
ExplanationReviewReason = Literal[
    "missing_source",
    "wrong_peer_group",
    "stale_data",
    "unsupported_claim",
    "contradicts_evidence",
    "unclear_rationale",
    "other",
]

_REASON_REQUIRED_STATES: set[ExplanationReviewState] = {
    "incomplete",
    "misleading",
    "unsupported",
    "rejected",
    "regeneration_requested",
}
_COMMENT_MAX_CHARS = 1_000


class ExplanationReviewTarget(BaseModel):
    """One reviewable subtarget inside an evidence pack."""

    target_type: ExplanationReviewTargetType
    target_id: str = Field(min_length=1)


class ExplanationReviewCreate(BaseModel):
    """Input for creating or updating one explanation review."""

    knowledge_base_id: str = Field(min_length=1)
    evidence_pack_id: str = Field(min_length=1)
    target: ExplanationReviewTarget
    state: ExplanationReviewState
    actor_user_id: str = Field(min_length=1)
    actor_email: str | None = None
    reasons: list[ExplanationReviewReason] = Field(
        default_factory=lambda: cast(list[ExplanationReviewReason], [])
    )
    comment: str | None = Field(default=None, max_length=_COMMENT_MAX_CHARS)

    @model_validator(mode="after")
    def _validate_reason_codes(self) -> ExplanationReviewCreate:
        if self.state in _REASON_REQUIRED_STATES and not self.reasons:
            raise ValueError(f"Review state '{self.state}' requires at least one reason.")
        return self


class ExplanationReviewRecord(BaseModel):
    """Stored review state for one evidence-pack target."""

    id: str
    knowledge_base_id: str
    evidence_pack_id: str
    target: ExplanationReviewTarget
    state: ExplanationReviewState
    actor_user_id: str
    actor_email: str | None = None
    reasons: list[ExplanationReviewReason] = Field(
        default_factory=lambda: cast(list[ExplanationReviewReason], [])
    )
    comment: str | None = None
    created_at: datetime
    updated_at: datetime
    update_count: int = Field(ge=0)


class ExplanationReviewQuery(BaseModel):
    """Filters for listing explanation reviews."""

    knowledge_base_id: str = Field(min_length=1)
    evidence_pack_id: str | None = None
    state: ExplanationReviewState | None = None
    target_type: ExplanationReviewTargetType | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class ExplanationReviewPage(BaseModel):
    """A page of explanation reviews."""

    items: list[ExplanationReviewRecord] = Field(
        default_factory=lambda: cast(list[ExplanationReviewRecord], [])
    )
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


@runtime_checkable
class ExplanationReviewRepository(Protocol):
    """Store and query KB-scoped explanation reviews."""

    def upsert(self, review: ExplanationReviewRecord) -> ExplanationReviewRecord: ...

    def get_for_target(
        self,
        *,
        knowledge_base_id: str,
        evidence_pack_id: str,
        target: ExplanationReviewTarget,
    ) -> ExplanationReviewRecord | None: ...

    def list_reviews(self, query: ExplanationReviewQuery) -> ExplanationReviewPage: ...


class InMemoryExplanationReviewRepository:
    """In-memory repository for tests and local development."""

    def __init__(self) -> None:
        self._reviews: dict[tuple[str, str, str, str], ExplanationReviewRecord] = {}

    def upsert(self, review: ExplanationReviewRecord) -> ExplanationReviewRecord:
        key = _review_key(review.knowledge_base_id, review.evidence_pack_id, review.target)
        self._reviews[key] = review.model_copy(deep=True)
        return review.model_copy(deep=True)

    def get_for_target(
        self,
        *,
        knowledge_base_id: str,
        evidence_pack_id: str,
        target: ExplanationReviewTarget,
    ) -> ExplanationReviewRecord | None:
        review = self._reviews.get(_review_key(knowledge_base_id, evidence_pack_id, target))
        return review.model_copy(deep=True) if review is not None else None

    def list_reviews(self, query: ExplanationReviewQuery) -> ExplanationReviewPage:
        filtered = [
            review.model_copy(deep=True)
            for review in self._reviews.values()
            if review.knowledge_base_id == query.knowledge_base_id
            and (query.evidence_pack_id is None or review.evidence_pack_id == query.evidence_pack_id)
            and (query.state is None or review.state == query.state)
            and (query.target_type is None or review.target.target_type == query.target_type)
        ]
        filtered.sort(key=lambda review: review.updated_at, reverse=True)
        total = len(filtered)
        items = filtered[query.offset : query.offset + query.limit]
        return ExplanationReviewPage(
            items=items,
            total=total,
            limit=query.limit,
            offset=query.offset,
        )


class ExplanationReviewService:
    """Validate and persist analyst review state for generated explanations."""

    def __init__(
        self,
        repository: ExplanationReviewRepository,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._repository = repository
        self._clock = clock

    def record_review(self, request: ExplanationReviewCreate) -> ExplanationReviewRecord:
        now = self._clock()
        existing = self._repository.get_for_target(
            knowledge_base_id=request.knowledge_base_id,
            evidence_pack_id=request.evidence_pack_id,
            target=request.target,
        )
        comment = _clean_comment(request.comment)
        if existing is None:
            review = ExplanationReviewRecord(
                id=generate_id(),
                knowledge_base_id=request.knowledge_base_id,
                evidence_pack_id=request.evidence_pack_id,
                target=request.target,
                state=request.state,
                actor_user_id=request.actor_user_id,
                actor_email=request.actor_email,
                reasons=list(request.reasons),
                comment=comment,
                created_at=now,
                updated_at=now,
                update_count=0,
            )
        else:
            review = existing.model_copy(
                update={
                    "state": request.state,
                    "actor_user_id": request.actor_user_id,
                    "actor_email": request.actor_email,
                    "reasons": list(request.reasons),
                    "comment": comment,
                    "updated_at": now,
                    "update_count": existing.update_count + 1,
                },
                deep=True,
            )
        return self._repository.upsert(review)

    def list_reviews(self, query: ExplanationReviewQuery) -> ExplanationReviewPage:
        return self._repository.list_reviews(query)


def _clean_comment(comment: str | None) -> str | None:
    if comment is None:
        return None
    cleaned = comment.strip()
    return cleaned or None


def _review_key(
    knowledge_base_id: str,
    evidence_pack_id: str,
    target: ExplanationReviewTarget,
) -> tuple[str, str, str, str]:
    return (
        knowledge_base_id,
        evidence_pack_id,
        target.target_type,
        target.target_id,
    )


__all__ = [
    "ExplanationReviewCreate",
    "ExplanationReviewPage",
    "ExplanationReviewQuery",
    "ExplanationReviewReason",
    "ExplanationReviewRecord",
    "ExplanationReviewRepository",
    "ExplanationReviewService",
    "ExplanationReviewState",
    "ExplanationReviewTarget",
    "ExplanationReviewTargetType",
    "InMemoryExplanationReviewRepository",
]
