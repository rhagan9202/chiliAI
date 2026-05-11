"""Frontend-facing API contracts for read-oriented backend surfaces."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ApiEnvelope(BaseModel):
    """Common status envelope for simple mutation responses."""

    status: Literal["accepted", "ok"]
    message: str


class PageInfo(BaseModel):
    """Pagination metadata for collection responses."""

    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_items: int = Field(ge=0)


class AlertListItem(BaseModel):
    """Summary alert row consumed by the analyst feed."""

    id: str
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
    tags: list[str] = Field(default_factory=list)


class AlertListResponse(BaseModel):
    """Paginated alert feed response."""

    items: list[AlertListItem] = Field(default_factory=list)
    page: PageInfo


class PolicyCitation(BaseModel):
    """Policy reference surfaced with evidence or alerts."""

    citation_id: str
    title: str
    excerpt: str
    source_document_id: str


class PolicyTrendPointResponse(BaseModel):
    """One point in a policy gap trend series."""

    label: str
    value: float = Field(ge=0.0)


class PolicyGapSummaryResponse(BaseModel):
    """Summary row for the policy intelligence gap queue."""

    id: str
    title: str
    status: Literal["monitoring", "drafting", "recommended"]
    severity: Literal["medium", "high", "critical"]
    impacted_entities: int = Field(ge=0)
    affected_case_count: int = Field(ge=0)
    knowledge_base_id: str
    updated_at: datetime


class PolicyGapListResponse(BaseModel):
    """Collection response for policy intelligence gaps."""

    items: list[PolicyGapSummaryResponse] = Field(default_factory=list)
    page: PageInfo


class PolicyGapDetailResponse(BaseModel):
    """Expanded policy gap detail payload."""

    gap: PolicyGapSummaryResponse
    summary: str
    impact_statement: str
    recommendation: str
    policy_citations: list[PolicyCitation] = Field(default_factory=list)
    trend: list[PolicyTrendPointResponse] = Field(default_factory=list)


class PolicyGapCaseListResponse(BaseModel):
    """Case list attached to one policy gap."""

    gap_id: str
    items: list["CaseSummaryResponse"] = Field(default_factory=list)
    page: PageInfo


class PolicyBriefCreateRequest(BaseModel):
    """Payload for generating a policy brief from a gap."""

    gap_id: str
    audience: str
    objective: str


class PolicyBriefResponse(BaseModel):
    """Generated policy brief returned to the policy intelligence UI."""

    id: str
    gap_id: str
    title: str
    audience: str
    objective: str
    narrative: str
    recommendations: list[str] = Field(default_factory=list)
    policy_citations: list[PolicyCitation] = Field(default_factory=list)
    created_at: datetime


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
    related_entity_ids: list[str] = Field(default_factory=list)
    policy_citations: list[PolicyCitation] = Field(default_factory=list)


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
    neighbors: list[GraphNodeResponse] = Field(default_factory=list)
    relationships: list[GraphEdgeResponse] = Field(default_factory=list)
    related_alert_ids: list[str] = Field(default_factory=list)


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
    subgraph_node_ids: list[str] = Field(default_factory=list)
    subgraph_edge_ids: list[str] = Field(default_factory=list)
    items: list[EvidenceItemResponse] = Field(default_factory=list)
    policy_citations: list[PolicyCitation] = Field(default_factory=list)


class CaseSummaryResponse(BaseModel):
    """Case list item for the human review workflow."""

    id: str
    title: str
    status: Literal["open", "in_review", "closed"]
    priority: Literal["low", "medium", "high", "critical"]
    assignee: str | None = None
    alert_ids: list[str] = Field(default_factory=list)
    updated_at: datetime


class CaseListResponse(BaseModel):
    """Case collection response."""

    items: list[CaseSummaryResponse] = Field(default_factory=list)
    page: PageInfo


class AnalystFeedbackResponse(BaseModel):
    """Analyst feedback record attached to a case."""

    case_id: str
    label: Literal["suspicious", "not_suspicious", "insufficient_evidence"]
    evidence_adequacy: Literal["low", "medium", "high"]
    missing_evidence: list[str] = Field(default_factory=list)
    notes: str
    submitted_at: datetime


class CaseDetailResponse(BaseModel):
    """Expanded case detail payload."""

    case: CaseSummaryResponse
    alerts: list[AlertListItem] = Field(default_factory=list)
    feedback_history: list[AnalystFeedbackResponse] = Field(default_factory=list)


class ChatMessageResponse(BaseModel):
    """One message in a RAG chat conversation."""

    id: str
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: datetime
    citation_ids: list[str] = Field(default_factory=list)


class ChatConversationResponse(BaseModel):
    """Conversation state returned to the RAG chat UI."""

    id: str
    title: str
    knowledge_base_id: str
    messages: list[ChatMessageResponse] = Field(default_factory=list)


class KnowledgeBaseSummaryResponse(BaseModel):
    """Summary record for the knowledge base manager."""

    id: str
    name: str
    description: str
    status: Literal["active", "building", "ready", "error", "archived"]
    document_count: int = Field(ge=0)
    entity_count: int = Field(ge=0)
    relationship_count: int = Field(ge=0)
    created_at: datetime


class KnowledgeBaseListResponse(BaseModel):
    """Collection response for knowledge base summaries."""

    items: list[KnowledgeBaseSummaryResponse] = Field(default_factory=list)
    total: int = Field(ge=0)


class KnowledgeBaseDocumentResponse(BaseModel):
    """Document row displayed in knowledge base inventory views."""

    id: str
    knowledge_base_id: str
    filename: str
    content_type: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)
    status: Literal["pending", "registered", "building", "ready", "failed", "error"]
    created_at: datetime


class KnowledgeBaseDocumentListResponse(BaseModel):
    """Document inventory for one knowledge base."""

    items: list[KnowledgeBaseDocumentResponse] = Field(default_factory=list)
    total: int = Field(ge=0)


class KnowledgeBaseCreateRequest(BaseModel):
    """Payload for creating a new knowledge base."""

    name: str
    description: str


class WorkflowRunResponse(BaseModel):
    """Workflow run summary for pipeline status views."""

    id: str
    workflow_type: Literal["ingestion", "graph_build", "analytics", "monitoring"]
    status: Literal["queued", "running", "completed", "failed"]
    knowledge_base_id: str
    started_at: datetime
    updated_at: datetime
    current_step: str


class WorkflowRunListResponse(BaseModel):
    """Collection of workflow runs."""

    items: list[WorkflowRunResponse] = Field(default_factory=list)


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
    factors: list[RiskFactorResponse] = Field(default_factory=list)


class TimeseriesPointResponse(BaseModel):
    """One point in an entity timeseries chart."""

    timestamp: datetime
    value: float
    label: str
    is_anomaly: bool = False


class TimeseriesResponse(BaseModel):
    """Timeseries payload for entity trend charts."""

    entity_id: str
    metric_name: str
    points: list[TimeseriesPointResponse] = Field(default_factory=list)


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
    alert_ids: list[str] = Field(default_factory=list)


class CaseUpdateRequest(BaseModel):
    """Patch payload for updating a case."""

    title: str | None = None
    status: Literal["open", "in_review", "closed"] | None = None
    priority: Literal["low", "medium", "high", "critical"] | None = None
    assignee: str | None = None


class CaseFeedbackCreateRequest(BaseModel):
    """Payload for storing analyst feedback on a case."""

    label: Literal["suspicious", "not_suspicious", "insufficient_evidence"]
    evidence_adequacy: Literal["low", "medium", "high"]
    missing_evidence: list[str] = Field(default_factory=list)
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
    "EvidenceItemResponse",
    "EvidencePackResponse",
    "GraphEdgeResponse",
    "GraphEntityDetailResponse",
    "GraphNodeResponse",
    "KnowledgeBaseCreateRequest",
    "KnowledgeBaseDocumentListResponse",
    "KnowledgeBaseDocumentResponse",
    "KnowledgeBaseListResponse",
    "KnowledgeBaseSummaryResponse",
    "PageInfo",
    "PolicyBriefCreateRequest",
    "PolicyBriefResponse",
    "PolicyCitation",
    "PolicyGapCaseListResponse",
    "PolicyGapDetailResponse",
    "PolicyGapListResponse",
    "PolicyGapSummaryResponse",
    "PolicyTrendPointResponse",
    "RealtimeSnapshotResponse",
    "RiskFactorResponse",
    "RiskScoreResponse",
    "TimeseriesPointResponse",
    "TimeseriesResponse",
    "WorkflowRunListResponse",
    "WorkflowRunResponse",
]
