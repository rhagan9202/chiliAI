"""Internal transport and workflow models for risk scoring."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class RiskSignal(BaseModel):
    """A normalized input signal used to derive a composite risk score."""

    signal_name: str
    value: float = Field(ge=0.0, le=1.0)
    weight: float = Field(gt=0.0)
    rationale: str | None = None


class RiskProfile(BaseModel):
    """A set of risk signals for one entity in one knowledge base."""

    knowledge_base_id: str
    entity_id: str
    signals: list[RiskSignal] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_signals(self) -> RiskProfile:
        if not self.signals:
            raise ValueError("RiskProfile requires at least one risk signal.")
        signal_names = [signal.signal_name for signal in self.signals]
        if len(set(signal_names)) != len(signal_names):
            raise ValueError("RiskProfile signal names must be unique.")
        return self


class RiskFactor(BaseModel):
    """A weighted factor contributing to the final risk score."""

    factor_name: str
    raw_value: float = Field(ge=0.0, le=1.0)
    weight: float = Field(gt=0.0)
    contribution: float = Field(ge=0.0, le=1.0)
    rationale: str | None = None


class RiskAssessmentResult(BaseModel):
    """Internal result returned after scoring an entity."""

    request_id: str
    knowledge_base_id: str
    entity_id: str
    overall_score: float = Field(ge=0.0, le=1.0)
    risk_level: str
    factor_count: int = Field(ge=0)
    factors: list[RiskFactor] = Field(default_factory=list)


__all__ = [
    "RiskAssessmentResult",
    "RiskFactor",
    "RiskProfile",
    "RiskSignal",
]