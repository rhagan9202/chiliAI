"""File-upload record sources: delimited CSV and line-delimited JSON."""

from __future__ import annotations

import csv
import io
import json
from typing import cast

from records.exceptions import RecordValidationError

__all__ = ["CsvFileSource", "JsonlFileSource"]


class CsvFileSource:
    """Parse a CSV upload into one row dict per record (all values are strings)."""

    def read_rows(self, raw: bytes) -> list[dict[str, object]]:
        text = raw.decode("utf-8-sig")
        if text.strip() == "":
            raise RecordValidationError("CSV upload is empty.")
        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames is None:
            raise RecordValidationError("CSV upload has no header row.")
        rows: list[dict[str, object]] = []
        for line in reader:
            row: dict[str, object] = {
                key: str(value)
                for key, value in line.items()
                if key is not None
            }
            rows.append(row)
        if not rows:
            raise RecordValidationError("CSV upload has a header but no data rows.")
        return rows


class JsonlFileSource:
    """Parse a JSON-Lines upload into one row dict per non-blank line."""

    def read_rows(self, raw: bytes) -> list[dict[str, object]]:
        text = raw.decode("utf-8")
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
