"""Tests for record source adapters."""

from __future__ import annotations

import pytest

from records.adapters.sources.api_push_source import ApiPushSource
from records.adapters.sources.file_source import CsvFileSource, JsonlFileSource
from records.exceptions import RecordValidationError


def test_csv_source_parses_rows() -> None:
    raw = b"claim_id,amount\nc1,10\nc2,20\n"
    rows = CsvFileSource().read_rows(raw)
    assert rows == [
        {"claim_id": "c1", "amount": "10"},
        {"claim_id": "c2", "amount": "20"},
    ]


def test_csv_source_rejects_empty_content() -> None:
    with pytest.raises(RecordValidationError):
        CsvFileSource().read_rows(b"")


def test_jsonl_source_parses_one_object_per_line() -> None:
    raw = b'{"claim_id": "c1", "amount": 10}\n{"claim_id": "c2", "amount": 20}\n'
    rows = JsonlFileSource().read_rows(raw)
    assert rows == [
        {"claim_id": "c1", "amount": 10},
        {"claim_id": "c2", "amount": 20},
    ]


def test_jsonl_source_rejects_non_object_line() -> None:
    with pytest.raises(RecordValidationError):
        JsonlFileSource().read_rows(b'[1, 2, 3]\n')


def test_api_push_source_parses_a_json_array() -> None:
    raw = b'[{"claim_id": "c1"}, {"claim_id": "c2"}]'
    rows = ApiPushSource().read_rows(raw)
    assert rows == [{"claim_id": "c1"}, {"claim_id": "c2"}]


def test_api_push_source_rejects_a_bare_object() -> None:
    with pytest.raises(RecordValidationError):
        ApiPushSource().read_rows(b'{"claim_id": "c1"}')


def test_csv_source_omits_missing_columns_in_short_rows() -> None:
    # The second data row has only one value; the "amount" column must be absent,
    # not present as the string "None".
    raw = b"claim_id,amount\nc1,10\nc2\n"
    rows = CsvFileSource().read_rows(raw)
    assert rows[0] == {"claim_id": "c1", "amount": "10"}
    assert rows[1] == {"claim_id": "c2"}
    assert "amount" not in rows[1]


def test_csv_source_rejects_non_utf8_bytes() -> None:
    with pytest.raises(RecordValidationError):
        CsvFileSource().read_rows(b"\xff\xfe\x00bad")


def test_jsonl_source_rejects_non_utf8_bytes() -> None:
    with pytest.raises(RecordValidationError):
        JsonlFileSource().read_rows(b"\xff\xfe\x00bad")


def test_api_push_source_rejects_non_utf8_bytes() -> None:
    with pytest.raises(RecordValidationError):
        ApiPushSource().read_rows(b"\xff\xfe\x00bad")
