"""Internal domain models for case management."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, cast

from pydantic import BaseModel, Field

from playbooks.models import PlaybookRef
from shared.utils import utc_now

CaseStatus = Literal["open", "in_review", "closed"]
CasePriority = Literal["low", "medium", "high", "critical"]
FeedbackLabel = Literal["suspicious", "not_suspicious", "insufficient_evidence"]
EvidenceAdequacy = Literal["low", "medium", "high"]


class CaseTimelineEvent(BaseModel):
    """A single entry in a case's evidence/entity timeline snapshot."""

    occurred_at: datetime
    label: str
    detail: str


class AnalystFeedback(BaseModel):
    """Analyst judgment captured against an investigation case."""

    case_id: str
    label: FeedbackLabel
    evidence_adequacy: EvidenceAdequacy
    missing_evidence: list[str] = Field(default_factory=lambda: cast(list[str], []))
    notes: str
    submitted_at: datetime = Field(default_factory=utc_now)


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
    playbook_ref: PlaybookRef | None = None
    alert_ids: list[str] = Field(default_factory=lambda: cast(list[str], []))
    timeline: list[CaseTimelineEvent] = Field(
        default_factory=lambda: cast(list[CaseTimelineEvent], [])
    )
    feedback_history: list[AnalystFeedback] = Field(
        default_factory=lambda: cast(list[AnalystFeedback], [])
    )
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


__all__ = [
    "AnalystFeedback",
    "Case",
    "EvidenceAdequacy",
    "FeedbackLabel",
    "CasePriority",
    "CaseStatus",
    "CaseTimelineEvent",
]
