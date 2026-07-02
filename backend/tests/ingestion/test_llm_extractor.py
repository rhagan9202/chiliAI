"""Tests for LlmDocumentExtractor."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from ingestion.chunker import ChunkingResult
from ingestion.extractor import LlmDocumentExtractor
from ingestion.models import Chunk, ChunkMetadata
from llm.models import CompletionMetadata, GenerationResult
from shared.types import (
    EntityDefinition,
    PropertyDefinition,
    PropertyType,
    RelationshipDefinition,
)


def _gen(payload: dict[str, object]) -> GenerationResult:
    return GenerationResult(
        request_id="r1",
        completion=json.dumps(payload),
        metadata=CompletionMetadata(
            provider="openai", model_name="gpt-4o-mini", temperature=0.2, max_tokens=512
        ),
    )


def _provider_claim_entity_defs() -> list[EntityDefinition]:
    return [
        EntityDefinition(
            name="provider",
            display_label="Provider",
            icon="stethoscope",
            properties={"npi": PropertyDefinition(type=PropertyType.STRING, display="NPI", required=True)},
        ),
        EntityDefinition(
            name="claim",
            display_label="Claim",
            icon="document",
            properties={"claim_id": PropertyDefinition(type=PropertyType.STRING, display="Claim ID", required=True)},
        ),
    ]


def _submitted_rel_defs() -> list[RelationshipDefinition]:
    return [
        RelationshipDefinition(
            name="submitted", display_label="Submitted", source="provider", target="claim"
        ),
    ]


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


def test_llm_extractor_uses_model_relationship_output() -> None:
    """Relationships come from the model's array, mapped by source/target index (ingestion.30)."""
    llm_client = MagicMock()
    llm_client.generate.return_value = _gen({
        "entities": [
            {"type": "provider", "properties": {"npi": "111"}},
            {"type": "claim", "properties": {"claim_id": "C1"}},
        ],
        "relationships": [
            {"type": "submitted", "source_index": 0, "target_index": 1, "evidence": "Dr X submitted claim C1."},
        ],
    })
    extractor = LlmDocumentExtractor(
        entity_definitions=_provider_claim_entity_defs(),
        relationship_definitions=_submitted_rel_defs(),
        llm_client=llm_client,
    )
    result = extractor.extract_document(_chunking_result())

    assert len(result.candidate_relationships) == 1
    rel = result.candidate_relationships[0]
    provider = next(e for e in result.candidate_entities if e.type == "provider")
    claim = next(e for e in result.candidate_entities if e.type == "claim")
    assert rel.type == "submitted"
    assert rel.source_candidate_id == provider.id
    assert rel.target_candidate_id == claim.id
    assert rel.evidence  # non-empty; model-supplied quote attached
    assert rel.evidence[0].quote == "Dr X submitted claim C1."


def test_llm_extractor_no_model_relationships_means_no_cartesian_edges() -> None:
    """3 providers + 2 claims with relationships:[] yields zero edges (no Cartesian fallback)."""
    llm_client = MagicMock()
    llm_client.generate.return_value = _gen({
        "entities": [
            {"type": "provider", "properties": {"npi": "1"}},
            {"type": "provider", "properties": {"npi": "2"}},
            {"type": "provider", "properties": {"npi": "3"}},
            {"type": "claim", "properties": {"claim_id": "A"}},
            {"type": "claim", "properties": {"claim_id": "B"}},
        ],
        "relationships": [],
    })
    extractor = LlmDocumentExtractor(
        entity_definitions=_provider_claim_entity_defs(),
        relationship_definitions=_submitted_rel_defs(),
        llm_client=llm_client,
    )
    result = extractor.extract_document(_chunking_result())

    assert len(result.candidate_entities) == 5
    assert result.candidate_relationships == []


def test_llm_extractor_drops_relationship_with_out_of_range_index() -> None:
    llm_client = MagicMock()
    llm_client.generate.return_value = _gen({
        "entities": [
            {"type": "provider", "properties": {"npi": "111"}},
            {"type": "claim", "properties": {"claim_id": "C1"}},
        ],
        "relationships": [{"type": "submitted", "source_index": 0, "target_index": 9}],
    })
    extractor = LlmDocumentExtractor(
        entity_definitions=_provider_claim_entity_defs(),
        relationship_definitions=_submitted_rel_defs(),
        llm_client=llm_client,
    )
    result = extractor.extract_document(_chunking_result())

    assert result.candidate_relationships == []
    assert any("out-of-range" in w for w in result.warnings)


