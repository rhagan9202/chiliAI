"""Repository protocol for connector definitions and sync state."""

from __future__ import annotations

from typing import Protocol

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


class ConnectorRepositoryProtocol(Protocol):
    """Storage boundary for SAFE-CMS-017 connector state."""

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
