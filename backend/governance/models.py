"""SAFE-CMS-020 governance report models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, cast

from pydantic import BaseModel, Field, computed_field

GovernanceComponentKind = Literal["playbook", "workflow_definition"]
GovernanceApprovalKind = Literal["workflow_definition"]
GovernanceBlockerSeverity = Literal["blocking", "warning"]


class GovernanceVersionSummary(BaseModel):
    """One production-version reference for release evidence."""

    component_kind: GovernanceComponentKind
    component_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    status: str = Field(min_length=1)
    source: str = Field(min_length=1)
    approved_by: str | None = None
    approved_at: datetime | None = None


class GovernancePendingApproval(BaseModel):
    """One artifact that still needs review before release."""

    approval_kind: GovernanceApprovalKind
    resource_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    status: str = Field(min_length=1)
    requested_by: str = Field(min_length=1)
    updated_at: datetime


class GovernanceFeedbackTrend(BaseModel):
    """Aggregated human feedback over explanation reviews."""

    total_reviews: int = Field(ge=0)
    challenged_reviews: int = Field(ge=0)
    approved_reviews: int = Field(ge=0)
    state_counts: dict[str, int] = Field(default_factory=lambda: cast(dict[str, int], {}))


class GovernanceReleaseBlocker(BaseModel):
    """A release-readiness condition that needs attention."""

    severity: GovernanceBlockerSeverity
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    resource_type: str = Field(min_length=1)
    resource_id: str = Field(min_length=1)


class GovernanceReport(BaseModel):
    """KB-scoped governance and release-readiness report."""

    knowledge_base_id: str = Field(min_length=1)
    domain_name: str = Field(min_length=1)
    generated_at: datetime
    production_versions: list[GovernanceVersionSummary] = Field(
        default_factory=lambda: cast(list[GovernanceVersionSummary], [])
    )
    pending_approvals: list[GovernancePendingApproval] = Field(
        default_factory=lambda: cast(list[GovernancePendingApproval], [])
    )
    feedback_trends: GovernanceFeedbackTrend
    release_blockers: list[GovernanceReleaseBlocker] = Field(
        default_factory=lambda: cast(list[GovernanceReleaseBlocker], [])
    )

    @computed_field
    @property
    def release_ready(self) -> bool:
        return all(blocker.severity != "blocking" for blocker in self.release_blockers)


__all__ = [
    "GovernanceApprovalKind",
    "GovernanceBlockerSeverity",
    "GovernanceComponentKind",
    "GovernanceFeedbackTrend",
    "GovernancePendingApproval",
    "GovernanceReleaseBlocker",
    "GovernanceReport",
    "GovernanceVersionSummary",
]
