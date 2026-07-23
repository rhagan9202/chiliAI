"""Durable graph entity-detail projection (BL-012).

Serves ``/graph/entities/{id}`` from the durable graph service (the same store
the worker and the dev-seed endpoint write to) instead of the seeded
``ApiState`` graph repository. Risk scores come from the durable risk service
and related alerts from the durable alert feed store (``alert_history``).
"""

from __future__ import annotations

from analytics.risk.exceptions import (
    RiskConfigurationError,
    RiskInsufficientSignalsError,
)
from analytics.risk.protocols import RiskServiceProtocol
from analytics.risk.service_models import RiskAssessmentRequest
from api.contracts import (
    GraphEdgeResponse,
    GraphEntityDetailResponse,
    GraphNodeResponse,
)
from config.schema import DomainConfig
from graph.protocols import GraphServiceProtocol
from knowledgebases.protocols import KnowledgeBaseRepository
from monitoring.adapters.protocols import AlertFeedStoreProtocol
from shared.types import Entity, EntityDefinition, Relationship

__all__ = ["build_graph_entity_detail"]

_KB_PAGE_SIZE = 200


def build_graph_entity_detail(
    entity_id: str,
    *,
    graph_service: GraphServiceProtocol,
    risk_service: RiskServiceProtocol,
    alert_store: AlertFeedStoreProtocol,
    kb_repository: KnowledgeBaseRepository,
    domain_config: DomainConfig,
) -> GraphEntityDetailResponse | None:
    """Return the durable entity detail, or ``None`` when the entity is absent."""
    kb_ids = _list_all_knowledge_base_ids(kb_repository)
    entity = graph_service.get_entity(kb_ids, entity_id)
    if entity is None:
        return None

    owning_kb_id = _owning_kb_id(graph_service, kb_ids, entity_id) or (
        kb_ids[0] if kb_ids else ""
    )
    neighbors, relationships = (
        graph_service.get_neighbors(owning_kb_id, entity_id)
        if owning_kb_id
        else ([], [])
    )
    definitions = {definition.name: definition for definition in domain_config.entities}

    return GraphEntityDetailResponse(
        entity=_to_node(
            entity,
            risk_score=_safe_risk_score(risk_service, owning_kb_id, entity_id),
            definitions=definitions,
        ),
        neighbors=[
            _to_node(
                neighbor,
                risk_score=_safe_risk_score(risk_service, owning_kb_id, neighbor.id),
                definitions=definitions,
            )
            for neighbor in neighbors
        ],
        relationships=[_to_edge(relationship) for relationship in relationships],
        related_alert_ids=_related_alert_ids(alert_store, entity_id),
    )


def _list_all_knowledge_base_ids(kb_repository: KnowledgeBaseRepository) -> list[str]:
    ids: list[str] = []
    offset = 0
    while True:
        page, total = kb_repository.list(limit=_KB_PAGE_SIZE, offset=offset)
        ids.extend(kb.id for kb in page)
        offset += len(page)
        if not page or offset >= total:
            break
    return ids


def _owning_kb_id(
    graph_service: GraphServiceProtocol,
    kb_ids: list[str],
    entity_id: str,
) -> str | None:
    for kb_id in kb_ids:
        if graph_service.get_entity([kb_id], entity_id) is not None:
            return kb_id
    return None


def _safe_risk_score(
    risk_service: RiskServiceProtocol,
    knowledge_base_id: str,
    entity_id: str,
) -> float:
    if not knowledge_base_id:
        return 0.0
    try:
        return risk_service.assess(
            RiskAssessmentRequest(
                knowledge_base_id=knowledge_base_id, entity_id=entity_id
            )
        ).overall_score
    except (RiskConfigurationError, RiskInsufficientSignalsError, ValueError):
        return 0.0


def _related_alert_ids(
    alert_store: AlertFeedStoreProtocol,
    entity_id: str,
) -> list[str]:
    related: list[str] = []
    offset = 0
    while True:
        records, total = alert_store.list_alerts(limit=500, offset=offset)
        related.extend(
            record.alert_id for record in records if record.entity_id == entity_id
        )
        offset += len(records)
        if not records or offset >= total:
            break
    return related


def _to_node(
    entity: Entity,
    *,
    risk_score: float,
    definitions: dict[str, EntityDefinition],
) -> GraphNodeResponse:
    label = str(entity.properties.get("display_name", entity.id))
    return GraphNodeResponse(
        id=entity.id,
        type=entity.type,
        label=label,
        summary=_entity_summary(entity, definitions),
        risk_score=risk_score,
        properties={
            key: value
            for key, value in entity.properties.items()
            if isinstance(value, (str, int, float, bool))
        },
    )


def _to_edge(relationship: Relationship) -> GraphEdgeResponse:
    return GraphEdgeResponse(
        id=relationship.id,
        type=relationship.type,
        source_id=relationship.source_id,
        target_id=relationship.target_id,
        summary=(
            f"{relationship.type.replace('_', ' ')} between "
            f"{relationship.source_id} and {relationship.target_id}."
        ),
    )


def _entity_summary(entity: Entity, definitions: dict[str, EntityDefinition]) -> str:
    definition = definitions.get(entity.type)
    label = definition.display_label if definition is not None else entity.type.title()
    display_name = entity.properties.get("display_name")
    if isinstance(display_name, str) and display_name.strip():
        return f"{label} entity named {display_name} in the active knowledge base."
    return f"{label} entity in the active knowledge base."
