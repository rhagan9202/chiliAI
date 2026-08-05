"""Readiness aggregation models for SAFE-CMS-018."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, TypeAlias, cast

from pydantic import BaseModel, Field

from capabilities.models import JsonValue

ReadinessComponentStatus: TypeAlias = Literal["ready", "blocked", "warning", "unknown"]


class ReadinessIssue(BaseModel):
    """One actionable readiness blocker or warning."""

    component: str = Field(min_length=1)
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    action: str | None = None


class ReadinessComponent(BaseModel):
    """Readiness state for one subsystem."""

    status: ReadinessComponentStatus
    label: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    blockers: list[ReadinessIssue] = Field(
        default_factory=lambda: cast(list[ReadinessIssue], [])
    )
    warnings: list[ReadinessIssue] = Field(
        default_factory=lambda: cast(list[ReadinessIssue], [])
    )
    details: dict[str, JsonValue] = Field(
        default_factory=lambda: cast(dict[str, JsonValue], {})
    )


class ReadinessKnowledgeBaseSummary(BaseModel):
    """KB context included with the readiness response."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    domain: str | None = None
    status: str = Field(min_length=1)
    document_count: int = Field(ge=0)
    entity_count: int = Field(ge=0)
    relationship_count: int = Field(ge=0)
    updated_at: datetime | None = None
    created_at: datetime


class ReadinessResponse(BaseModel):
    """Aggregated readiness response for one active knowledge base."""

    knowledge_base: ReadinessKnowledgeBaseSummary
    active_domain_name: str = Field(min_length=1)
    ready: bool
    components: dict[str, ReadinessComponent]
    blockers: list[ReadinessIssue] = Field(
        default_factory=lambda: cast(list[ReadinessIssue], [])
    )
    warnings: list[ReadinessIssue] = Field(
        default_factory=lambda: cast(list[ReadinessIssue], [])
    )


__all__ = [
    "ReadinessComponent",
    "ReadinessComponentStatus",
    "ReadinessIssue",
    "ReadinessKnowledgeBaseSummary",
    "ReadinessResponse",
]
