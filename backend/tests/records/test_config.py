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


def test_feed_config_defaults_accepted_formats() -> None:
    feed = RecordFeedConfig(
        name="claims_feed",
        record_type="claim_record",
        source="file_upload",
        id_field="claim_id",
        record_schema=_schema(),
    )
    assert feed.accepted_formats == ["csv", "jsonl"]


def test_feed_config_accepts_custom_accepted_formats() -> None:
    feed = RecordFeedConfig(
        name="claims_feed",
        record_type="claim_record",
        source="file_upload",
        id_field="claim_id",
        record_schema=_schema(),
        accepted_formats=["csv"],
    )
    assert feed.accepted_formats == ["csv"]


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
                    "score": {
                        "type": "decimal",
                        "display": "Score",
                        "min_value": 0,
                        "max_value": 1,
                    },
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


def test_domain_config_rejects_relationship_target_entity_not_mapped() -> None:
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
                        "source_entity_type": "claim",
                        "target_entity_type": "not_mapped",
                    }
                ],
            }
        ]
    }
    with pytest.raises(ValidationError, match="not mapped by the feed"):
        base.__class__.model_validate(payload)


def test_domain_config_rejects_observation_score_field_not_in_schema() -> None:
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
                "observations": [
                    {
                        "metric_name": "risk",
                        "entity_type": "claim",
                        "score_field": "missing_score",
                    }
                ],
            }
        ]
    }
    with pytest.raises(
        ValidationError, match="score_field 'missing_score' is not in record_schema"
    ):
        base.__class__.model_validate(payload)


def _observation_feed_payload(
    score_schema: dict[str, object], observation: dict[str, object]
) -> dict[str, object]:
    """A single-feed records payload mapping one observation onto 'score'."""
    return {
        "feeds": [
            {
                "name": "obs_feed",
                "record_type": "claim_record",
                "source": "file_upload",
                "id_field": "claim_id",
                "record_schema": {
                    "claim_id": {"type": "string", "display": "Claim ID", "required": True},
                    "score": score_schema,
                },
                "entities": [{"entity_type": "claim", "id_field": "claim_id"}],
                "observations": [observation],
            }
        ]
    }


def _validate_with_records(records_payload: dict[str, object]) -> None:
    from config.loader import load_config  # noqa: PLC0415

    base = load_config()
    payload = base.model_dump()
    payload["records"] = records_payload
    payload["peer_stats"] = None
    base.__class__.model_validate(payload)


def test_domain_config_accepts_unit_bounded_score_field() -> None:
    _validate_with_records(
        _observation_feed_payload(
            {"type": "decimal", "display": "Score", "min_value": 0, "max_value": 1},
            {"metric_name": "risk", "entity_type": "claim", "score_field": "score"},
        )
    )


def test_domain_config_accepts_score_max_covering_declared_max() -> None:
    _validate_with_records(
        _observation_feed_payload(
            {"type": "decimal", "display": "Score", "min_value": 0, "max_value": 100},
            {
                "metric_name": "risk",
                "entity_type": "claim",
                "score_field": "score",
                "score_max": 100,
            },
        )
    )


def test_domain_config_accepts_integer_score_field_with_score_max() -> None:
    _validate_with_records(
        _observation_feed_payload(
            {"type": "integer", "display": "Score", "min_value": 0, "max_value": 100},
            {
                "metric_name": "risk",
                "entity_type": "claim",
                "score_field": "score",
                "score_max": 100,
            },
        )
    )


def test_domain_config_rejects_non_numeric_score_field() -> None:
    """A string-typed field with numeric bounds would pass load-time checks
    while intake enforces bounds only for numeric types — values would then
    hard-fail worker-side, recreating the DLQ/FAILED symptom for a
    'validated' pack. Reject it at config load instead (red-cell A2)."""
    with pytest.raises(ValidationError, match="must be a numeric record_schema type"):
        _validate_with_records(
            _observation_feed_payload(
                {
                    "type": "string",
                    "display": "Score",
                    "min_value": 0,
                    "max_value": 1,
                },
                {"metric_name": "risk", "entity_type": "claim", "score_field": "score"},
            )
        )


def test_domain_config_rejects_unbounded_score_field_without_score_max() -> None:
    with pytest.raises(ValidationError, match="must declare max_value <= 1"):
        _validate_with_records(
            _observation_feed_payload(
                {"type": "decimal", "display": "Score", "min_value": 0},
                {"metric_name": "risk", "entity_type": "claim", "score_field": "score"},
            )
        )


def test_domain_config_rejects_wide_score_field_without_score_max() -> None:
    with pytest.raises(ValidationError, match="must declare max_value <= 1"):
        _validate_with_records(
            _observation_feed_payload(
                {"type": "decimal", "display": "Score", "min_value": 0, "max_value": 100},
                {"metric_name": "risk", "entity_type": "claim", "score_field": "score"},
            )
        )


def test_domain_config_rejects_score_max_on_field_without_declared_max() -> None:
    """A field with no max_value (e.g. a raw count) can never be proven in-range."""
    with pytest.raises(ValidationError, match="declares no max_value"):
        _validate_with_records(
            _observation_feed_payload(
                {"type": "integer", "display": "Score", "min_value": 0},
                {
                    "metric_name": "risk",
                    "entity_type": "claim",
                    "score_field": "score",
                    "score_max": 100,
                },
            )
        )


def test_domain_config_rejects_score_max_below_declared_max() -> None:
    with pytest.raises(ValidationError, match="greater than score_max"):
        _validate_with_records(
            _observation_feed_payload(
                {"type": "decimal", "display": "Score", "min_value": 0, "max_value": 100},
                {
                    "metric_name": "risk",
                    "entity_type": "claim",
                    "score_field": "score",
                    "score_max": 10,
                },
            )
        )


def test_domain_config_rejects_score_field_without_declared_min() -> None:
    with pytest.raises(ValidationError, match="must declare min_value >= 0"):
        _validate_with_records(
            _observation_feed_payload(
                {"type": "decimal", "display": "Score", "max_value": 1},
                {"metric_name": "risk", "entity_type": "claim", "score_field": "score"},
            )
        )


def test_domain_config_rejects_score_field_with_negative_min() -> None:
    with pytest.raises(ValidationError, match="must declare min_value >= 0"):
        _validate_with_records(
            _observation_feed_payload(
                {
                    "type": "decimal",
                    "display": "Score",
                    "min_value": -1,
                    "max_value": 1,
                },
                {"metric_name": "risk", "entity_type": "claim", "score_field": "score"},
            )
        )


def test_observation_mapping_rejects_non_positive_score_max() -> None:
    with pytest.raises(ValidationError):
        RecordObservationMapping(
            metric_name="risk",
            entity_type="claim",
            score_field="score",
            score_max=0,
        )
