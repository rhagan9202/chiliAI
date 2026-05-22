"""Records-mapped entities and relationships carry source provenance."""

from __future__ import annotations

from datetime import datetime, timezone

from config.schema import (
    RecordEntityMapping,
    RecordFeedConfig,
    RecordRelationshipMapping,
)
from records.mappers.feed_mapper import map_batch
from records.models import RawRecord
from shared.types import PropertyDefinition, PropertyType


def _record(payload: dict[str, object], record_id: str = "r1") -> RawRecord:
    return RawRecord(
        record_id=record_id,
        knowledge_base_id="kb-1",
        record_type="carrier_claim_record",
        content_hash="hash-" + record_id,
        source_type="file_upload",
        correlation_id="corr-1",
        payload=payload,
        ingested_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _feed() -> RecordFeedConfig:
    return RecordFeedConfig(
        name="carrier_claims_a",
        record_type="carrier_claim_record",
        source="file_upload",
        id_field="CLM_ID",
        record_schema={
            "CLM_ID": PropertyDefinition(type=PropertyType.STRING, display="Claim ID", required=True),
            "NPI": PropertyDefinition(type=PropertyType.STRING, display="NPI"),
        },
        entities=[
            RecordEntityMapping(
                entity_type="claim",
                id_field="CLM_ID",
                property_fields={"claim_id": "CLM_ID"},
            ),
            RecordEntityMapping(
                entity_type="provider",
                id_field="NPI",
                property_fields={"npi": "NPI"},
            ),
        ],
        relationships=[
            RecordRelationshipMapping(
                relationship_type="submitted_by",
                source_entity_type="claim",
                target_entity_type="provider",
            ),
        ],
    )


def test_entity_carries_source_provenance() -> None:
    result = map_batch(_feed(), [_record({"CLM_ID": "C1", "NPI": "1234567890"})])

    claim = next(e for e in result.entities if e.type == "claim")
    assert claim.metadata["source_kind"] == "record"
    assert claim.metadata["source_feed"] == "carrier_claims_a"
    assert claim.metadata["source_raw_record_id"] == "r1"


def test_relationship_carries_source_provenance() -> None:
    result = map_batch(_feed(), [_record({"CLM_ID": "C1", "NPI": "1234567890"})])

    rel = result.relationships[0]
    assert rel.metadata["source_kind"] == "record"
    assert rel.metadata["source_feed"] == "carrier_claims_a"
    assert rel.metadata["source_raw_record_id"] == "r1"
