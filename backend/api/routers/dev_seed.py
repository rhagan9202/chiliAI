"""Dev/e2e-only seed endpoint.

Writes a deterministic, fully-formed investigation scenario (knowledge base +
graph subgraph + alert projection + evidence pack + case) directly into the
*real* repositories so full-stack e2e tests can assert the UI against real data
served by the real API.

The alert/evidence pipeline (Flow B) is LLM-dependent and cannot deterministically
produce alerts in a dev stack, so this endpoint inserts the alert and evidence
into the same real stores the worker would write to — no component, endpoint, or
integration is mocked; only the (non-deterministic) generation step is bypassed.

The demo scenario is derived entirely from the **active** ``DomainConfig``
(E8 — no hardcoded domain types):

* The subgraph shape is a hub entity connected to up to two spoke entities,
  chosen from the config's declared relationships: the first relationship
  source that appears in two or more relationship definitions becomes the hub
  (falling back to the first relationship, then to a single entity when the
  config declares no relationships).
* Entity property values are generated from each ``PropertyDefinition``
  (strings honor ``pattern``/length bounds, numerics honor min/max, enums pick
  a declared value, required properties are always present) and the seeded
  output is checked with ``shared.types.validate_entity`` /
  ``validate_relationship`` before anything is written — the endpoint answers
  422 rather than persisting data that is invalid for the active domain.
* The policy item is generated from the active pack's ``policy_rules`` (first
  entity-target rule whose selector matches a seeded type, else the first
  entity-target rule, seeding a standalone target entity when needed). When
  the active pack declares no entity-target policy rules this part is skipped
  and ``policy_item_id`` is returned as an empty string.
* Under the default medicare pack the seeded display values keep the exact
  shapes the Playwright suite asserts on (entity label "Redwood DME Group",
  alert title "Outlier billing concentration", case title
  "Redwood DME escalation", policy title rendered from the pack's own
  ``title_template``); the medicare-specific strings are applied only when the
  active config actually yields the claim→provider/beneficiary demo shape.

This router is registered ONLY when ``CHILI_ENV != production`` (see
``api/app.py``), so the endpoint does not exist in production.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from analytics.explainability.repository import EvidencePackRepository
from api._alert_store import AlertProjectionRecord, AlertProjectionRepository
from api.dependencies import (
    get_alert_repository,
    get_case_repository,
    get_conversation_repository,
    get_evidence_pack_repository,
    get_graph_repository,
    get_knowledge_base_repository,
    get_policy_repository,
)
from api.middleware.rbac import require_role
from config.schema import DomainConfig, PolicyRule, PolicyRulePack
from policy.adapters.protocols import PolicyItemRepository
from policy.models import PolicyCitation
from policy.service import create_policy_service
from cases.adapters.protocols import CaseRepository
from cases.models import Case
from conversations.adapters.protocols import ConversationRepository
from conversations.models import Conversation, ConversationMessage
from graph.adapters.protocols import GraphRepository
from knowledgebases.protocols import KnowledgeBaseRepository
from shared.types import (
    Alert,
    Entity,
    EntityDefinition,
    EvidencePack,
    KnowledgeBase,
    PropertyDefinition,
    PropertyType,
    Relationship,
    RelationshipDefinition,
    validate_entity,
    validate_relationship,
)
from shared.utils import generate_id, utc_now

__all__ = ["router"]

router = APIRouter(prefix="/admin/dev-seed", tags=["dev"])

_DEMO_DATE = "2026-01-15"


def get_domain_config() -> DomainConfig:
    """Active domain config provider; tests override via ``dependency_overrides``."""
    from api.dependencies import get_domain_config as application_get_domain_config

    return application_get_domain_config()


class DevSeedResponse(BaseModel):
    """Identifiers of the deterministic scenario seeded into the real stores."""

    knowledge_base_id: str
    entity_id: str
    alert_id: str
    evidence_pack_id: str
    case_id: str
    policy_item_id: str
    conversation_id: str


# ---------------------------------------------------------------------------
# Config-driven value generation
# ---------------------------------------------------------------------------


def pattern_example(pattern: str, index: int) -> str | None:
    """Return a deterministic string that full-matches ``pattern``, or None.

    Supports the constructs domain packs realistically use: literal characters,
    escaped literals, ``\\d``/``\\w``/``\\s``, character classes (including
    ranges), ``.``, and the quantifiers ``{n}``, ``{n,m}``, ``+``, ``*``, ``?``.
    Digit positions are filled from ``index`` (zero-padded) so instances of the
    same entity type get distinct natural-key values. Returns ``None`` for
    unsupported constructs (groups, alternation, negated classes, ...).
    """
    body = pattern.removeprefix("^")
    if body.endswith("$") and not body.endswith("\\$"):
        body = body[:-1]

    # Each unit is ("digit", "") or ("literal", <char>).
    units: list[tuple[str, str]] = []
    length = len(body)
    position = 0

    def class_unit(char_class: str) -> tuple[str, str] | None:
        if char_class.startswith("^"):
            return None
        has_digit = False
        literals: list[str] = []
        cursor = 0
        while cursor < len(char_class):
            char = char_class[cursor]
            if char == "\\":
                if cursor + 1 >= len(char_class):
                    return None
                escaped = char_class[cursor + 1]
                if escaped == "d":
                    has_digit = True
                else:
                    literals.append(escaped)
                cursor += 2
                continue
            if cursor + 2 < len(char_class) and char_class[cursor + 1] == "-":
                if char.isdigit():
                    has_digit = True
                else:
                    literals.append(char)
                cursor += 3
                continue
            if char.isdigit():
                has_digit = True
            else:
                literals.append(char)
            cursor += 1
        if has_digit:
            return ("digit", "")
        if literals:
            return ("literal", literals[0])
        return None

    def read_quantifier(cursor: int) -> tuple[int, int] | None:
        """Return (repeat_count, next_cursor); None when unparseable."""
        if cursor < length:
            char = body[cursor]
            if char == "{":
                end = body.find("}", cursor)
                if end == -1:
                    return None
                spec = body[cursor + 1 : end].split(",")[0].strip()
                if not spec.isdigit():
                    return None
                cursor = end + 1
                count = int(spec)
            elif char == "+":
                cursor += 1
                count = 1
            elif char in "*?":
                cursor += 1
                count = 0
            else:
                return (1, cursor)
            # Swallow a lazy-quantifier suffix ("+?", "{2,}?", ...).
            if cursor < length and body[cursor] == "?":
                cursor += 1
            return (count, cursor)
        return (1, cursor)

    while position < length:
        char = body[position]
        unit: tuple[str, str] | None
        if char == "\\":
            if position + 1 >= length:
                return None
            escaped = body[position + 1]
            position += 2
            if escaped == "d":
                unit = ("digit", "")
            elif escaped == "w":
                unit = ("literal", "a")
            elif escaped == "s":
                unit = ("literal", " ")
            elif escaped.isalpha():
                return None  # \D, \W, \S, \b, ... unsupported
            else:
                unit = ("literal", escaped)
        elif char == "[":
            end = body.find("]", position + 1)
            if end == -1:
                return None
            unit = class_unit(body[position + 1 : end])
            position = end + 1
        elif char == ".":
            unit = ("literal", "a")
            position += 1
        else:
            if char in "()|+*?{}":
                return None
            unit = ("literal", char)
            position += 1
        if unit is None:
            return None
        quantifier = read_quantifier(position)
        if quantifier is None:
            return None
        count, position = quantifier
        units.extend([unit] * count)

    digit_slots = sum(1 for kind, _ in units if kind == "digit")
    digit_fill = str(index).rjust(digit_slots, "0")[-digit_slots:] if digit_slots else ""
    filled: list[str] = []
    next_digit = 0
    for kind, text in units:
        if kind == "digit":
            filled.append(digit_fill[next_digit])
            next_digit += 1
        else:
            filled.append(text)
    candidate = "".join(filled)
    return candidate if re.fullmatch(pattern, candidate) is not None else None


def generate_property_value(
    name: str, definition: PropertyDefinition, index: int
) -> object:
    """Generate a deterministic, definition-conformant demo value."""
    if definition.type is PropertyType.STRING:
        if definition.pattern is not None:
            candidate = pattern_example(definition.pattern, index)
            if candidate is not None:
                return candidate
        value = f"{name}-{index}"
        if definition.min_length is not None and len(value) < definition.min_length:
            value = value.ljust(definition.min_length, "x")
        if definition.max_length is not None and len(value) > definition.max_length:
            value = value[: definition.max_length]
        return value
    if definition.type is PropertyType.ENUM:
        values = definition.enum_values or []
        return values[0] if values else ""
    if definition.type is PropertyType.INTEGER:
        number = int(definition.min_value) if definition.min_value is not None else 1
        if definition.max_value is not None and number > definition.max_value:
            number = int(definition.max_value)
        return number
    if definition.type is PropertyType.DECIMAL:
        amount = float(definition.min_value) if definition.min_value is not None else 1.0
        if definition.max_value is not None and amount > definition.max_value:
            amount = float(definition.max_value)
        return amount
    if definition.type is PropertyType.DATE:
        return _DEMO_DATE
    if definition.type is PropertyType.BOOLEAN:
        return True
    if definition.type is PropertyType.LIST:
        item_count = definition.min_length if definition.min_length is not None else 0
        return [f"item-{position + 1}" for position in range(item_count)]
    # PropertyType.NESTED
    return {}


def build_demo_entity(definition: EntityDefinition, index: int) -> Entity:
    """Build one demo entity with every declared property populated."""
    properties: dict[str, object] = {
        property_name: generate_property_value(property_name, property_definition, index)
        for property_name, property_definition in definition.properties.items()
    }
    return Entity(
        id=f"{definition.name}-{index}",
        type=definition.name,
        properties=dict(properties),
    )


# ---------------------------------------------------------------------------
# Demo-shape selection
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DemoShape:
    """The subgraph shape derived from the active config's relationships."""

    hub: EntityDefinition
    spokes: tuple[tuple[RelationshipDefinition, EntityDefinition], ...]


