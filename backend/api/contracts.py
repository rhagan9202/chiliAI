"""Frontend-facing API contracts for read-oriented backend surfaces."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, cast

from pydantic import BaseModel, Field

from config.schema import CapabilitiesConfig, UiRoleConfig


class ApiEnvelope(BaseModel):
    """Common status envelope for simple mutation responses."""

    status: Literal["accepted", "ok"]
    message: str


class PageInfo(BaseModel):
    """Pagination metadata for collection responses."""

    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_items: int = Field(ge=0)


class DomainFeaturesResponse(BaseModel):
    """Feature flags and role/navigation metadata derived from DomainConfig."""

    capabilities: CapabilitiesConfig
    default_entity_type: str | None = None
    default_role: str | None = None
    enabled_pages: list[str] = Field(default_factory=lambda: cast(list[str], []))
    roles: dict[str, UiRoleConfig] = Field(default_factory=dict)


class DomainConfigSchemaResponse(BaseModel):
    """JSON Schema payload for the active domain config model."""

    schema_payload: dict[str, object] = Field(default_factory=dict, alias="schema")


class AlertListItem(BaseModel):
    """Summary alert row consumed by the analyst feed."""

    id: str
    knowledge_base_id: str
    entity_id: str
    entity_type: str
    entity_label: str
    severity: Literal["low", "medium", "high", "critical"]
    status: Literal["open", "acknowledged", "investigating", "resolved", "dismissed"]
    title: str
    reasoning: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_pack_id: str | None = None
    created_at: datetime
    tags: list[str] = Field(default_factory=lambda: cast(list[str], []))


class AlertListResponse(BaseModel):
    """Paginated alert feed response."""

    items: list[AlertListItem] = Field(default_factory=lambda: cast(list[AlertListItem], []))
    page: PageInfo


class PolicyCitation(BaseModel):
    """Policy reference surfaced with evidence or alerts."""

    citation_id: str
    title: str
    excerpt: str
    source_document_id: str


class PolicyCitationResponse(BaseModel):
    """A policy/document reference attached to a matched policy item."""

    citation_id: str
    title: str
    source_ref: str
    excerpt: str | None = None


class PolicyDispositionResponse(BaseModel):
    """The recorded triage decision for a policy item."""

    action: Literal["accept", "reject", "defer", "escalate"]
    actor: str
    note: str | None = None
    decided_at: datetime
    case_id: str | None = None


class PolicyItemSummaryResponse(BaseModel):
    """Summary row for the policy intelligence item queue."""

    id: str
    knowledge_base_id: str
    rule_id: str
    rule_pack_id: str
    target_kind: Literal["entity", "alert", "metric"]
    target_ref: str
    title: str
    severity: Literal["medium", "high", "critical"]
    status: Literal["open", "accepted", "rejected", "deferred", "escalated"]
    updated_at: datetime


class PolicyItemListResponse(BaseModel):
    """Collection response for KB-scoped policy items."""

    items: list[PolicyItemSummaryResponse] = Field(
        default_factory=lambda: cast(list[PolicyItemSummaryResponse], [])
    )
    total: int = 0


class PolicyItemDetailResponse(BaseModel):
    """Expanded policy item detail payload."""

    item: PolicyItemSummaryResponse
    matched_fields: dict[str, str | float | int | bool] = Field(
        default_factory=lambda: cast(dict[str, str | float | int | bool], {})
    )
    citations: list[PolicyCitationResponse] = Field(
        default_factory=lambda: cast(list[PolicyCitationResponse], [])
    )
    disposition: PolicyDispositionResponse | None = None


class PolicyTriageRequest(BaseModel):
    """Payload for triaging a policy item (accept/reject/defer/escalate)."""

    action: Literal["accept", "reject", "defer", "escalate"]
    note: str | None = None


class RealtimeSnapshotResponse(BaseModel):
    """Realtime workspace snapshot emitted over SSE."""

    sequence: int = Field(ge=0)
    emitted_at: datetime
    active_alerts: int = Field(ge=0)
    running_workflows: int = Field(ge=0)
    knowledge_base_statuses: dict[str, str] = Field(default_factory=dict)


class AlertDetailResponse(BaseModel):
    """Expanded alert record used by alert and investigation views."""

    alert: AlertListItem
    related_entity_ids: list[str] = Field(default_factory=lambda: cast(list[str], []))
    policy_citations: list[PolicyCitation] = Field(default_factory=lambda: cast(list[PolicyCitation], []))


class GraphNodeResponse(BaseModel):
    """Node returned by graph investigation endpoints."""

    id: str
    type: str
    label: str
    summary: str
    risk_score: float = Field(ge=0.0, le=1.0)
    properties: dict[str, str | int | float | bool] = Field(default_factory=dict)


class GraphEdgeResponse(BaseModel):
    """Edge returned by graph investigation endpoints."""

    id: str
    type: str
    source_id: str
    target_id: str
    summary: str


class GraphEntityDetailResponse(BaseModel):
    """Entity detail and neighboring graph context for investigation views."""

    entity: GraphNodeResponse
    neighbors: list[GraphNodeResponse] = Field(default_factory=lambda: cast(list[GraphNodeResponse], []))
    relationships: list[GraphEdgeResponse] = Field(default_factory=lambda: cast(list[GraphEdgeResponse], []))
    related_alert_ids: list[str] = Field(default_factory=lambda: cast(list[str], []))


class EvidenceItemResponse(BaseModel):
    """Individual evidence item shown inside an evidence pack."""

    source_id: str
    source_type: str
    quote: str
    rationale: str
    score: float = Field(ge=0.0, le=1.0)


class EvidencePackResponse(BaseModel):
    """Frontend-oriented evidence pack detail payload."""

    id: str
    alert_id: str
    reasoning: str
    confidence: float = Field(ge=0.0, le=1.0)
    scores: dict[str, float] = Field(default_factory=dict)
    subgraph_node_ids: list[str] = Field(default_factory=lambda: cast(list[str], []))
    subgraph_edge_ids: list[str] = Field(default_factory=lambda: cast(list[str], []))
    items: list[EvidenceItemResponse] = Field(default_factory=lambda: cast(list[EvidenceItemResponse], []))
    policy_citations: list[PolicyCitation] = Field(default_factory=lambda: cast(list[PolicyCitation], []))


class CaseSummaryResponse(BaseModel):
    """Case list item for the human review workflow."""

    id: str
    knowledge_base_id: str
    title: str
    status: Literal["open", "in_review", "closed"]
    priority: Literal["low", "medium", "high", "critical"]
    assignee: str | None = None
    originating_alert_id: str | None = None
    evidence_pack_id: str | None = None
    alert_ids: list[str] = Field(default_factory=lambda: cast(list[str], []))
    updated_at: datetime


class CaseTimelineEventResponse(BaseModel):
    """A single entry in a case's captured evidence/entity timeline."""

    occurred_at: datetime
    label: str
    detail: str


