"""Adapter-level protocols for explainability generation."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from analytics.explainability.models import ExplanationContext


@runtime_checkable
class ExplainabilityContextSourceProtocol(Protocol):
    """Load explanation context for a specific alert."""

    def load_context(self, *, knowledge_base_id: str, alert_id: str) -> ExplanationContext: ...