def select_demo_shape(config: DomainConfig) -> DemoShape:
    """Pick a hub entity type plus up to two connecting relationships.

    Prefers the first relationship *source* that appears in at least two
    declared relationships (e.g. medicare ``claim``, food ``shipment``); falls
    back to the first declared relationship, then to a lone entity when the
    config declares no relationships at all.
    """
    if not config.entities:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "The active domain config declares no entity types; "
                "there is nothing to seed for this domain."
            ),
        )
    definitions_by_name = {definition.name: definition for definition in config.entities}
    relationships_by_source: dict[str, list[RelationshipDefinition]] = {}
    for relationship in config.relationships:
        relationships_by_source.setdefault(relationship.source, []).append(relationship)

    for source_name, outgoing in relationships_by_source.items():
        if len(outgoing) >= 2:
            return DemoShape(
                hub=definitions_by_name[source_name],
                spokes=tuple(
                    (relationship, definitions_by_name[relationship.target])
                    for relationship in outgoing[:2]
                ),
            )
    if config.relationships:
        first = config.relationships[0]
        return DemoShape(
            hub=definitions_by_name[first.source],
            spokes=((first, definitions_by_name[first.target]),),
        )
    return DemoShape(hub=config.entities[0], spokes=())


def display_label_for(
    entity: Entity, definition: EntityDefinition, config: DomainConfig
) -> str:
    """Human label for an entity from the config's UI display fields."""
    display_fields = config.ui.display_fields if config.ui is not None else {}
    fields = display_fields.get(entity.type)
    if fields is not None and fields.title in entity.properties:
        return str(entity.properties[fields.title])
    return f"{definition.display_label} {entity.id}"


