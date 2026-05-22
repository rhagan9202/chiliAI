"""Tests for LlmDocumentExtractor."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from ingestion.chunker import ChunkingResult
from ingestion.extractor import LlmDocumentExtractor
from ingestion.models import Chunk, ChunkMetadata
from llm.models import CompletionMetadata, GenerationResult
from shared.types import EntityDefinition, PropertyDefinition, PropertyType


def _chunking_result() -> ChunkingResult:
    return ChunkingResult(
        source_document_id="doc-1",
        parsed_document_id="pd-1",
        strategy_used="FixedWindowChunkingStrategy",
        chunks=[
            Chunk(
                id="chunk-1",
                content="Provider NPI 1234567890 specializes in Cardiology.",
                metadata=ChunkMetadata(source_document_id="doc-1", chunk_index=0, start_offset=0, end_offset=51),
            ),
        ],
    )


def _entity_defs() -> list[EntityDefinition]:
    return [
        EntityDefinition(
            name="provider",
            display_label="Provider",
            icon="stethoscope",
            properties={
                "npi": PropertyDefinition(type=PropertyType.STRING, display="NPI", required=True),
                "specialty": PropertyDefinition(type=PropertyType.STRING, display="Specialty"),
            },
        ),
    ]


def test_llm_extractor_returns_validated_entities() -> None:
    llm_client = MagicMock()
    llm_client.generate.return_value = GenerationResult(
        request_id="r1",
        completion=json.dumps({
            "entities": [
                {"type": "provider", "properties": {"npi": "1234567890", "specialty": "Cardiology"}},
            ],
            "relationships": [],
        }),
        metadata=CompletionMetadata(provider="openai", model_name="gpt-4o-mini", temperature=0.2, max_tokens=512),
    )

    extractor = LlmDocumentExtractor(
        entity_definitions=_entity_defs(),
        relationship_definitions=[],
        llm_client=llm_client,
    )
    result = extractor.extract_document(_chunking_result())

    assert len(result.candidate_entities) == 1
    assert result.candidate_entities[0].type == "provider"
    assert result.candidate_entities[0].properties["npi"] == "1234567890"


def test_llm_extractor_drops_entities_failing_required_property() -> None:
    llm_client = MagicMock()
    llm_client.generate.return_value = GenerationResult(
        request_id="r1",
        completion=json.dumps({
            "entities": [
                {"type": "provider", "properties": {"specialty": "Cardiology"}},  # missing required npi
            ],
            "relationships": [],
        }),
        metadata=CompletionMetadata(provider="openai", model_name="gpt-4o-mini", temperature=0.2, max_tokens=512),
    )

    extractor = LlmDocumentExtractor(
        entity_definitions=_entity_defs(),
        relationship_definitions=[],
        llm_client=llm_client,
    )
    result = extractor.extract_document(_chunking_result())

    assert result.candidate_entities == []
    assert any("required" in w for w in result.warnings)


def test_llm_extractor_dedupes_by_natural_key_across_chunks() -> None:
    llm_client = MagicMock()
    # Both chunks return the same provider entity.
    llm_client.generate.return_value = GenerationResult(
        request_id="r1",
        completion=json.dumps({
            "entities": [{"type": "provider", "properties": {"npi": "1234567890"}}],
            "relationships": [],
        }),
        metadata=CompletionMetadata(provider="openai", model_name="gpt-4o-mini", temperature=0.2, max_tokens=512),
    )

    chunking = ChunkingResult(
        source_document_id="doc-1",
        parsed_document_id="pd-1",
        strategy_used="FixedWindowChunkingStrategy",
        chunks=[
            Chunk(id="c1", content="first mention NPI 1234567890.", metadata=ChunkMetadata(source_document_id="doc-1", chunk_index=0, start_offset=0, end_offset=30)),
            Chunk(id="c2", content="second mention NPI 1234567890.", metadata=ChunkMetadata(source_document_id="doc-1", chunk_index=1, start_offset=30, end_offset=60)),
        ],
    )
    extractor = LlmDocumentExtractor(
        entity_definitions=_entity_defs(),
        relationship_definitions=[],
        llm_client=llm_client,
        natural_keys={"provider": ["npi"]},
    )
    result = extractor.extract_document(chunking)

    assert len(result.candidate_entities) == 1


def test_llm_extractor_invalid_json_warns_and_continues() -> None:
    llm_client = MagicMock()
    llm_client.generate.return_value = GenerationResult(
        request_id="r1",
        completion="not json",
        metadata=CompletionMetadata(provider="openai", model_name="gpt-4o-mini", temperature=0.2, max_tokens=512),
    )
    extractor = LlmDocumentExtractor(
        entity_definitions=_entity_defs(),
        relationship_definitions=[],
        llm_client=llm_client,
    )
    result = extractor.extract_document(_chunking_result())
    assert result.candidate_entities == []
    assert result.warnings  # non-empty


def test_llm_extractor_records_warning_on_provider_error() -> None:
    from llm.exceptions import LlmProviderError
    llm_client = MagicMock()
    llm_client.generate.side_effect = LlmProviderError("ollama down")

    extractor = LlmDocumentExtractor(
        entity_definitions=_entity_defs(),
        relationship_definitions=[],
        llm_client=llm_client,
    )
    result = extractor.extract_document(_chunking_result())

    assert result.candidate_entities == []
    assert any("LLM extraction failed" in w for w in result.warnings)


def test_llm_extractor_strips_markdown_json_fences() -> None:
    llm_client = MagicMock()
    fenced = "```json\n" + json.dumps({
        "entities": [{"type": "provider", "properties": {"npi": "1234567890"}}],
        "relationships": [],
    }) + "\n```"
    llm_client.generate.return_value = GenerationResult(
        request_id="r1",
        completion=fenced,
        metadata=CompletionMetadata(provider="openai", model_name="m", temperature=0.2, max_tokens=128),
    )
    extractor = LlmDocumentExtractor(
        entity_definitions=_entity_defs(),
        relationship_definitions=[],
        llm_client=llm_client,
    )
    result = extractor.extract_document(_chunking_result())
    assert len(result.candidate_entities) == 1
    assert result.candidate_entities[0].properties["npi"] == "1234567890"


def test_create_document_extractor_returns_pattern_when_no_llm_client() -> None:
    from ingestion.extractor import PatternDocumentExtractor, create_document_extractor
    extractor = create_document_extractor(entity_definitions=_entity_defs())
    assert isinstance(extractor, PatternDocumentExtractor)


def test_create_document_extractor_returns_llm_when_client_provided() -> None:
    from ingestion.extractor import create_document_extractor
    llm_client = MagicMock()
    extractor = create_document_extractor(
        entity_definitions=_entity_defs(),
        llm_client=llm_client,
    )
    assert isinstance(extractor, LlmDocumentExtractor)