def test_llm_extractor_drops_relationship_with_validation_dropped_endpoint() -> None:
    llm_client = MagicMock()
    llm_client.generate.return_value = _gen({
        "entities": [
            {"type": "provider", "properties": {}},  # missing required npi -> dropped (index 0)
            {"type": "claim", "properties": {"claim_id": "C1"}},  # index 1
        ],
        "relationships": [{"type": "submitted", "source_index": 0, "target_index": 1}],
    })
    extractor = LlmDocumentExtractor(
        entity_definitions=_provider_claim_entity_defs(),
        relationship_definitions=_submitted_rel_defs(),
        llm_client=llm_client,
    )
    result = extractor.extract_document(_chunking_result())

    assert result.candidate_relationships == []
    assert any("dropped" in w for w in result.warnings)


def test_llm_extractor_drops_relationship_with_endpoint_type_mismatch() -> None:
    llm_client = MagicMock()
    llm_client.generate.return_value = _gen({
        "entities": [
            {"type": "claim", "properties": {"claim_id": "C1"}},
            {"type": "provider", "properties": {"npi": "111"}},
        ],
        # 'submitted' is provider->claim, but indices give claim->provider.
        "relationships": [{"type": "submitted", "source_index": 0, "target_index": 1}],
    })
    extractor = LlmDocumentExtractor(
        entity_definitions=_provider_claim_entity_defs(),
        relationship_definitions=_submitted_rel_defs(),
        llm_client=llm_client,
    )
    result = extractor.extract_document(_chunking_result())

    assert result.candidate_relationships == []
    assert any("match" in w for w in result.warnings)


def test_llm_extractor_drops_relationship_with_unknown_type() -> None:
    llm_client = MagicMock()
    llm_client.generate.return_value = _gen({
        "entities": [
            {"type": "provider", "properties": {"npi": "111"}},
            {"type": "claim", "properties": {"claim_id": "C1"}},
        ],
        "relationships": [{"type": "nonexistent", "source_index": 0, "target_index": 1}],
    })
    extractor = LlmDocumentExtractor(
        entity_definitions=_provider_claim_entity_defs(),
        relationship_definitions=_submitted_rel_defs(),
        llm_client=llm_client,
    )
    result = extractor.extract_document(_chunking_result())

    assert result.candidate_relationships == []
    assert any("Unknown relationship type" in w for w in result.warnings)


def _two_chunk_result() -> ChunkingResult:
    return ChunkingResult(
        source_document_id="doc-1",
        parsed_document_id="pd-1",
        strategy_used="FixedWindowChunkingStrategy",
        chunks=[
            Chunk(id="c1", content="Provider 111.", metadata=ChunkMetadata(source_document_id="doc-1", chunk_index=0, start_offset=0, end_offset=13)),
            Chunk(id="c2", content="Provider 111 submitted claim C1.", metadata=ChunkMetadata(source_document_id="doc-1", chunk_index=1, start_offset=13, end_offset=45)),
        ],
    )


def test_llm_extractor_repoints_relationship_to_deduped_survivor() -> None:
    """A relationship found in a later chunk resolves to the chunk-1 survivor (ingestion.31)."""
    llm_client = MagicMock()
    llm_client.generate.side_effect = [
        _gen({"entities": [{"type": "provider", "properties": {"npi": "111"}}], "relationships": []}),
        _gen({
            "entities": [
                {"type": "provider", "properties": {"npi": "111"}},  # duplicate of chunk-1 provider
                {"type": "claim", "properties": {"claim_id": "C1"}},
            ],
            "relationships": [{"type": "submitted", "source_index": 0, "target_index": 1}],
        }),
    ]
    extractor = LlmDocumentExtractor(
        entity_definitions=_provider_claim_entity_defs(),
        relationship_definitions=_submitted_rel_defs(),
        llm_client=llm_client,
        natural_keys={"provider": ["npi"]},
    )
    result = extractor.extract_document(_two_chunk_result())

    providers = [e for e in result.candidate_entities if e.type == "provider"]
    assert len(providers) == 1
    survivor = providers[0]
    assert survivor.chunk_id == "c1"

    assert len(result.candidate_relationships) == 1
    rel = result.candidate_relationships[0]
    assert rel.source_candidate_id == survivor.id
    claim = next(e for e in result.candidate_entities if e.type == "claim")
    assert rel.target_candidate_id == claim.id

    merged_chunk_ids = survivor.metadata.get("merged_chunk_ids")
    assert isinstance(merged_chunk_ids, list)
    assert set(merged_chunk_ids) == {"c1", "c2"}


