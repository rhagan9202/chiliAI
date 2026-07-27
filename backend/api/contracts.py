"""Frontend-facing API contracts for read-oriented backend surfaces."""

from __future__ import annotations

from datetime import date, datetime
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


class FeatureAttributionResponse(BaseModel):
    """A single feature's signed contribution to a risk score or alert."""

    feature_name: str
    contribution: float
    rationale: str = ""


class NarrativeSectionResponse(BaseModel):
    """A titled prose section of a generated evidence narrative."""

    heading: str
    body: str
    evidence_refs: list[str] = Field(default_factory=lambda: cast(list[str], []))


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
    attribution: list[FeatureAttributionResponse] = Field(
        default_factory=lambda: cast(list[FeatureAttributionResponse], [])
    )
    narrative_sections: list[NarrativeSectionResponse] = Field(
        default_factory=lambda: cast(list[NarrativeSectionResponse], [])
    )


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


class ChatConversationSummaryResponse(BaseModel):
    """One row in the conversation list (UXA-403).

    Carries enough to choose from — title, when it was last touched, how much
    was said, and the last thing said — without shipping every message.
    """

    id: str
    title: str
    knowledge_base_id: str
    message_count: int
    last_message: str | None = None
    updated_at: datetime


class ChatConversationListResponse(BaseModel):
    """A knowledge base's conversations, most recently updated first."""

    items: list[ChatConversationSummaryResponse] = Field(
        default_factory=lambda: cast(list[ChatConversationSummaryResponse], [])
    )
    page: PageInfo


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
    has_more: bool = False
    next_offset: int | None = None


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


ScorecardCompletenessValue = Literal[
    "complete",
    "missing_source",
    "stale_source",
    "formula_error",
]
ScorecardExportFormatValue = Literal["json", "markdown"]
ScorecardHealthValue = Literal["pass", "warn", "fail", "incomplete"]
ScorecardRunStatusValue = Literal["generated", "failed", "superseded"]


class ScorecardTemplateResponse(BaseModel):
    """Configured scorecard template summary for dashboard selectors."""

    id: str
    name: str
    category: Literal["UH", "MFH", "combined"]
    scope: Literal["enterprise", "majcom", "region", "installation", "market_area"]
    period: Literal["monthly", "quarterly", "annual", "ad_hoc"]


class ScorecardTemplateListResponse(BaseModel):
    """Configured scorecard templates."""

    items: list[ScorecardTemplateResponse] = Field(
        default_factory=lambda: cast(list[ScorecardTemplateResponse], [])
    )


class ScorecardRunGenerateRequest(BaseModel):
    """Payload for generating a scorecard run."""

    knowledge_base_id: str
    template_id: str
    scope_type: str
    scope_id: str
    period_start: date
    period_end: date


class ScorecardCitationResponse(BaseModel):
    """Source reference attached to one scorecard metric."""

    citation_id: str
    feed_name: str
    record_id: str
    field: str | None = None


class ScorecardMetricResponse(BaseModel):
    """Frontend-safe metric result with a stable metric_id field."""

    metric_id: str
    label: str
    description: str = ""
    unit: str = ""
    housing_category: Literal["UH", "MFH", "combined"] = "combined"
    value: float | None = None
    health: ScorecardHealthValue
    completeness: ScorecardCompletenessValue
    citations: list[ScorecardCitationResponse] = Field(
        default_factory=lambda: cast(list[ScorecardCitationResponse], [])
    )
    warnings: list[str] = Field(default_factory=lambda: cast(list[str], []))


class ScorecardSectionResponse(BaseModel):
    """A scorecard section with evaluated metrics."""

    id: str
    label: str
    metrics: list[ScorecardMetricResponse] = Field(
        default_factory=lambda: cast(list[ScorecardMetricResponse], [])
    )


class ScorecardRunResponse(BaseModel):
    """Frontend-facing scorecard run without stored export payloads."""

    id: str
    knowledge_base_id: str
    template_id: str
    template_name: str
    scope_type: str
    scope_id: str
    period_start: date
    period_end: date
    source_snapshot_hash: str
    status: ScorecardRunStatusValue
    overall_health: ScorecardHealthValue
    sections: list[ScorecardSectionResponse] = Field(
        default_factory=lambda: cast(list[ScorecardSectionResponse], [])
    )
    created_at: datetime
    updated_at: datetime


