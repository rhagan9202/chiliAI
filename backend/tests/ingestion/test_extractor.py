"""Tests for the baseline document extractor."""

from __future__ import annotations

from ingestion.chunker import ChunkingResult
from ingestion.extractor import PatternDocumentExtractor
from ingestion.models import Chunk, ChunkMetadata
from shared.types import EntityDefinition, PropertyDefinition, PropertyType


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