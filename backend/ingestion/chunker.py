"""Chunk parsed ingestion content into extraction-ready units."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
import re
from string import Formatter
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from ingestion.models import Chunk, ChunkMetadata, ParsedDocument, StructuredRecord

if TYPE_CHECKING:
	from config.schema import ChunkingConfig
from shared.utils import generate_id, utc_now


@dataclass(frozen=True)
class TextChunk:
	"""Internal text window with absolute offsets into the source text."""

	content: str
	start_offset: int
	end_offset: int


class ChunkingResult(BaseModel):
	"""Chunking output for a parsed document."""

	source_document_id: str
	parsed_document_id: str
	chunks: list[Chunk] = Field(default_factory=list)
	strategy_used: str
	chunked_at: datetime = Field(default_factory=utc_now)


@runtime_checkable
class Tokenizer(Protocol):
	"""Estimate token counts for a text span."""

	def estimate_tokens(self, text: str) -> int: ...


@runtime_checkable
class ChunkingStrategy(Protocol):
	"""Split freeform text into overlap-aware chunks."""

	def split(
		self,
		text: str,
		*,
		chunk_size: int,
		chunk_overlap: int,
		min_chunk_size: int,
	) -> list[TextChunk]: ...


class HeuristicTokenizer:
	"""Estimate tokens using a coarse character-based heuristic."""

	def estimate_tokens(self, text: str) -> int:
		if text == "":
			return 0
		return max(1, len(text) // 4)


class TiktokenTokenizer:
	"""Optional tokenizer adapter backed by ``tiktoken`` when installed."""

	def __init__(self, *, encoding_name: str = "cl100k_base") -> None:
		try:
			import tiktoken  # type: ignore[import-not-found]
		except ImportError as exc:  # pragma: no cover - dependency is optional
			raise RuntimeError(
				"tiktoken is not installed. Use HeuristicTokenizer or add the dependency."
			) from exc
		self._encoding = tiktoken.get_encoding(encoding_name)

	def estimate_tokens(self, text: str) -> int:
		return len(self._encoding.encode(text))


class FixedSizeSplitter:
	"""Split text with a fixed-width sliding window and overlap."""

	def split(
		self,
		text: str,
		*,
		chunk_size: int,
		chunk_overlap: int,
		min_chunk_size: int,
	) -> list[TextChunk]:
		if text == "":
			return []

		chunks: list[TextChunk] = []
		start = 0
		while start < len(text):
			end = min(start + chunk_size, len(text))
			if chunks and end < len(text) and (end - start) < min_chunk_size:
				previous = chunks.pop()
				start = previous.start_offset
				end = len(text)
			chunk = TextChunk(
				content=text[start:end],
				start_offset=start,
				end_offset=end,
			)
			if chunk.content:
				chunks.append(chunk)
			if end >= len(text):
				break
			next_start = max(end - chunk_overlap, start + 1)
			start = next_start
		return chunks


class RecursiveCharacterSplitter:
	"""Prefer higher-level separators before falling back to fixed windows."""

	_separators: tuple[str, ...] = ("\n\n", "\n", ". ", " ")

	def split(
		self,
		text: str,
		*,
		chunk_size: int,
		chunk_overlap: int,
		min_chunk_size: int,
	) -> list[TextChunk]:
		if text == "":
			return []

		chunks: list[TextChunk] = []
		start = 0
		while start < len(text):
			end = self._resolve_boundary(text, start, chunk_size, min_chunk_size)
			chunk = TextChunk(
				content=text[start:end],
				start_offset=start,
				end_offset=end,
			)
			if chunk.content:
				chunks.append(chunk)
			if end >= len(text):
				break
			start = max(end - chunk_overlap, start + 1)
		return chunks

	def _resolve_boundary(
		self,
		text: str,
		start: int,
		chunk_size: int,
		min_chunk_size: int,
	) -> int:
		hard_end = min(start + chunk_size, len(text))
		if hard_end >= len(text):
			return len(text)

		lower_bound = min(start + min_chunk_size, hard_end)
		for separator in self._separators:
			boundary = text.rfind(separator, lower_bound, hard_end)
			if boundary != -1:
				return boundary + len(separator)
		return hard_end


class SentenceSplitter:
	"""Group sentence-like spans into chunks that respect size limits."""

	_sentence_pattern = re.compile(r"[^.!?]+[.!?]*\s*", re.MULTILINE)

	def split(
		self,
		text: str,
		*,
		chunk_size: int,
		chunk_overlap: int,
		min_chunk_size: int,
	) -> list[TextChunk]:
		if text == "":
			return []

		sentences = self._sentence_spans(text)
		if not sentences:
			return FixedSizeSplitter().split(
				text,
				chunk_size=chunk_size,
				chunk_overlap=chunk_overlap,
				min_chunk_size=min_chunk_size,
			)

		chunks: list[TextChunk] = []
		index = 0
		while index < len(sentences):
			chunk_start = sentences[index].start_offset
			chunk_end = sentences[index].end_offset
			next_index = index + 1

			while next_index < len(sentences):
				candidate = sentences[next_index]
				if (candidate.end_offset - chunk_start) > chunk_size:
					break
				chunk_end = candidate.end_offset
				next_index += 1

			if chunk_end == chunk_start:
				chunk_end = min(chunk_start + chunk_size, len(text))

			chunks.append(
				TextChunk(
					content=text[chunk_start:chunk_end],
					start_offset=chunk_start,
					end_offset=chunk_end,
				)
			)

			if chunk_end >= len(text):
				break

			overlap_start = max(chunk_end - chunk_overlap, chunk_start + 1)
			overlap_index = self._find_sentence_index(sentences, overlap_start)
			if overlap_index <= index:
				overlap_index = next_index
			index = overlap_index
		return self._merge_small_tail(chunks, text, min_chunk_size)

	def _sentence_spans(self, text: str) -> list[TextChunk]:
		spans: list[TextChunk] = []
		for match in self._sentence_pattern.finditer(text):
			start, end = match.span()
			if start == end:
				continue
			spans.append(
				TextChunk(
					content=text[start:end],
					start_offset=start,
					end_offset=end,
				)
			)
		if not spans:
			spans.append(TextChunk(content=text, start_offset=0, end_offset=len(text)))
		return spans

	@staticmethod
	def _find_sentence_index(sentences: list[TextChunk], offset: int) -> int:
		for index, sentence in enumerate(sentences):
			if sentence.end_offset > offset:
				return index
		return len(sentences)

	@staticmethod
	def _merge_small_tail(
		chunks: list[TextChunk],
		text: str,
		min_chunk_size: int,
	) -> list[TextChunk]:
		if len(chunks) < 2:
			return chunks
		last = chunks[-1]
		if (last.end_offset - last.start_offset) >= min_chunk_size:
			return chunks

		merged = TextChunk(
			content=text[chunks[-2].start_offset:last.end_offset],
			start_offset=chunks[-2].start_offset,
			end_offset=last.end_offset,
		)
		return [*chunks[:-2], merged]


class StructuredRecordChunker:
	"""Convert structured records into text chunks for downstream extraction."""

	def __init__(self, *, record_template: str | None = None) -> None:
		self._record_template = record_template

	def chunk_records(
		self,
		records: list[StructuredRecord],
		*,
		source_document_id: str,
		parser_metadata: dict[str, object],
		start_index: int = 0,
		tokenizer: Tokenizer | None = None,
	) -> list[Chunk]:
		chunks: list[Chunk] = []
		for offset, record in enumerate(records):
			content = self._render_record(record)
			chunks.append(
				Chunk(
					id=generate_id(),
					content=content,
					metadata=ChunkMetadata(
						source_document_id=source_document_id,
						chunk_index=start_index + offset,
						section_heading=self._record_heading(record),
						parser_metadata=dict(parser_metadata),
					),
					tokens_estimate=(
						tokenizer.estimate_tokens(content) if tokenizer is not None else None
					),
				)
			)
		return chunks

	def _render_record(self, record: StructuredRecord) -> str:
		if self._record_template is None:
			return json.dumps(record.fields, sort_keys=True, default=str)

		values: dict[str, object] = {
			**record.fields,
			"record_id": record.id,
			"row_number": record.row_number if record.row_number is not None else "",
		}
		formatter = Formatter()
		rendered_parts: list[str] = []
		for literal_text, field_name, format_spec, conversion in formatter.parse(
			self._record_template
		):
			rendered_parts.append(literal_text)
			if field_name is None:
				continue
			if field_name not in values:
				rendered_parts.append("{" + field_name + "}")
				continue
			value = values[field_name]
			if conversion == "r":
				value = repr(value)
			elif conversion == "s":
				value = str(value)
			rendered_parts.append(format(value, format_spec or ""))
		return "".join(rendered_parts)

	@staticmethod
	def _record_heading(record: StructuredRecord) -> str | None:
		if record.row_number is not None:
			return f"record {record.row_number}"
		return f"record {record.id}"


class DocumentChunker:
	"""Chunk parsed documents using text and record-aware strategies."""

	def __init__(
		self,
		strategy: ChunkingStrategy,
		*,
		tokenizer: Tokenizer,
		config: ChunkingConfig,
		record_chunker: StructuredRecordChunker | None = None,
	) -> None:
		self._strategy = strategy
		self._tokenizer = tokenizer
		self._config = config
		self._record_chunker = record_chunker or StructuredRecordChunker(
			record_template=config.record_template
		)

	def chunk_document(
		self,
		parsed_document: ParsedDocument,
		source_document_id: str,
	) -> ChunkingResult:
		chunks: list[Chunk] = []
		if parsed_document.text_content is not None and parsed_document.text_content != "":
			text_chunks = self._strategy.split(
				parsed_document.text_content,
				chunk_size=self._config.chunk_size,
				chunk_overlap=self._config.chunk_overlap,
				min_chunk_size=self._config.min_chunk_size,
			)
			chunks.extend(
				self._build_text_chunks(
					text_chunks,
					source_document_id=source_document_id,
					parser_metadata=parsed_document.parser_metadata,
				)
			)

		if parsed_document.records:
			chunks.extend(
				self._record_chunker.chunk_records(
					parsed_document.records,
					source_document_id=source_document_id,
					parser_metadata=parsed_document.parser_metadata,
					start_index=len(chunks),
					tokenizer=self._tokenizer,
				)
			)

		return ChunkingResult(
			source_document_id=source_document_id,
			parsed_document_id=parsed_document.id,
			chunks=chunks,
			strategy_used=type(self._strategy).__name__,
		)

	def _build_text_chunks(
		self,
		text_chunks: list[TextChunk],
		*,
		source_document_id: str,
		parser_metadata: dict[str, object],
	) -> list[Chunk]:
		chunks: list[Chunk] = []
		for index, text_chunk in enumerate(text_chunks):
			chunks.append(
				Chunk(
					id=generate_id(),
					content=text_chunk.content,
					metadata=ChunkMetadata(
						source_document_id=source_document_id,
						chunk_index=index,
						start_offset=text_chunk.start_offset,
						end_offset=text_chunk.end_offset,
						parser_metadata=dict(parser_metadata),
					),
					tokens_estimate=self._tokenizer.estimate_tokens(text_chunk.content),
				)
			)
		return chunks


def resolve_chunking_config(config: ChunkingConfig | None = None) -> ChunkingConfig:
	"""Return chunking config with optional environment overrides applied."""
	from config.schema import ChunkingConfig as _ChunkingConfig

	base = config or _ChunkingConfig()
	data = base.model_dump()

	strategy = os.environ.get("CHILI_CHUNKING_STRATEGY")
	if strategy is not None:
		data["strategy"] = strategy

	chunk_size = os.environ.get("CHILI_CHUNK_SIZE")
	if chunk_size is not None:
		data["chunk_size"] = int(chunk_size)

	chunk_overlap = os.environ.get("CHILI_CHUNK_OVERLAP")
	if chunk_overlap is not None:
		data["chunk_overlap"] = int(chunk_overlap)

	min_chunk_size = os.environ.get("CHILI_MIN_CHUNK_SIZE")
	if min_chunk_size is not None:
		data["min_chunk_size"] = int(min_chunk_size)

	record_template = os.environ.get("CHILI_RECORD_TEMPLATE")
	if record_template is not None:
		data["record_template"] = record_template

	return _ChunkingConfig.model_validate(data)


def create_document_chunker(config: ChunkingConfig | None = None) -> DocumentChunker:
	"""Create a document chunker from config and environment overrides."""

	resolved = resolve_chunking_config(config)
	strategies: dict[str, ChunkingStrategy] = {
		"recursive": RecursiveCharacterSplitter(),
		"fixed_size": FixedSizeSplitter(),
		"sentence": SentenceSplitter(),
	}
	strategy = strategies[resolved.strategy]
	return DocumentChunker(
		strategy,
		tokenizer=HeuristicTokenizer(),
		config=resolved,
	)


__all__ = [
	"ChunkingResult",
	"ChunkingStrategy",
	"DocumentChunker",
	"FixedSizeSplitter",
	"HeuristicTokenizer",
	"RecursiveCharacterSplitter",
	"SentenceSplitter",
	"StructuredRecordChunker",
	"TextChunk",
	"TiktokenTokenizer",
	"Tokenizer",
	"create_document_chunker",
	"resolve_chunking_config",
]
