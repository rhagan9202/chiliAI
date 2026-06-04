"""Adapter-level protocol for policy item persistence backends."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from policy.models import PolicyItem


@runtime_checkable
class PolicyItemRepository(Protocol):
    """Persist and query policy items, scoped by knowledge base.

    Identity is the natural key ``(knowledge_base_id, rule_id, target_ref)``.
    """

    def upsert(self, item: PolicyItem) -> PolicyItem:
        """Insert a new ``open`` item, refresh an existing ``open`` item in place,
        or leave an already-disposed item untouched. Return the stored item."""
        ...

    def get(self, *, knowledge_base_id: str, item_id: str) -> PolicyItem | None:
        """Return one item by its id within a KB scope, or ``None`` if absent."""
        ...

    def list(
        self,
        *,
        knowledge_base_id: str,
        limit: int,
        offset: int,
        status: str | None = None,
    ) -> tuple[list[PolicyItem], int]:
        """Return a page of items (newest first) plus the total match count."""
        ...

    def update(self, item: PolicyItem) -> PolicyItem:
        """Replace an existing item (matched by natural key); raise
        ``PolicyItemNotFoundError`` if absent. Used to record triage."""
        ...

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        """Delete all items for a knowledge base; return the count removed."""
        ...


__all__ = ["PolicyItemRepository"]