class CaseListResponse(BaseModel):
    """Case collection response."""

    items: list[CaseSummaryResponse] = Field(default_factory=lambda: cast(list[CaseSummaryResponse], []))
    page: PageInfo


class AnalystFeedbackResponse(BaseModel):
    """Analyst feedback record attached to a case."""

    case_id: str
    label: Literal["suspicious", "not_suspicious", "insufficient_evidence"]
    evidence_adequacy: Literal["low", "medium", "high"]
    missing_evidence: list[str] = Field(default_factory=lambda: cast(list[str], []))
    notes: str
    submitted_at: datetime


class CaseDetailResponse(BaseModel):
    """Expanded case detail payload."""

    case: CaseSummaryResponse
    alerts: list[AlertListItem] = Field(default_factory=lambda: cast(list[AlertListItem], []))
    evidence_pack: EvidencePackResponse | None = None
    entity_timeline: list[CaseTimelineEventResponse] = Field(
        default_factory=lambda: cast(list[CaseTimelineEventResponse], [])
    )
    feedback_history: list[AnalystFeedbackResponse] = Field(default_factory=lambda: cast(list[AnalystFeedbackResponse], []))


class ChatCitationResponse(BaseModel):
    """Rich citation payload returned alongside an assistant chat message.

    Mirrors :class:`rag.models.RagCitation` so the frontend can render
    provenance (snippet preview, document anchor, score) and offer
    click-through navigation to investigation entities (see BL-002).
    """

    record_id: str
    content_id: str
    score: float
    snippet: str
    document_id: str | None = None
    chunk_index: int | None = None
    highlight: str | None = None
    entity_id: str | None = None


class ChatMessageResponse(BaseModel):
    """One message in a RAG chat conversation."""

    id: str
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: datetime
    citation_ids: list[str] = Field(default_factory=lambda: cast(list[str], []))
    citations: list[ChatCitationResponse] = Field(
        default_factory=lambda: cast(list[ChatCitationResponse], [])
    )


class ChatConversationResponse(BaseModel):
    """Conversation state returned to the RAG chat UI."""

    id: str
    title: str
    knowledge_base_id: str
    messages: list[ChatMessageResponse] = Field(default_factory=lambda: cast(list[ChatMessageResponse], []))


class ChatStreamCitationResponse(BaseModel):
    """Citation payload emitted in the final RAG SSE event."""

    record_id: str
    content_id: str
    score: float
    snippet: str
    document_id: str | None = None
    chunk_index: int | None = None
    highlight: str | None = None
    entity_id: str | None = None


class ChatStreamFinalEventResponse(BaseModel):
    """Final RAG SSE event payload."""

    token: str
    done: Literal[True]
    sources: list[str] = Field(default_factory=lambda: cast(list[str], []))
    citations: list[ChatStreamCitationResponse] = Field(
        default_factory=lambda: cast(list[ChatStreamCitationResponse], [])
    )


