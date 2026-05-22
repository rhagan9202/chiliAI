"""Integration: extract from a markdown policy fixture using a live Ollama."""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest

from config.schema import LlmConfig
from ingestion.extractor import LlmDocumentExtractor
from llm.factory import create_llm_client
from shared.types import EntityDefinition, PropertyDefinition, PropertyType


pytestmark = pytest.mark.integration


def _ollama_model_available() -> bool:
    """Return True only when Ollama is reachable AND the target model is pulled."""
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    model = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")
    try:
        resp = httpx.get(base_url + "/api/tags", timeout=2.0)
        if resp.status_code != 200:
            return False
        available = {m["name"] for m in resp.json().get("models", [])}
        return model in available
    except Exception:
        return False


@pytest.mark.skipif(
    not _ollama_model_available(),
    reason="Ollama not reachable or target model not pulled (set OLLAMA_MODEL to an available model)",
)
def test_extract_policy_fixture_with_ollama() -> None:
    fixture = Path(__file__).parent / "fixtures" / "policies" / "policy_001_inpatient_billing.md"
    text = fixture.read_text()

    # Build a ChunkingResult directly without going through a parser registry —
    # the policy fixtures are markdown that doesn't need any structural parsing
    # for this test. The extractor only reads chunk.content.
    from ingestion.chunker import ChunkingResult
    from ingestion.models import Chunk, ChunkMetadata

    chunks = ChunkingResult(
        source_document_id="doc-1",
        parsed_document_id="pd-1",
        strategy_used="fixed_size",
        chunks=[
            Chunk(
                id="chunk-1",
                content=text,
                metadata=ChunkMetadata(
                    source_document_id="doc-1",
                    chunk_index=0,
                    start_offset=0,
                    end_offset=len(text),
                ),
            ),
        ],
    )

    ollama_base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")
    config = LlmConfig(
        provider="ollama",
        model=ollama_model,
        base_url=ollama_base_url,
        temperature=0.0,
    )
    client = create_llm_client(config)

    entity_defs = [
        EntityDefinition(
            name="provider",
            display_label="Provider",
            icon="stethoscope",
            properties={
                "npi": PropertyDefinition(type=PropertyType.STRING, display="NPI", required=True),
            },
        ),
    ]
    extractor = LlmDocumentExtractor(
        entity_definitions=entity_defs,
        relationship_definitions=[],
        llm_client=client,
        natural_keys={"provider": ["npi"]},
        model_name=ollama_model,
    )
    result = extractor.extract_document(chunks)
    # Surface LLM errors as test failures rather than silently returning empty.
    assert not result.warnings, f"Extraction produced warnings: {result.warnings}"
    npis = {c.properties.get("npi") for c in result.candidate_entities}
    # The fixture references NPI 1234567890; assert the extractor catches it.
    # Small local models can be imperfect; if the model misses it, the test will
    # surface that as a real signal to upgrade the model or refine the prompt.
    assert "1234567890" in npis
