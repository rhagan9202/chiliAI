"""Shared internal helpers for knowledgebases adapters."""

from __future__ import annotations

from shared.types import KnowledgeBase
from shared.utils import utc_now

__all__ = ["build_knowledge_base_summary_updates"]


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
