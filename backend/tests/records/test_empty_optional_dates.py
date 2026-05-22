"""Empty strings for optional typed fields are treated as absent.

CMS DE-SynPUF beneficiary summary files use empty strings (not nulls) to
represent living beneficiaries whose death date is not yet recorded.  Without
this fix, ``date.fromisoformat("")`` raises ``ValueError`` during validation.
"""

from __future__ import annotations

from config.schema import RecordEntityMapping, RecordFeedConfig
from records.validation import coerce_row, validate_rows
from shared.types import PropertyDefinition, PropertyType


def _feed_with_optional_dates() -> RecordFeedConfig:
    return RecordFeedConfig(
        name="beneficiary_test",
        record_type="beneficiary_record",
        source="file_upload",
        id_field="DESYNPUF_ID",
        record_schema={
            "DESYNPUF_ID": PropertyDefinition(
                type=PropertyType.STRING, display="ID", required=True
            ),
            "BENE_BIRTH_DT": PropertyDefinition(
                type=PropertyType.DATE, display="Birth Date"
            ),
            "BENE_DEATH_DT": PropertyDefinition(
                type=PropertyType.DATE, display="Death Date"
            ),
        },
        entities=[
            RecordEntityMapping(
                entity_type="beneficiary",
                id_field="DESYNPUF_ID",
                property_fields={"hic_number": "DESYNPUF_ID"},
            ),
        ],
    )


def test_empty_optional_date_dropped_from_coerced_row() -> None:
    feed = _feed_with_optional_dates()
    row: dict[str, object] = {
        "DESYNPUF_ID": "B0001",
        "BENE_BIRTH_DT": "19400101",
        "BENE_DEATH_DT": "",
    }
    coerced = coerce_row(row, feed.record_schema)
    # Required ID stays; populated optional date stays; empty optional date is gone.
    assert coerced["DESYNPUF_ID"] == "B0001"
    assert coerced["BENE_BIRTH_DT"] == "1940-01-01"
    assert "BENE_DEATH_DT" not in coerced


def test_validate_rows_passes_when_optional_date_is_empty() -> None:
    feed = _feed_with_optional_dates()
    rows: list[dict[str, object]] = [
        {"DESYNPUF_ID": "B0001", "BENE_BIRTH_DT": "19400101", "BENE_DEATH_DT": ""},
    ]
    # Should not raise.
    result = validate_rows(feed, rows)
    assert result[0]["DESYNPUF_ID"] == "B0001"
    assert "BENE_DEATH_DT" not in result[0]


def test_validate_rows_passes_multiple_rows_with_mixed_death_dates() -> None:
    """Living and deceased beneficiaries in the same batch all pass."""
    feed = _feed_with_optional_dates()
    rows: list[dict[str, object]] = [
        {"DESYNPUF_ID": "B0001", "BENE_BIRTH_DT": "19400101", "BENE_DEATH_DT": ""},
        {"DESYNPUF_ID": "B0002", "BENE_BIRTH_DT": "19350615", "BENE_DEATH_DT": ""},
        {
            "DESYNPUF_ID": "B0003",
            "BENE_BIRTH_DT": "19290101",
            "BENE_DEATH_DT": "20100601",
        },
    ]
    result = validate_rows(feed, rows)
    assert len(result) == 3
    assert "BENE_DEATH_DT" not in result[0]
    assert "BENE_DEATH_DT" not in result[1]
    assert result[2]["BENE_DEATH_DT"] == "2010-06-01"


def test_empty_string_for_optional_decimal_is_dropped() -> None:
    """The same empty-string treatment applies to decimal optional fields."""
    feed = RecordFeedConfig(
        name="score_feed",
        record_type="score_record",
        source="file_upload",
        id_field="rec_id",
        record_schema={
            "rec_id": PropertyDefinition(
                type=PropertyType.STRING, display="ID", required=True
            ),
            "score": PropertyDefinition(
                type=PropertyType.DECIMAL, display="Score"
            ),
        },
    )
    row: dict[str, object] = {"rec_id": "r1", "score": ""}
    coerced = coerce_row(row, feed.record_schema)
    assert "score" not in coerced
    assert coerced["rec_id"] == "r1"


def test_empty_required_field_is_kept_in_coerced_row() -> None:
    """Empty strings on REQUIRED fields are NOT silently dropped by coerce_row.

    The empty string is preserved so the caller can see the field was present
    but blank.  The string validator does not treat "" as an error (that would
    require a pattern check), so validate_rows also passes here.  If callers
    need to reject blank required strings they should add a pattern constraint
    to the PropertyDefinition.
    """
    feed = RecordFeedConfig(
        name="req_feed",
        record_type="req_record",
        source="file_upload",
        id_field="rec_id",
        record_schema={
            "rec_id": PropertyDefinition(
                type=PropertyType.STRING, display="ID", required=True
            ),
        },
    )
    # coerce_row keeps the empty string because the field is required.
    row: dict[str, object] = {"rec_id": ""}
    coerced = coerce_row(row, feed.record_schema)
    assert coerced["rec_id"] == ""

    # validate_rows passes because the required string field is present (even if blank).
    rows: list[dict[str, object]] = [{"rec_id": ""}]
    result = validate_rows(feed, rows)
    assert result[0]["rec_id"] == ""
