"""Explainability adapters."""

from __future__ import annotations

from analytics.explainability.adapters.deterministic import DeterministicNarrativeGenerator
from analytics.explainability.adapters.in_memory import InMemoryExplainabilityContextSource
from analytics.explainability.adapters.llm_narrative import LlmNarrativeGenerator
from analytics.explainability.adapters.protocols import ExplainabilityContextSourceProtocol
from analytics.explainability.adapters.shap_attribution import (
    NoopFeatureAttributor,
    ShapRiskAttributor,
)

__all__ = [
    "DeterministicNarrativeGenerator",
    "ExplainabilityContextSourceProtocol",
    "InMemoryExplainabilityContextSource",
    "LlmNarrativeGenerator",
    "NoopFeatureAttributor",
    "ShapRiskAttributor",
]