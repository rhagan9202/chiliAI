"""Adapter-level protocol for scorecard run persistence backends."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from scorecards.models import ScorecardRun, ScorecardRunStatus


@runtime_checkable
class ScorecardRunRepository(Protocol):
    """Persist and query durable scorecard runs scoped by knowledge base."""

    def upsert(self, run: ScorecardRun) -> ScorecardRun:
        """Insert a run, or return the existing run with the same natural key."""
        ...

    def get(self, *, knowledge_base_id: str, run_id: str) -> ScorecardRun | None:
        """Return one run by id within a KB scope, or ``None`` if absent."""
        ...

    def list(
        self,
        *,
        knowledge_base_id: str,
        limit: int,
        offset: int,
        template_id: str | None = None,
        status: ScorecardRunStatus | None = None,
    ) -> tuple[list[ScorecardRun], int]:
        """Return a page of runs (newest first) plus the total match count."""
        ...

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        """Delete all runs for a knowledge base; return the count removed."""
        ...


__all__ = ["ScorecardRunRepository"]
