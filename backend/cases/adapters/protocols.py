"""Adapter-level protocol for case persistence backends."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from cases.models import Case


@runtime_checkable
class CaseRepository(Protocol):
    """Persist and query investigation cases, scoped by knowledge base."""

    def create(self, case: Case) -> Case:
        """Insert a new case idempotently and return it."""
        ...

    def get(self, *, knowledge_base_id: str, case_id: str) -> Case | None:
        """Return one case within a KB scope, or ``None`` if absent."""
        ...

    def list(
        self,
        *,
        knowledge_base_id: str,
        limit: int,
        offset: int,
        status: str | None = None,
        priority: str | None = None,
    ) -> tuple[list[Case], int]:
        """Return a page of cases (newest first) plus the total match count."""
        ...

    def update(self, case: Case) -> Case:
        """Update an existing case; raise ``CaseNotFoundError`` if absent."""
        ...

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        """Delete all cases for a knowledge base; return the count removed."""
        ...


__all__ = ["CaseRepository"]
