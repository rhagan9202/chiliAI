"""Connector lifecycle service for SAFE-CMS-017."""

from __future__ import annotations

from connectors.models import (
    ConnectorDefinition,
    ConnectorDefinitionCreate,
    ConnectorDefinitionPage,
    ConnectorQuarantinePage,
    ConnectorQuarantineRecord,
    ConnectorQuarantineRecordCreate,
    ConnectorSyncCounters,
    ConnectorSyncRun,
    ConnectorSyncRunCreate,
    ConnectorSyncRunPage,
    ConnectorSyncRunUpdate,
)
from connectors.repository import ConnectorRepositoryProtocol


class ConnectorService:
    """Coordinate connector definitions, sync runs, and quarantine records."""

    def __init__(self, repository: ConnectorRepositoryProtocol) -> None:
        self._repository = repository

    def register_connector(
        self,
        knowledge_base_id: str,
        payload: ConnectorDefinitionCreate,
    ) -> ConnectorDefinition:
        if payload.knowledge_base_id != knowledge_base_id:
            raise ValueError("Connector knowledge_base_id mismatch.")
        existing = self._repository.get_definition(
            knowledge_base_id=knowledge_base_id,
            connector_id=payload.connector_id,
        )
        if existing is not None:
            candidate = ConnectorDefinition(
                **payload.model_dump(),
                status=existing.status,
                created_at=existing.created_at,
                updated_at=existing.updated_at,
            )
            if existing.model_dump(mode="json") != candidate.model_dump(mode="json"):
                raise ValueError(
                    f"Connector '{payload.connector_id}' already exists with a "
                    "different definition."
                )
            return existing
        return self._repository.save_definition(payload)

    def list_connectors(
        self,
        *,
        knowledge_base_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ConnectorDefinitionPage:
        return self._repository.list_definitions(
            knowledge_base_id=knowledge_base_id,
            limit=limit,
            offset=offset,
        )

    def start_sync(
        self,
        *,
        knowledge_base_id: str,
        connector_id: str,
        requested_by: str,
        idempotency_key: str | None = None,
    ) -> ConnectorSyncRun:
        connector = self._repository.get_definition(
            knowledge_base_id=knowledge_base_id,
            connector_id=connector_id,
        )
        if connector is None:
            raise KeyError(connector_id)
        if idempotency_key is not None:
            existing_runs = self._repository.list_runs(
                connector_id=connector_id,
                knowledge_base_id=knowledge_base_id,
            )
            for run in existing_runs.items:
                if run.idempotency_key == idempotency_key:
                    return run
        return self._repository.create_run(
            ConnectorSyncRunCreate(
                connector_id=connector_id,
                knowledge_base_id=knowledge_base_id,
                requested_by=requested_by,
                idempotency_key=idempotency_key,
            )
        )

    def complete_sync(
        self,
        run_id: str,
        *,
        counters: ConnectorSyncCounters,
        ingest_correlation_id: str,
        source_cursor: str | None = None,
    ) -> ConnectorSyncRun:
        return self._repository.update_run(
            run_id,
            ConnectorSyncRunUpdate(
                status="completed",
                counters=counters,
                ingest_correlation_id=ingest_correlation_id,
                source_cursor=source_cursor,
            ),
        )

    def fail_sync(self, run_id: str, *, error_message: str) -> ConnectorSyncRun:
        return self._repository.update_run(
            run_id,
            ConnectorSyncRunUpdate(
                status="failed",
                error_message=error_message,
            ),
        )

    def quarantine_record(
        self,
        *,
        run_id: str,
        connector_id: str,
        knowledge_base_id: str,
        source_record_id: str,
        reason: str,
        raw_ref: str | None = None,
    ) -> ConnectorQuarantineRecord:
        return self._repository.add_quarantine_record(
            ConnectorQuarantineRecordCreate(
                run_id=run_id,
                connector_id=connector_id,
                knowledge_base_id=knowledge_base_id,
                source_record_id=source_record_id,
                reason=reason,
                raw_ref=raw_ref,
            )
        )

    def list_runs(
        self,
        *,
        connector_id: str | None = None,
        knowledge_base_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ConnectorSyncRunPage:
        return self._repository.list_runs(
            connector_id=connector_id,
            knowledge_base_id=knowledge_base_id,
            limit=limit,
            offset=offset,
        )

    def list_quarantine(
        self,
        *,
        run_id: str | None = None,
        connector_id: str | None = None,
        knowledge_base_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ConnectorQuarantinePage:
        return self._repository.list_quarantine(
            run_id=run_id,
            connector_id=connector_id,
            knowledge_base_id=knowledge_base_id,
            limit=limit,
            offset=offset,
        )


__all__ = ["ConnectorService"]
