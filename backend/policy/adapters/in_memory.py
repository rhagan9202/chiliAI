"""In-memory policy item repository for tests and local development."""

from __future__ import annotations

from collections.abc import Sequence

from policy.exceptions import PolicyItemNotFoundError
from policy.models import PolicyItem

__all__ = ["InMemoryPolicyItemRepository"]

# Natural identity: (knowledge_base_id, rule_id, target_ref).
_Key = tuple[str, str, str]


def _key(item: PolicyItem) -> _Key:
    return (item.knowledge_base_id, item.rule_id, item.target_ref)


class InMemoryPolicyItemRepository:
    """A dict-backed ``PolicyItemRepository`` keyed by the natural identity."""

    def __init__(self) -> None:
        self._items: dict[_Key, PolicyItem] = {}

    def upsert(self, item: PolicyItem) -> PolicyItem:
        key = _key(item)
        existing = self._items.get(key)
        if existing is None:
            self._items[key] = item
            return item
        if existing.status != "open":
            # Disposed items are never reopened by re-evaluation.
            return existing
        refreshed = existing.model_copy(
            update={
                "title": item.title,
                "severity": item.severity,
                "matched_fields": item.matched_fields,
                "citations": item.citations,
                "updated_at": item.updated_at,
            }
        )
        self._items[key] = refreshed
        return refreshed

    def get(self, *, knowledge_base_id: str, item_id: str) -> PolicyItem | None:
        for item in self._items.values():
            if item.knowledge_base_id == knowledge_base_id and item.id == item_id:
                return item
        return None

    def list(
        self,
        *,
        knowledge_base_id: str,
        limit: int,
        offset: int,
        statuses: Sequence[str] | None = None,
        query: str | None = None,
    ) -> tuple[list[PolicyItem], int]:
        wanted = frozenset(statuses or ())
        needle = (query or "").strip().lower()
        matches = [
            item
            for item in self._items.values()
            if item.knowledge_base_id == knowledge_base_id
            and (not wanted or item.status in wanted)
            and (not needle or needle in item.title.lower())
        ]
        matches.sort(key=lambda item: (item.updated_at, item.id), reverse=True)
        total = len(matches)
        if limit <= 0 or offset < 0:
            return [], total
        return matches[offset : offset + limit], total

    def count_by_status(self, knowledge_base_id: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self._items.values():
            if item.knowledge_base_id != knowledge_base_id:
                continue
            counts[item.status] = counts.get(item.status, 0) + 1
        return counts

    def update(self, item: PolicyItem) -> PolicyItem:
        key = _key(item)
        if key not in self._items:
            raise PolicyItemNotFoundError(item.knowledge_base_id, item.id)
        self._items[key] = item
        return item

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        keys = [key for key in self._items if key[0] == knowledge_base_id]
        for key in keys:
            del self._items[key]
        return len(keys)
