"""Api-push record source: a JSON array of record objects."""

from __future__ import annotations

import json
from typing import cast

from records.exceptions import RecordValidationError

__all__ = ["ApiPushSource"]


class ApiPushSource:
    """Parse an api-push request body (a JSON array) into record rows."""

    def read_rows(self, raw: bytes) -> list[dict[str, object]]:
        try:
            decoded = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RecordValidationError("Api-push payload is not valid UTF-8.") from exc
        try:
            parsed = json.loads(decoded)
        except json.JSONDecodeError as exc:
            raise RecordValidationError("Api-push payload is not valid JSON.") from exc
        if not isinstance(parsed, list):
            raise RecordValidationError("Api-push payload must be a JSON array of objects.")
        items = cast(list[object], parsed)
        rows: list[dict[str, object]] = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise RecordValidationError(
                    f"Api-push payload item {index} is not a JSON object."
                )
            row = cast(dict[str, object], item)
            rows.append({str(key): value for key, value in row.items()})
        if not rows:
            raise RecordValidationError("Api-push payload contains no records.")
        return rows
