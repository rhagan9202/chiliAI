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
import logging
import re
from typing import cast

from ingestion.chunker import ChunkingResult
from ingestion.models import (
	CandidateEntity,
	CandidateRelationship,
	Chunk,
	ExtractionEvidence,
	ExtractionResult,
	TextSpan,
)
from llm.adapters.protocols import LlmClientProtocol
from llm.exceptions import LlmProviderError
from llm.models import ChatMessage, GenerationRequest, MessageRole
from shared.types import EntityDefinition, RelationshipDefinition
from shared.utils import generate_id


_LOG = logging.getLogger(__name__)


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
			for source_candidate, target_candidate in candidate_pairs(
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


class LlmDocumentExtractor:
	"""Extract entities and relationships per chunk via an LlmClient.

	Reads entity and relationship definitions, generates per-chunk prompts,
	parses JSON responses, validates each entity against required property
	constraints, deduplicates within a document by configured natural key,
	and runs an intra-chunk relationship pass.

	Falls back to ``PatternDocumentExtractor`` when no LLM provider is
	configured (via ``create_document_extractor`` below).
	"""

	def __init__(
		self,
		entity_definitions: list[EntityDefinition],
		relationship_definitions: list[RelationshipDefinition] | None = None,
		*,
		llm_client: LlmClientProtocol,
		natural_keys: dict[str, list[str]] | None = None,
		extraction_method: str = "llm_v1",
		model_name: str = "extractor-model",
	) -> None:
		self._entity_definitions = entity_definitions
		self._relationship_definitions = relationship_definitions or []
		self._client = llm_client
		self._natural_keys = natural_keys or {}
		self._extraction_method = extraction_method
		self._model_name = model_name

	def extract_document(self, chunking_result: ChunkingResult) -> ExtractionResult:
		all_candidates: list[CandidateEntity] = []
		warnings: list[str] = []
		seen_natural_keys: dict[str, set[tuple[object, ...]]] = {}

		for chunk in chunking_result.chunks:
			chunk_candidates, chunk_warnings = self._extract_chunk(chunking_result, chunk)
			warnings.extend(chunk_warnings)
			for candidate in chunk_candidates:
				if self._is_duplicate(candidate, seen_natural_keys):
					continue
				all_candidates.append(candidate)

		all_relationships = self._extract_relationships(chunking_result, all_candidates)

		return ExtractionResult(
			id=generate_id(),
			source_document_id=chunking_result.source_document_id,
			parsed_document_id=chunking_result.parsed_document_id,
			chunks=chunking_result.chunks,
			candidate_entities=all_candidates,
			candidate_relationships=all_relationships,
			warnings=warnings,
		)

	def _extract_chunk(
		self,
		chunking_result: ChunkingResult,
		chunk: Chunk,
	) -> tuple[list[CandidateEntity], list[str]]:
		prompt = self._build_prompt(chunk.content)
		try:
			result = self._client.generate(
				GenerationRequest(
					request_id=generate_id(),
					knowledge_base_id=None,
					messages=[
						ChatMessage(role=MessageRole.SYSTEM, content=prompt["system"]),
						ChatMessage(role=MessageRole.USER, content=prompt["user"]),
					],
					model_name=self._model_name,
					temperature=0.1,
					max_tokens=1024,
				)
			)
		except LlmProviderError as exc:
			return [], [f"LLM extraction failed for chunk {chunk.id}: {exc}"]

		try:
			parsed: object = json.loads(result.completion)
		except json.JSONDecodeError as exc:
			return [], [f"LLM returned non-JSON for chunk {chunk.id}: {exc}"]

		if not isinstance(parsed, dict):
			return [], [f"LLM returned non-object JSON for chunk {chunk.id}."]

		payload = cast(dict[str, object], parsed)
		raw_entities_field = payload.get("entities")
		if raw_entities_field is None:
			return [], []
		if not isinstance(raw_entities_field, list):
			return [], [f"LLM 'entities' field is not a list for chunk {chunk.id}."]

		entity_list = cast(list[object], raw_entities_field)
		candidates: list[CandidateEntity] = []
		chunk_warnings: list[str] = []
		for raw_entity in entity_list:
			if not isinstance(raw_entity, dict):
				chunk_warnings.append(f"Skipping non-object entity in chunk {chunk.id}.")
				continue
			typed_entity = cast(dict[str, object], raw_entity)
			entity, warning = self._build_candidate(chunking_result, chunk, typed_entity)
			if entity is not None:
				candidates.append(entity)
			elif warning is not None:
				chunk_warnings.append(warning)
		return candidates, chunk_warnings

	def _build_prompt(self, content: str) -> dict[str, str]:
		entity_schemas = [
			{
				"type": d.name,
				"properties": {
					p: {"required": pdef.required, "type": pdef.type.value}
					for p, pdef in d.properties.items()
				},
			}
			for d in self._entity_definitions
		]
		relationship_schemas = [
			{"type": r.name, "source": r.source, "target": r.target}
			for r in self._relationship_definitions
		]
		system = (
			"You extract structured entities and relationships from text. "
			"Output strict JSON of the form "
			'{"entities": [{"type": "...", "properties": {...}}], '
			'"relationships": [{"type": "...", "source_index": 0, "target_index": 1}]}. '
			"Use only entity types listed in the schema. Omit fields you cannot find."
		)
		user = (
			f"Entity schemas: {json.dumps(entity_schemas)}\n"
			f"Relationship schemas: {json.dumps(relationship_schemas)}\n\n"
			f"Text:\n{content}\n\n"
			"Return JSON only."
		)
		return {"system": system, "user": user}

	def _build_candidate(
		self,
		chunking_result: ChunkingResult,
		chunk: Chunk,
		raw: dict[str, object],
	) -> tuple[CandidateEntity | None, str | None]:
		entity_type = raw.get("type")
		raw_properties = raw.get("properties", {})
		if not isinstance(entity_type, str) or not isinstance(raw_properties, dict):
			return None, f"Skipping malformed entity in chunk {chunk.id}."
		properties: dict[str, object] = cast(dict[str, object], raw_properties)

		defn = next((d for d in self._entity_definitions if d.name == entity_type), None)
		if defn is None:
			return None, f"Unknown entity type '{entity_type}' in chunk {chunk.id}."

		missing_required = [
			name for name, pdef in defn.properties.items()
			if pdef.required and name not in properties
		]
		if missing_required:
			return None, (
				f"Entity '{entity_type}' in chunk {chunk.id} is missing required "
				f"properties: {missing_required}"
			)

		return CandidateEntity(
			id=generate_id(),
			source_document_id=chunking_result.source_document_id,
			chunk_id=chunk.id,
			type=entity_type,
			properties=properties,
			confidence=0.8,
			extraction_method=self._extraction_method,
			evidence=[],
			metadata={"llm_model": self._model_name},
		), None

	def _is_duplicate(
		self,
		candidate: CandidateEntity,
		seen: dict[str, set[tuple[object, ...]]],
	) -> bool:
		key_fields = self._natural_keys.get(candidate.type)
		if not key_fields:
			return False
		try:
			key = tuple(candidate.properties[f] for f in key_fields)
		except KeyError:
			return False
		bucket = seen.setdefault(candidate.type, set())
		if key in bucket:
			return True
		bucket.add(key)
		return False

	def _extract_relationships(
		self,
		chunking_result: ChunkingResult,
		candidates: list[CandidateEntity],
	) -> list[CandidateRelationship]:
		"""Intra-chunk relationship pass — mirrors PatternDocumentExtractor's behavior."""

		relationships: list[CandidateRelationship] = []
		for chunk in chunking_result.chunks:
			chunk_candidates = [c for c in candidates if c.chunk_id == chunk.id]
			for rel_def in self._relationship_definitions:
				sources = [c for c in chunk_candidates if c.type == rel_def.source]
				targets = [c for c in chunk_candidates if c.type == rel_def.target]
				for source in sources:
					for target in targets:
						if source.id == target.id:
							continue
						relationships.append(
							CandidateRelationship(
								id=generate_id(),
								source_document_id=chunking_result.source_document_id,
								chunk_id=chunk.id,
								type=rel_def.name,
								source_candidate_id=source.id,
								target_candidate_id=target.id,
								confidence=min(source.confidence, target.confidence),
								extraction_method=self._extraction_method,
								evidence=[],
								metadata={},
							)
						)
		return relationships


def create_document_extractor(
	entity_definitions: list[EntityDefinition],
	relationship_definitions: list[RelationshipDefinition] | None = None,
	*,
	llm_client: LlmClientProtocol | None = None,
	natural_keys: dict[str, list[str]] | None = None,
) -> PatternDocumentExtractor | LlmDocumentExtractor:
	"""Create the default document extractor for ingestion workers.

	Returns ``LlmDocumentExtractor`` when an ``llm_client`` is provided,
	otherwise falls back to ``PatternDocumentExtractor``.
	"""

	if llm_client is None:
		return PatternDocumentExtractor(entity_definitions, relationship_definitions)
	return LlmDocumentExtractor(
		entity_definitions,
		relationship_definitions,
		llm_client=llm_client,
		natural_keys=natural_keys,
	)


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


def candidate_pairs(
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


__all__ = ["LlmDocumentExtractor", "PatternDocumentExtractor", "candidate_pairs", "create_document_extractor"]
