"""Service entry point for evidence-pack generation flows."""

from __future__ import annotations

from analytics.explainability.adapters.deterministic import DeterministicNarrativeGenerator
from analytics.explainability.adapters.protocols import ExplainabilityContextSourceProtocol
from analytics.explainability.adapters.shap_attribution import NoopFeatureAttributor
from analytics.explainability.exceptions import (
    ExplainabilityConfigurationError,
    ExplainabilityInsufficientEvidenceError,
    ExplainabilitySourceError,
)
from analytics.explainability.models import ExplanationContext, ExplanationItem
from analytics.explainability.protocols import FeatureAttributorProtocol, NarrativeGeneratorProtocol
from analytics.explainability.service_models import (
    ExplainabilityEvidence,
    ExplainabilityRequest,
    ExplainabilityResponse,
)
from events.protocols import EventBus
from events.types import ExplainabilityGeneratedEvent, ExplainabilityGeneratedReference
from shared.types import EvidenceNarrativeSection, EvidencePack
from shared.utils import generate_id


class ExplainabilityService:
    """Coordinate context loading, evidence assembly, and event publication."""

    # TODO(production): Integrate SHAP/LIME for model-agnostic feature attribution.
    # Add configurable evidence selection strategies (top-k by score, diversity
    # sampling, subgraph-aware selection).

    def __init__(
        self,
        context_source: ExplainabilityContextSourceProtocol,
        *,
        event_bus: EventBus,
        narrative_generator: NarrativeGeneratorProtocol | None = None,
        feature_attributor: FeatureAttributorProtocol | None = None,
    ) -> None:
        self._context_source = context_source
        self._event_bus = event_bus
        self._narrative_generator = narrative_generator or DeterministicNarrativeGenerator()
        self._feature_attributor = feature_attributor or NoopFeatureAttributor()

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

        return self.generate_from_context(
            context, max_evidence_items=request.max_evidence_items
        )

    def generate_from_context(
        self,
        context: ExplanationContext,
        *,
        max_evidence_items: int = 3,
    ) -> ExplainabilityResponse:
        """Assemble and publish an evidence pack from an already-loaded context.

        Used by the worker, which builds the context from the graph subgraph and
        risk assessment directly, bypassing the context-source load step.
        """

        if not context.explanation_items:
            raise ExplainabilityInsufficientEvidenceError(
                "Explainability context requires at least one explanation item."
            )

        selected_items = _select_items(context.explanation_items, max_items=max_evidence_items)
        narrative = self._narrative_generator.summarize(context=context, items=selected_items)
        attribution = self._feature_attributor.attribute(context=context)
        evidence_pack = EvidencePack(
            id=generate_id(),
            alert_id=context.alert.id,
            reasoning=narrative.summary,
            subgraph_nodes=context.subgraph.node_ids,
            subgraph_edges=context.subgraph.edge_ids,
            confidence=context.confidence,
            scores=context.scores,
            attribution=attribution,
            narrative_sections=[
                EvidenceNarrativeSection(
                    heading=section.heading,
                    body=section.body,
                    evidence_refs=list(section.evidence_refs),
                )
                for section in narrative.sections
            ],
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
    narrative_generator: NarrativeGeneratorProtocol | None = None,
    feature_attributor: FeatureAttributorProtocol | None = None,
) -> ExplainabilityService:
    """Create the default explainability service."""

    return ExplainabilityService(
        context_source,
        event_bus=event_bus,
        narrative_generator=narrative_generator,
        feature_attributor=feature_attributor,
    )


def _select_items(items: list[ExplanationItem], *, max_items: int) -> list[ExplanationItem]:
    return sorted(items, key=lambda item: item.score, reverse=True)[:max_items]


__all__ = ["ExplainabilityService", "create_explainability_service"]