def test_llm_extractor_avoids_self_loop_after_dedup() -> None:
    """Two same-key entities collapse to one survivor; the edge between them is dropped."""
    peer_defs = [
        RelationshipDefinition(name="peer", display_label="Peer", source="provider", target="provider"),
    ]
    llm_client = MagicMock()
    llm_client.generate.return_value = _gen({
        "entities": [
            {"type": "provider", "properties": {"npi": "111"}},
            {"type": "provider", "properties": {"npi": "111"}},
        ],
        "relationships": [{"type": "peer", "source_index": 0, "target_index": 1}],
    })
    extractor = LlmDocumentExtractor(
        entity_definitions=_provider_claim_entity_defs(),
        relationship_definitions=peer_defs,
        llm_client=llm_client,
        natural_keys={"provider": ["npi"]},
    )
    result = extractor.extract_document(_chunking_result())

    assert len([e for e in result.candidate_entities if e.type == "provider"]) == 1
    assert result.candidate_relationships == []


def test_llm_extractor_relationship_endpoints_unchanged_without_natural_key() -> None:
    """With no natural key, endpoints keep their per-chunk candidate ids (no regression)."""
    llm_client = MagicMock()
    llm_client.generate.return_value = _gen({
        "entities": [
            {"type": "provider", "properties": {"npi": "111"}},
            {"type": "claim", "properties": {"claim_id": "C1"}},
        ],
        "relationships": [{"type": "submitted", "source_index": 0, "target_index": 1}],
    })
    extractor = LlmDocumentExtractor(
        entity_definitions=_provider_claim_entity_defs(),
        relationship_definitions=_submitted_rel_defs(),
        llm_client=llm_client,
    )
    result = extractor.extract_document(_chunking_result())

    provider = next(e for e in result.candidate_entities if e.type == "provider")
    claim = next(e for e in result.candidate_entities if e.type == "claim")
    rel = result.candidate_relationships[0]
    assert rel.source_candidate_id == provider.id
    assert rel.target_candidate_id == claim.id
    assert "merged_chunk_ids" not in provider.metadata


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


def test_create_document_extractor_derives_natural_keys_from_entity_definitions() -> None:
    """natural_keys from EntityDefinition.natural_key are picked up automatically."""
    from ingestion.extractor import create_document_extractor
    from shared.types import PropertyDefinition, PropertyType

    entity_defs = [
        EntityDefinition(
            name="provider",
            display_label="Provider",
            icon="stethoscope",
            properties={
                "npi": PropertyDefinition(type=PropertyType.STRING, display="NPI", required=True),
            },
            natural_key=["npi"],
        ),
        EntityDefinition(
            name="claim",
            display_label="Claim",
            icon="document",
            properties={
                "claim_id": PropertyDefinition(type=PropertyType.STRING, display="Claim ID", required=True),
            },
            # no natural_key — should be omitted from derived dict
        ),
    ]
    llm_client = MagicMock()
    extractor = create_document_extractor(entity_defs, llm_client=llm_client)
    assert isinstance(extractor, LlmDocumentExtractor)
    # Derived keys should include only entities that have natural_key set.
    assert extractor.natural_keys == {"provider": ["npi"]}


def test_create_document_extractor_explicit_natural_keys_take_precedence() -> None:
    """Explicitly passed natural_keys override auto-derivation from entity definitions."""
    from ingestion.extractor import create_document_extractor
    from shared.types import PropertyDefinition, PropertyType

    entity_defs = [
        EntityDefinition(
            name="provider",
            display_label="Provider",
            icon="stethoscope",
            properties={
                "npi": PropertyDefinition(type=PropertyType.STRING, display="NPI", required=True),
            },
            natural_key=["npi"],
        ),
    ]
    explicit_keys = {"provider": ["npi", "last_name"]}
    llm_client = MagicMock()
    extractor = create_document_extractor(entity_defs, llm_client=llm_client, natural_keys=explicit_keys)
    assert isinstance(extractor, LlmDocumentExtractor)
    # Explicit keys take precedence over auto-derived ones.
    assert extractor.natural_keys == explicit_keys
