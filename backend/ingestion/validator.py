"""Validation logic for extracted entity and relationship candidates."""

from __future__ import annotations

from ingestion.models import ExtractionResult, ValidationReport
from shared.types import (
    Entity,
    EntityDefinition,
    Relationship,
    RelationshipDefinition,
    validate_entity,
    validate_relationship,
)
from shared.utils import generate_id


class ExtractionResultValidator:
    """Validate extracted candidates against config-defined entity and relationship schemas."""

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
            entity = Entity(
                id=candidate.id,
                type=candidate.type,
                properties=dict(candidate.properties),
                metadata={
                    **candidate.metadata,
                    "source_document_id": candidate.source_document_id,
                    "chunk_id": candidate.chunk_id,
                    "confidence": candidate.confidence,
                    "extraction_method": candidate.extraction_method,
                },
            )
            errors = validate_entity(entity, self._entity_definitions)
            if errors:
                entity_errors[candidate.id] = errors
                continue
            valid_entities.append(entity)
            entities_by_id[entity.id] = entity

        for candidate in extraction_result.candidate_relationships:
            relationship = Relationship(
                id=candidate.id,
                type=candidate.type,
                source_id=candidate.source_candidate_id,
                target_id=candidate.target_candidate_id,
                properties=dict(candidate.properties),
            )
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


__all__ = ["ExtractionResultValidator", "create_extraction_validator"]