class WorkflowRunResponse(BaseModel):
    """Workflow run summary for pipeline status views."""

    id: str
    workflow_type: Literal["ingestion", "graph_build", "analytics", "monitoring"]
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    knowledge_base_id: str
    started_at: datetime
    updated_at: datetime
    current_step: str
    last_error: str | None = None


class WorkflowRunListResponse(BaseModel):
    """Collection of workflow runs."""

    items: list[WorkflowRunResponse] = Field(default_factory=lambda: cast(list[WorkflowRunResponse], []))


class RiskFactorResponse(BaseModel):
    """Frontend risk-factor breakdown."""

    factor_name: str
    contribution: float = Field(ge=0.0, le=1.0)
    rationale: str | None = None


class RiskScoreResponse(BaseModel):
    """Risk summary for one entity."""

    entity_id: str
    overall_score: float = Field(ge=0.0, le=1.0)
    risk_level: Literal["low", "medium", "high", "critical"]
    factors: list[RiskFactorResponse] = Field(default_factory=lambda: cast(list[RiskFactorResponse], []))
    availability_status: Literal["available", "unavailable"] = "available"
    unavailable_reason: str | None = None


class EntityTimeseriesPointResponse(BaseModel):
    """One point in an entity timeseries chart."""

    timestamp: datetime
    value: float
    label: str
    is_anomaly: bool = False


class EntityTimeseriesResponse(BaseModel):
    """Timeseries payload for entity trend charts."""

    entity_id: str
    metric_name: str
    points: list[EntityTimeseriesPointResponse] = Field(default_factory=lambda: cast(list[EntityTimeseriesPointResponse], []))
    availability_status: Literal["available", "unavailable"] = "available"
    unavailable_reason: str | None = None


class AnalyticsOverviewResponse(BaseModel):
    """High-level analytics summary for dashboard widgets."""

    active_alerts: int = Field(ge=0)
    open_cases: int = Field(ge=0)
    entities_monitored: int = Field(ge=0)
    high_risk_entities: int = Field(ge=0)


class CaseCreateRequest(BaseModel):
    """Payload for creating a new case."""

    title: str
    priority: Literal["low", "medium", "high", "critical"]
    assignee: str | None = None
    alert_ids: list[str] = Field(default_factory=lambda: cast(list[str], []))


class CaseUpdateRequest(BaseModel):
    """Patch payload for updating a case."""

    title: str | None = None
    status: Literal["open", "in_review", "closed"] | None = None
    priority: Literal["low", "medium", "high", "critical"] | None = None
    assignee: str | None = None


class CasePromoteRequest(BaseModel):
    """Payload for promoting an alert into a new investigation case."""

    alert_id: str
    notes: str | None = None


class CaseFeedbackCreateRequest(BaseModel):
    """Payload for storing analyst feedback on a case."""

    label: Literal["suspicious", "not_suspicious", "insufficient_evidence"]
    evidence_adequacy: Literal["low", "medium", "high"]
    missing_evidence: list[str] = Field(default_factory=lambda: cast(list[str], []))
    notes: str


class ChatConversationCreateRequest(BaseModel):
    """Payload for creating a new chat conversation."""

    knowledge_base_id: str
    title: str | None = None


class ChatMessageCreateRequest(BaseModel):
    """Payload for appending a message to an existing conversation."""

    content: str
    include_graph_context: bool = True
    filters: dict[str, str | int | float | bool] = Field(default_factory=dict)


__all__ = [
    "AlertDetailResponse",
    "AlertListItem",
    "AlertListResponse",
    "AnalystFeedbackResponse",
    "AnalyticsOverviewResponse",
    "ApiEnvelope",
    "CaseCreateRequest",
    "CaseDetailResponse",
    "CaseFeedbackCreateRequest",
    "CaseListResponse",
    "CaseSummaryResponse",
    "CaseUpdateRequest",
    "ChatConversationCreateRequest",
    "ChatConversationResponse",
    "ChatMessageCreateRequest",
    "ChatMessageResponse",
    "ChatStreamCitationResponse",
    "ChatStreamFinalEventResponse",
    "DomainConfigSchemaResponse",
    "DomainFeaturesResponse",
    "EvidenceItemResponse",
    "EvidencePackResponse",
    "EntityTimeseriesPointResponse",
    "EntityTimeseriesResponse",
    "GraphEdgeResponse",
    "GraphEntityDetailResponse",
    "GraphNodeResponse",
    "PageInfo",
    "PolicyCitation",
    "PolicyCitationResponse",
    "PolicyDispositionResponse",
    "PolicyItemDetailResponse",
    "PolicyItemListResponse",
    "PolicyItemSummaryResponse",
    "PolicyTriageRequest",
    "RealtimeSnapshotResponse",
    "RiskFactorResponse",
    "RiskScoreResponse",
    "WorkflowRunListResponse",
    "WorkflowRunResponse",
]
