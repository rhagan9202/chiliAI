"""File-upload record sources: delimited CSV and line-delimited JSON."""

from __future__ import annotations

import csv
import io
import json
from typing import cast

from records.exceptions import RecordValidationError

__all__ = ["CsvFileSource", "JsonlFileSource"]


class CsvFileSource:
    """Parse a CSV upload into one row dict per record.

    Present cell values are kept as plain strings.  Columns whose value is
    ``None`` (i.e. the row is shorter than the header) are omitted from the
    row dict entirely so that downstream validation sees the key as absent.
    """

    def read_rows(self, raw: bytes) -> list[dict[str, object]]:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise RecordValidationError("CSV upload is not valid UTF-8.") from exc
        if text.strip() == "":
            raise RecordValidationError("CSV upload is empty.")
        reader = csv.DictReader(io.StringIO(text))
        rows: list[dict[str, object]] = []
        for line in reader:
            row: dict[str, object] = {}
            for key, value in line.items():
                # Skip the sentinel key csv.DictReader uses for overflow values.
                if key is None:
                    continue
                # Skip columns whose value is None — the data row was shorter
                # than the header; omitting the key lets validators detect it.
                if value is None:
                    continue
                row[str(key)] = str(value)
            rows.append(row)
        if not rows:
            raise RecordValidationError("CSV upload has a header but no data rows.")
        return rows


class JsonlFileSource:
    """Parse a JSON-Lines upload into one row dict per non-blank line."""

    def read_rows(self, raw: bytes) -> list[dict[str, object]]:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RecordValidationError("JSONL upload is not valid UTF-8.") from exc
        rows: list[dict[str, object]] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if line.strip() == "":
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RecordValidationError(
                    f"JSONL line {line_number} is not valid JSON."
                ) from exc
            if not isinstance(parsed, dict):
                raise RecordValidationError(
                    f"JSONL line {line_number} is not a JSON object."
                )
            row = cast(dict[str, object], parsed)
            rows.append({str(key): value for key, value in row.items()})
        if not rows:
            raise RecordValidationError("JSONL upload has no record lines.")
        return rows
