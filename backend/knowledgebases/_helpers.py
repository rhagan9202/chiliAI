"""Shared internal helpers for knowledgebases adapters."""

from __future__ import annotations

from knowledgebases.models import MAX_DOCUMENT_WARNING_REASONS, DocumentRecord
from shared.types import KnowledgeBase
from shared.utils import utc_now

__all__ = [
    "build_knowledge_base_summary_updates",
    "build_stage_document_warning_updates",
]


def build_knowledge_base_summary_updates(
    knowledge_base: KnowledgeBase,
    *,
    status: str | None,
    entity_count: int | None,
    relationship_count: int | None,
) -> dict[str, object]:
    updates: dict[str, object] = {}
    if status is not None and knowledge_base.status != status:
        updates["status"] = status
    if entity_count is not None and knowledge_base.entity_count != entity_count:
        updates["entity_count"] = entity_count
    if (
        relationship_count is not None
        and knowledge_base.relationship_count != relationship_count
    ):
        updates["relationship_count"] = relationship_count
    if updates:
        updates["updated_at"] = utc_now()
    return updates


def build_stage_document_warning_updates(
    document: DocumentRecord,
    *,
    stage: str,
    count: int,
    reasons: list[str],
) -> dict[str, object]:
    """Fold one pipeline stage's absolute warning contribution into a
    document's per-stage ledger, and recompute the document-level total and
    sampled reasons from every stage's contribution.

    Absolute per (document, stage) rather than additive overall: replaying
    the handler that owns ``stage`` (a retry, or an at-least-once
    redelivery) converges to the same value instead of accumulating, while a
    different stage's contribution is never overwritten.

    A document written under the pre-2026-36 flat-total scheme -- a
    non-zero ``warning_count`` but no per-stage ledger yet -- is migrated in
    place the first time any stage writes: its prior total is folded in as a
    synthetic ``"legacy"`` stage entry so that earlier contribution survives
    instead of being silently dropped. This only fires once per document,
    since after the first stage write ``stage_warning_counts`` is no longer
    empty.

    Shared by both adapters (`in_memory.py`, `object_store.py`) so the guard
    order, the reasons cap, and this fold/derive math cannot diverge between
    them -- that divergence is the defect class this fix exists to close.
    """
    stage_counts = dict(document.stage_warning_counts)
    stage_reasons = dict(document.stage_warning_reasons)
    if not stage_counts and document.warning_count:
        stage_counts["legacy"] = document.warning_count
        stage_reasons["legacy"] = list(document.warning_reasons)

    stage_counts[stage] = count
    stage_reasons[stage] = reasons[:MAX_DOCUMENT_WARNING_REASONS]

    combined_reasons: list[str] = []
    for sample in stage_reasons.values():
        combined_reasons.extend(sample)

    return {
        "stage_warning_counts": stage_counts,
        "stage_warning_reasons": stage_reasons,
        "warning_count": sum(stage_counts.values()),
        "warning_reasons": combined_reasons[:MAX_DOCUMENT_WARNING_REASONS],
    }
