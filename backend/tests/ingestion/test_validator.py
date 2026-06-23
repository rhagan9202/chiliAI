"""Tests for validating extracted candidates into runtime objects."""

from __future__ import annotations

from ingestion.models import (
    CandidateEntity,
    CandidateRelationship,
    Chunk,
    ChunkMetadata,
    ExtractionResult,
)
from ingestion.validator import ExtractionResultValidator
from shared.provenance import SOURCE_KIND_DOCUMENT, SOURCE_KIND_KEY, SOURCE_KIND_RECORD
from shared.types import EntityDefinition, PropertyDefinition, PropertyType, RelationshipDefinition


def _entity_definition(name: str, properties: list[str]) -> EntityDefinition:
    return EntityDefinition(
        name=name,
        display_label=name.title(),
        icon="box",
        properties={
            property_name: PropertyDefinition(type=PropertyType.STRING, display=property_name)
            for property_name in properties
        },
    )


def test_validator_accepts_valid_entities_and_relationships() -> None:
    validator = ExtractionResultValidator(
        [
            _entity_definition("claim", ["claim_id"]),
            _entity_definition("provider", ["npi"]),
        ],
        [
            RelationshipDefinition(
                name="submitted_by",
                display_label="Submitted By",
                source="claim",
                target="provider",
            )
        ],
    )

    report = validator.validate_extraction(
        ExtractionResult(
            id="extract-1",
            source_document_id="doc-1",
            candidate_entities=[
                CandidateEntity(
                    id="claim-1",
                    source_document_id="doc-1",
                    chunk_id="chunk-1",
                    type="claim",
                    properties={"claim_id": "42"},
                    confidence=0.9,
                    extraction_method="pattern_v1",
                ),
                CandidateEntity(
                    id="provider-1",
                    source_document_id="doc-1",
                    chunk_id="chunk-1",
                    type="provider",
                    properties={"npi": "1234567890"},
                    confidence=0.9,
                    extraction_method="pattern_v1",
                ),
            ],
            candidate_relationships=[
                CandidateRelationship(
                    id="rel-1",
                    source_document_id="doc-1",
                    chunk_id="chunk-1",
                    type="submitted_by",
                    source_candidate_id="claim-1",
                    target_candidate_id="provider-1",
                    confidence=0.9,
                    extraction_method="pattern_v1",
                )
            ],
        )
    )

    assert len(report.valid_entities) == 2
    assert len(report.valid_relationships) == 1
    assert report.entity_errors == {}
    assert report.relationship_errors == {}


def test_validator_rejects_unknown_entity_type() -> None:
    validator = ExtractionResultValidator([
        _entity_definition("claim", ["claim_id"]),
    ], [])

    report = validator.validate_extraction(
        ExtractionResult(
            id="extract-1",
            source_document_id="doc-1",
            candidate_entities=[
                CandidateEntity(
                    id="entity-1",
                    source_document_id="doc-1",
                    chunk_id="chunk-1",
                    type="provider",
                    properties={"npi": "123"},
                    confidence=0.9,
                    extraction_method="pattern_v1",
                )
            ],
        )
    )

    assert report.valid_entities == []
    assert "entity-1" in report.entity_errors


def test_validator_rejects_relationship_with_invalid_endpoint_types() -> None:
    validator = ExtractionResultValidator(
        [
            _entity_definition("claim", ["claim_id"]),
            _entity_definition("provider", ["npi"]),
        ],
        [
            RelationshipDefinition(
                name="submitted_by",
                display_label="Submitted By",
                source="claim",
                target="provider",
            )
        ],
    )

    report = validator.validate_extraction(
        ExtractionResult(
            id="extract-1",
            source_document_id="doc-1",
            candidate_entities=[
                CandidateEntity(
                    id="provider-1",
                    source_document_id="doc-1",
                    chunk_id="chunk-1",
                    type="provider",
                    properties={"npi": "1234567890"},
                    confidence=0.9,
                    extraction_method="pattern_v1",
                ),
                CandidateEntity(
                    id="claim-1",
                    source_document_id="doc-1",
                    chunk_id="chunk-1",
                    type="claim",
                    properties={"claim_id": "42"},
                    confidence=0.9,
                    extraction_method="pattern_v1",
                ),
            ],
            candidate_relationships=[
                CandidateRelationship(
                    id="rel-1",
                    source_document_id="doc-1",
                    chunk_id="chunk-1",
                    type="submitted_by",
                    source_candidate_id="provider-1",
                    target_candidate_id="claim-1",
                    confidence=0.9,
                    extraction_method="pattern_v1",
                )
            ],
        )
    )

    assert report.valid_relationships == []
    assert "rel-1" in report.relationship_errors


