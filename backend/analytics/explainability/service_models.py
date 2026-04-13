"""Service-boundary models for explainability generation."""

from __future__ import annotations

from pydantic import BaseModel, Field

from shared.types import EvidencePack


class ExplainabilityRequest(BaseModel):
    """A caller-supplied request to generate an evidence pack."""

    knowledge_base_id: str
    alert_id: str
    max_evidence_items: int = Field(default=3, gt=0)


class ExplainabilityEvidence(BaseModel):
    """A service-boundary explanation item."""

    source_id: str
    source_type: str
    quote: str
    rationale: str
    score: float = Field(ge=0.0, le=1.0)


class ExplainabilityResponse(BaseModel):
    """The assembled evidence pack and surfaced evidence details."""

    request_id: str
    knowledge_base_id: str
    alert_id: str
    evidence_pack: EvidencePack
    evidence_items: list[ExplainabilityEvidence] = Field(default_factory=list)


__all__ = [
    "ExplainabilityEvidence",
    "ExplainabilityRequest",
    "ExplainabilityResponse",
]