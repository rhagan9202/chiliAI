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
from ingestion.models import (
	CandidateEntity,
	CandidateRelationship,
	Chunk,
	ExtractionEvidence,
	ExtractionResult,
	TextSpan,
)
from shared.types import EntityDefinition, RelationshipDefinition
from shared.utils import generate_id


class PatternDocumentExtractor:
	"""Baseline config-driven extractor using property label matching patterns."""

	# TODO(production): This is a regex-based baseline extractor. Implement an
	# LlmDocumentExtractor that uses the LLM service with structured prompts to
	# extract entities and relationships. The LLM extractor should:
	# - Accept a prompt template per entity type from config
	# - Support confidence calibration beyond coverage heuristics
	# - Perform coreference resolution across chunks (same entity, different mentions)
	# - Deduplicate entities with fuzzy matching before emitting candidates
	# - Extract cross-chunk relationships (currently limited to intra-chunk)
	# See docs/architecture.md §6 ingestion pipeline.

	def __init__(
		self,
		entity_definitions: list[EntityDefinition],
		relationship_definitions: list[RelationshipDefinition] | None = None,
		*,
		extraction_method: str = "pattern_v1",
	) -> None:
		self._entity_definitions = entity_definitions
		self._relationship_definitions = relationship_definitions or []
		self._extraction_method = extraction_method

	def extract_document(self, chunking_result: ChunkingResult) -> ExtractionResult:
		candidate_entities: list[CandidateEntity] = []
		candidate_relationships: list[CandidateRelationship] = []
		warnings: list[str] = []

		for chunk in chunking_result.chunks:
			chunk_entities = self._extract_entities_from_chunk(chunking_result, chunk)
			candidate_entities.extend(chunk_entities)
			candidate_relationships.extend(
				self._extract_relationships_from_chunk(chunking_result, chunk, chunk_entities)
			)

		if not candidate_entities:
			warnings.append("No entity candidates extracted from persisted chunks.")

		return ExtractionResult(
			id=generate_id(),
			source_document_id=chunking_result.source_document_id,
			parsed_document_id=chunking_result.parsed_document_id,
			chunks=chunking_result.chunks,
			candidate_entities=candidate_entities,
			candidate_relationships=candidate_relationships,
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

	def _extract_relationships_from_chunk(
		self,
		chunking_result: ChunkingResult,
		chunk: Chunk,
		candidate_entities: list[CandidateEntity],
	) -> list[CandidateRelationship]:
		candidates: list[CandidateRelationship] = []
		for relationship_definition in self._relationship_definitions:
			source_candidates = [
				candidate
				for candidate in candidate_entities
				if candidate.type == relationship_definition.source
			]
			target_candidates = [
				candidate
				for candidate in candidate_entities
				if candidate.type == relationship_definition.target
			]
			for source_candidate, target_candidate in _candidate_pairs(
				source_candidates,
				target_candidates,
				chunk=chunk,
				allow_self_reference=relationship_definition.source == relationship_definition.target,
			):
				candidates.append(
					CandidateRelationship(
						id=generate_id(),
						source_document_id=chunking_result.source_document_id,
						chunk_id=chunk.id,
						type=relationship_definition.name,
						source_candidate_id=source_candidate.id,
						target_candidate_id=target_candidate.id,
						confidence=min(source_candidate.confidence, target_candidate.confidence),
						extraction_method=self._extraction_method,
						evidence=_relationship_evidence(chunk, source_candidate, target_candidate),
						metadata={
							"source_entity_type": source_candidate.type,
							"target_entity_type": target_candidate.type,
						},
					)
				)
		return candidates


def create_document_extractor(
	entity_definitions: list[EntityDefinition],
	relationship_definitions: list[RelationshipDefinition] | None = None,
) -> PatternDocumentExtractor:
	"""Create the default document extractor for ingestion workers."""

	return PatternDocumentExtractor(entity_definitions, relationship_definitions)


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


def _candidate_pairs(
	source_candidates: list[CandidateEntity],
	target_candidates: list[CandidateEntity],
	*,
	chunk: Chunk,
	allow_self_reference: bool,
) -> list[tuple[CandidateEntity, CandidateEntity]]:
	if not source_candidates or not target_candidates:
		return []

	if allow_self_reference:
		sorted_candidates = sorted(source_candidates, key=_candidate_anchor)
		if len(sorted_candidates) == 1:
			return [(sorted_candidates[0], sorted_candidates[0])]
		return [
			(sorted_candidates[index], sorted_candidates[index + 1])
			for index in range(len(sorted_candidates) - 1)
		]

	scored_pairs: list[tuple[float, CandidateEntity, CandidateEntity]] = []
	for source_candidate in source_candidates:
		for target_candidate in target_candidates:
			if source_candidate.id == target_candidate.id:
				continue
			scored_pairs.append(
				(_relationship_pair_score(chunk, source_candidate, target_candidate), source_candidate, target_candidate)
			)

	scored_pairs.sort(key=lambda item: item[0])
	used_sources: set[str] = set()
	used_targets: set[str] = set()
	pairs: list[tuple[CandidateEntity, CandidateEntity]] = []
	for _score, source_candidate, target_candidate in scored_pairs:
		if source_candidate.id in used_sources or target_candidate.id in used_targets:
			continue
		used_sources.add(source_candidate.id)
		used_targets.add(target_candidate.id)
		pairs.append((source_candidate, target_candidate))
	return pairs


def _relationship_pair_score(
	chunk: Chunk,
	source_candidate: CandidateEntity,
	target_candidate: CandidateEntity,
) -> float:
	source_anchor = _candidate_anchor(source_candidate)
	target_anchor = _candidate_anchor(target_candidate)
	distance_penalty = abs(source_anchor - target_anchor)
	confidence_bonus = -(source_candidate.confidence + target_candidate.confidence)
	structured_record_bonus = -5.0 if (chunk.metadata.section_heading or "").startswith("record ") else 0.0
	return distance_penalty + confidence_bonus + structured_record_bonus


def _candidate_anchor(candidate: CandidateEntity) -> int:
	for evidence in candidate.evidence:
		if evidence.span is not None and evidence.span.start_offset is not None:
			return evidence.span.start_offset
	return 10**9


def _relationship_evidence(
	chunk: Chunk,
	source_candidate: CandidateEntity,
	target_candidate: CandidateEntity,
) -> list[ExtractionEvidence]:
	evidence: list[ExtractionEvidence] = []
	for candidate in (source_candidate, target_candidate):
		if candidate.evidence:
			evidence.append(candidate.evidence[0].model_copy())
	if evidence:
		return evidence
	return [
		ExtractionEvidence(
			chunk_id=chunk.id,
			quote=chunk.content,
			rationale=(
				f"Linked '{source_candidate.type}' to '{target_candidate.type}' within the same chunk."
			),
		)
	]


__all__ = ["PatternDocumentExtractor", "create_document_extractor"]