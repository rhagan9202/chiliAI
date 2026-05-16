"""Tests for record row coercion and feed-schema validation."""

from __future__ import annotations

import pytest

from config.schema import RecordFeedConfig
from records.exceptions import RecordValidationError
from records.validation import coerce_row, validate_rows
from shared.types import PropertyDefinition, PropertyType


def _feed() -> RecordFeedConfig:
    return RecordFeedConfig(
        name="claims_feed",
        record_type="claim_record",
        source="file_upload",
        id_field="claim_id",
        record_schema={
            "claim_id": PropertyDefinition(
                type=PropertyType.STRING, display="Claim ID", required=True
            ),
            "amount": PropertyDefinition(
                type=PropertyType.DECIMAL, display="Amount", required=True, min_value=0
            ),
            "score": PropertyDefinition(type=PropertyType.DECIMAL, display="Score"),
        },
    )


def test_coerce_row_converts_string_numbers() -> None:
    schema = _feed().record_schema
    coerced = coerce_row({"claim_id": "c1", "amount": "12.5"}, schema)
    assert coerced["amount"] == 12.5
    assert coerced["claim_id"] == "c1"


def test_coerce_row_raises_on_non_numeric_string() -> None:
    schema = _feed().record_schema
    with pytest.raises(RecordValidationError):
        coerce_row({"claim_id": "c1", "amount": "not-a-number"}, schema)


def test_validate_rows_returns_coerced_rows() -> None:
    rows = validate_rows(_feed(), [{"claim_id": "c1", "amount": "10"}])
    assert rows == [{"claim_id": "c1", "amount": 10.0}]


def test_validate_rows_rejects_missing_required_field() -> None:
    with pytest.raises(RecordValidationError, match="row 0"):
        validate_rows(_feed(), [{"claim_id": "c1"}])


def test_validate_rows_rejects_unknown_field() -> None:
    with pytest.raises(RecordValidationError, match="Unexpected"):
        validate_rows(_feed(), [{"claim_id": "c1", "amount": 10, "extra": "x"}])


def _feed_with_int_bool() -> RecordFeedConfig:
    return RecordFeedConfig(
        name="typed_feed",
        record_type="typed_record",
        source="file_upload",
        id_field="rec_id",
        record_schema={
            "rec_id": PropertyDefinition(
                type=PropertyType.STRING, display="Record ID", required=True
            ),
            "count": PropertyDefinition(
                type=PropertyType.INTEGER, display="Count", required=True
            ),
            "active": PropertyDefinition(
                type=PropertyType.BOOLEAN, display="Active", required=True
            ),
        },
    )


def test_coerce_row_coerces_string_to_integer() -> None:
    schema = _feed_with_int_bool().record_schema
    coerced = coerce_row({"rec_id": "r1", "count": "42", "active": True}, schema)
    assert coerced["count"] == 42
    assert isinstance(coerced["count"], int)


def test_coerce_row_raises_on_non_integer_string() -> None:
    schema = _feed_with_int_bool().record_schema
    with pytest.raises(RecordValidationError, match="not a valid integer"):
        coerce_row({"rec_id": "r1", "count": "not-an-int", "active": True}, schema)


@pytest.mark.parametrize("token,expected", [
    ("true", True),
    ("True", True),
    ("TRUE", True),
    ("1", True),
    ("yes", True),
    ("YES", True),
    ("false", False),
    ("False", False),
    ("FALSE", False),
    ("0", False),
    ("no", False),
    ("NO", False),
])
def test_coerce_row_coerces_boolean_tokens(token: str, expected: bool) -> None:
    schema = _feed_with_int_bool().record_schema
    coerced = coerce_row({"rec_id": "r1", "count": 1, "active": token}, schema)
    assert coerced["active"] is expected


def test_coerce_row_raises_on_unrecognized_boolean_token() -> None:
    schema = _feed_with_int_bool().record_schema
    with pytest.raises(RecordValidationError, match="not a valid boolean"):
        coerce_row({"rec_id": "r1", "count": 1, "active": "maybe"}, schema)
