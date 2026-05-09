"""Service entry point for evidence-pack generation flows."""

from __future__ import annotations

from analytics.explainability.adapters.protocols import ExplainabilityContextSourceProtocol
from analytics.explainability.exceptions import (
    ExplainabilityConfigurationError,
    ExplainabilityInsufficientEvidenceError,
    ExplainabilitySourceError,
)
from analytics.explainability.models import (
    ExplanationItem,
    ExplanationNarrative,
    NarrativeSection,
)
from analytics.explainability.service_models import (
    ExplainabilityEvidence,
    ExplainabilityRequest,
    ExplainabilityResponse,
)
from events.protocols import EventBus
from events.types import ExplainabilityGeneratedEvent, ExplainabilityGeneratedReference
from shared.types import EvidencePack
from shared.utils import generate_id


class ExplainabilityService:
    """Coordinate context loading, evidence assembly, and event publication."""

    # TODO(production): Integrate SHAP/LIME for model-agnostic feature attribution.
    # Add LLM-generated narrative explanations (natural language reasoning).
    # Add configurable evidence selection strategies (top-k by score, diversity
    # sampling, subgraph-aware selection).

    def __init__(self, context_source: ExplainabilityContextSourceProtocol, *, event_bus: EventBus) -> None:
        self._context_source = context_source
        self._event_bus = event_bus

    def generate(self, request: ExplainabilityRequest) -> ExplainabilityResponse:
        try:
            context = self._context_source.load_context(
                knowledge_base_id=request.knowledge_base_id,
                alert_id=request.alert_id,
            )
        except ValueError as exc:
            raise ExplainabilityConfigurationError(str(exc)) from exc
        except Exception as exc:
            raise ExplainabilitySourceError("Failed to load explainability context.") from exc

        if not context.explanation_items:
            raise ExplainabilityInsufficientEvidenceError(
                "Explainability context requires at least one explanation item."
            )

        selected_items = _select_items(context.explanation_items, max_items=request.max_evidence_items)
        narrative = _build_narrative(selected_items)
        evidence_pack = EvidencePack(
            id=generate_id(),
            alert_id=context.alert.id,
            reasoning=narrative.summary,
            subgraph_nodes=context.subgraph.node_ids,
            subgraph_edges=context.subgraph.edge_ids,
            confidence=context.confidence,
            scores=context.scores,
        )
        response = ExplainabilityResponse(
            request_id=generate_id(),
            knowledge_base_id=context.knowledge_base_id,
            alert_id=context.alert.id,
            evidence_pack=evidence_pack,
            evidence_items=[
                ExplainabilityEvidence(
                    source_id=item.source_id,
                    source_type=item.source_type,
                    quote=item.quote,
                    rationale=item.rationale,
                    score=item.score,
                )
                for item in selected_items
            ],
            narrative=narrative,
        )
        self._event_bus.publish(
            ExplainabilityGeneratedEvent(
                evidence_packs=[
                    ExplainabilityGeneratedReference(
                        knowledge_base_id=response.knowledge_base_id,
                        request_id=response.request_id,
                        alert_id=response.alert_id,
                        evidence_pack_id=response.evidence_pack.id,
                        evidence_item_count=len(response.evidence_items),
                        subgraph_node_count=len(response.evidence_pack.subgraph_nodes),
                        subgraph_edge_count=len(response.evidence_pack.subgraph_edges),
                    )
                ]
            )
        )
        return response


def create_explainability_service(
    context_source: ExplainabilityContextSourceProtocol,
    *,
    event_bus: EventBus,
) -> ExplainabilityService:
    """Create the default explainability service."""

    return ExplainabilityService(context_source, event_bus=event_bus)


def _select_items(items: list[ExplanationItem], *, max_items: int) -> list[ExplanationItem]:
    return sorted(items, key=lambda item: item.score, reverse=True)[:max_items]


def _build_reasoning(items: list[ExplanationItem]) -> str:
    """Flatten explanation rationales into the legacy reasoning string.

    Retained as a deterministic helper used by `_build_narrative` and tests
    that still rely on the flattened form for the evidence-pack `reasoning`
    field.
    """

    return " ".join(item.rationale for item in items)


def _build_narrative(items: list[ExplanationItem]) -> ExplanationNarrative:
    """Group explanation items by `source_type` into a structured narrative."""

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


def _format_heading(source_type: str) -> str:
    cleaned = source_type.replace("_", " ").strip()
    return cleaned.title() if cleaned else source_type


__all__ = ["ExplainabilityService", "create_explainability_service"]
