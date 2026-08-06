"""Typed audit ledger models."""

from __future__ import annotations

from datetime import datetime
from typing import Final, Literal, cast

from pydantic import BaseModel, Field

AuditOutcome = Literal["success", "failure"]
JsonSummary = dict[str, object | None]

PLATFORM_TENANT_ID: Final[str] = "platform"
"""The single tenant every audit event is written under.

chiliAI has no tenancy implementation yet — every story in
``docs/backlog/_multitenancy.md`` is still `planned` — so ``tenant_id`` cannot
carry a real tenant. Writers previously each improvised one: the knowledge-base
id (cases, alerts, KBs, evidence reviews), ``"platform"`` (auth), or
``"default"`` (workflow definitions, via an unset constructor argument). Because
``tenant_id`` was also a *mandatory* read filter, that split the ledger into
mutually invisible namespaces and made "a complete timeline of material actions
for a KB" — the thing the audit ledger exists to answer — unobtainable by any
single query.

Until real multitenancy lands, every event is written under this constant and
knowledge-base scoping uses the dedicated ``knowledge_base_id`` field. When
tenancy does arrive, this is the seam to replace: resolve the tenant from the
authenticated principal rather than from anything a caller supplies.
"""


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

    # Optional, unlike the write side. It was mandatory, which meant a caller
    # had to guess which namespace a writer had used; scoping by
    # knowledge_base_id alone now returns a KB's complete timeline regardless of
    # the tenant a historical row was written under. Kept as a filter so the
    # field stays useful once real tenancy exists.
    tenant_id: str | None = Field(default=None, min_length=1)
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
