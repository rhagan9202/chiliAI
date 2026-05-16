"""Tests for the config-driven feed mapper."""

from __future__ import annotations

import pytest

from config.schema import (
    RecordEntityMapping,
    RecordFeedConfig,
    RecordObservationMapping,
    RecordRelationshipMapping,
)
from records.exceptions import RecordMappingError
from records.mappers.feed_mapper import map_batch, map_observations
from records.models import RawRecord, content_hash_for


def _feed() -> RecordFeedConfig:
    return RecordFeedConfig(
        name="claims_feed",
        record_type="claim_record",
        source="file_upload",
        id_field="claim_id",
        entities=[
            RecordEntityMapping(
                entity_type="claim",
                id_field="claim_id",
                property_fields={"amount": "billed_amount"},
            ),
            RecordEntityMapping(entity_type="provider", id_field="provider_npi"),
        ],
        relationships=[
            RecordRelationshipMapping(
                relationship_type="submitted_by",
                source_entity_type="claim",
                target_entity_type="provider",
            )
        ],
        observations=[
            RecordObservationMapping(
                metric_name="claim_anomaly",
                entity_type="claim",
                score_field="anomaly_score",
                rationale="Structured-feed anomaly score.",
            )
        ],
    )


def _record(claim_id: str) -> RawRecord:
    payload: dict[str, object] = {
        "claim_id": claim_id,
        "provider_npi": "1234567890",
        "billed_amount": 99.0,
        "anomaly_score": 0.8,
    }
    return RawRecord(
        knowledge_base_id="kb-1",
        record_type="claim_record",
        record_id=claim_id,
        payload=payload,
        source_type="file_upload",
        source_ref="claims.csv",
        correlation_id="corr-1",
        content_hash=content_hash_for(payload),
    )


def test_map_batch_builds_entities_and_relationships() -> None:
    mapped = map_batch(_feed(), [_record("c1")])
    entity_ids = {entity.id for entity in mapped.entities}
    assert entity_ids == {"claim:c1", "provider:1234567890"}
    claim = next(entity for entity in mapped.entities if entity.id == "claim:c1")
    assert claim.type == "claim"
    assert claim.properties["amount"] == 99.0
    assert len(mapped.relationships) == 1
    relationship = mapped.relationships[0]
    assert relationship.type == "submitted_by"
    assert relationship.source_id == "claim:c1"
    assert relationship.target_id == "provider:1234567890"


def test_map_batch_deduplicates_repeated_entities() -> None:
    mapped = map_batch(_feed(), [_record("c1"), _record("c1")])
    assert len(mapped.entities) == 2  # claim:c1 + provider:1234567890, deduplicated


def test_map_batch_raises_on_missing_id_field() -> None:
    record = _record("c1")
    record.payload.pop("provider_npi")
    with pytest.raises(RecordMappingError):
        map_batch(_feed(), [record])


def test_map_observations_uses_record_ingested_at() -> None:
    record = _record("c1")
    observations = map_observations(_feed(), [record])
    assert len(observations) == 1
    observation = observations[0]
    assert observation.entity_id == "claim:c1"
    assert observation.metric_name == "claim_anomaly"
    assert observation.score == 0.8
    assert observation.observed_at == record.ingested_at
