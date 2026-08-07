"""Repository protocol for connector definitions and sync state."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from connectors.models import (
    ConnectorDefinition,
    ConnectorDefinitionCreate,
    ConnectorDefinitionPage,
    ConnectorQuarantinePage,
    ConnectorQuarantineRecord,
    ConnectorQuarantineRecordCreate,
    ConnectorSyncRun,
    ConnectorSyncRunCreate,
    ConnectorSyncRunPage,
    ConnectorSyncRunUpdate,
    ConnectorSyncStatus,
)


@runtime_checkable
class ConnectorRepositoryProtocol(Protocol):
    """Storage boundary for SAFE-CMS-017 connector state.

    ``runtime_checkable`` so the DI memoization guard can accept either
    backend. Note that it only checks method *presence*, not signatures — it
    is a "did the memoized object get replaced by something unrelated" guard,
    not a conformance check.
    """

    def save_definition(self, payload: ConnectorDefinitionCreate) -> ConnectorDefinition: ...

    def get_definition(
        self,
        *,
        knowledge_base_id: str,
        connector_id: str,
    ) -> ConnectorDefinition | None: ...

    def list_definitions(
        self,
        *,
        knowledge_base_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ConnectorDefinitionPage: ...

    def create_run(self, payload: ConnectorSyncRunCreate) -> ConnectorSyncRun: ...

    def get_run(self, run_id: str) -> ConnectorSyncRun | None: ...

    def claim_sync_run(
        self,
        run_id: str,
        *,
        now: datetime,
    ) -> ConnectorSyncRun | None:
        """Transition a ``queued`` run to ``running``, or return ``None``.

        Returns ``None`` when the run is absent or is not ``queued``. The caller
        must treat that as "another worker owns this run" and stop, not as an
        error: Redis Streams is at-least-once and ``reclaim_stale_pending`` can
        hand the same event to a second worker, so this is the guard that stops
        two workers pulling one source concurrently.

        Unlike a score *batch*, a sync run is not reclaimable on a timer. A
        connector pull is resumable by design — the run carries
        ``source_cursor``, so a redelivered page event resumes from the cursor
        rather than needing the run row itself to be re-claimed.
        """
        ...

    def update_run(
        self,
        run_id: str,
        update: ConnectorSyncRunUpdate,
    ) -> ConnectorSyncRun: ...

    def list_runs(
        self,
        *,
        connector_id: str | None = None,
        knowledge_base_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ConnectorSyncRunPage: ...

    def list_stale_runs(
        self,
        *,
        statuses: tuple[ConnectorSyncStatus, ...],
        updated_before: datetime,
        limit: int = 1000,
    ) -> list[ConnectorSyncRun]:
        """Runs in ``statuses`` not updated since ``updated_before``, any KB.

        Deliberately not `list_runs` with an optional knowledge_base_id: this is
        a maintenance scan across every KB, and conflating the two would make it
        easy to accidentally run an unscoped query on the analyst-facing path.

        Named and shaped identically to
        ``ScoreRunRepositoryProtocol.list_stale_runs`` on purpose — two stale
        scans with different signatures is how the third one gets written wrong.
        """
        ...

    def add_quarantine_record(
        self,
        payload: ConnectorQuarantineRecordCreate,
    ) -> ConnectorQuarantineRecord: ...

    def list_quarantine(
        self,
        *,
        run_id: str | None = None,
        connector_id: str | None = None,
        knowledge_base_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ConnectorQuarantinePage: ...


__all__ = ["ConnectorRepositoryProtocol"]
