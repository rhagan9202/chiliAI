"""SAFE-CMS-020 governance and evaluation-loop models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, cast

from pydantic import BaseModel, Field, computed_field

GovernanceComponentKind = Literal[
    "connector",
    "model",
    "playbook",
    "prompt",
    "scoring",
    "workflow_definition",
]
GovernanceApprovalKind = Literal["governance_eval_run", "workflow_definition"]
GovernanceBlockerSeverity = Literal["blocking", "warning"]
GovernanceEvalStatus = Literal["candidate", "approved", "rejected"]
GovernanceMetricDirection = Literal["higher", "lower"]
GovernanceBaselineDecisionValue = Literal["approved", "rejected"]


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


class GovernanceMetricInput(BaseModel):
    """One candidate-vs-baseline metric submitted for evaluation."""

    name: str = Field(min_length=1)
    baseline_value: float
    candidate_value: float
    threshold: float = Field(default=0.0, ge=0.0)
    direction: GovernanceMetricDirection


class GovernanceMetricResult(BaseModel):
    """One persisted candidate-vs-baseline metric result."""

    name: str = Field(min_length=1)
    baseline_value: float
    candidate_value: float
    threshold: float = Field(ge=0.0)
    direction: GovernanceMetricDirection
    delta: float
    passed: bool


class GovernanceDriftSummary(BaseModel):
    """Compact drift summary for a governance evaluation run."""

    metric_count: int = Field(ge=0)
    failed_metric_count: int = Field(ge=0)
    max_abs_delta: float = Field(ge=0.0)


class GovernanceBaselineDecision(BaseModel):
    """Approval or rejection decision for a candidate evaluation run."""

    decision: GovernanceBaselineDecisionValue
    decided_by: str = Field(min_length=1)
    decided_at: datetime
    rationale: str = Field(min_length=1)


class GovernanceEvalRunCreate(BaseModel):
    """Payload for registering a candidate governance evaluation run."""

    knowledge_base_id: str = Field(min_length=1)
    artifact_kind: GovernanceComponentKind
    artifact_id: str = Field(min_length=1)
    artifact_version: str = Field(min_length=1)
    baseline_version: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    metrics: list[GovernanceMetricInput] = Field(min_length=1)
    dataset_source_refs: list[str] = Field(default_factory=lambda: cast(list[str], []))
    affected_alert_ids: list[str] = Field(default_factory=lambda: cast(list[str], []))
    affected_case_ids: list[str] = Field(default_factory=lambda: cast(list[str], []))
    created_by: str = Field(min_length=1)


class GovernanceEvalRun(BaseModel):
    """Persisted governance evaluation run and optional baseline decision."""

    run_id: str = Field(min_length=1)
    knowledge_base_id: str = Field(min_length=1)
    artifact_kind: GovernanceComponentKind
    artifact_id: str = Field(min_length=1)
    artifact_version: str = Field(min_length=1)
    baseline_version: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    status: GovernanceEvalStatus
    metrics: list[GovernanceMetricResult] = Field(min_length=1)
    drift_summary: GovernanceDriftSummary
    dataset_source_refs: list[str] = Field(default_factory=lambda: cast(list[str], []))
    affected_alert_ids: list[str] = Field(default_factory=lambda: cast(list[str], []))
    affected_case_ids: list[str] = Field(default_factory=lambda: cast(list[str], []))
    created_by: str = Field(min_length=1)
    created_at: datetime
    approval: GovernanceBaselineDecision | None = None


class GovernanceEvalRunPage(BaseModel):
    """Paginated governance evaluation run query response."""

    items: list[GovernanceEvalRun] = Field(
        default_factory=lambda: cast(list[GovernanceEvalRun], [])
    )
    total_items: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


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
    eval_runs: list[GovernanceEvalRun] = Field(
        default_factory=lambda: cast(list[GovernanceEvalRun], [])
    )
    release_blockers: list[GovernanceReleaseBlocker] = Field(
        default_factory=lambda: cast(list[GovernanceReleaseBlocker], [])
    )

    @computed_field
    @property
    def release_ready(self) -> bool:
        return all(blocker.severity != "blocking" for blocker in self.release_blockers)


__all__ = [
    "GovernanceBaselineDecision",
    "GovernanceBaselineDecisionValue",
    "GovernanceApprovalKind",
    "GovernanceBlockerSeverity",
    "GovernanceComponentKind",
    "GovernanceDriftSummary",
    "GovernanceEvalRun",
    "GovernanceEvalRunCreate",
    "GovernanceEvalRunPage",
    "GovernanceEvalStatus",
    "GovernanceFeedbackTrend",
    "GovernanceMetricDirection",
    "GovernanceMetricInput",
    "GovernanceMetricResult",
    "GovernancePendingApproval",
    "GovernanceReleaseBlocker",
    "GovernanceReport",
    "GovernanceVersionSummary",
]
