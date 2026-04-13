"""Platform and config-definition types.

All domain entity types (provider, claim, beneficiary, etc.) exist only in
config YAML. At runtime they flow through the system as generic ``Entity``
instances whose ``type`` field and ``properties`` dict are validated against
config at system boundaries.

NO hardcoded domain-specific types live here.
"""

from __future__ import annotations

import enum
from datetime import date, datetime
import re
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Config-definition types — describe the schema loaded from YAML
# ---------------------------------------------------------------------------


class PropertyType(str, enum.Enum):
    """Supported property value types in entity definitions."""

    STRING = "string"
    INTEGER = "integer"
    DECIMAL = "decimal"
    DATE = "date"
    LIST = "list"
    BOOLEAN = "boolean"
    ENUM = "enum"
    NESTED = "nested"


class PropertyDefinition(BaseModel):
    """Schema for a single property on an entity definition."""

    type: PropertyType
    display: str
    required: bool = False
    enum_values: list[str] | None = None
    min_value: float | None = None
    max_value: float | None = None
    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None


class EntityDefinition(BaseModel):
    """Defines an entity type in the domain configuration."""

    name: str
    display_label: str
    icon: str
    properties: dict[str, PropertyDefinition]


class RelationshipDefinition(BaseModel):
    """Defines a relationship type in the domain configuration."""

    name: str
    display_label: str
    source: str
    target: str


# ---------------------------------------------------------------------------
# Generic runtime types — domain-agnostic containers
# ---------------------------------------------------------------------------


class Entity(BaseModel):
    """A domain entity whose ``type`` matches an ``EntityDefinition.name``."""

    id: str
    type: str
    properties: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    # TODO(production): Add created_at/updated_at timestamps for audit and
    # change-detection during graph merges. Add version: int for optimistic
    # concurrency control in graph upserts.


class Relationship(BaseModel):
    """A relationship whose ``type`` matches a ``RelationshipDefinition.name``."""

    id: str
    type: str
    source_id: str
    target_id: str
    properties: dict[str, Any] = Field(default_factory=dict)
    # TODO(production): Add created_at/updated_at timestamps. Add weight: float | None
    # for weighted graph algorithms. Add version: int for concurrency control.


# ---------------------------------------------------------------------------
# Platform types — domain-agnostic, part of chiliAI itself
# ---------------------------------------------------------------------------


class Alert(BaseModel):
    """An alert surfaced by the analytics pipeline."""

    id: str
    entity_type: str
    entity_id: str
    # TODO(production): Replace bare str with a SeverityLevel enum ("low", "medium",
    # "high", "critical") to enforce valid values at system boundaries.
    severity: str
    title: str
    reasoning: str
    evidence_pack_id: str | None = None
    created_at: datetime
    acknowledged: bool = False
    # TODO(production): Add full alert status lifecycle — e.g. status: AlertStatus
    # enum ("open", "acknowledged", "investigating", "resolved", "dismissed").
    # Add updated_at: datetime | None for tracking status changes.
    # Add resolved_by: str | None and resolution_notes: str | None.


class EvidencePack(BaseModel):
    """Supporting evidence bundle attached to an alert."""

    id: str
    alert_id: str
    reasoning: str
    subgraph_nodes: list[str]
    subgraph_edges: list[str]
    confidence: float
    scores: dict[str, float] = Field(default_factory=dict)
    # TODO(production): Enrich EvidencePack with structured fields:
    # - created_at: datetime for audit trail
    # - source_documents: list[str] linking back to originating documents
    # - timeline_events: list[TimelineEntry] for temporal evidence ordering
    # - visual_layout: dict for pre-computed graph visualization coordinates


class KnowledgeBase(BaseModel):
    """Metadata record for a knowledge base."""

    id: str
    name: str
    description: str
    entity_count: int = 0
    relationship_count: int = 0
    document_count: int = 0
    status: str = "active"
    created_at: datetime
    # TODO(production): Add updated_at: datetime | None to track last modification.
    # Add domain_config_version: str | None to pin which config version was active.
    # Add owner: str | None and tags: dict[str, str] for organization.


# ---------------------------------------------------------------------------
# Runtime validation helper
# ---------------------------------------------------------------------------


def validate_entity(
    entity: Entity,
    entity_definitions: list[EntityDefinition],
) -> list[str]:
    """Validate an ``Entity`` against config-defined entity definitions.

    Returns a list of validation error strings (empty means valid).
    Intended for use at system boundaries (ingestion, API input).
    """
    errors: list[str] = []

    defn_map = {d.name: d for d in entity_definitions}
    defn = defn_map.get(entity.type)
    if defn is None:
        errors.append(
            f"Unknown entity type '{entity.type}'. "
            f"Valid types: {sorted(defn_map.keys())}"
        )
        return errors

    defined_props = set(defn.properties.keys())
    actual_props = set(entity.properties.keys())

    for property_name, property_definition in defn.properties.items():
        if property_definition.required and property_name not in entity.properties:
            errors.append(
                f"Missing required property '{property_name}' on entity type '{entity.type}'."
            )

    for extra in sorted(actual_props - defined_props):
        errors.append(
            f"Unexpected property '{extra}' on entity type '{entity.type}'."
        )

    for property_name in sorted(actual_props & defined_props):
        errors.extend(
            _validate_property_value(
                entity.type,
                property_name,
                entity.properties[property_name],
                defn.properties[property_name],
            )
        )

    return errors


