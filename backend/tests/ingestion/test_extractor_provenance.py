"""Document-derived entities and relationships carry source provenance."""

from __future__ import annotations

from ingestion.models import (
    CandidateEntity,
    CandidateRelationship,
    Chunk,
    ChunkMetadata,
    ExtractionResult,
)
from ingestion.validator import ExtractionResultValidator
from shared.provenance import (
    SOURCE_CHUNK_ID_KEY,
    SOURCE_DOCUMENT_ID_KEY,
    SOURCE_KIND_DOCUMENT,
    SOURCE_KIND_KEY,
    SOURCE_KIND_RECORD,
)
from shared.types import EntityDefinition, PropertyDefinition, PropertyType, RelationshipDefinition


def _entity_definition(name: str, properties: list[str]) -> EntityDefinition:
    return EntityDefinition(
        name=name,
        display_label=name.title(),
        icon="box",
        properties={
            prop: PropertyDefinition(type=PropertyType.STRING, display=prop)
            for prop in properties
        },
    )


def _make_validator() -> ExtractionResultValidator:
    return ExtractionResultValidator(
        entity_definitions=[
            _entity_definition("provider", ["npi"]),
            _entity_definition("claim", ["claim_id"]),
        ],
        relationship_definitions=[
            RelationshipDefinition(
                name="submitted_by",
                display_label="Submitted By",
                source="claim",
                target="provider",
            )
        ],
    )


def _candidate_entity() -> CandidateEntity:
    return CandidateEntity(
        id="cand-1",
        source_document_id="doc-1",
        chunk_id="chunk-7",
        type="provider",
        properties={"npi": "1234567890"},
        confidence=0.9,
        extraction_method="pattern_v1",
        evidence=[],
        metadata={},
    )


def _candidate_claim() -> CandidateEntity:
    return CandidateEntity(
        id="cand-2",
        source_document_id="doc-1",
        chunk_id="chunk-7",
        type="claim",
        properties={"claim_id": "42"},
        confidence=0.9,
        extraction_method="pattern_v1",
        evidence=[],
        metadata={},
    )


def _candidate_relationship() -> CandidateRelationship:
    return CandidateRelationship(
        id="rel-1",
        source_document_id="doc-1",
        chunk_id="chunk-7",
        type="submitted_by",
        source_candidate_id="cand-2",
        target_candidate_id="cand-1",
        confidence=0.9,
        extraction_method="pattern_v1",
        evidence=[],
        metadata={},
    )


def test_built_entity_carries_document_provenance() -> None:
    """Entity converted from CandidateEntity carries source_kind=document provenance."""
    validator = _make_validator()
    extraction = ExtractionResult(
        id="extract-1",
        source_document_id="doc-1",
        candidate_entities=[_candidate_entity()],
    )
    report = validator.validate_extraction(extraction)

    assert len(report.valid_entities) == 1
    entity = report.valid_entities[0]
    assert entity.metadata[SOURCE_KIND_KEY] == SOURCE_KIND_DOCUMENT
    assert entity.metadata[SOURCE_DOCUMENT_ID_KEY] == "doc-1"
    assert entity.metadata[SOURCE_CHUNK_ID_KEY] == "chunk-7"
    assert entity.metadata["confidence"] == 0.9
    assert entity.metadata["extraction_method"] == "pattern_v1"


def test_built_relationship_carries_document_provenance() -> None:
    """Relationship converted from CandidateRelationship carries source_kind=document provenance."""
    validator = _make_validator()
    extraction = ExtractionResult(
        id="extract-1",
        source_document_id="doc-1",
        candidate_entities=[_candidate_claim(), _candidate_entity()],
        candidate_relationships=[_candidate_relationship()],
    )
    report = validator.validate_extraction(extraction)

    assert len(report.valid_relationships) == 1
    rel = report.valid_relationships[0]
    assert rel.metadata[SOURCE_KIND_KEY] == SOURCE_KIND_DOCUMENT
    assert rel.metadata[SOURCE_DOCUMENT_ID_KEY] == "doc-1"
    assert rel.metadata[SOURCE_CHUNK_ID_KEY] == "chunk-7"


def test_record_derived_entities_and_relationships_carry_record_provenance() -> None:
    """Candidates anchored on a record-derived chunk carry source_kind=record."""
    validator = _make_validator()
    record_chunk = Chunk(
        id="chunk-7",
        content="record 0",
        metadata=ChunkMetadata(
            source_document_id="doc-1",
            chunk_index=0,
            source_kind=SOURCE_KIND_RECORD,
        ),
    )
    extraction = ExtractionResult(
        id="extract-1",
        source_document_id="doc-1",
        chunks=[record_chunk],
        candidate_entities=[_candidate_claim(), _candidate_entity()],
        candidate_relationships=[_candidate_relationship()],
    )
    report = validator.validate_extraction(extraction)

    assert {entity.metadata[SOURCE_KIND_KEY] for entity in report.valid_entities} == {
        SOURCE_KIND_RECORD
    }
    assert report.valid_relationships[0].metadata[SOURCE_KIND_KEY] == SOURCE_KIND_RECORD


def test_entity_provenance_does_not_overwrite_extra_candidate_metadata() -> None:
    """Extra metadata on the CandidateEntity is preserved alongside provenance keys."""
    validator = _make_validator()
    candidate = CandidateEntity(
        id="cand-1",
        source_document_id="doc-99",
        chunk_id="chunk-3",
        type="provider",
        properties={"npi": "1234567890"},
        confidence=0.85,
        extraction_method="pattern_v1",
        evidence=[],
        metadata={"custom_key": "custom_value"},
    )
    extraction = ExtractionResult(
        id="extract-1",
        source_document_id="doc-99",
        candidate_entities=[candidate],
    )
    report = validator.validate_extraction(extraction)

    assert len(report.valid_entities) == 1
    entity = report.valid_entities[0]
    assert entity.metadata[SOURCE_KIND_KEY] == SOURCE_KIND_DOCUMENT
    assert entity.metadata["custom_key"] == "custom_value"
