"""Validation logic for extracted entity and relationship candidates."""

from __future__ import annotations

from ingestion.models import CandidateEntity, CandidateRelationship, ExtractionResult, ValidationReport
from ingestion.normalization import normalize_properties
from shared.provenance import (
    SOURCE_CHUNK_ID_KEY,
    SOURCE_DOCUMENT_ID_KEY,
    SOURCE_KIND_DOCUMENT,
    SOURCE_KIND_KEY,
)
from shared.types import (
    Entity,
    EntityDefinition,
    Relationship,
    RelationshipDefinition,
    validate_entity,
    validate_relationship,
)
from shared.utils import generate_id


# Mirror the platform-owned fields that ``validate_entity`` exempts from the
# unexpected-property check (shared/types.py); these must never be stripped.
_PLATFORM_OWNED_PROPERTIES = {"created_at", "updated_at", "version"}


def _partition_entity_properties(
    entity_type: str,
    properties: dict[str, object],
    definitions_by_type: dict[str, EntityDefinition],
) -> tuple[dict[str, object], dict[str, object]]:
    """Split properties into (schema-known, unknown-extra) for a known entity type.

    Unknown entity types are returned intact (``validate_entity`` rejects them);
    extras are only separated when the type is recognized so a single hallucinated
    property cannot drop an otherwise-valid entity. The caller relegates the extras
    to ``metadata.extra_properties`` and admits the entity.
    """
    definition = definitions_by_type.get(entity_type)
    if definition is None:
        return dict(properties), {}
    allowed = set(definition.properties) | _PLATFORM_OWNED_PROPERTIES
    known: dict[str, object] = {}
    extra: dict[str, object] = {}
    for name, value in properties.items():
        if name in allowed:
            known[name] = value
        else:
            extra[name] = value
    return known, extra


def _entity_from_candidate(
    candidate: CandidateEntity,
    source_kind: str,
    *,
    properties: dict[str, object],
    extra_properties: dict[str, object],
) -> Entity:
    """Convert a CandidateEntity to a validated Entity, stamping origin provenance."""
    metadata: dict[str, object] = {
        **candidate.metadata,
        SOURCE_KIND_KEY: source_kind,
        SOURCE_DOCUMENT_ID_KEY: candidate.source_document_id,
        SOURCE_CHUNK_ID_KEY: candidate.chunk_id,
        "confidence": candidate.confidence,
        "extraction_method": candidate.extraction_method,
    }
    if extra_properties:
        metadata["extra_properties"] = extra_properties
    return Entity(
        id=candidate.id,
        type=candidate.type,
        properties=properties,
        metadata=metadata,
    )


def _relationship_from_candidate(
    candidate: CandidateRelationship,
    source_kind: str,
) -> Relationship:
    """Convert a CandidateRelationship to a Relationship, stamping origin provenance."""
    return Relationship(
        id=candidate.id,
        type=candidate.type,
        source_id=candidate.source_candidate_id,
        target_id=candidate.target_candidate_id,
        properties=dict(candidate.properties),
        metadata={
            **candidate.metadata,
            SOURCE_KIND_KEY: source_kind,
            SOURCE_DOCUMENT_ID_KEY: candidate.source_document_id,
            SOURCE_CHUNK_ID_KEY: candidate.chunk_id,
            "confidence": candidate.confidence,
            "extraction_method": candidate.extraction_method,
        },
    )


class ExtractionResultValidator:
    """Validate extracted candidates against config-defined entity and relationship schemas."""

    # TODO(production): Add confidence threshold filtering (discard candidates below
    # a configurable minimum confidence). Add duplicate entity detection (same type +
    # similar properties within the same document). Add validation warnings for
    # near-misses (e.g. optional property missing). Add property-type-aware value
    # validation (date format, numeric ranges, enum membership from config).

    def __init__(
        self,
        entity_definitions: list[EntityDefinition],
        relationship_definitions: list[RelationshipDefinition],
    ) -> None:
        self._entity_definitions = entity_definitions
        self._relationship_definitions = relationship_definitions

    def validate_extraction(self, extraction_result: ExtractionResult) -> ValidationReport:
        valid_entities: list[Entity] = []
        valid_relationships: list[Relationship] = []
        entity_errors: dict[str, list[str]] = {}
        relationship_errors: dict[str, list[str]] = {}
        warnings: list[str] = []
        entities_by_id: dict[str, Entity] = {}

        source_kind_by_chunk = {
            chunk.id: chunk.metadata.source_kind for chunk in extraction_result.chunks
        }
        definitions_by_type = {d.name: d for d in self._entity_definitions}

        for candidate in extraction_result.candidate_entities:
            source_kind = source_kind_by_chunk.get(candidate.chunk_id, SOURCE_KIND_DOCUMENT)
            known_properties, extra_properties = _partition_entity_properties(
                candidate.type,
                candidate.properties,
                definitions_by_type,
            )
            if extra_properties:
                plural = "y" if len(extra_properties) == 1 else "ies"
                warnings.append(
                    f"Entity '{candidate.id}' ({candidate.type}): relocated "
                    f"{len(extra_properties)} unrecognized propert{plural} to "
                    f"metadata.extra_properties: {sorted(extra_properties)}."
                )
            definition = definitions_by_type.get(candidate.type)
            if definition is not None:
                known_properties, normalization_errors = normalize_properties(
                    known_properties, definition
                )
                if normalization_errors:
                    entity_errors[candidate.id] = normalization_errors
                    continue
            entity = _entity_from_candidate(
                candidate,
                source_kind,
                properties=known_properties,
                extra_properties=extra_properties,
            )
            errors = validate_entity(entity, self._entity_definitions)
            if errors:
                entity_errors[candidate.id] = errors
                continue
            valid_entities.append(entity)
            entities_by_id[entity.id] = entity

        for candidate in extraction_result.candidate_relationships:
            source_kind = source_kind_by_chunk.get(candidate.chunk_id, SOURCE_KIND_DOCUMENT)
            relationship = _relationship_from_candidate(candidate, source_kind)
            errors = validate_relationship(
                relationship,
                self._relationship_definitions,
                entities_by_id,
            )
            if errors:
                relationship_errors[candidate.id] = errors
                continue
            valid_relationships.append(relationship)

        return ValidationReport(
            id=generate_id(),
            extraction_result_id=extraction_result.id,
            source_document_id=extraction_result.source_document_id,
            valid_entities=valid_entities,
            valid_relationships=valid_relationships,
            entity_errors=entity_errors,
            relationship_errors=relationship_errors,
            warnings=warnings,
        )


def create_extraction_validator(
    entity_definitions: list[EntityDefinition],
    relationship_definitions: list[RelationshipDefinition],
) -> ExtractionResultValidator:
    """Create the default validator for extracted candidates."""

    return ExtractionResultValidator(entity_definitions, relationship_definitions)


__all__ = [
    "ExtractionResultValidator",
    "create_extraction_validator",
]