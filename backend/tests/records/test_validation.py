"""Tests for record row coercion and feed-schema validation."""

from __future__ import annotations

import pytest

from config.schema import RecordFeedConfig
from records.exceptions import RecordValidationError
from records.models import RejectedRow
from records.validation import coerce_row, validate_rows, validate_rows_partition
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


def test_validate_rows_partition_returns_only_valid_rows() -> None:
    ok, rejected = validate_rows_partition(_feed(), [{"claim_id": "c1", "amount": "10"}])
    assert ok == [{"claim_id": "c1", "amount": 10.0}]
    assert rejected == []


def test_validate_rows_partition_splits_valid_and_invalid_rows() -> None:
    ok, rejected = validate_rows_partition(
        _feed(),
        [
            {"claim_id": "c1", "amount": "10"},
            {"claim_id": "c2", "amount": "not-a-number"},
            {"claim_id": "c3"},  # missing required amount
            {"claim_id": "c4", "amount": "40"},
        ],
    )
    assert ok == [
        {"claim_id": "c1", "amount": 10.0},
        {"claim_id": "c4", "amount": 40.0},
    ]
    assert [r.index for r in rejected] == [1, 2]
    assert all(isinstance(r, RejectedRow) for r in rejected)
    assert "not a valid number" in rejected[0].reason


def test_validate_rows_partition_does_not_raise_on_all_invalid() -> None:
    ok, rejected = validate_rows_partition(_feed(), [{"claim_id": "c1"}])
    assert ok == []
    assert len(rejected) == 1
    assert rejected[0].index == 0


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


def test_validate_rows_reports_coercion_error_with_row_index() -> None:
    """A coercion failure is folded into the batched 'row N' error format."""

    with pytest.raises(RecordValidationError, match="row 1") as exc_info:
        validate_rows(
            _feed(),
            [
                {"claim_id": "c1", "amount": "10"},
                {"claim_id": "c2", "amount": "not-a-number"},
            ],
        )
    message = str(exc_info.value)
    assert "Feed 'claims_feed' validation failed" in message
    assert "not a valid number" in message


# ---------------------------------------------------------------------------
# YYYYMMDD date coercion
# ---------------------------------------------------------------------------


def _feed_with_date() -> RecordFeedConfig:
    return RecordFeedConfig(
        name="date_feed",
        record_type="date_record",
        source="file_upload",
        id_field="rec_id",
        record_schema={
            "rec_id": PropertyDefinition(
                type=PropertyType.STRING, display="ID", required=True
            ),
            "svc_dt": PropertyDefinition(type=PropertyType.DATE, display="Date"),
        },
    )


@pytest.mark.parametrize("raw,expected_iso", [
    ("20080103", "2008-01-03"),
    ("20231225", "2023-12-25"),
    ("20000101", "2000-01-01"),
])
def test_coerce_row_converts_yyyymmdd_to_iso(raw: str, expected_iso: str) -> None:
    schema = _feed_with_date().record_schema
    coerced = coerce_row({"rec_id": "r1", "svc_dt": raw}, schema)
    assert coerced["svc_dt"] == expected_iso


def test_validate_rows_accepts_yyyymmdd_date() -> None:
    rows = validate_rows(_feed_with_date(), [{"rec_id": "r1", "svc_dt": "20080103"}])
    assert rows[0]["svc_dt"] == "2008-01-03"


def test_validate_rows_accepts_iso_date_unchanged() -> None:
    rows = validate_rows(_feed_with_date(), [{"rec_id": "r1", "svc_dt": "2008-01-03"}])
    assert rows[0]["svc_dt"] == "2008-01-03"


# ---------------------------------------------------------------------------
# allow_extra_fields
# ---------------------------------------------------------------------------


def _feed_allow_extra() -> RecordFeedConfig:
    return RecordFeedConfig(
        name="wide_feed",
        record_type="wide_record",
        source="file_upload",
        id_field="rec_id",
        allow_extra_fields=True,
        record_schema={
            "rec_id": PropertyDefinition(
                type=PropertyType.STRING, display="ID", required=True
            ),
            "amount": PropertyDefinition(
                type=PropertyType.DECIMAL, display="Amount", required=True, min_value=0
            ),
        },
    )


def test_validate_rows_allows_extra_fields_when_configured() -> None:
    """Extra columns pass through to the payload without triggering validation errors."""
    rows = validate_rows(
        _feed_allow_extra(),
        [{"rec_id": "r1", "amount": "50.0", "col_a": "x", "col_b": "y"}],
    )
    assert rows == [{"rec_id": "r1", "amount": 50.0, "col_a": "x", "col_b": "y"}]


def test_validate_rows_still_enforces_required_when_allow_extra_fields() -> None:
    """Required-field enforcement still applies when allow_extra_fields is True."""
    with pytest.raises(RecordValidationError, match="Missing required"):
        validate_rows(
            _feed_allow_extra(),
            [{"rec_id": "r1", "col_a": "x"}],  # missing required 'amount'
        )


def test_validate_rows_still_rejects_unknown_field_by_default() -> None:
    """Without allow_extra_fields, unknown columns still raise an error."""
    with pytest.raises(RecordValidationError, match="Unexpected"):
        validate_rows(_feed(), [{"claim_id": "c1", "amount": 10, "extra": "x"}])
