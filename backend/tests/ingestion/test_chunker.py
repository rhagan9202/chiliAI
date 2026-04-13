"""Tests for chunking strategies and document chunker."""

from __future__ import annotations

import os

import pytest

from config.schema import ChunkingConfig
from ingestion.chunker import (
    ChunkingStrategy,
    DocumentChunker,
    FixedSizeSplitter,
    HeuristicTokenizer,
    RecursiveCharacterSplitter,
    SentenceSplitter,
    StructuredRecordChunker,
    Tokenizer,
    create_document_chunker,
    resolve_chunking_config,
)
from ingestion.models import ParsedDocument, StructuredRecord
from ingestion.protocols import DocumentChunkerProtocol


def _parsed_document(
    *,
    text_content: str | None = None,
    records: list[StructuredRecord] | None = None,
) -> ParsedDocument:
    return ParsedDocument(
        id="parsed-1",
        source_document_id="source-1",
        text_content=text_content,
        records=records or [],
        parser_name="test-parser",
        parser_metadata={"page": 1},
    )


class TestHeuristicTokenizer:
    def test_estimate_tokens_for_empty_text(self) -> None:
        assert HeuristicTokenizer().estimate_tokens("") == 0

    def test_estimate_tokens_for_non_empty_text(self) -> None:
        assert HeuristicTokenizer().estimate_tokens("abcd" * 10) == 10


class TestFixedSizeSplitter:
    def test_splits_with_overlap_and_offsets(self) -> None:
        splitter = FixedSizeSplitter()
        text = "abcdefghijklmnopqrstuvwxyz"

        chunks = splitter.split(
            text,
            chunk_size=10,
            chunk_overlap=2,
            min_chunk_size=1,
        )

        assert [chunk.content for chunk in chunks] == [
            "abcdefghij",
            "ijklmnopqr",
            "qrstuvwxyz",
        ]
        assert chunks[1].start_offset == 8
        assert text[chunks[2].start_offset : chunks[2].end_offset] == chunks[2].content


class TestRecursiveCharacterSplitter:
    def test_prefers_paragraph_boundary(self) -> None:
        splitter = RecursiveCharacterSplitter()
        text = "alpha beta gamma\n\nsecond paragraph content"

        chunks = splitter.split(
            text,
            chunk_size=25,
            chunk_overlap=0,
            min_chunk_size=5,
        )

        assert len(chunks) == 2
        assert chunks[0].content.endswith("\n\n")
        assert text[chunks[0].start_offset : chunks[0].end_offset] == chunks[0].content


class TestSentenceSplitter:
    def test_groups_sentences_up_to_limit(self) -> None:
        splitter = SentenceSplitter()
        text = "One short sentence. Two short sentence. Three short sentence."

        chunks = splitter.split(
            text,
            chunk_size=42,
            chunk_overlap=0,
            min_chunk_size=1,
        )

        assert len(chunks) == 2
        assert chunks[0].content == "One short sentence. Two short sentence. "
        assert text[chunks[1].start_offset : chunks[1].end_offset] == chunks[1].content


class TestStructuredRecordChunker:
    def test_renders_json_by_default(self) -> None:
        record_chunker = StructuredRecordChunker()
        chunks = record_chunker.chunk_records(
            [StructuredRecord(id="record-1", fields={"name": "alpha", "value": 3})],
            source_document_id="source-1",
            parser_metadata={},
            tokenizer=HeuristicTokenizer(),
        )

        assert chunks[0].content == '{"name": "alpha", "value": 3}'
        assert chunks[0].metadata.section_heading == "record record-1"

    def test_renders_template_when_configured(self) -> None:
        record_chunker = StructuredRecordChunker(
            record_template="row={row_number}; name={name}; value={value}"
        )
        chunks = record_chunker.chunk_records(
            [StructuredRecord(id="record-1", row_number=7, fields={"name": "alpha", "value": 3})],
            source_document_id="source-1",
            parser_metadata={},
            tokenizer=HeuristicTokenizer(),
        )

        assert chunks[0].content == "row=7; name=alpha; value=3"


class TestDocumentChunker:
    def test_chunks_text_only_documents(self) -> None:
        config = ChunkingConfig(strategy="fixed_size", chunk_size=12, chunk_overlap=2)
        chunker = DocumentChunker(
            FixedSizeSplitter(),
            tokenizer=HeuristicTokenizer(),
            config=config,
        )

        result = chunker.chunk_document(
            _parsed_document(text_content="abcdefghijklmnopqrstuvwx"),
            source_document_id="source-1",
        )

        assert isinstance(chunker, DocumentChunkerProtocol)
        assert result.strategy_used == "FixedSizeSplitter"
        assert len(result.chunks) == 3
        assert result.chunks[0].metadata.chunk_index == 0
        assert result.chunks[1].metadata.start_offset == 10
        assert all(chunk.tokens_estimate is not None for chunk in result.chunks)

    def test_chunks_records_only_documents(self) -> None:
        config = ChunkingConfig(strategy="recursive")
        chunker = DocumentChunker(
            RecursiveCharacterSplitter(),
            tokenizer=HeuristicTokenizer(),
            config=config,
        )

        result = chunker.chunk_document(
            _parsed_document(
                records=[
                    StructuredRecord(id="record-1", fields={"claim_id": "1"}),
                    StructuredRecord(id="record-2", fields={"claim_id": "2"}),
                ]
            ),
            source_document_id="source-1",
        )

        assert len(result.chunks) == 2
        assert result.chunks[1].metadata.chunk_index == 1
        assert result.chunks[0].metadata.start_offset is None

    def test_chunks_mixed_documents(self) -> None:
        config = ChunkingConfig(strategy="fixed_size", chunk_size=10, chunk_overlap=0)
        chunker = DocumentChunker(
            FixedSizeSplitter(),
            tokenizer=HeuristicTokenizer(),
            config=config,
        )

        result = chunker.chunk_document(
            _parsed_document(
                text_content="abcdefghijklmnop",
                records=[StructuredRecord(id="record-1", fields={"claim_id": "1"})],
            ),
            source_document_id="source-1",
        )

        assert len(result.chunks) == 3
        assert result.chunks[2].metadata.chunk_index == 2
        assert len({chunk.id for chunk in result.chunks}) == 3


class TestFactories:
    def test_create_document_chunker_uses_runtime_checkable_protocols(self) -> None:
        chunker = create_document_chunker(ChunkingConfig(strategy="sentence"))

        assert isinstance(chunker, DocumentChunkerProtocol)
        assert isinstance(chunker._strategy, ChunkingStrategy)
        assert isinstance(chunker._tokenizer, Tokenizer)

    def test_env_overrides_are_applied(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CHILI_CHUNK_SIZE", "256")
        monkeypatch.setenv("CHILI_CHUNK_OVERLAP", "32")

        resolved = resolve_chunking_config(ChunkingConfig())

        assert resolved.chunk_size == 256
        assert resolved.chunk_overlap == 32

    def test_env_override_strategy_validation_raises_for_unknown_value(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("CHILI_CHUNKING_STRATEGY", "unknown")

        with pytest.raises(Exception):
            resolve_chunking_config(ChunkingConfig())