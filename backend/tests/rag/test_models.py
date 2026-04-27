"""Tests for rag module models."""

from __future__ import annotations

import pytest

from rag.models import ContextRecord, RagGenerationResult
from rag.service_models import RagCitation, RagQueryRequest, RagStreamChunk


def test_context_record_requires_embedding() -> None:
    with pytest.raises(ValueError, match="non-empty embedding"):
        ContextRecord(record_id="record-1", content_id="content-1", embedding=[], content="Alpha")


def test_rag_query_request_requires_question() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        RagQueryRequest(knowledge_base_id="kb-1", question=" ")


def test_rag_generation_result_requires_answer() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        RagGenerationResult(
            request_id="request-1",
            answer=" ",
            provider="in-memory",
            model_name="model",
        )


def test_rag_citation_extended_fields_default_to_none() -> None:
    citation = RagCitation(
        record_id="r-1",
        content_id="c-1",
        score=0.5,
        snippet="snippet",
    )

    assert citation.document_id is None
    assert citation.chunk_index is None
    assert citation.highlight is None


def test_rag_citation_extended_fields_round_trip() -> None:
    citation = RagCitation(
        record_id="r-1",
        content_id="c-1",
        score=0.5,
        snippet="snippet",
        document_id="doc-9",
        chunk_index=3,
        highlight="key span",
    )

    assert citation.document_id == "doc-9"
    assert citation.chunk_index == 3
    assert citation.highlight == "key span"


def test_rag_stream_chunk_defaults_to_empty_citations() -> None:
    chunk = RagStreamChunk(chunk_text="hello", is_final=False)

    assert chunk.citations == []
    assert chunk.is_final is False


def test_rag_stream_chunk_final_can_carry_citations() -> None:
    citation = RagCitation(record_id="r", content_id="c", score=0.1, snippet="s")
    chunk = RagStreamChunk(chunk_text="", is_final=True, citations=[citation])

    assert chunk.is_final is True
    assert chunk.citations == [citation]
