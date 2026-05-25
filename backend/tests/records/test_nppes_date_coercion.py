"""NPPES-format MM/DD/YYYY dates are coerced to ISO-8601 before validation."""

from __future__ import annotations

import pytest

from config.schema import RecordEntityMapping, RecordFeedConfig
from records.exceptions import RecordValidationError
from records.validation import coerce_row, validate_rows
from shared.types import PropertyDefinition, PropertyType


def _nppes_feed() -> RecordFeedConfig:
    return RecordFeedConfig(
        name="nppes_test",
        record_type="provider_record",
        source="file_upload",
        id_field="NPI",
        record_schema={
            "NPI": PropertyDefinition(type=PropertyType.STRING, display="NPI", required=True),
            "Provider Enumeration Date": PropertyDefinition(type=PropertyType.DATE, display="Enumeration Date"),
            "NPI Deactivation Date": PropertyDefinition(type=PropertyType.DATE, display="Deactivation Date"),
        },
        entities=[
            RecordEntityMapping(
                entity_type="provider",
                id_field="NPI",
                property_fields={"npi": "NPI", "enumeration_date": "Provider Enumeration Date"},
            ),
        ],
    )


def test_mmddyyyy_normalized_to_iso() -> None:
    feed = _nppes_feed()
    coerced = coerce_row(
        {"NPI": "1234567890", "Provider Enumeration Date": "05/23/2005", "NPI Deactivation Date": ""},
        feed.record_schema,
    )
    assert coerced["Provider Enumeration Date"] == "2005-05-23"
    # Empty optional date dropped (covered by the prior fix).
    assert "NPI Deactivation Date" not in coerced


def test_single_digit_month_day() -> None:
    feed = _nppes_feed()
    coerced = coerce_row(
        {"NPI": "1234567890", "Provider Enumeration Date": "5/3/2005"},
        feed.record_schema,
    )
    assert coerced["Provider Enumeration Date"] == "2005-05-03"


def test_invalid_mmddyyyy_raises() -> None:
    feed = _nppes_feed()
    with pytest.raises(RecordValidationError):
        coerce_row(
            {"NPI": "1234567890", "Provider Enumeration Date": "13/45/2005"},  # bad month + day
            feed.record_schema,
        )


def test_validate_rows_accepts_real_nppes_row() -> None:
    feed = _nppes_feed()
    rows: list[dict[str, object]] = [
        {
            "NPI": "1679576722",
            "Provider Enumeration Date": "05/23/2005",
            "NPI Deactivation Date": "",
        },
    ]
    # Must not raise.
    result = validate_rows(feed, rows)
    assert result[0]["Provider Enumeration Date"] == "2005-05-23"
    assert "NPI Deactivation Date" not in result[0]


def test_existing_yyyymmdd_still_works() -> None:
    feed = _nppes_feed()
    coerced = coerce_row(
        {"NPI": "1234567890", "Provider Enumeration Date": "20050523"},
        feed.record_schema,
    )
    assert coerced["Provider Enumeration Date"] == "2005-05-23"


def test_already_iso_passes_through() -> None:
    feed = _nppes_feed()
    coerced = coerce_row(
        {"NPI": "1234567890", "Provider Enumeration Date": "2005-05-23"},
        feed.record_schema,
    )
    assert coerced["Provider Enumeration Date"] == "2005-05-23"
