"""Tests for the baseline document extractor."""

from __future__ import annotations

from ingestion.chunker import ChunkingResult
from ingestion.extractor import PatternDocumentExtractor, candidate_pairs
from ingestion.models import CandidateEntity, Chunk, ChunkMetadata, ExtractionEvidence, TextSpan
from shared.types import (
    EntityDefinition,
    PropertyDefinition,
    PropertyType,
    RelationshipDefinition,
)


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


def test_pattern_extractor_extracts_candidate_from_json_chunk() -> None:
    extractor = PatternDocumentExtractor(
        [_entity_definition("claim", ["claim_id", "amount"])]
    )
    result = extractor.extract_document(
        ChunkingResult(
            source_document_id="doc-1",
            parsed_document_id="parsed-1",
            strategy_used="StructuredRecordChunker",
            chunks=[
                Chunk(
                    id="chunk-1",
                    content='{"amount": 125.50, "claim_id": "42"}',
                    metadata=ChunkMetadata(
                        source_document_id="doc-1",
                        chunk_index=0,
                        start_offset=0,
                        end_offset=36,
                    ),
                )
            ],
        )
    )

    assert len(result.candidate_entities) == 1
    candidate = result.candidate_entities[0]
    assert candidate.type == "claim"
    assert candidate.properties["claim_id"] == "42"
    assert candidate.properties["amount"] == 125.5
    assert candidate.evidence[0].span is not None


def test_pattern_extractor_emits_warning_when_no_candidates_found() -> None:
    extractor = PatternDocumentExtractor([_entity_definition("claim", ["claim_id"])])

    result = extractor.extract_document(
        ChunkingResult(
            source_document_id="doc-1",
            parsed_document_id="parsed-1",
            strategy_used="RecursiveCharacterSplitter",
            chunks=[
                Chunk(
                    id="chunk-1",
                    content="No structured identifiers appear here.",
                    metadata=ChunkMetadata(source_document_id="doc-1", chunk_index=0),
                )
            ],
        )
    )

    assert result.candidate_entities == []
    assert result.warnings == ["No entity candidates extracted from persisted chunks."]


def test_pattern_extractor_extracts_relationship_candidates() -> None:
    extractor = PatternDocumentExtractor(
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
    result = extractor.extract_document(
        ChunkingResult(
            source_document_id="doc-1",
            parsed_document_id="parsed-1",
            strategy_used="StructuredRecordChunker",
            chunks=[
                Chunk(
                    id="chunk-1",
                    content='{"claim_id": "42", "npi": "1234567890"}',
                    metadata=ChunkMetadata(source_document_id="doc-1", chunk_index=0),
                )
            ],
        )
    )

    assert len(result.candidate_entities) == 2
    assert len(result.candidate_relationships) == 1
    relationship = result.candidate_relationships[0]
    assert relationship.type == "submitted_by"
    assert relationship.source_candidate_id != relationship.target_candidate_id
    assert relationship.evidence != []


def test_candidate_pairs_prefers_nearest_targets() -> None:
    chunk = Chunk(
        id="chunk-1",
        content="claim 1 npi 111 claim 2 npi 222",
        metadata=ChunkMetadata(source_document_id="doc-1", chunk_index=0),
    )
    pairs = candidate_pairs(
        [
            CandidateEntity(
                id="claim-1",
                source_document_id="doc-1",
                chunk_id="chunk-1",
                type="claim",
                properties={"claim_id": "1"},
                confidence=0.9,
                extraction_method="pattern_v1",
                evidence=[
                    ExtractionEvidence(
                        chunk_id="chunk-1",
                        span=TextSpan(text="claim 1", start_offset=0, end_offset=7),
                    )
                ],
            ),
            CandidateEntity(
                id="claim-2",
                source_document_id="doc-1",
                chunk_id="chunk-1",
                type="claim",
                properties={"claim_id": "2"},
                confidence=0.9,
                extraction_method="pattern_v1",
                evidence=[
                    ExtractionEvidence(
                        chunk_id="chunk-1",
                        span=TextSpan(text="claim 2", start_offset=16, end_offset=23),
                    )
                ],
            ),
        ],
        [
            CandidateEntity(
                id="provider-1",
                source_document_id="doc-1",
                chunk_id="chunk-1",
                type="provider",
                properties={"npi": "111"},
                confidence=0.9,
                extraction_method="pattern_v1",
                evidence=[
                    ExtractionEvidence(
                        chunk_id="chunk-1",
                        span=TextSpan(text="npi 111", start_offset=8, end_offset=15),
                    )
                ],
            ),
            CandidateEntity(
                id="provider-2",
                source_document_id="doc-1",
                chunk_id="chunk-1",
                type="provider",
                properties={"npi": "222"},
                confidence=0.9,
                extraction_method="pattern_v1",
                evidence=[
                    ExtractionEvidence(
                        chunk_id="chunk-1",
                        span=TextSpan(text="npi 222", start_offset=24, end_offset=31),
                    )
                ],
            ),
        ],
        chunk=chunk,
        allow_self_reference=False,
    )

    assert [(source.id, target.id) for source, target in pairs] == [
        ("claim-1", "provider-1"),
        ("claim-2", "provider-2"),
    ]
