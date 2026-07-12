"""In-memory scorecard run repository for tests and local development."""

from __future__ import annotations

from scorecards.models import ScorecardRun, ScorecardRunStatus

__all__ = ["InMemoryScorecardRunRepository"]

_Key = tuple[str, str, str, str, object, object, str]


def _key(run: ScorecardRun) -> _Key:
    return (
        run.knowledge_base_id,
        run.template_id,
        run.scope_type,
        run.scope_id,
        run.period_start,
        run.period_end,
        run.source_snapshot_hash,
    )


class InMemoryScorecardRunRepository:
    """A dict-backed repository keyed by the scorecard run natural identity."""

    def __init__(self) -> None:
        self._runs: dict[_Key, ScorecardRun] = {}

    def upsert(self, run: ScorecardRun) -> ScorecardRun:
        key = _key(run)
        existing = self._runs.get(key)
        if existing is not None:
            return existing
        self._runs[key] = run
        return run

    def get(self, *, knowledge_base_id: str, run_id: str) -> ScorecardRun | None:
        for run in self._runs.values():
            if run.knowledge_base_id == knowledge_base_id and run.id == run_id:
                return run
        return None

    def list(
        self,
        *,
        knowledge_base_id: str,
        limit: int,
        offset: int,
        template_id: str | None = None,
        status: ScorecardRunStatus | None = None,
    ) -> tuple[list[ScorecardRun], int]:
        matches = [
            run
            for run in self._runs.values()
            if run.knowledge_base_id == knowledge_base_id
            and (template_id is None or run.template_id == template_id)
            and (status is None or run.status == status)
        ]
        matches.sort(key=lambda run: (run.created_at, run.id), reverse=True)
        total = len(matches)
        if limit <= 0 or offset < 0:
            return [], total
        return matches[offset : offset + limit], total

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        keys = [key for key in self._runs if key[0] == knowledge_base_id]
        for key in keys:
            del self._runs[key]
        return len(keys)