def validate_relationship(
    relationship: Relationship,
    relationship_definitions: list[RelationshipDefinition],
    entities_by_id: dict[str, Entity],
) -> list[str]:
    """Validate a ``Relationship`` against config and resolved entity endpoints."""
    errors: list[str] = []

    defn_map = {definition.name: definition for definition in relationship_definitions}
    definition = defn_map.get(relationship.type)
    if definition is None:
        errors.append(
            f"Unknown relationship type '{relationship.type}'. "
            f"Valid types: {sorted(defn_map.keys())}"
        )
        return errors

    source_entity = entities_by_id.get(relationship.source_id)
    if source_entity is None:
        errors.append(
            f"Relationship '{relationship.id}' source entity '{relationship.source_id}' was not validated."
        )
    elif source_entity.type != definition.source:
        errors.append(
            f"Relationship '{relationship.type}' requires source type '{definition.source}' "
            f"but got '{source_entity.type}'."
        )

    target_entity = entities_by_id.get(relationship.target_id)
    if target_entity is None:
        errors.append(
            f"Relationship '{relationship.id}' target entity '{relationship.target_id}' was not validated."
        )
    elif target_entity.type != definition.target:
        errors.append(
            f"Relationship '{relationship.type}' requires target type '{definition.target}' "
            f"but got '{target_entity.type}'."
        )

    for extra in sorted(relationship.properties.keys()):
        errors.append(
            f"Unexpected property '{extra}' on relationship type '{relationship.type}'."
        )

    return errors


def _validate_property_value(
    entity_type: str,
    property_name: str,
    value: Any,
    definition: PropertyDefinition,
) -> list[str]:
    errors: list[str] = []

    if not _matches_property_type(value, definition):
        errors.append(
            f"Property '{property_name}' on entity type '{entity_type}' "
            f"must be of type '{definition.type.value}'."
        )
        return errors

    if definition.type is PropertyType.ENUM:
        enum_values = definition.enum_values or []
        if str(value) not in enum_values:
            errors.append(
                f"Property '{property_name}' on entity type '{entity_type}' "
                f"must be one of {enum_values}."
            )

    if definition.type in {PropertyType.INTEGER, PropertyType.DECIMAL}:
        numeric_value = float(value)
        if definition.min_value is not None and numeric_value < definition.min_value:
            errors.append(
                f"Property '{property_name}' on entity type '{entity_type}' "
                f"must be >= {definition.min_value}."
            )
        if definition.max_value is not None and numeric_value > definition.max_value:
            errors.append(
                f"Property '{property_name}' on entity type '{entity_type}' "
                f"must be <= {definition.max_value}."
            )

    if definition.type in {PropertyType.STRING, PropertyType.LIST, PropertyType.NESTED}:
        length = len(value)
        if definition.min_length is not None and length < definition.min_length:
            errors.append(
                f"Property '{property_name}' on entity type '{entity_type}' "
                f"must have length >= {definition.min_length}."
            )
        if definition.max_length is not None and length > definition.max_length:
            errors.append(
                f"Property '{property_name}' on entity type '{entity_type}' "
                f"must have length <= {definition.max_length}."
            )

    if definition.pattern is not None and isinstance(value, str):
        if re.fullmatch(definition.pattern, value) is None:
            errors.append(
                f"Property '{property_name}' on entity type '{entity_type}' "
                f"must match pattern '{definition.pattern}'."
            )

    return errors


def _matches_property_type(value: Any, definition: PropertyDefinition) -> bool:
    property_type = definition.type
    if property_type is PropertyType.STRING:
        return isinstance(value, str)
    if property_type is PropertyType.INTEGER:
        return isinstance(value, int) and not isinstance(value, bool)
    if property_type is PropertyType.DECIMAL:
        return (isinstance(value, int) or isinstance(value, float)) and not isinstance(value, bool)
    if property_type is PropertyType.DATE:
        if isinstance(value, (date, datetime)):
            return True
        if isinstance(value, str):
            try:
                date.fromisoformat(value)
            except ValueError:
                return False
            return True
        return False
    if property_type is PropertyType.LIST:
        return isinstance(value, list)
    if property_type is PropertyType.BOOLEAN:
        return isinstance(value, bool)
    if property_type is PropertyType.ENUM:
        return isinstance(value, str)
    if property_type is PropertyType.NESTED:
        return isinstance(value, dict)
    return False


__all__ = [
    "Alert",
    "Entity",
    "EntityDefinition",
    "EvidencePack",
    "KnowledgeBase",
    "PropertyDefinition",
    "PropertyType",
    "Relationship",
    "RelationshipDefinition",
    "validate_entity",
    "validate_relationship",
]
