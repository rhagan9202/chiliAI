"""Connector definition, sync-run, and quarantine models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, TypeAlias, cast

from pydantic import BaseModel, Field, computed_field

from shared.utils import generate_id, utc_now

ConnectorSourceType: TypeAlias = Literal["filesystem", "object_store", "http"]
ConnectorScheduleMode: TypeAlias = Literal["manual", "interval", "cron"]
ConnectorStatus: TypeAlias = Literal["active", "disabled"]
ConnectorSyncStatus: TypeAlias = Literal["queued", "running", "completed", "failed", "canceled"]
ConnectorConfigValue: TypeAlias = str | int | float | bool | None


class ConnectorSchedule(BaseModel):
    """How a connector is expected to run."""

    mode: ConnectorScheduleMode = "manual"
    expression: str | None = None


class ConnectorMappingRef(BaseModel):
    """Reference to a domain-pack mapping consumed by a connector."""

    mapping_id: str = Field(min_length=1)
    mapping_version: str = Field(min_length=1)
    feed_name: str = Field(min_length=1)


class ConnectorDefinitionCreate(BaseModel):
    """Payload for registering a connector definition."""

    connector_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    source_type: ConnectorSourceType
    knowledge_base_id: str = Field(min_length=1)
    domain_name: str | None = None
    credentials_ref: str | None = None
    schedule: ConnectorSchedule = Field(default_factory=ConnectorSchedule)
    mapping: ConnectorMappingRef
    config: dict[str, ConnectorConfigValue] = Field(
        default_factory=lambda: cast(dict[str, ConnectorConfigValue], {})
    )


class ConnectorDefinition(BaseModel):
    """Stored connector definition."""

    connector_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    source_type: ConnectorSourceType
    knowledge_base_id: str = Field(min_length=1)
    domain_name: str | None = None
    credentials_ref: str | None = None
    schedule: ConnectorSchedule = Field(default_factory=ConnectorSchedule)
    mapping: ConnectorMappingRef
    config: dict[str, ConnectorConfigValue] = Field(
        default_factory=lambda: cast(dict[str, ConnectorConfigValue], {})
    )
    status: ConnectorStatus = "active"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @computed_field
    @property
    def credentials_display(self) -> str | None:
        return redact_credentials_ref(self.credentials_ref)


class ConnectorDefinitionPage(BaseModel):
    """Paginated connector definition list."""

    items: list[ConnectorDefinition] = Field(
        default_factory=lambda: cast(list[ConnectorDefinition], [])
    )
    total_items: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class ConnectorSyncCounters(BaseModel):
    """Source and ingestion counts for a connector sync run."""

    pulled: int = Field(default=0, ge=0)
    accepted: int = Field(default=0, ge=0)
    quarantined: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)


class ConnectorSyncRunCreate(BaseModel):
    """Payload for creating a connector sync run."""

    connector_id: str = Field(min_length=1)
    knowledge_base_id: str = Field(min_length=1)
    requested_by: str = Field(min_length=1)
    idempotency_key: str | None = Field(default=None, min_length=1)


class ConnectorSyncRunUpdate(BaseModel):
    """Mutable sync run fields."""

    status: ConnectorSyncStatus | None = None
    counters: ConnectorSyncCounters | None = None
    ingest_correlation_id: str | None = None
    source_cursor: str | None = None
    error_message: str | None = None


class ConnectorSyncRun(BaseModel):
    """Stored connector sync run."""

    run_id: str = Field(default_factory=generate_id, min_length=1)
    connector_id: str = Field(min_length=1)
    knowledge_base_id: str = Field(min_length=1)
    requested_by: str = Field(min_length=1)
    status: ConnectorSyncStatus = "queued"
    counters: ConnectorSyncCounters = Field(default_factory=ConnectorSyncCounters)
    idempotency_key: str | None = None
    ingest_correlation_id: str | None = None
    source_cursor: str | None = None
    error_message: str | None = None
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    updated_at: datetime = Field(default_factory=utc_now)


class ConnectorSyncRunPage(BaseModel):
    """Paginated connector sync-run list."""

    items: list[ConnectorSyncRun] = Field(
        default_factory=lambda: cast(list[ConnectorSyncRun], [])
    )
    total_items: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class ConnectorQuarantineRecordCreate(BaseModel):
    """Payload for quarantining one connector source record."""

    run_id: str = Field(min_length=1)
    connector_id: str = Field(min_length=1)
    knowledge_base_id: str = Field(min_length=1)
    source_record_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    raw_ref: str | None = None


class ConnectorQuarantineRecord(BaseModel):
    """Stored quarantined source record metadata."""

    quarantine_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    connector_id: str = Field(min_length=1)
    knowledge_base_id: str = Field(min_length=1)
    source_record_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    raw_ref: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class ConnectorQuarantinePage(BaseModel):
    """Paginated connector quarantine records."""

    items: list[ConnectorQuarantineRecord] = Field(
        default_factory=lambda: cast(list[ConnectorQuarantineRecord], [])
    )
    total_items: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


def redact_credentials_ref(value: str | None) -> str | None:
    if value is None:
        return None
    if len(value) <= 8:
        return "..."
    return f"{value[:7]}...{value[-4:]}"


__all__ = [
    "ConnectorConfigValue",
    "ConnectorDefinition",
    "ConnectorDefinitionCreate",
    "ConnectorDefinitionPage",
    "ConnectorMappingRef",
    "ConnectorQuarantinePage",
    "ConnectorQuarantineRecord",
    "ConnectorQuarantineRecordCreate",
    "ConnectorSchedule",
    "ConnectorScheduleMode",
    "ConnectorSourceType",
    "ConnectorStatus",
    "ConnectorSyncCounters",
    "ConnectorSyncRun",
    "ConnectorSyncRunCreate",
    "ConnectorSyncRunPage",
    "ConnectorSyncRunUpdate",
    "ConnectorSyncStatus",
    "redact_credentials_ref",
]
