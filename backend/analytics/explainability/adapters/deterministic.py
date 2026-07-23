"""Deterministic, rule-based narrative generator.

Groups explanation items by `source_type` (in first-seen order) into narrative
sections and flattens all selected rationales into a summary string. This is
today's baseline narrative behavior, extracted behind
`NarrativeGeneratorProtocol` so alternate generators (e.g. LLM-backed) can be
swapped in via `AnalyticsConfig.narrative_backend` without changing callers.
"""

from __future__ import annotations

from collections.abc import Sequence

from analytics.explainability.models import (
    ExplanationContext,
    ExplanationItem,
    ExplanationNarrative,
    NarrativeSection,
)

__all__ = ["DeterministicNarrativeGenerator"]


class DeterministicNarrativeGenerator:
    """Group explanation items by `source_type` into a structured narrative."""

    def summarize(
        self, *, context: ExplanationContext, items: Sequence[ExplanationItem]
    ) -> ExplanationNarrative:
        grouped: dict[str, list[ExplanationItem]] = {}
        order: list[str] = []
        for item in items:
            if item.source_type not in grouped:
                grouped[item.source_type] = []
                order.append(item.source_type)
            grouped[item.source_type].append(item)

        sections: list[NarrativeSection] = []
        for source_type in order:
            section_items = grouped[source_type]
            sections.append(
                NarrativeSection(
                    heading=_format_heading(source_type),
                    body=" ".join(item.rationale for item in section_items),
                    evidence_refs=[item.source_id for item in section_items],
                )
            )

        return ExplanationNarrative(summary=_build_reasoning(items), sections=sections)


def _build_reasoning(items: Sequence[ExplanationItem]) -> str:
    """Flatten explanation rationales into the legacy reasoning string."""

    return " ".join(item.rationale for item in items)


def _format_heading(source_type: str) -> str:
    cleaned = source_type.replace("_", " ").strip()
    return cleaned.title() if cleaned else source_type
