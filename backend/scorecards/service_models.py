"""Service boundary models for scorecard workflows."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from scorecards.models import ScorecardExportFormat, ScorecardRun


class ScorecardEvaluationRequest(BaseModel):
    """Request data needed by a future scorecard service to run evaluation."""

    knowledge_base_id: str
    template_id: str
    as_of: datetime | None = None


class ScorecardEvaluationResponse(BaseModel):
    """Response wrapper for a completed scorecard evaluation."""

    run: ScorecardRun


class ScorecardExportRequest(BaseModel):
    """Request data for rendering an already evaluated run."""

    format: ScorecardExportFormat


__all__ = [
    "ScorecardEvaluationRequest",
    "ScorecardEvaluationResponse",
    "ScorecardExportRequest",
]