class ScorecardRunListResponse(BaseModel):
    """Paginated scorecard run collection."""

    items: list[ScorecardRunResponse] = Field(
        default_factory=lambda: cast(list[ScorecardRunResponse], [])
    )
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class ScorecardExportResponse(BaseModel):
    """Stored scorecard export content."""

    run_id: str
    format: ScorecardExportFormatValue
    content: str


class HousingPortfolioSummaryResponse(BaseModel):
    """Empty-safe executive housing portfolio totals."""

    total_installations: int = Field(default=0, ge=0)
    installations_reporting: int = Field(default=0, ge=0)
    open_work_orders: int = Field(default=0, ge=0)
    overdue_work_orders: int = Field(default=0, ge=0)
    occupancy_rate: float | None = None
    resident_satisfaction: float | None = None


class HousingExecutiveKpiResponse(BaseModel):
    """One executive KPI in the Air Force housing dashboard."""

    id: str
    label: str
    value: float | None = None
    unit: str = ""
    status: Literal["ok", "watch", "critical", "unknown"] = "unknown"


class HousingOverviewResponse(BaseModel):
    """Safe empty overview payload for the housing executive dashboard."""

    period_start: date | None = None
    period_end: date | None = None
    portfolio_summary: HousingPortfolioSummaryResponse = Field(
        default_factory=HousingPortfolioSummaryResponse
    )
    executive_kpis: list[HousingExecutiveKpiResponse] = Field(
        default_factory=lambda: cast(list[HousingExecutiveKpiResponse], [])
    )