def test_validator_rejects_missing_required_and_invalid_constrained_properties() -> None:
    validator = ExtractionResultValidator(
        [
            EntityDefinition(
                name="provider",
                display_label="Provider",
                icon="box",
                properties={
                    "npi": PropertyDefinition(
                        type=PropertyType.STRING,
                        display="NPI",
                        required=True,
                        pattern="^[0-9]{10}$",
                    ),
                    "age": PropertyDefinition(
                        type=PropertyType.INTEGER,
                        display="Age",
                        min_value=0,
                        max_value=120,
                    ),
                },
            )
        ],
        [],
    )

    report = validator.validate_extraction(
        ExtractionResult(
            id="extract-1",
            source_document_id="doc-1",
            candidate_entities=[
                CandidateEntity(
                    id="provider-1",
                    source_document_id="doc-1",
                    chunk_id="chunk-1",
                    type="provider",
                    properties={"npi": "abc", "age": 200},
                    confidence=0.9,
                    extraction_method="pattern_v1",
                ),
                CandidateEntity(
                    id="provider-2",
                    source_document_id="doc-1",
                    chunk_id="chunk-1",
                    type="provider",
                    properties={"age": 45},
                    confidence=0.9,
                    extraction_method="pattern_v1",
                ),
            ],
        )
    )

    assert report.valid_entities == []
    assert report.entity_errors["provider-1"] == [
        "Property 'age' on entity type 'provider' must be <= 120.0.",
        "Property 'npi' on entity type 'provider' must match pattern '^[0-9]{10}$'.",
    ]
    assert report.entity_errors["provider-2"] == [
        "Missing required property 'npi' on entity type 'provider'."
    ]


def _chunk(chunk_id: str, *, source_kind: str, chunk_index: int) -> Chunk:
    return Chunk(
        id=chunk_id,
        content="content",
        metadata=ChunkMetadata(
            source_document_id="doc-1",
            chunk_index=chunk_index,
            source_kind=source_kind,
        ),
    )


def test_validator_stamps_source_kind_per_chunk_origin() -> None:
    """Record-derived candidates get source_kind=record; text-derived get document."""
    validator = ExtractionResultValidator(
        [
            _entity_definition("claim", ["claim_id"]),
            _entity_definition("provider", ["npi"]),
        ],
        [
            RelationshipDefinition(
                name="submitted_by",
                display_label="Submitted By",
                source="claim",
                target="provider",
            )
        ],
    )

    report = validator.validate_extraction(
        ExtractionResult(
            id="extract-1",
            source_document_id="doc-1",
            chunks=[
                _chunk("chunk-text", source_kind=SOURCE_KIND_DOCUMENT, chunk_index=0),
                _chunk("chunk-record", source_kind=SOURCE_KIND_RECORD, chunk_index=1),
            ],
            candidate_entities=[
                CandidateEntity(
                    id="claim-1",
                    source_document_id="doc-1",
                    chunk_id="chunk-text",
                    type="claim",
                    properties={"claim_id": "42"},
                    confidence=0.9,
                    extraction_method="pattern_v1",
                ),
                CandidateEntity(
                    id="provider-1",
                    source_document_id="doc-1",
                    chunk_id="chunk-record",
                    type="provider",
                    properties={"npi": "1234567890"},
                    confidence=0.9,
                    extraction_method="pattern_v1",
                ),
            ],
            candidate_relationships=[
                CandidateRelationship(
                    id="rel-1",
                    source_document_id="doc-1",
                    chunk_id="chunk-record",
                    type="submitted_by",
                    source_candidate_id="claim-1",
                    target_candidate_id="provider-1",
                    confidence=0.9,
                    extraction_method="pattern_v1",
                )
            ],
        )
    )

    by_id = {entity.id: entity for entity in report.valid_entities}
    assert by_id["claim-1"].metadata[SOURCE_KIND_KEY] == SOURCE_KIND_DOCUMENT
    assert by_id["provider-1"].metadata[SOURCE_KIND_KEY] == SOURCE_KIND_RECORD
    assert report.valid_relationships[0].metadata[SOURCE_KIND_KEY] == SOURCE_KIND_RECORD


def test_validator_defaults_source_kind_to_document_without_chunk() -> None:
    """A candidate whose chunk is absent falls back to document provenance."""
    validator = ExtractionResultValidator([_entity_definition("claim", ["claim_id"])], [])

    report = validator.validate_extraction(
        ExtractionResult(
            id="extract-1",
            source_document_id="doc-1",
            candidate_entities=[
                CandidateEntity(
                    id="claim-1",
                    source_document_id="doc-1",
                    chunk_id="chunk-missing",
                    type="claim",
                    properties={"claim_id": "42"},
                    confidence=0.9,
                    extraction_method="pattern_v1",
                )
            ],
        )
    )

    assert report.valid_entities[0].metadata[SOURCE_KIND_KEY] == SOURCE_KIND_DOCUMENT


def test_validator_strips_unknown_property_and_admits_entity() -> None:
    """A single hallucinated property is relocated to metadata, not a dropped entity."""
    validator = ExtractionResultValidator([_entity_definition("provider", ["npi"])], [])

    report = validator.validate_extraction(
        ExtractionResult(
            id="extract-1",
            source_document_id="doc-1",
            candidate_entities=[
                CandidateEntity(
                    id="provider-1",
                    source_document_id="doc-1",
                    chunk_id="chunk-1",
                    type="provider",
                    properties={"npi": "1234567890", "halluc": "boom"},
                    confidence=0.9,
                    extraction_method="pattern_v1",
                )
            ],
        )
    )

    assert report.entity_errors == {}
    assert len(report.valid_entities) == 1
    entity = report.valid_entities[0]
    assert "halluc" not in entity.properties
    assert entity.properties["npi"] == "1234567890"
    assert entity.metadata["extra_properties"] == {"halluc": "boom"}
    assert len(report.warnings) == 1
    assert "provider-1" in report.warnings[0]
    assert "halluc" in report.warnings[0]