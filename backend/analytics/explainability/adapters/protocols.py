"""Adapter-level protocols for explainability generation."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from analytics.explainability.models import ExplanationContext


@runtime_checkable
class ExplainabilityContextSourceProtocol(Protocol):
    """Load explanation context for a specific alert."""

    # TODO(production): Extend with batch loading and richer context queries:
    # - load_contexts(kb_id, alert_ids: list[str]) -> list[ExplanationContext]
    # - load_context_with_graph(kb_id, alert_id, depth) -> ExplanationContext
    # Implement production adapter assembling context from graph + risk + vectorstore.

    def load_context(self, *, knowledge_base_id: str, alert_id: str) -> ExplanationContext: ...


__all__ = [
    "ExplainabilityContextSourceProtocol",
]