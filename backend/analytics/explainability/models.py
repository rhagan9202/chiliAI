"""Internal transport and workflow models for explainability generation."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from shared.types import Alert


class ExplanationItem(BaseModel):
    """A single piece of evidence contributing to an evidence pack."""

    source_id: str
    source_type: str
    quote: str
    rationale: str
    score: float = Field(ge=0.0, le=1.0)


class ExplanationSubgraph(BaseModel):
    """A minimal explanatory subgraph extracted for analyst review."""

    node_ids: list[str] = Field(default_factory=list)
    edge_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_subgraph(self) -> ExplanationSubgraph:
        if not self.node_ids:
            raise ValueError("ExplanationSubgraph requires at least one node id.")
        return self


class ExplanationContext(BaseModel):
    """Seed context used to assemble an evidence pack."""

    knowledge_base_id: str
    alert: Alert
    explanation_items: list[ExplanationItem] = Field(default_factory=list)
    subgraph: ExplanationSubgraph
    confidence: float = Field(ge=0.0, le=1.0)
    scores: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_items(self) -> ExplanationContext:
        if not self.explanation_items:
            raise ValueError("ExplanationContext requires at least one explanation item.")
        return self


class NarrativeSection(BaseModel):
    """A grouped narrative passage tied to specific evidence items."""

    heading: str
    body: str
    evidence_refs: list[str] = Field(default_factory=list)


class ExplanationNarrative(BaseModel):
    """Structured multi-section narrative produced from explanation items."""

    summary: str
    sections: list[NarrativeSection] = Field(default_factory=list)


__all__ = [
    "ExplanationContext",
    "ExplanationItem",
    "ExplanationNarrative",
    "ExplanationSubgraph",
    "NarrativeSection",
]
