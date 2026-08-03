"""Identity-resolution service boundary for SAFE-CMS-012."""

from analytics.identity_resolution.models import (
    IdentityCandidateEntity,
    IdentityCandidateScore,
    IdentityLinkDecision,
    IdentityLinkDecisionRecord,
    IdentityLinkDecisionRequest,
    IdentityLinkPage,
    IdentityLinkRecord,
    IdentityLinkRepositoryQuery,
    IdentityLinkReviewState,
    IdentityMatchConfidence,
    IdentityMatchReason,
    IdentityRelationshipProjectionRequest,
    IdentityResolutionRequest,
    IdentityResolutionResult,
    IdentityReviewState,
)
from analytics.identity_resolution.repository import (
    IdentityDecisionService,
    IdentityLinkRepository,
    InMemoryIdentityLinkRepository,
)
from analytics.identity_resolution.service import IdentityResolutionService

__all__ = [
    "IdentityDecisionService",
    "IdentityCandidateEntity",
    "IdentityCandidateScore",
    "IdentityLinkDecision",
    "IdentityLinkDecisionRecord",
    "IdentityLinkDecisionRequest",
    "IdentityLinkPage",
    "IdentityLinkRecord",
    "IdentityLinkRepository",
    "IdentityLinkRepositoryQuery",
    "IdentityLinkReviewState",
    "IdentityMatchConfidence",
    "IdentityMatchReason",
    "IdentityRelationshipProjectionRequest",
    "IdentityResolutionRequest",
    "IdentityResolutionResult",
    "IdentityResolutionService",
    "IdentityReviewState",
    "InMemoryIdentityLinkRepository",
]
