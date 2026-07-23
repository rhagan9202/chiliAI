"""Service-level protocols for the explainability analytics module."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from analytics.explainability.models import ExplanationContext, ExplanationItem, ExplanationNarrative
from analytics.explainability.service_models import ExplainabilityRequest, ExplainabilityResponse
from shared.types import FeatureAttribution


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
    """Produce a structured narrative from selected explanation items.

    Implementations must never raise: on any internal failure (e.g. an
    unreachable or misbehaving backing service) they degrade to a fallback
    narrative and log a WARNING rather than propagating the error.
    """

    def summarize(
        self, *, context: ExplanationContext, items: Sequence[ExplanationItem]
    ) -> ExplanationNarrative: ...


@runtime_checkable
class FeatureAttributorProtocol(Protocol):
    """Produce per-feature attributions for an explanation context's scores.

    Implementations must never raise: on any internal failure (e.g. a missing
    optional dependency or a misbehaving explainer backend) they degrade to an
    empty attribution list and log a WARNING rather than propagating the
    error.
    """

    def attribute(self, *, context: ExplanationContext) -> list[FeatureAttribution]: ...


__all__ = [
    "ExplainabilityServiceProtocol",
    "FeatureAttributorProtocol",
    "NarrativeGeneratorProtocol",
]