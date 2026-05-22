"""Canonical metadata keys + values for provenance on entities, relationships, and vector points.

Every write site that stamps provenance, and every read site that filters or
deletes by provenance, must reference these constants — never bare string
literals — so that a typo at one site cannot silently desynchronize from
another.
"""

from __future__ import annotations

from typing import Final


# --- Metadata keys ---------------------------------------------------------

SOURCE_KIND_KEY: Final = "source_kind"
SOURCE_FEED_KEY: Final = "source_feed"
SOURCE_RAW_RECORD_ID_KEY: Final = "source_raw_record_id"
SOURCE_DOCUMENT_ID_KEY: Final = "source_document_id"
SOURCE_CHUNK_ID_KEY: Final = "source_chunk_id"
SOURCE_ID_KEY: Final = "source_id"


# --- source_kind values ----------------------------------------------------

SOURCE_KIND_RECORD: Final = "record"
SOURCE_KIND_DOCUMENT: Final = "document"


__all__ = [
    "SOURCE_KIND_KEY",
    "SOURCE_FEED_KEY",
    "SOURCE_RAW_RECORD_ID_KEY",
    "SOURCE_DOCUMENT_ID_KEY",
    "SOURCE_CHUNK_ID_KEY",
    "SOURCE_ID_KEY",
    "SOURCE_KIND_RECORD",
    "SOURCE_KIND_DOCUMENT",
]
