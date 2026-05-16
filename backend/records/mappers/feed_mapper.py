"""Map structured record rows onto graph entities, relationships, observations.

Entity ids are deterministic (``"{entity_type}:{raw_id}"``) so re-running a
feed upserts the same nodes — the worker's Flow 1 handler is idempotent.
Observation timestamps come from the persisted record's ``ingested_at`` so a
retried handler writes identical ``observations`` rows.
"""

from __future__ import annotations

from dataclasses import dataclass

from config.schema import RecordFeedConfig
from monitoring.models import MonitoringObservation
from records.exceptions import RecordMappingError
from records.models import RawRecord
from shared.types import Entity, Relationship


@dataclass(frozen=True, slots=True)
class MappedGraph:
    """Graph objects produced from a record batch."""

    entities: list[Entity]
    relationships: list[Relationship]


def _entity_id(entity_type: str, raw_id: object) -> str:
    return f"{entity_type}:{raw_id}"


def _as_float(value: object) -> float:
    if isinstance(value, bool):
        raise RecordMappingError("Observation score must be numeric, not boolean.")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError as exc:
            raise RecordMappingError(
                f"Observation score '{value}' is not numeric."
            ) from exc
    raise RecordMappingError(
        f"Observation score of type {type(value).__name__} is not numeric."
    )


def map_batch(feed: RecordFeedConfig, records: list[RawRecord]) -> MappedGraph:
    """Map a record batch to deduplicated graph entities and relationships."""

    entities: dict[str, Entity] = {}
    relationships: dict[str, Relationship] = {}
    for record in records:
        row = record.payload
        row_entity_ids: dict[str, str] = {}
        for entity_mapping in feed.entities:
            raw_id = row.get(entity_mapping.id_field)
            if raw_id is None:
                raise RecordMappingError(
                    f"Feed '{feed.name}' record '{record.record_id}' is missing "
                    f"id field '{entity_mapping.id_field}'."
                )
            entity_id = _entity_id(entity_mapping.entity_type, raw_id)
            properties: dict[str, object] = {
                entity_property: row[record_field]
                for entity_property, record_field in entity_mapping.property_fields.items()
                if record_field in row
            }
            entities[entity_id] = Entity(
                id=entity_id, type=entity_mapping.entity_type, properties=properties
            )
            row_entity_ids[entity_mapping.entity_type] = entity_id
        for relationship_mapping in feed.relationships:
            source_id = row_entity_ids.get(relationship_mapping.source_entity_type)
            target_id = row_entity_ids.get(relationship_mapping.target_entity_type)
            if source_id is None or target_id is None:
                raise RecordMappingError(
                    f"Feed '{feed.name}' relationship "
                    f"'{relationship_mapping.relationship_type}' references an entity "
                    f"type not mapped by record '{record.record_id}'."
                )
            relationship_id = (
                f"{relationship_mapping.relationship_type}:{source_id}->{target_id}"
            )
            relationships[relationship_id] = Relationship(
                id=relationship_id,
                type=relationship_mapping.relationship_type,
                source_id=source_id,
                target_id=target_id,
            )
    return MappedGraph(
        entities=list(entities.values()),
        relationships=list(relationships.values()),
    )


def map_observations(
    feed: RecordFeedConfig, records: list[RawRecord]
) -> list[MonitoringObservation]:
    """Derive scored observations from a record batch.

    Each observation's ``observed_at`` is the source record's ``ingested_at``,
    keeping observation writes idempotent across handler retries.
    """

    id_field_by_entity_type = {
        entity_mapping.entity_type: entity_mapping.id_field
        for entity_mapping in feed.entities
    }
    observations: list[MonitoringObservation] = []
    for record in records:
        row = record.payload
        for observation_mapping in feed.observations:
            score_value = row.get(observation_mapping.score_field)
            if score_value is None:
                continue
            id_field = id_field_by_entity_type.get(observation_mapping.entity_type)
            if id_field is None:
                raise RecordMappingError(
                    f"Feed '{feed.name}' observation references entity type "
                    f"'{observation_mapping.entity_type}' not mapped by the feed."
                )
            raw_id = row.get(id_field)
            if raw_id is None:
                raise RecordMappingError(
                    f"Feed '{feed.name}' record '{record.record_id}' is missing "
                    f"observation id field '{id_field}'."
                )
            observations.append(
                MonitoringObservation(
                    entity_id=_entity_id(observation_mapping.entity_type, raw_id),
                    entity_type=observation_mapping.entity_type,
                    metric_name=observation_mapping.metric_name,
                    score=_as_float(score_value),
                    observed_at=record.ingested_at,
                    rationale=observation_mapping.rationale,
                )
            )
    return observations


__all__ = [
    "MappedGraph",
    "map_batch",
    "map_observations",
]
