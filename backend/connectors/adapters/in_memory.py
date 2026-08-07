"""In-memory connector repository for tests and local development."""

from __future__ import annotations

from datetime import datetime
from threading import RLock

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
)
from shared.utils import generate_id, utc_now


class InMemoryConnectorRepository:
    """Dict-backed repository for connector definitions, runs, and quarantine."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._definitions: dict[tuple[str, str], ConnectorDefinition] = {}
        self._runs: dict[str, ConnectorSyncRun] = {}
        self._quarantine: dict[str, ConnectorQuarantineRecord] = {}

    def save_definition(self, payload: ConnectorDefinitionCreate) -> ConnectorDefinition:
        definition = ConnectorDefinition(**payload.model_dump())
        key = (definition.knowledge_base_id, definition.connector_id)
        with self._lock:
            existing = self._definitions.get(key)
            if existing is not None:
                return existing.model_copy(deep=True)
            self._definitions[key] = definition.model_copy(deep=True)
            return definition.model_copy(deep=True)

    def get_definition(
        self,
        *,
        knowledge_base_id: str,
        connector_id: str,
    ) -> ConnectorDefinition | None:
        with self._lock:
            definition = self._definitions.get((knowledge_base_id, connector_id))
            return definition.model_copy(deep=True) if definition is not None else None

    def list_definitions(
        self,
        *,
        knowledge_base_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ConnectorDefinitionPage:
        normalized_limit, normalized_offset = _page_bounds(limit, offset)
        with self._lock:
            definitions = [
                definition
                for definition in self._definitions.values()
                if knowledge_base_id is None
                or definition.knowledge_base_id == knowledge_base_id
            ]
            definitions.sort(key=lambda item: (item.knowledge_base_id, item.connector_id))
            items = definitions[normalized_offset : normalized_offset + normalized_limit]
            return ConnectorDefinitionPage(
                items=[item.model_copy(deep=True) for item in items],
                total_items=len(definitions),
                limit=normalized_limit,
                offset=normalized_offset,
            )

    def create_run(self, payload: ConnectorSyncRunCreate) -> ConnectorSyncRun:
        run = ConnectorSyncRun(**payload.model_dump())
        with self._lock:
            self._runs[run.run_id] = run.model_copy(deep=True)
            return run.model_copy(deep=True)

    def get_run(self, run_id: str) -> ConnectorSyncRun | None:
        with self._lock:
            run = self._runs.get(run_id)
            return run.model_copy(deep=True) if run is not None else None

    def claim_sync_run(
        self,
        run_id: str,
        *,
        now: datetime,
    ) -> ConnectorSyncRun | None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None or run.status != "queued":
                return None
            claimed = run.model_copy(
                update={"status": "running", "updated_at": now}, deep=True
            )
            self._runs[run_id] = claimed
            return claimed.model_copy(deep=True)

    def update_run(
        self,
        run_id: str,
        update: ConnectorSyncRunUpdate,
    ) -> ConnectorSyncRun:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                raise KeyError(run_id)
            update_values: dict[str, object] = {}
            if update.status is not None:
                update_values["status"] = update.status
            if update.counters is not None:
                update_values["counters"] = update.counters
            if update.ingest_correlation_id is not None:
                update_values["ingest_correlation_id"] = update.ingest_correlation_id
            if update.source_cursor is not None:
                update_values["source_cursor"] = update.source_cursor
            if update.error_message is not None:
                update_values["error_message"] = update.error_message
            if update.status in {"completed", "failed", "canceled"}:
                update_values["completed_at"] = utc_now()
            update_values["updated_at"] = utc_now()
            updated = run.model_copy(update=update_values, deep=True)
            self._runs[run_id] = updated
            return updated.model_copy(deep=True)

    def list_runs(
        self,
        *,
        connector_id: str | None = None,
        knowledge_base_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ConnectorSyncRunPage:
        normalized_limit, normalized_offset = _page_bounds(limit, offset)
        with self._lock:
            runs = [
                run
                for run in self._runs.values()
                if (connector_id is None or run.connector_id == connector_id)
                and (
                    knowledge_base_id is None
                    or run.knowledge_base_id == knowledge_base_id
                )
            ]
            runs.sort(key=lambda item: item.started_at, reverse=True)
            items = runs[normalized_offset : normalized_offset + normalized_limit]
            return ConnectorSyncRunPage(
                items=[item.model_copy(deep=True) for item in items],
                total_items=len(runs),
                limit=normalized_limit,
                offset=normalized_offset,
            )

    def add_quarantine_record(
        self,
        payload: ConnectorQuarantineRecordCreate,
    ) -> ConnectorQuarantineRecord:
        quarantine = ConnectorQuarantineRecord(
            quarantine_id=f"{payload.run_id}:{generate_id()}",
            **payload.model_dump(),
        )
        with self._lock:
            self._quarantine[quarantine.quarantine_id] = quarantine.model_copy(deep=True)
            return quarantine.model_copy(deep=True)

    def list_quarantine(
        self,
        *,
        run_id: str | None = None,
        connector_id: str | None = None,
        knowledge_base_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ConnectorQuarantinePage:
        normalized_limit, normalized_offset = _page_bounds(limit, offset)
        with self._lock:
            records = [
                record
                for record in self._quarantine.values()
                if (run_id is None or record.run_id == run_id)
                and (connector_id is None or record.connector_id == connector_id)
                and (
                    knowledge_base_id is None
                    or record.knowledge_base_id == knowledge_base_id
                )
            ]
            records.sort(key=lambda item: (item.run_id, item.source_record_id))
            items = records[normalized_offset : normalized_offset + normalized_limit]
            return ConnectorQuarantinePage(
                items=[item.model_copy(deep=True) for item in items],
                total_items=len(records),
                limit=normalized_limit,
                offset=normalized_offset,
            )


def _page_bounds(limit: int, offset: int) -> tuple[int, int]:
    return max(limit, 1), max(offset, 0)


__all__ = ["InMemoryConnectorRepository"]
