"""Tests for the records configuration schema and DomainConfig wiring."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from config.schema import (
    CapabilitiesConfig,
    RecordEntityMapping,
    RecordFeedConfig,
    RecordObservationMapping,
    RecordsConfig,
)
from shared.types import PropertyDefinition, PropertyType


def _schema() -> dict[str, PropertyDefinition]:
    return {
        "claim_id": PropertyDefinition(type=PropertyType.STRING, display="Claim ID", required=True),
        "score": PropertyDefinition(type=PropertyType.DECIMAL, display="Score"),
    }


def test_capabilities_defaults_structured_ingestion_off() -> None:
    assert CapabilitiesConfig().structured_ingestion is False


def test_records_config_defaults_to_no_feeds() -> None:
    assert RecordsConfig().feeds == []


def test_feed_config_accepts_a_full_definition() -> None:
    feed = RecordFeedConfig(
        name="claims_feed",
        record_type="claim_record",
        source="file_upload",
        id_field="claim_id",
        record_schema=_schema(),
        entities=[RecordEntityMapping(entity_type="claim", id_field="claim_id")],
        observations=[
            RecordObservationMapping(
                metric_name="claim_anomaly", entity_type="claim", score_field="score"
            )
        ],
    )
    assert feed.name == "claims_feed"
    assert feed.entities[0].entity_type == "claim"


def test_feed_rejects_unknown_source() -> None:
    with pytest.raises(ValidationError):
        RecordFeedConfig(
            name="f",
            record_type="r",
            source="kafka",  # type: ignore[arg-type]
            id_field="claim_id",
            record_schema=_schema(),
        )


def test_domain_config_rejects_feed_with_unknown_entity_type() -> None:
    from config.loader import load_config  # noqa: PLC0415

    base = load_config()
    payload = base.model_dump()
    payload["records"] = {
        "feeds": [
            {
                "name": "bad_feed",
                "record_type": "claim_record",
                "source": "file_upload",
                "id_field": "claim_id",
                "record_schema": {
                    "claim_id": {"type": "string", "display": "Claim ID", "required": True}
                },
                "entities": [{"entity_type": "not_an_entity", "id_field": "claim_id"}],
            }
        ]
    }
    with pytest.raises(ValidationError, match="unknown entity type"):
        base.__class__.model_validate(payload)
