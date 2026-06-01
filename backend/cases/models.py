"""Internal domain models for case management."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, cast

from pydantic import BaseModel, Field

from shared.utils import utc_now

CaseStatus = Literal["open", "in_review", "closed"]
CasePriority = Literal["low", "medium", "high", "critical"]


class CaseTimelineEvent(BaseModel):
    """A single entry in a case's evidence/entity timeline snapshot."""

    occurred_at: datetime
    label: str
    detail: str


class Case(BaseModel):
    """A durable, KB-scoped investigation case."""

    id: str
    knowledge_base_id: str
    title: str
    status: CaseStatus
    priority: CasePriority
    assignee: str | None = None
    originating_alert_id: str | None = None
    evidence_pack_id: str | None = None
    alert_ids: list[str] = Field(default_factory=lambda: cast(list[str], []))
    timeline: list[CaseTimelineEvent] = Field(
        default_factory=lambda: cast(list[CaseTimelineEvent], [])
    )
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


__all__ = [
    "Case",
    "CasePriority",
    "CaseStatus",
    "CaseTimelineEvent",
]
