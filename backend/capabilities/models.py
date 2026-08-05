"""Typed capability registry models for SAFE-CMS-015."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, TypeAlias, cast

from pydantic import BaseModel, ConfigDict, Field

JsonValue: TypeAlias = object
CapabilitySideEffectClass: TypeAlias = Literal[
    "read",
    "write",
    "external_call",
    "approval",
]
CapabilityHealthStatus: TypeAlias = Literal["healthy", "degraded", "disabled"]


class CapabilityPermission(BaseModel):
    """Permission metadata for a registered capability."""

    model_config = ConfigDict(frozen=True)

    required_roles: list[str] = Field(default_factory=lambda: cast(list[str], []))
    requires_audit: bool = False
    required_scopes: list[str] = Field(default_factory=lambda: cast(list[str], []))


class CapabilityDomainCompatibility(BaseModel):
    """Domain and environment availability metadata."""

    model_config = ConfigDict(frozen=True)

    supported_domains: list[str] = Field(default_factory=lambda: cast(list[str], []))
    unsupported_domains: list[str] = Field(default_factory=lambda: cast(list[str], []))
    environment_tags: list[str] = Field(default_factory=lambda: cast(list[str], []))


class CapabilityHealth(BaseModel):
    """Last-known capability health metadata."""

    model_config = ConfigDict(frozen=True)

    status: CapabilityHealthStatus = "healthy"
    last_checked_at: datetime | None = None
    details: str | None = None


class CapabilityExample(BaseModel):
    """Concrete example payloads for authors and agents."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    input: dict[str, JsonValue] = Field(default_factory=lambda: cast(dict[str, JsonValue], {}))
    output: dict[str, JsonValue] = Field(default_factory=lambda: cast(dict[str, JsonValue], {}))


class CapabilityManifest(BaseModel):
    """Static descriptor for one workflow-callable capability."""

    model_config = ConfigDict(frozen=True)

    capability_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    module: str = Field(min_length=1)
    label: str = Field(min_length=1)
    description: str = Field(min_length=1)
    input_schema: dict[str, JsonValue]
    output_schema: dict[str, JsonValue]
    side_effect_class: CapabilitySideEffectClass
    permission: CapabilityPermission = Field(default_factory=CapabilityPermission)
    domain_compatibility: CapabilityDomainCompatibility = Field(
        default_factory=CapabilityDomainCompatibility
    )
    health: CapabilityHealth = Field(default_factory=CapabilityHealth)
    examples: list[CapabilityExample] = Field(
        default_factory=lambda: cast(list[CapabilityExample], [])
    )


class CapabilityQuery(BaseModel):
    """Filters for listing registered capabilities."""

    domain_name: str | None = None
    role: str | None = None
    module: str | None = None
    side_effect_class: CapabilitySideEffectClass | None = None
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class CapabilityPage(BaseModel):
    """Paginated registered capability list."""

    items: list[CapabilityManifest] = Field(
        default_factory=lambda: cast(list[CapabilityManifest], [])
    )
    total_items: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class CapabilityExecutionEnvelope(BaseModel):
    """Typed capability execution result envelope."""

    capability_id: str = Field(min_length=1)
    success: bool
    output: dict[str, JsonValue] | None = None
    error_code: str | None = None
    error_message: str | None = None
    audit_required: bool = False
