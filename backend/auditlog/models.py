"""Typed audit ledger models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, cast

from pydantic import BaseModel, Field

AuditOutcome = Literal["success", "failure"]
JsonSummary = dict[str, object | None]


class AuditEventCreate(BaseModel):
    """Input payload for appending one material audit event."""

    tenant_id: str = Field(min_length=1)
    knowledge_base_id: str | None = None
    occurred_at: datetime | None = None
    actor_user_id: str = Field(min_length=1)
    actor_email: str | None = None
    actor_roles: list[str] = Field(default_factory=list)
    action: str = Field(min_length=1)
    resource_type: str = Field(min_length=1)
    resource_id: str = Field(min_length=1)
    before: JsonSummary | None = None
    after: JsonSummary | None = None
    correlation_id: str = Field(min_length=1)
    client_ip: str | None = None
    user_agent: str | None = None
    outcome: AuditOutcome = "success"
    failure_reason: str | None = None
    metadata: JsonSummary = Field(default_factory=dict)


class AuditEvent(BaseModel):
    """Stored append-only audit event."""

    event_id: str = Field(min_length=1)
    occurred_at: datetime
    tenant_id: str = Field(min_length=1)
    knowledge_base_id: str | None = None
    actor_user_id: str = Field(min_length=1)
    actor_email: str | None = None
    actor_roles: list[str] = Field(default_factory=list)
    action: str = Field(min_length=1)
    resource_type: str = Field(min_length=1)
    resource_id: str = Field(min_length=1)
    before: JsonSummary | None = None
    after: JsonSummary | None = None
    correlation_id: str = Field(min_length=1)
    client_ip: str | None = None
    user_agent: str | None = None
    outcome: AuditOutcome = "success"
    failure_reason: str | None = None
    metadata: JsonSummary = Field(default_factory=dict)


class AuditEventQuery(BaseModel):
    """Filters for reading audit events."""

    tenant_id: str = Field(min_length=1)
    knowledge_base_id: str | None = None
    actor_user_id: str | None = None
    action_prefix: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    outcome: AuditOutcome | None = None
    occurred_from: datetime | None = None
    occurred_to: datetime | None = None
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class AuditEventPage(BaseModel):
    """One filtered page of audit events."""

    items: list[AuditEvent] = Field(default_factory=lambda: cast(list[AuditEvent], []))
    total_items: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class AuditWriteFailure(BaseModel):
    """Failure captured when the audit sink cannot append an event."""

    occurred_at: datetime
    action: str
    resource_type: str
    resource_id: str
    error_class: str
    error_message: str
