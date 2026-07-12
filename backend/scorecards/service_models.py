"""Service boundary models for scorecard workflows."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from scorecards.models import ScorecardExportFormat, ScorecardRun, ScorecardRunStatus


class ScorecardGenerateRequest(BaseModel):
    """Request data for generating or reusing a scorecard run."""

    knowledge_base_id: str
    template_id: str
    scope_type: str
    scope_id: str
    period_start: date
    period_end: date


class ScorecardRunListRequest(BaseModel):
    """Query parameters for listing durable scorecard runs."""

    knowledge_base_id: str
    template_id: str | None = None
    status: ScorecardRunStatus | None = None
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class ScorecardTemplateSummary(BaseModel):
    """Summary metadata for one configured scorecard template."""

    id: str
    name: str
    category: str
    scope: str
    period: str


class ScorecardTemplateListResponse(BaseModel):
    """Response wrapper for configured template summaries."""

    items: list[ScorecardTemplateSummary] = Field(default_factory=list)


class ScorecardRunListResponse(BaseModel):
    """Response wrapper for paginated scorecard runs."""

    items: list[ScorecardRun] = Field(default_factory=list)
    total: int = Field(default=0, ge=0)


class ScorecardExportResponse(BaseModel):
    """Stored export payload for one durable scorecard run."""

    run_id: str
    format: ScorecardExportFormat
    content: str


class ScorecardEvaluationRequest(ScorecardGenerateRequest):
    """Backward-compatible alias for scorecard generation requests."""


class ScorecardEvaluationResponse(BaseModel):
    """Backward-compatible response wrapper for a completed scorecard evaluation."""

    run: ScorecardRun


class ScorecardExportRequest(BaseModel):
    """Backward-compatible request data for rendering an already evaluated run."""

    format: ScorecardExportFormat


__all__ = [
    "ScorecardExportResponse",
    "ScorecardEvaluationRequest",
    "ScorecardEvaluationResponse",
    "ScorecardGenerateRequest",
    "ScorecardExportRequest",
    "ScorecardRunListRequest",
    "ScorecardRunListResponse",
    "ScorecardTemplateListResponse",
    "ScorecardTemplateSummary",
]
