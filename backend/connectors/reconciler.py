"""Stale connector sync-run reconciliation.

The executor advances a run by enqueueing its own successor, one page at a
time. That makes retry and cancellation granular, but it means a single lost
event stalls the run silently: no error, no terminal state, just a run that
stays `running` forever. This is the backstop.

Mirrors ``ScoreRunReconciler`` and ``WorkflowEventTracker.reconcile_stale_runs``
and is driven from the same periodic tick in ``run_worker``. Three sweeps that
disagreed about what "stale" means would be worse than one.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from connectors.models import ConnectorSyncRunUpdate, ConnectorSyncStatus
from connectors.repository import ConnectorRepositoryProtocol
from shared.utils import utc_now

__all__ = ["ConnectorSyncReconciler"]

logger = logging.getLogger(__name__)

# `queued` counts as well as `running`: a kickoff event lost before the first
# page leaves a run that never moves at all, which is just as stuck as one that
# stalled mid-pull.
_STALE_CANDIDATE_STATUSES: tuple[ConnectorSyncStatus, ...] = ("queued", "running")
_STALE_REASON = "stale_connector_sync_reconciled"


class ConnectorSyncReconciler:
    """Fail connector sync runs that have stopped making progress."""

    def __init__(
        self,
        repository: ConnectorRepositoryProtocol,
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
            # Re-read: a page may have landed between the scan and here, in
            # which case the run is progressing and must be left alone. Failing
            # a run that was working is how operators learn to distrust the
            # reconciler that is right.
            current = self._repository.get_run(run.run_id)
            if current is None or current.status not in _STALE_CANDIDATE_STATUSES:
                continue
            if current.updated_at >= cutoff:
                continue
            self._repository.update_run(
                current.run_id,
                ConnectorSyncRunUpdate(status="failed", error_message=_STALE_REASON),
            )
            logger.warning(
                "Reconciled stale connector sync run run=%s connector=%s kb=%s "
                "last_update=%s",
                current.run_id,
                current.connector_id,
                current.knowledge_base_id,
                current.updated_at.isoformat(),
            )
            reconciled += 1
        return reconciled
