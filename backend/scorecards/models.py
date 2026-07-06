"""Internal domain models for scorecard evaluation."""

from __future__ import annotations

from datetime import datetime
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
ScorecardRunStatus = Literal["pending", "running", "completed", "failed"]


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


class ScorecardRun(BaseModel):
    """A deterministic scorecard evaluation result."""

    template_id: str
    template_name: str
    category: Literal["UH", "MFH", "combined"]
    scope: Literal["enterprise", "majcom", "region", "installation", "market_area"]
    period: Literal["monthly", "quarterly", "annual", "ad_hoc"]
    status: ScorecardRunStatus = "completed"
    health: ScorecardHealth
    export_formats: list[ScorecardExportFormat] = Field(
        default_factory=lambda: cast(list[ScorecardExportFormat], [])
    )
    sections: list[ScorecardSectionResult] = Field(
        default_factory=lambda: cast(list[ScorecardSectionResult], [])
    )
    evaluated_at: datetime = Field(default_factory=utc_now)


__all__ = [
    "ScorecardCitation",
    "ScorecardCompleteness",
    "ScorecardExportFormat",
    "ScorecardHealth",
    "ScorecardMetricResult",
    "ScorecardRun",
    "ScorecardRunStatus",
    "ScorecardSectionResult",
]
