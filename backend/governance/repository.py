"""Repository protocols for SAFE-CMS-020 governance evaluations."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from governance.models import GovernanceEvalRun, GovernanceEvalRunPage

__all__ = ["GovernanceEvalRepository"]


@runtime_checkable
class GovernanceEvalRepository(Protocol):
    """Store persisted governance evaluation runs and approval decisions."""

    def save_eval_run(self, run: GovernanceEvalRun) -> GovernanceEvalRun:
        """Persist a new evaluation run."""
        ...

    def update_eval_run(self, run: GovernanceEvalRun) -> GovernanceEvalRun:
        """Replace an existing evaluation run."""
        ...

    def get_eval_run(self, run_id: str) -> GovernanceEvalRun | None:
        """Return one evaluation run by id."""
        ...

    def list_eval_runs(
        self,
        *,
        knowledge_base_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> GovernanceEvalRunPage:
        """List evaluation runs, optionally filtered by knowledge base."""
        ...
