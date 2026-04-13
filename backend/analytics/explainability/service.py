"""Service entry point for evidence-pack generation flows."""

from __future__ import annotations

from analytics.explainability.adapters.protocols import ExplainabilityContextSourceProtocol
from analytics.explainability.exceptions import (
    ExplainabilityConfigurationError,
    ExplainabilityInsufficientEvidenceError,
    ExplainabilitySourceError,
)
from analytics.explainability.models import ExplanationItem
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
    # sampling, subgraph-aware selection). Current _build_reasoning() concatenates
    # rationale strings — needs structured narrative generation.

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
        evidence_pack = EvidencePack(
            id=generate_id(),
            alert_id=context.alert.id,
            reasoning=_build_reasoning(selected_items),
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
    return " ".join(item.rationale for item in items)


__all__ = ["ExplainabilityService", "create_explainability_service"]