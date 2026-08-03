"""Internal transport and workflow models for explainability generation."""

from __future__ import annotations

from typing import cast

from pydantic import BaseModel, Field, model_validator

from shared.types import Alert


class ExplanationLineage(BaseModel):
    """Optional lineage ids available while assembling an evidence pack."""

    score_request_id: str | None = None
    correlation_id: str | None = None
    workflow_id: str | None = None
    model_version: str | None = None
    prompt_version: str | None = None
    transformation_version: str | None = None


class ExplanationItem(BaseModel):
    """A single piece of evidence contributing to an evidence pack."""

    source_id: str
    source_type: str
    quote: str
    rationale: str
    score: float = Field(ge=0.0, le=1.0)


class ExplanationSubgraph(BaseModel):
    """A minimal explanatory subgraph extracted for analyst review."""

    node_ids: list[str] = Field(default_factory=lambda: cast(list[str], []))
    edge_ids: list[str] = Field(default_factory=lambda: cast(list[str], []))

    @model_validator(mode="after")
    def _validate_subgraph(self) -> ExplanationSubgraph:
        if not self.node_ids:
            raise ValueError("ExplanationSubgraph requires at least one node id.")
        return self


class ExplanationContext(BaseModel):
    """Seed context used to assemble an evidence pack."""

    knowledge_base_id: str
    alert: Alert
    explanation_items: list[ExplanationItem] = Field(
        default_factory=lambda: cast(list[ExplanationItem], [])
    )
    subgraph: ExplanationSubgraph
    confidence: float = Field(ge=0.0, le=1.0)
    scores: dict[str, float] = Field(default_factory=lambda: cast(dict[str, float], {}))
    lineage: ExplanationLineage = Field(default_factory=ExplanationLineage)

    @model_validator(mode="after")
    def _validate_items(self) -> ExplanationContext:
        if not self.explanation_items:
            raise ValueError("ExplanationContext requires at least one explanation item.")
        return self


class NarrativeSection(BaseModel):
    """A grouped narrative passage tied to specific evidence items."""

    heading: str
    body: str
    evidence_refs: list[str] = Field(default_factory=lambda: cast(list[str], []))


class ExplanationNarrative(BaseModel):
    """Structured multi-section narrative produced from explanation items."""

    summary: str
    sections: list[NarrativeSection] = Field(
        default_factory=lambda: cast(list[NarrativeSection], [])
    )


__all__ = [
    "ExplanationContext",
    "ExplanationItem",
    "ExplanationLineage",
    "ExplanationNarrative",
    "ExplanationSubgraph",
    "NarrativeSection",
]
