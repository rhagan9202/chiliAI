"""Validation logic for extracted entity and relationship candidates."""

from __future__ import annotations

from ingestion.models import CandidateEntity, CandidateRelationship, ExtractionResult, ValidationReport
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


def _entity_from_candidate(candidate: CandidateEntity) -> Entity:
    """Convert a CandidateEntity to a validated Entity, stamping document provenance."""
    return Entity(
        id=candidate.id,
        type=candidate.type,
        properties=dict(candidate.properties),
        metadata={
            **candidate.metadata,
            SOURCE_KIND_KEY: SOURCE_KIND_DOCUMENT,
            SOURCE_DOCUMENT_ID_KEY: candidate.source_document_id,
            SOURCE_CHUNK_ID_KEY: candidate.chunk_id,
            "confidence": candidate.confidence,
            "extraction_method": candidate.extraction_method,
        },
    )


def _relationship_from_candidate(candidate: CandidateRelationship) -> Relationship:
    """Convert a CandidateRelationship to a Relationship, stamping document provenance."""
    return Relationship(
        id=candidate.id,
        type=candidate.type,
        source_id=candidate.source_candidate_id,
        target_id=candidate.target_candidate_id,
        properties=dict(candidate.properties),
        metadata={
            **candidate.metadata,
            SOURCE_KIND_KEY: SOURCE_KIND_DOCUMENT,
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
        entities_by_id: dict[str, Entity] = {}

        for candidate in extraction_result.candidate_entities:
            entity = _entity_from_candidate(candidate)
            errors = validate_entity(entity, self._entity_definitions)
            if errors:
                entity_errors[candidate.id] = errors
                continue
            valid_entities.append(entity)
            entities_by_id[entity.id] = entity

        for candidate in extraction_result.candidate_relationships:
            relationship = _relationship_from_candidate(candidate)
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