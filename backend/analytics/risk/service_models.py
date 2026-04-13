"""Service-boundary models for risk scoring."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


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
    factors: list[RiskFactorScore] = Field(default_factory=list)


__all__ = [
    "RiskAssessmentRequest",
    "RiskAssessmentResponse",
    "RiskFactorScore",
]