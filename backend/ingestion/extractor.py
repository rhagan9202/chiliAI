"""Entity and relationship extraction logic.

This module is responsible for extracting entities and relationships from
ingested data according to the domain configuration. It uses the definitions
of entities and relationships to identify and structure the relevant
information from raw input, preparing it for downstream processing and
storage.

The extractor may leverage NLP techniques, pattern matching, or other methods
to recognize and classify entities and relationships based on the configured
schema. It serves as a critical component in transforming unstructured data
into structured formats that align with the domain model.
"""

from __future__ import annotations

import json
import re

from ingestion.chunker import ChunkingResult
from ingestion.models import CandidateEntity, Chunk, ExtractionEvidence, ExtractionResult, TextSpan
from shared.types import EntityDefinition
from shared.utils import generate_id


class PatternDocumentExtractor:
	"""Baseline config-driven extractor using property label matching patterns."""

	def __init__(
		self,
		entity_definitions: list[EntityDefinition],
		*,
		extraction_method: str = "pattern_v1",
	) -> None:
		self._entity_definitions = entity_definitions
		self._extraction_method = extraction_method

	def extract_document(self, chunking_result: ChunkingResult) -> ExtractionResult:
		candidate_entities: list[CandidateEntity] = []
		warnings: list[str] = []

		for chunk in chunking_result.chunks:
			candidate_entities.extend(self._extract_entities_from_chunk(chunking_result, chunk))

		if not candidate_entities:
			warnings.append("No entity candidates extracted from persisted chunks.")

		return ExtractionResult(
			id=generate_id(),
			source_document_id=chunking_result.source_document_id,
			parsed_document_id=chunking_result.parsed_document_id,
			chunks=chunking_result.chunks,
			candidate_entities=candidate_entities,
			candidate_relationships=[],
			warnings=warnings,
		)

	def _extract_entities_from_chunk(
		self,
		chunking_result: ChunkingResult,
		chunk: Chunk,
	) -> list[CandidateEntity]:
		candidates: list[CandidateEntity] = []
		for entity_definition in self._entity_definitions:
			properties: dict[str, object] = {}
			evidence: list[ExtractionEvidence] = []

			for property_name in entity_definition.properties:
				match = _match_property_value(chunk.content, property_name)
				if match is None:
					continue
				value_text, start_offset, end_offset = match
				properties[property_name] = _coerce_value(value_text)
				evidence.append(
					ExtractionEvidence(
						chunk_id=chunk.id,
						span=TextSpan(
							text=value_text,
							start_offset=(
								chunk.metadata.start_offset + start_offset
								if chunk.metadata.start_offset is not None
								else start_offset
							),
							end_offset=(
								chunk.metadata.start_offset + end_offset
								if chunk.metadata.start_offset is not None
								else end_offset
							),
						),
						quote=value_text,
						rationale=f"Matched property '{property_name}' for entity '{entity_definition.name}'.",
					)
				)

			if not properties:
				continue

			coverage = len(properties) / max(1, len(entity_definition.properties))
			confidence = min(0.95, 0.45 + coverage * 0.45)
			candidates.append(
				CandidateEntity(
					id=generate_id(),
					source_document_id=chunking_result.source_document_id,
					chunk_id=chunk.id,
					type=entity_definition.name,
					properties=properties,
					confidence=confidence,
					extraction_method=self._extraction_method,
					evidence=evidence,
					metadata={
						"matched_property_count": len(properties),
						"available_property_count": len(entity_definition.properties),
					},
				)
			)
		return candidates


def create_document_extractor(
	entity_definitions: list[EntityDefinition],
) -> PatternDocumentExtractor:
	"""Create the default document extractor for ingestion workers."""

	return PatternDocumentExtractor(entity_definitions)


def _match_property_value(content: str, property_name: str) -> tuple[str, int, int] | None:
	escaped = re.escape(property_name)
	patterns = (
		rf'"{escaped}"\s*:\s*(?P<value>"[^"]*"|\[[^\]]*\]|[^,}}\n]+)',
		rf'\b{escaped}\b\s*[:=]\s*(?P<value>[^\n,;]+)',
	)
	for pattern in patterns:
		match = re.search(pattern, content, flags=re.IGNORECASE)
		if match is None:
			continue
		start_offset, end_offset = match.span("value")
		return match.group("value").strip(), start_offset, end_offset
	return None


def _coerce_value(value: str) -> object:
	stripped = value.strip()
	try:
		return json.loads(stripped)
	except json.JSONDecodeError:
		return stripped.strip('"')


__all__ = ["PatternDocumentExtractor", "create_document_extractor"]