"""Storage-layer models."""

from __future__ import annotations

from shared.protocols import StoredObject, StoredObjectWriteResult

# TODO(production): Add created_at/updated_at timestamps, etag/version_id for
# optimistic concurrency, and checksum: str | None for integrity verification.
# Add ListObjectsResult model for paginated listing with cursor support.


__all__ = [
    "StoredObject",
    "StoredObjectWriteResult",
]