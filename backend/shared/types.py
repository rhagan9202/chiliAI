"""Platform and config-definition types.

All domain entity types (provider, claim, beneficiary, etc.) exist only in
config YAML. At runtime they flow through the system as generic ``Entity``
instances whose ``type`` field and ``properties`` dict are validated against
config at system boundaries.

NO hardcoded domain-specific types live here.
"""

from __future__ import annotations

import enum
from datetime import datetime
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
    enum_values: list[str] | None = None


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


class Relationship(BaseModel):
    """A relationship whose ``type`` matches a ``RelationshipDefinition.name``."""

    id: str
    type: str
    source_id: str
    target_id: str
    properties: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Platform types — domain-agnostic, part of chiliAI itself
# ---------------------------------------------------------------------------


class Alert(BaseModel):
    """An alert surfaced by the analytics pipeline."""

    id: str
    entity_type: str
    entity_id: str
    severity: str
    title: str
    reasoning: str
    evidence_pack_id: str | None = None
    created_at: datetime
    acknowledged: bool = False


class EvidencePack(BaseModel):
    """Supporting evidence bundle attached to an alert."""

    id: str
    alert_id: str
    reasoning: str
    subgraph_nodes: list[str]
    subgraph_edges: list[str]
    confidence: float
    scores: dict[str, float] = Field(default_factory=dict)


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

    for extra in sorted(actual_props - defined_props):
        errors.append(
            f"Unexpected property '{extra}' on entity type '{entity.type}'."
        )

    return errors
