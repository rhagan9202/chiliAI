"""Service-boundary models for risk scoring."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

RiskTrend = Literal["increasing", "stable", "decreasing"]


class RiskAssessmentRequest(BaseModel):
    """A caller-supplied risk assessment request."""

    knowledge_base_id: str
    entity_id: str
    medium_risk_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    high_risk_threshold: float = Field(default=0.8, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_thresholds(self) -> RiskAssessmentRequest:
        if self.high_risk_threshold <= self.medium_risk_threshold:
            raise ValueError("RiskAssessmentRequest high_risk_threshold must exceed medium_risk_threshold.")
        return self


class RiskFactorScore(BaseModel):
    """A service-boundary factor score."""

    factor_name: str
    raw_value: float = Field(ge=0.0, le=1.0)
    weight: float = Field(gt=0.0)
    contribution: float = Field(ge=0.0, le=1.0)
    rationale: str | None = None


class RiskAssessmentResponse(BaseModel):
    """A summary of a composite risk assessment."""

    request_id: str
    knowledge_base_id: str
    entity_id: str
    overall_score: float = Field(ge=0.0, le=1.0)
    risk_level: str
    factor_count: int = Field(ge=0)
    factors: list[RiskFactorScore] = Field(default_factory=list[RiskFactorScore])
    trend: RiskTrend | None = None
    previous_score: float | None = Field(default=None, ge=0.0, le=1.0)


class RiskScoreListRequest(BaseModel):
    """A caller-supplied request for ranked risk scores."""

    knowledge_base_id: str
    entity_type: str | None = None
    limit: int = Field(default=20, gt=0, le=500)


class RiskScore(BaseModel):
    """A single ranked risk score entry."""

    entity_id: str
    entity_type: str
    overall_score: float = Field(ge=0.0, le=1.0)
    risk_level: str


class RiskScoreListResponse(BaseModel):
    """A paginated, ranked list of risk scores."""

    knowledge_base_id: str
    items: list[RiskScore] = Field(default_factory=list[RiskScore])
    total: int = Field(ge=0)


# Re-export so API routers can import RankedRiskEntry from the service boundary.
from analytics.risk.models import RankedRiskEntry as RankedRiskEntry  # noqa: PLC0414

__all__ = [
    "RankedRiskEntry",
    "RiskAssessmentRequest",
    "RiskAssessmentResponse",
    "RiskFactorScore",
    "RiskScore",
    "RiskScoreListRequest",
    "RiskScoreListResponse",
    "RiskTrend",
]