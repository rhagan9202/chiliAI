"""Internal domain models for scorecard evaluation."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, cast

from pydantic import BaseModel, Field

from shared.utils import utc_now

ScorecardCompleteness = Literal[
    "complete",
    "missing_source",
    "stale_source",
    "formula_error",
]
ScorecardExportFormat = Literal["json", "markdown"]
ScorecardHealth = Literal["pass", "warn", "fail", "incomplete"]
ScorecardRunStatus = Literal["generated", "failed", "superseded"]


class ScorecardCitation(BaseModel):
    """A source record reference attached to a metric value."""

    citation_id: str
    feed_name: str
    record_id: str
    field: str | None = None


class ScorecardMetricResult(BaseModel):
    """A computed metric result within a scorecard section."""

    id: str
    label: str
    description: str = ""
    unit: str = ""
    housing_category: Literal["UH", "MFH", "combined"] = "combined"
    value: float | None = None
    health: ScorecardHealth
    completeness: ScorecardCompleteness
    citations: list[ScorecardCitation] = Field(
        default_factory=lambda: cast(list[ScorecardCitation], [])
    )
    warnings: list[str] = Field(default_factory=lambda: cast(list[str], []))


class ScorecardSectionResult(BaseModel):
    """A group of evaluated scorecard metrics."""

    id: str
    label: str
    metrics: list[ScorecardMetricResult] = Field(
        default_factory=lambda: cast(list[ScorecardMetricResult], [])
    )


class ScorecardEvaluationResult(BaseModel):
    """A pure evaluator result that has not been persisted as a durable run."""

    template_id: str
    template_name: str
    overall_health: ScorecardHealth
    sections: list[ScorecardSectionResult] = Field(
        default_factory=lambda: cast(list[ScorecardSectionResult], [])
    )
    evaluated_at: datetime = Field(default_factory=utc_now)


class ScorecardRun(BaseModel):
    """A durable scorecard run shape shared by service, repository, and API layers."""

    id: str
    knowledge_base_id: str
    template_id: str
    template_name: str
    scope_type: str
    scope_id: str
    period_start: date
    period_end: date
    source_snapshot_hash: str
    status: ScorecardRunStatus = "generated"
    overall_health: ScorecardHealth = "incomplete"
    sections: list[ScorecardSectionResult] = Field(
        default_factory=lambda: cast(list[ScorecardSectionResult], [])
    )
    export_payloads: dict[ScorecardExportFormat, str] = Field(
        default_factory=lambda: cast(dict[ScorecardExportFormat, str], {})
    )
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


__all__ = [
    "ScorecardCitation",
    "ScorecardCompleteness",
    "ScorecardEvaluationResult",
    "ScorecardExportFormat",
    "ScorecardHealth",
    "ScorecardMetricResult",
    "ScorecardRun",
    "ScorecardRunStatus",
    "ScorecardSectionResult",
]
