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

# Which embedding stream a vector belongs to. RAG retrieval filters on this, so
# a vector indexed without it is invisible to every query — which is exactly
# what happened: the document indexing path stamped it as a bare literal, the
# records path did not stamp it at all, and the retriever filtered on a third
# bare literal. Records were unretrievable from the day they were first indexed.
EMBEDDING_CHANNEL_KEY: Final = "embedding_channel"


# --- source_kind values ----------------------------------------------------

SOURCE_KIND_RECORD: Final = "record"
SOURCE_KIND_DOCUMENT: Final = "document"


# --- embedding_channel values ----------------------------------------------

# Natural-language content, and the only channel RAG retrieval reads.
EMBEDDING_CHANNEL_TEXT: Final = "text"
# Structural/graph embeddings, indexed into their own namespace.
EMBEDDING_CHANNEL_GRAPH: Final = "graph"


__all__ = [
    "EMBEDDING_CHANNEL_GRAPH",
    "EMBEDDING_CHANNEL_KEY",
    "EMBEDDING_CHANNEL_TEXT",
    "SOURCE_KIND_KEY",
    "SOURCE_FEED_KEY",
    "SOURCE_RAW_RECORD_ID_KEY",
    "SOURCE_DOCUMENT_ID_KEY",
    "SOURCE_CHUNK_ID_KEY",
    "SOURCE_ID_KEY",
    "SOURCE_KIND_RECORD",
    "SOURCE_KIND_DOCUMENT",
]
