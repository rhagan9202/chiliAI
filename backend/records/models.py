"""Internal domain models for structured-record ingestion."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from shared.utils import utc_now


def content_hash_for(payload: Mapping[str, object]) -> str:
    """Return a stable SHA-256 hex digest of a record payload.

    The payload is serialized with sorted keys so logically equal rows hash
    identically regardless of field order — this digest backs the
    ``raw_records`` idempotency check.
    """

    canonical = json.dumps(
        dict(payload), sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def submission_hash_for(feed_name: str, content_hashes: list[str]) -> str:
    """Return a stable SHA-256 digest identifying a whole submission.

    The digest is computed over the feed name and the *sorted* list of per-row
    ``content_hash`` values, so a re-pushed identical batch hashes identically
    regardless of row order — this backs the submission-level idempotency check.
    """

    canonical = json.dumps(
        {"feed": feed_name, "rows": sorted(content_hashes)},
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class RawRecord(BaseModel):
    """A canonical row landed in the ``raw_records`` table."""

    knowledge_base_id: str
    record_type: str
    record_id: str
    payload: dict[str, object] = Field(default_factory=dict)
    source_type: Literal["file_upload", "api_push"]
    source_ref: str | None = None
    correlation_id: str
    content_hash: str
    ingested_at: datetime = Field(default_factory=utc_now)


class RejectedRow(BaseModel):
    """A submitted row that failed coercion or feed-schema validation."""

    index: int
    reason: str


class RecordBatch(BaseModel):
    """A batch of raw records produced by one feed submission."""

    knowledge_base_id: str
    feed_name: str
    record_type: str
    correlation_id: str
    records: list[RawRecord] = Field(default_factory=lambda: [])


__all__ = [
    "RawRecord",
    "RecordBatch",
    "RejectedRow",
    "content_hash_for",
    "submission_hash_for",
]
