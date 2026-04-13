"""In-memory explainability context source for tests and local development."""

from __future__ import annotations

from analytics.explainability.models import ExplanationContext

__all__ = ["InMemoryExplainabilityContextSource"]


class InMemoryExplainabilityContextSource:
    """A seeded source of explainability contexts keyed by knowledge base and alert."""

    def __init__(self, contexts: list[ExplanationContext] | None = None) -> None:
        self._contexts: dict[tuple[str, str], ExplanationContext] = {}
        for context in contexts or []:
            self.put_context(context)

    def put_context(self, context: ExplanationContext) -> None:
        self._contexts[(context.knowledge_base_id, context.alert.id)] = context

    def load_context(self, *, knowledge_base_id: str, alert_id: str) -> ExplanationContext:
        context = self._contexts.get((knowledge_base_id, alert_id))
        if context is None:
            raise ValueError(
                f"No explainability context registered for knowledge_base_id='{knowledge_base_id}' and alert_id='{alert_id}'."
            )
        return context