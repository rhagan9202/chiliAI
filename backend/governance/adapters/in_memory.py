"""In-memory governance evaluation repository."""

from __future__ import annotations

from governance.models import GovernanceEvalRun, GovernanceEvalRunPage

__all__ = ["InMemoryGovernanceEvalRepository"]


class InMemoryGovernanceEvalRepository:
    """Store governance evaluation runs for tests and local development."""

    def __init__(self, runs: list[GovernanceEvalRun] | None = None) -> None:
        self._runs = {run.run_id: run for run in runs or []}

    def save_eval_run(self, run: GovernanceEvalRun) -> GovernanceEvalRun:
        if run.run_id in self._runs:
            raise ValueError(f"Governance eval run '{run.run_id}' already exists.")
        self._runs[run.run_id] = run
        return run

    def update_eval_run(self, run: GovernanceEvalRun) -> GovernanceEvalRun:
        if run.run_id not in self._runs:
            raise KeyError(run.run_id)
        self._runs[run.run_id] = run
        return run

    def get_eval_run(self, run_id: str) -> GovernanceEvalRun | None:
        return self._runs.get(run_id)

    def list_eval_runs(
        self,
        *,
        knowledge_base_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> GovernanceEvalRunPage:
        if limit < 1:
            raise ValueError("limit must be positive.")
        if offset < 0:
            raise ValueError("offset must be non-negative.")
        items = sorted(
            (
                run
                for run in self._runs.values()
                if knowledge_base_id is None or run.knowledge_base_id == knowledge_base_id
            ),
            key=lambda run: (run.created_at, run.run_id),
        )
        return GovernanceEvalRunPage(
            items=items[offset : offset + limit],
            total_items=len(items),
            limit=limit,
            offset=offset,
        )
