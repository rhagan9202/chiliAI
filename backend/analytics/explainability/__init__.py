"""Public exports for the explainability analytics module."""

from __future__ import annotations

from analytics.explainability.adapters.in_memory import InMemoryExplainabilityContextSource
from analytics.explainability.adapters.protocols import ExplainabilityContextSourceProtocol
from analytics.explainability.exceptions import (
    ExplainabilityConfigurationError,
    ExplainabilityError,
    ExplainabilityInsufficientEvidenceError,
    ExplainabilitySourceError,
)
from analytics.explainability.models import (
    ExplanationContext,
    ExplanationItem,
    ExplanationNarrative,
    ExplanationSubgraph,
    NarrativeSection,
)
from analytics.explainability.protocols import ExplainabilityServiceProtocol
from analytics.explainability.service import ExplainabilityService, create_explainability_service
from analytics.explainability.service_models import (
    ExplainabilityEvidence,
    ExplainabilityRequest,
    ExplainabilityResponse,
)

__all__ = [
    "ExplainabilityConfigurationError",
    "ExplainabilityError",
    "ExplainabilityEvidence",
    "ExplainabilityInsufficientEvidenceError",
    "ExplainabilityRequest",
    "ExplainabilityResponse",
    "ExplainabilityService",
    "ExplainabilityServiceProtocol",
    "ExplainabilitySourceError",
    "ExplainabilityContextSourceProtocol",
    "ExplanationContext",
    "ExplanationItem",
    "ExplanationNarrative",
    "ExplanationSubgraph",
    "InMemoryExplainabilityContextSource",
    "NarrativeSection",
    "create_explainability_service",
]
