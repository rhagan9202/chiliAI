"""Service-level protocols for the explainability analytics module."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from analytics.explainability.models import ExplanationContext, ExplanationItem, ExplanationNarrative
from analytics.explainability.service_models import ExplainabilityRequest, ExplainabilityResponse


@runtime_checkable
class ExplainabilityServiceProtocol(Protocol):
    """Service boundary for evidence-pack generation."""

    def generate(self, request: ExplainabilityRequest) -> ExplainabilityResponse: ...

    def generate_from_context(
        self,
        context: ExplanationContext,
        *,
        max_evidence_items: int = 3,
    ) -> ExplainabilityResponse: ...


@runtime_checkable
class NarrativeGeneratorProtocol(Protocol):
    """Produce a structured narrative from selected explanation items."""

    def summarize(
        self, *, context: ExplanationContext, items: Sequence[ExplanationItem]
    ) -> ExplanationNarrative: ...


__all__ = [
    "ExplainabilityServiceProtocol",
    "NarrativeGeneratorProtocol",
]