class HousingInstallationResponse(BaseModel):
    """One installation row for the housing dashboard.

    Carries the per-installation inputs (value + weight pairs, work-order
    counts, supply/authorization totals) sufficient to recompute every
    ``/housing/overview`` portfolio aggregate for any filtered subset with
    identical semantics — each field's description documents its weighting
    role and formula. Count aggregates derive from ``status``:
    total = row count, reporting = rows with ``status != "unknown"``,
    critical = rows with ``status == "critical"``.
    """

    installation_id: str
    name: str
    majcom: str | None = None
    state: str | None = None
    branch: str | None = None
    status: Literal["ok", "watch", "critical", "unknown"] = "unknown"
    status_reasons: list[str] = Field(
        default_factory=lambda: cast(list[str], []),
        description=(
            "Human-readable threshold findings behind status, one per tripped "
            "metric band (metric, observed value, threshold). Empty for ok; "
            "a single no-data reason for unknown."
        ),
    )
    open_work_orders: int = Field(default=0, ge=0)
    open_work_orders_rank: int | None = Field(
        default=None,
        ge=1,
        description=(
            "1-based competition rank by open work orders (1 = most) among "
            "reporting installations; ties share the smaller rank. None when "
            "the installation reports no inventory or resident-experience "
            "data."
        ),
    )
    occupancy_rate: float | None = Field(
        default=None,
        description=(
            "Occupancy as the unit-weighted utilization across this "
            "installation's inventory rows that reported a utilization rate, "
            "each weighted by its total units (available + offline); rounded "
            "to 4 decimals. None when no row reported utilization. Portfolio "
            "occupancy over any subset = sum(occupancy_rate * "
            "occupancy_unit_weight) / sum(occupancy_unit_weight) across "
            "installations where occupancy_unit_weight is non-null."
        ),
    )
    occupancy_unit_weight: float | None = Field(
        default=None,
        ge=0.0,
        description=(
            "Weight behind occupancy_rate: total units (available + offline) "
            "summed over the inventory rows that reported a utilization rate. "
            "None when no row reported utilization. This is the weight in the "
            "portfolio occupancy formula on occupancy_rate."
        ),
    )
    condition_index: float | None = Field(
        default=None,
        description=(
            "Unit-weighted condition index: sum(condition_index * "
            "available_units) / sum(available_units) over this installation's "
            "inventory rows that reported a condition index (the scorecard's "
            "weighted_mean semantics). None when no row reported condition. "
            "Portfolio Average Condition Index over any subset = "
            "sum(condition_index * condition_unit_weight) / "
            "sum(condition_unit_weight) across installations where "
            "condition_unit_weight is non-null."
        ),
    )
    condition_unit_weight: float | None = Field(
        default=None,
        ge=0.0,
        description=(
            "Weight behind condition_index: available units summed over the "
            "inventory rows that reported a condition index (offline units "
            "carry no condition weight). None when no row reported condition. "
            "This is the weight in the portfolio condition formula on "
            "condition_index."
        ),
    )
    resident_satisfaction: float | None = Field(
        default=None,
        description=(
            "Mean satisfaction score across this installation's resident "
            "experience survey rows (unweighted within the installation). "
            "None when no survey reported a score. Portfolio Resident "
            "Satisfaction over any subset is the flat mean across every "
            "survey value = sum(resident_satisfaction * "
            "satisfaction_survey_count) / sum(satisfaction_survey_count) "
            "across installations with a non-zero count."
        ),
    )
    satisfaction_survey_count: int = Field(
        default=0,
        ge=0,
        description=(
            "Number of resident-experience rows that reported a satisfaction "
            "score — the weight behind resident_satisfaction in the portfolio "
            "satisfaction formula. 0 when unreported (resident_satisfaction "
            "is then None)."
        ),
    )
    overdue_work_orders: int = Field(
        default=0,
        ge=0,
        description=(
            "Overdue work orders summed from resident-experience rows. "
            "Portfolio Work Orders Overdue rate over any subset = "
            "sum(overdue_work_orders) / sum(open_work_orders), unknown when "
            "sum(open_work_orders) is 0."
        ),
    )
    uh_available_units: float | None = Field(
        default=None,
        ge=0.0,
        description=(
            "Available unaccompanied-housing units summed from UH inventory "
            "rows. None when no UH inventory row landed (absent data, not "
            "zero supply). Portfolio UH Supply Ratio over any subset = "
            "sum(uh_available_units) / sum(uh_authorized_units), unknown "
            "unless sum(uh_authorized_units) > 0 and at least one "
            "installation has non-null uh_available_units."
        ),
    )
    uh_authorized_units: float = Field(
        default=0.0,
        ge=0.0,
        description=(
            "UMD unaccompanied authorizations summed for this installation — "
            "the denominator contribution in the portfolio UH Supply Ratio. "
            "0 when no UMD authorization row reported (contributes nothing "
            "to the sum or the sum > 0 gate)."
        ),
    )
    mfh_available_units: float | None = Field(
        default=None,
        ge=0.0,
        description=(
            "Available military family housing units summed from MFH "
            "inventory rows. None when no MFH inventory row landed (absent "
            "data, not zero supply). Portfolio MFH Supply Ratio over any "
            "subset = sum(mfh_available_units) / sum(mfh_authorized_units), "
            "unknown unless sum(mfh_authorized_units) > 0 and at least one "
            "installation has non-null mfh_available_units."
        ),
    )
    mfh_authorized_units: float = Field(
        default=0.0,
        ge=0.0,
        description=(
            "UMD accompanied authorizations summed for this installation — "
            "the denominator contribution in the portfolio MFH Supply Ratio. "
            "0 when no UMD authorization row reported (contributes nothing "
            "to the sum or the sum > 0 gate)."
        ),
    )


class HousingInstallationMapPointResponse(BaseModel):
    """Map point for one housing installation."""

    installation_id: str
    name: str
    latitude: float
    longitude: float
    branch: str | None = None
    status: Literal["ok", "watch", "critical", "unknown"] = "unknown"


class HousingInstallationsResponse(BaseModel):
    """Safe empty installation list and map payload."""

    period_start: date | None = None
    period_end: date | None = None
    total: int = Field(default=0, ge=0)
    items: list[HousingInstallationResponse] = Field(
        default_factory=lambda: cast(list[HousingInstallationResponse], [])
    )
    map_points: list[HousingInstallationMapPointResponse] = Field(
        default_factory=lambda: cast(list[HousingInstallationMapPointResponse], [])
    )


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
    "HousingExecutiveKpiResponse",
    "HousingInstallationMapPointResponse",
    "HousingInstallationResponse",
    "HousingInstallationsResponse",
    "HousingOverviewResponse",
    "HousingPortfolioSummaryResponse",
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
    "ScorecardCitationResponse",
    "ScorecardExportFormatValue",
    "ScorecardExportResponse",
    "ScorecardMetricResponse",
    "ScorecardRunGenerateRequest",
    "ScorecardRunListResponse",
    "ScorecardRunResponse",
    "ScorecardSectionResponse",
    "ScorecardTemplateListResponse",
    "ScorecardTemplateResponse",
    "WorkflowRunListResponse",
    "WorkflowRunResponse",
]
