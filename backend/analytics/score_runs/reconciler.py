"""Stale score-run reconciliation.

The executor advances a run by enqueueing its own successor, one batch at a
time. That makes retry and cancellation granular, but it means a single lost
event stalls the run silently: no error, no terminal state, just a run that
stays `running` forever. This is the backstop.

Mirrors ``WorkflowEventTracker.reconcile_stale_runs`` and is driven from the
same periodic tick in ``run_worker``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from analytics.score_runs.models import ScoreRunStatus
from analytics.score_runs.protocols import ScoreRunRepositoryProtocol
from shared.utils import utc_now

__all__ = ["ScoreRunReconciler"]

logger = logging.getLogger(__name__)

_STALE_CANDIDATE_STATUSES: tuple[ScoreRunStatus, ...] = ("queued", "running")
_STALE_REASON = "stale_score_run_reconciled"


class ScoreRunReconciler:
    """Fail score runs that have stopped making progress."""

    def __init__(
        self,
        repository: ScoreRunRepositoryProtocol,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._repository = repository
        self._clock = clock

    def reconcile_stale_runs(
        self, *, max_age_seconds: int, batch_size: int = 1000
    ) -> int:
        """Mark runs failed when they have not progressed since the cutoff.

        Only `queued` and `running` are candidates — a terminal run is never
        touched, and reaching a terminal state is what makes a run immune.
        Returns the number of runs reconciled.
        """

        if max_age_seconds <= 0:
            raise ValueError("max_age_seconds must be greater than 0.")
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than 0.")

        now = self._clock()
        cutoff = now - timedelta(seconds=max_age_seconds)
        candidates = self._repository.list_stale_runs(
            statuses=_STALE_CANDIDATE_STATUSES,
            updated_before=cutoff,
            limit=batch_size,
        )

        reconciled = 0
        for run in candidates:
            # Re-read: a batch may have landed between the scan and here, in
            # which case the run is progressing and must be left alone.
            current = self._repository.get_run(run.id)
            if current is None or current.status not in _STALE_CANDIDATE_STATUSES:
                continue
            if current.updated_at >= cutoff:
                continue
            self._repository.update_run(
                current.id,
                status="failed",
                error_summary=_STALE_REASON,
                finished_at=now,
                updated_at=now,
            )
            logger.warning(
                "Reconciled stale score run id=%s kb=%s last_update=%s",
                current.id,
                current.knowledge_base_id,
                current.updated_at.isoformat(),
            )
            reconciled += 1
        return reconciled
