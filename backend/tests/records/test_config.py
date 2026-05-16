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


def test_domain_config_rejects_feed_id_field_not_in_schema() -> None:
    from config.loader import load_config  # noqa: PLC0415

    base = load_config()
    payload = base.model_dump()
    payload["records"] = {
        "feeds": [
            {
                "name": "bad_feed",
                "record_type": "claim_record",
                "source": "file_upload",
                "id_field": "missing_field",
                "record_schema": {
                    "claim_id": {"type": "string", "display": "Claim ID", "required": True}
                },
            }
        ]
    }
    with pytest.raises(ValidationError, match="is not declared in record_schema"):
        base.__class__.model_validate(payload)


def test_domain_config_rejects_entity_mapping_id_field_not_in_schema() -> None:
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
                "entities": [{"entity_type": "claim", "id_field": "not_in_schema"}],
            }
        ]
    }
    with pytest.raises(ValidationError, match="is not in record_schema"):
        base.__class__.model_validate(payload)


def test_domain_config_rejects_unknown_relationship_type() -> None:
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
                    "claim_id": {"type": "string", "display": "Claim ID", "required": True},
                    "provider_id": {"type": "string", "display": "Provider ID"},
                },
                "entities": [
                    {"entity_type": "claim", "id_field": "claim_id"},
                    {"entity_type": "provider", "id_field": "provider_id"},
                ],
                "relationships": [
                    {
                        "relationship_type": "not_a_relationship",
                        "source_entity_type": "claim",
                        "target_entity_type": "provider",
                    }
                ],
            }
        ]
    }
    with pytest.raises(ValidationError, match="unknown relationship"):
        base.__class__.model_validate(payload)


def test_domain_config_rejects_observation_entity_not_mapped() -> None:
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
                    "claim_id": {"type": "string", "display": "Claim ID", "required": True},
                    "score": {"type": "decimal", "display": "Score"},
                },
                "entities": [{"entity_type": "claim", "id_field": "claim_id"}],
                "observations": [
                    {
                        "metric_name": "risk",
                        "entity_type": "provider",
                        "score_field": "score",
                    }
                ],
            }
        ]
    }
    with pytest.raises(ValidationError, match="not mapped by the feed"):
        base.__class__.model_validate(payload)


def test_domain_config_rejects_relationship_source_entity_not_mapped() -> None:
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
                "entities": [{"entity_type": "claim", "id_field": "claim_id"}],
                "relationships": [
                    {
                        "relationship_type": "submitted_by",
                        "source_entity_type": "not_mapped",
                        "target_entity_type": "claim",
                    }
                ],
            }
        ]
    }
    with pytest.raises(ValidationError, match="not mapped by the feed"):
        base.__class__.model_validate(payload)
