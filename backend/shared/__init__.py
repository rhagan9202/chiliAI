"""Shared contracts library — domain types, protocols, and utilities.

This module is the leaf dependency that all other backend modules may import.
It must stay dependency-light and must never contain business logic.
"""

from __future__ import annotations

from shared.protocols import Configurable
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
)
from shared.utils import generate_id, normalize_text

__all__ = [
    "Alert",
    "Configurable",
    "Entity",
    "EntityDefinition",
    "EvidencePack",
    "KnowledgeBase",
    "PropertyDefinition",
    "PropertyType",
    "Relationship",
    "RelationshipDefinition",
    "generate_id",
    "normalize_text",
    "validate_entity",
]
