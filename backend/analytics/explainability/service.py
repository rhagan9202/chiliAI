"""Service entry point for evidence-pack generation flows."""

from __future__ import annotations

from urllib.parse import quote

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
from shared.types import (
    EvidenceNarrativeSection,
    EvidencePack,
    EvidenceProvenanceReference,
    FeatureAttribution,
)
from shared.utils import generate_id
from playbooks.models import PlaybookRef

_PROVENANCE_TRANSFORMATION_VERSION = "explainability-provenance-v1"
_PROVENANCE_SNIPPET_MAX_CHARS = 160


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

        context = _with_generator_lineage(context, self._narrative_generator)
        selected_items = _select_items(context.explanation_items, max_items=max_evidence_items)
        narrative = self._narrative_generator.summarize(context=context, items=selected_items)
        attribution = self._feature_attributor.attribute(context=context)
        narrative_sections = [
            EvidenceNarrativeSection(
                heading=section.heading,
                body=section.body,
                evidence_refs=list(section.evidence_refs),
            )
            for section in narrative.sections
        ]
        evidence_pack = EvidencePack(
            id=generate_id(),
            alert_id=context.alert.id,
            reasoning=narrative.summary,
            subgraph_nodes=context.subgraph.node_ids,
            subgraph_edges=context.subgraph.edge_ids,
            confidence=context.confidence,
            scores=context.scores,
            attribution=attribution,
            narrative_sections=narrative_sections,
            provenance=_build_provenance(
                context=context,
                selected_items=selected_items,
                attribution=attribution,
                narrative_sections=narrative_sections,
            ),
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


def _build_provenance(
    *,
    context: ExplanationContext,
    selected_items: list[ExplanationItem],
    attribution: list[FeatureAttribution],
    narrative_sections: list[EvidenceNarrativeSection],
) -> list[EvidenceProvenanceReference]:
    refs: list[EvidenceProvenanceReference] = []
    seen: set[tuple[str, str]] = set()
    transformation_version = (
        context.lineage.transformation_version or _PROVENANCE_TRANSFORMATION_VERSION
    )
    playbook_ref = context.lineage.playbook_ref

    for index, item in enumerate(selected_items):
        _append_reference(
            refs,
            seen,
            reference_type=item.source_type,
            reference_id=_item_reference_id(item, index=index),
            label=_snippet(item.quote),
            confidence=item.score,
            route_target=_route_target_for_item(context, item),
            transformation_version=transformation_version,
            metadata=_with_playbook_ref_metadata(
                {
                    "source_id": item.source_id,
                    "quote_length": len(item.quote),
                    "rationale_snippet": _snippet(item.rationale),
                    "rationale_length": len(item.rationale),
                },
                playbook_ref,
            ),
        )

    for node_id in context.subgraph.node_ids:
        _append_reference(
            refs,
            seen,
            reference_type="graph_node",
            reference_id=node_id,
            label=node_id,
            route_target=_entity_route(context.knowledge_base_id, node_id),
            transformation_version=transformation_version,
        )

    for edge_id in context.subgraph.edge_ids:
        _append_reference(
            refs,
            seen,
            reference_type="graph_edge",
            reference_id=edge_id,
            label=edge_id,
            transformation_version=transformation_version,
        )

    score_reference_id = context.lineage.score_request_id or f"{context.alert.entity_id}:overall"
    _append_reference(
        refs,
        seen,
        reference_type="risk_score",
        reference_id=score_reference_id,
        label="Overall risk score",
        confidence=context.confidence,
        route_target=_entity_route(context.knowledge_base_id, context.alert.entity_id),
        transformation_version=transformation_version,
        metadata=_with_playbook_ref_metadata(dict(context.scores), playbook_ref),
    )

    for feature in attribution:
        _append_reference(
            refs,
            seen,
            reference_type="feature_attribution",
            reference_id=feature.feature_name,
            label=feature.feature_name,
            transformation_version=transformation_version,
            metadata=_with_playbook_ref_metadata(
                {
                    "contribution": feature.contribution,
                    "rationale_snippet": _snippet(feature.rationale),
                    "rationale_length": len(feature.rationale),
                },
                playbook_ref,
            ),
        )

    for index, section in enumerate(narrative_sections):
        _append_reference(
            refs,
            seen,
            reference_type="narrative_section",
            reference_id=f"section:{index}:{section.heading}",
            label=section.heading,
            transformation_version=transformation_version,
            metadata=_with_playbook_ref_metadata(
                {
                    "body_length": len(section.body),
                    "evidence_refs": list(section.evidence_refs),
                },
                playbook_ref,
            ),
        )

    _append_lineage_reference(
        refs,
        seen,
        reference_type="correlation",
        reference_id=context.lineage.correlation_id,
        label="Workflow correlation ID",
        transformation_version=transformation_version,
    )
    _append_lineage_reference(
        refs,
        seen,
        reference_type="workflow",
        reference_id=context.lineage.workflow_id,
        label="Workflow run",
        transformation_version=transformation_version,
    )
    _append_lineage_reference(
        refs,
        seen,
        reference_type="model_version",
        reference_id=context.lineage.model_version,
        label="Model version",
        transformation_version=transformation_version,
    )
    _append_lineage_reference(
        refs,
        seen,
        reference_type="prompt_version",
        reference_id=context.lineage.prompt_version,
        label="Prompt version",
        transformation_version=transformation_version,
    )

    return refs


def _with_playbook_ref_metadata(
    metadata: dict[str, object], playbook_ref: PlaybookRef | None
) -> dict[str, object]:
    if playbook_ref is None:
        return metadata
    return {
        **metadata,
        "playbook_ref": playbook_ref.model_dump(mode="json"),
    }


def _append_lineage_reference(
    refs: list[EvidenceProvenanceReference],
    seen: set[tuple[str, str]],
    *,
    reference_type: str,
    reference_id: str | None,
    label: str,
    transformation_version: str,
) -> None:
    if reference_id is None:
        return
    _append_reference(
        refs,
        seen,
        reference_type=reference_type,
        reference_id=reference_id,
        label=label,
        transformation_version=transformation_version,
    )


def _append_reference(
    refs: list[EvidenceProvenanceReference],
    seen: set[tuple[str, str]],
    *,
    reference_type: str,
    reference_id: str,
    label: str = "",
    confidence: float | None = None,
    route_target: str | None = None,
    transformation_version: str,
    metadata: dict[str, object] | None = None,
) -> None:
    key = (reference_type, reference_id)
    if key in seen:
        return
    seen.add(key)
    refs.append(
        EvidenceProvenanceReference(
            reference_type=reference_type,
            reference_id=reference_id,
            label=label,
            transformation_version=transformation_version,
            confidence=confidence,
            route_target=route_target,
            metadata=metadata or {},
        )
    )


def _with_generator_lineage(
    context: ExplanationContext, narrative_generator: NarrativeGeneratorProtocol
) -> ExplanationContext:
    model_version = context.lineage.model_version or _optional_string_attr(
        narrative_generator, "model_name"
    )
    prompt_version = context.lineage.prompt_version or _optional_string_attr(
        narrative_generator, "prompt_version"
    )
    if (
        model_version == context.lineage.model_version
        and prompt_version == context.lineage.prompt_version
    ):
        return context
    return context.model_copy(
        update={
            "lineage": context.lineage.model_copy(
                update={
                    "model_version": model_version,
                    "prompt_version": prompt_version,
                }
            )
        }
    )


def _optional_string_attr(value: object, name: str) -> str | None:
    attr = getattr(value, name, None)
    return attr if isinstance(attr, str) and attr else None


def _snippet(value: str) -> str:
    if len(value) <= _PROVENANCE_SNIPPET_MAX_CHARS:
        return value
    return value[: _PROVENANCE_SNIPPET_MAX_CHARS - 3] + "..."


def _item_reference_id(item: ExplanationItem, *, index: int) -> str:
    if item.source_type in {"risk_factor", "risk_summary"}:
        return f"{item.source_id}:{item.quote}"
    if item.source_type == "document":
        return f"{item.source_id}#evidence:{index}"
    return item.source_id


def _route_target_for_item(
    context: ExplanationContext, item: ExplanationItem
) -> str | None:
    if item.source_type == "document":
        return (
            f"/knowledgebases/{quote(context.knowledge_base_id, safe='')}/documents/"
            f"{quote(item.source_id, safe='')}/preview"
        )
    if item.source_type in {"graph_node", "risk_factor", "risk_summary"}:
        return _entity_route(context.knowledge_base_id, item.source_id)
    return None


def _entity_route(knowledge_base_id: str, entity_id: str) -> str:
    return (
        f"/investigation/entities/{quote(entity_id, safe='')}"
        f"?knowledge_base_id={quote(knowledge_base_id, safe='')}"
    )


__all__ = ["ExplainabilityService", "create_explainability_service"]
