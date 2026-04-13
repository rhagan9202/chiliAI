"""Tests for validating extracted candidates into runtime objects."""

from __future__ import annotations

from ingestion.models import CandidateEntity, CandidateRelationship, ExtractionResult
from ingestion.validator import ExtractionResultValidator
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