"""Models for the knowledgebases module."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from shared.utils import utc_now

__all__ = ["MAX_DOCUMENT_WARNING_REASONS", "DocumentRecord"]

# Bounded sample of human-readable warning reasons kept per document; counts
# are exact, reasons are a sample (mirrors the extraction-warning event cap).
MAX_DOCUMENT_WARNING_REASONS = 10


class DocumentRecord(BaseModel):
    """Metadata recorded for a registered document inside a knowledge base."""

    id: str
    knowledge_base_id: str
    filename: str
    content_type: str | None = None
    size_bytes: int | None = None
    status: str = "registered"
    storage_key: str | None = None
    content_hash: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    # Ingestion diagnostics: parse + extraction/validation warnings accumulated
    # by the worker so the UI can explain degraded or empty ingestion results.
    #
    # `stage_warning_counts` / `stage_warning_reasons` are the source of
    # truth, keyed by pipeline stage (e.g. "parse", "extract"): each stage's
    # entry is set *absolutely* by `set_stage_document_warnings` (see
    # `knowledgebases.protocols.KnowledgeBaseRepository`), so replaying a
    # stage's handler converges instead of accumulating, while a different
    # stage's entry is never touched. `warning_count` / `warning_reasons` are
    # maintained alongside them on every stage write -- the document-level
    # total (sum across stages) and a capped reasons sample (stage insertion
    # order) -- so existing readers (API `DocumentSummary`, the object-store
    # snapshot's on-disk schema) see the same shape as before.
    #
    # A document persisted before this per-stage ledger existed carries a
    # non-zero `warning_count`/`warning_reasons` with empty stage dicts. The
    # old flat total was itself the sum of both stages under the prior
    # additive scheme, so there is no way to recover which portion belonged
    # to which stage. The first stage write after that discards the old flat
    # total rather than folding it in (see
    # `_helpers.build_stage_document_warning_updates`): folding would
    # double-count every stage that goes on to rewrite, and never converge.
    # This transiently under-reports until every stage has rewritten once,
    # but it can never inflate -- the safer failure direction for an
    # advisory count.
    warning_count: int = Field(default=0, ge=0)
    warning_reasons: list[str] = Field(default_factory=list)
    stage_warning_counts: dict[str, int] = Field(default_factory=dict)
    stage_warning_reasons: dict[str, list[str]] = Field(default_factory=dict)
