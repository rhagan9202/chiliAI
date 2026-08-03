"""Identity-resolution service boundary for SAFE-CMS-012."""

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
from analytics.identity_resolution.service import IdentityResolutionService

__all__ = [
    "IdentityCandidateEntity",
    "IdentityCandidateScore",
    "IdentityMatchConfidence",
    "IdentityMatchReason",
    "IdentityRelationshipProjectionRequest",
    "IdentityResolutionRequest",
    "IdentityResolutionResult",
    "IdentityResolutionService",
    "IdentityReviewState",
]