# ---------------------------------------------------------------------------
# Policy-rule selection
# ---------------------------------------------------------------------------


def select_policy_rule(
    config: DomainConfig, seeded_types: set[str]
) -> tuple[PolicyRulePack, PolicyRule] | None:
    """Pick the entity-target policy rule to demo, preferring seeded types."""
    entity_rules = [
        (pack, rule)
        for pack in config.policy_rules
        for rule in pack.rules
        if rule.target_kind == "entity"
    ]
    for pack, rule in entity_rules:
        if rule.target_selector.get("entity_type") in seeded_types:
            return (pack, rule)
    return entity_rules[0] if entity_rules else None


def resolve_matched_value(
    pack: PolicyRulePack, rule: PolicyRule
) -> str | float | int | bool:
    """Resolve the rule's predicate value into a demo matched-field value."""
    predicate_value = rule.predicate.value
    raw: str | float | int | bool | list[str]
    if predicate_value.literal is not None:
        raw = predicate_value.literal
    elif predicate_value.config_ref is not None:
        raw = pack.thresholds[predicate_value.config_ref]
    else:  # pragma: no cover - PolicyPredicateValue enforces exactly one source
        raw = ""
    if isinstance(raw, list):
        return raw[0] if raw else ""
    if isinstance(raw, bool) or isinstance(raw, str):
        return raw
    # Nudge numeric values across strict bounds so the demo item is coherent.
    if rule.predicate.op == "gt":
        return raw + 1
    if rule.predicate.op == "lt":
        return raw - 1
    return raw


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=DevSeedResponse,
    dependencies=[Depends(require_role("analyst"))],
)
async def dev_seed(
    config: DomainConfig = Depends(get_domain_config),
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    graph_repository: GraphRepository = Depends(get_graph_repository),
    alert_repository: AlertProjectionRepository = Depends(get_alert_repository),
    evidence_repository: EvidencePackRepository = Depends(get_evidence_pack_repository),
    case_repository: CaseRepository = Depends(get_case_repository),
    policy_repository: PolicyItemRepository = Depends(get_policy_repository),
    conversation_repository: ConversationRepository = Depends(get_conversation_repository),
) -> DevSeedResponse:
    """Seed a deterministic KB + subgraph + alert + evidence + case (dev/e2e only)."""
    now = utc_now()
    kb_id = generate_id()

    # --- derive the demo subgraph from the ACTIVE domain config ------------
    shape = select_demo_shape(config)
    indices: dict[str, int] = {}

    def next_index(type_name: str) -> int:
        indices[type_name] = indices.get(type_name, 0) + 1
        return indices[type_name]

    hub_entity = build_demo_entity(shape.hub, next_index(shape.hub.name))
    graph_entities: list[Entity] = [hub_entity]
    relationships: list[Relationship] = []
    spoke_entities: list[tuple[EntityDefinition, Entity]] = []
    for relationship_definition, target_definition in shape.spokes:
        target_entity = build_demo_entity(
            target_definition, next_index(target_definition.name)
        )
        graph_entities.append(target_entity)
        spoke_entities.append((target_definition, target_entity))
        relationships.append(
            Relationship(
                id=f"rel-{relationship_definition.name}",
                type=relationship_definition.name,
                source_id=hub_entity.id,
                target_id=target_entity.id,
            )
        )

    # The alert anchors on the first spoke target (medicare: the provider a
    # claim was submitted_by); a relationship-less domain anchors on the hub.
    anchor_definition, anchor_entity = (
        spoke_entities[0] if spoke_entities else (shape.hub, hub_entity)
    )

    # --- policy rule (config-driven; skipped when the pack has none) -------
    selection = select_policy_rule(config, {entity.type for entity in graph_entities})
    policy_target_entity: Entity | None = None
    if selection is not None:
        _, selected_rule = selection
        selector_type = selected_rule.target_selector.get("entity_type")
        definitions_by_name = {d.name: d for d in config.entities}
        policy_target_entity = next(
            (entity for entity in graph_entities if entity.type == selector_type),
            None,
        )
        if policy_target_entity is None and selector_type in definitions_by_name:
            policy_target_entity = build_demo_entity(
                definitions_by_name[selector_type], next_index(selector_type)
            )
            graph_entities.append(policy_target_entity)
        if policy_target_entity is None:
            policy_target_entity = hub_entity

    # --- guardrail: seeded output MUST be valid for the active domain ------
    validation_errors: list[str] = []
    for entity in graph_entities:
        validation_errors.extend(validate_entity(entity, config.entities))
    entities_by_id = {entity.id: entity for entity in graph_entities}
    for relationship in relationships:
        validation_errors.extend(
            validate_relationship(relationship, config.relationships, entities_by_id)
        )
    if validation_errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "message": (
                    "Could not generate demo data valid for the active domain "
                    f"'{config.domain.name}'; nothing was written."
                ),
                "errors": validation_errors,
            },
        )

    # --- display text: medicare pack keeps the e2e-locked strings ----------
    entity_label = display_label_for(anchor_entity, anchor_definition, config)
    is_medicare_shape = (
        shape.hub.name == "claim"
        and anchor_definition.name == "provider"
        and len(spoke_entities) > 1
        and spoke_entities[1][0].name == "beneficiary"
    )
    if is_medicare_shape:
        entity_label = "Redwood DME Group"
        alert_title = "Outlier billing concentration"
        alert_reasoning = "Provider activity is materially above peers."
        evidence_reasoning = (
            "Provider billing concentration and upcoding indicate elevated fraud risk."
        )
        case_title = "Redwood DME escalation"
        conversation_title = "Redwood DME provider review"
        assistant_answer = (
            "Redwood DME Group shows outlier billing concentration "
            "well above its peer cohort, with linked high-value claims."
        )
        alert_tags = ["billing", "peer-deviation"]
    else:
        alert_title = f"Outlier {anchor_definition.display_label.lower()} activity"
        alert_reasoning = (
            f"{anchor_definition.display_label} activity is materially above peers."
        )
        evidence_reasoning = (
            f"{anchor_definition.display_label} activity concentration "
            "indicates elevated risk."
        )
        case_title = f"{entity_label} escalation"
        conversation_title = f"{entity_label} review"
        assistant_answer = (
            f"{entity_label} shows outlier activity well above its peer cohort, "
            "with linked high-risk records."
        )
        alert_tags = [anchor_entity.type, "peer-deviation"]

    # --- knowledge base -----------------------------------------------------
    kb_repository.create(
        KnowledgeBase(
            id=kb_id,
            name="E2E Seed KB",
            description="Deterministic scenario for full-stack e2e.",
            entity_count=len(graph_entities),
            relationship_count=len(relationships),
            status="ready",
            created_at=now,
            domain=config.domain.name,
        )
    )

    # --- graph subgraph -----------------------------------------------------
    graph_repository.upsert_entities(kb_id, graph_entities)
    graph_repository.upsert_relationships(kb_id, relationships)

    # --- evidence pack ------------------------------------------------------
    evidence_pack_id = generate_id()
    alert_id = generate_id()
    evidence_repository.put(
        kb_id,
        EvidencePack(
            id=evidence_pack_id,
            alert_id=alert_id,
            reasoning=evidence_reasoning,
            subgraph_nodes=[entity.id for entity in graph_entities],
            subgraph_edges=[relationship.id for relationship in relationships],
            confidence=0.82,
            scores={"overall": 0.82, "peer_deviation": 0.94},
        ),
    )

    # --- alert projection ---------------------------------------------------
    alert_repository.upsert(
        AlertProjectionRecord(
            knowledge_base_id=kb_id,
            alert=Alert(
                id=alert_id,
                entity_type=anchor_entity.type,
                entity_id=anchor_entity.id,
                severity="critical",
                title=alert_title,
                reasoning=alert_reasoning,
                evidence_pack_id=evidence_pack_id,
                created_at=now,
            ),
            entity_label=entity_label,
            confidence=0.96,
            tags=alert_tags,
            related_entity_ids=list(
                dict.fromkeys([anchor_entity.id, hub_entity.id])
            ),
        )
    )

    # --- case (independent of the alert so the alert stays promotable) ----
    case_id = generate_id()
    case_repository.create(
        Case(
            id=case_id,
            knowledge_base_id=kb_id,
            title=case_title,
            status="open",
            priority="high",
            assignee="analyst@example.com",
            alert_ids=[],
        )
    )

    # --- policy item (from the active pack's own rule definitions) ----------
    policy_item_id = ""
    if selection is not None and policy_target_entity is not None:
        rule_pack, rule = selection
        policy_service = create_policy_service(policy_repository)
        policy_item = policy_service.record_match(
            knowledge_base_id=kb_id,
            rule_id=rule.id,
            rule_pack_id=rule_pack.id,
            target_kind="entity",
            target_ref=policy_target_entity.id,
            title=rule.title_template.replace("{target_ref}", policy_target_entity.id),
            severity=rule.severity,
            matched_fields={
                rule.predicate.field: resolve_matched_value(rule_pack, rule)
            },
            citations=[
                PolicyCitation(
                    citation_id=citation.citation_id,
                    title=citation.title,
                    source_ref=citation.source_ref,
                    excerpt=citation.excerpt,
                )
                for citation in rule.citations
            ],
        )
        policy_item_id = policy_item.id

    # --- conversation (one seeded RAG chat thread for the KB) ---------------
    conversation_id = generate_id()
    conversation_repository.create(
        Conversation(
            id=conversation_id,
            title=conversation_title,
            knowledge_base_id=kb_id,
            messages=[
                ConversationMessage(
                    id=generate_id(),
                    role="user",
                    content=f"Why is {entity_label} flagged as high risk?",
                    created_at=now,
                ),
                ConversationMessage(
                    id=generate_id(),
                    role="assistant",
                    content=assistant_answer,
                    created_at=now,
                ),
            ],
        )
    )

    return DevSeedResponse(
        knowledge_base_id=kb_id,
        entity_id=anchor_entity.id,
        alert_id=alert_id,
        evidence_pack_id=evidence_pack_id,
        case_id=case_id,
        policy_item_id=policy_item_id,
        conversation_id=conversation_id,
    )
