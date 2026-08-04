"""Frontend-facing API contracts for read-oriented backend surfaces."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, cast

from pydantic import BaseModel, Field, model_validator

from config.schema import CapabilitiesConfig, UiRoleConfig
from shared.types import Entity


class PageInfo(BaseModel):
    """Pagination metadata for collection responses."""

    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_items: int = Field(ge=0)


class AuditEventResponse(BaseModel):
    """One immutable audit ledger event."""

    event_id: str
    occurred_at: datetime
    tenant_id: str
    knowledge_base_id: str | None = None
    actor_user_id: str
    actor_email: str | None = None
    actor_roles: list[str] = Field(default_factory=lambda: cast(list[str], []))
    action: str
    resource_type: str
    resource_id: str
    before: dict[str, object | None] | None = None
    after: dict[str, object | None] | None = None
    correlation_id: str
    client_ip: str | None = None
    user_agent: str | None = None
    outcome: Literal["success", "failure"]
    failure_reason: str | None = None
    metadata: dict[str, object | None] = Field(default_factory=dict)


class AuditEventListResponse(BaseModel):
    """Paginated audit ledger query response."""

    items: list[AuditEventResponse] = Field(
        default_factory=lambda: cast(list[AuditEventResponse], [])
    )
    page: PageInfo


class AuditWriteFailureResponse(BaseModel):
    """One captured audit sink write failure."""

    occurred_at: datetime
    action: str
    resource_type: str
    resource_id: str
    error_class: str
    error_message: str


class AuditStatusResponse(BaseModel):
    """Operational audit ledger write-failure status."""

    failed_write_count: int = Field(ge=0)
    recent_write_failures: list[AuditWriteFailureResponse] = Field(
        default_factory=lambda: cast(list[AuditWriteFailureResponse], [])
    )


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
    # Last write to the row. For an acknowledged alert whose only update was
    # the acknowledgement this is when that happened, which is what lets the
    # Queue Health tab measure time-to-acknowledge (UXA-402).
    updated_at: datetime
    tags: list[str] = Field(default_factory=lambda: cast(list[str], []))
    assignee: str | None = None
    generation_metadata: dict[str, Any] = Field(default_factory=dict)


class AlertListResponse(BaseModel):
    """Paginated alert feed response."""

    items: list[AlertListItem] = Field(default_factory=lambda: cast(list[AlertListItem], []))
    page: PageInfo


class AlertAssignmentRequest(BaseModel):
    """Assign or clear assignment for one KB-scoped alert."""

    knowledge_base_id: str = Field(min_length=1)
    assignee: str | None = None


class AlertStatusUpdateRequest(BaseModel):
    """Transition one KB-scoped alert to a new lifecycle status."""

    knowledge_base_id: str = Field(min_length=1)
    status: Literal["open", "acknowledged", "investigating", "resolved", "dismissed"]
    reason: str | None = None


class AlertBulkStatusUpdateRequest(BaseModel):
    """Transition a selected group of KB-scoped alerts where transitions are valid."""

    knowledge_base_id: str = Field(min_length=1)
    alert_ids: list[str] = Field(min_length=1)
    status: Literal["open", "acknowledged", "investigating", "resolved", "dismissed"]
    reason: str | None = None


class AlertTriageEventResponse(BaseModel):
    """Audit receipt for an alert assignment or lifecycle transition."""

    event_type: Literal["assigned", "status_changed"]
    actor: str
    occurred_at: datetime
    assignee: str | None = None
    from_status: str | None = None
    to_status: str | None = None
    reason: str | None = None


class AlertOperationResponse(BaseModel):
    """Response for one alert queue mutation."""

    status: Literal["accepted"]
    message: str
    alert: AlertListItem
    audit_event: AlertTriageEventResponse


class AlertBulkRejection(BaseModel):
    """One alert skipped by a bulk lifecycle mutation."""

    alert_id: str
    reason: Literal["not_found", "invalid_transition"]


class AlertBulkStatusUpdateResponse(BaseModel):
    """Response for a bulk alert lifecycle mutation."""

    status: Literal["accepted"]
    message: str
    updated_alerts: list[AlertListItem] = Field(
        default_factory=lambda: cast(list[AlertListItem], [])
    )
    rejected_alerts: list[AlertBulkRejection] = Field(
        default_factory=lambda: cast(list[AlertBulkRejection], [])
    )


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


EvidenceExportFormat = Literal["json", "markdown"]


class EvidencePackExportResponse(BaseModel):
    """A portable rendering of one evidence pack (UXA-405).

    Mirrors ``ScorecardExportResponse``, the product's only other export, so
    there is one export idiom rather than two. ``filename`` is server-chosen so
    the download name is decided once rather than reconstructed by every caller.
    """

    evidence_pack_id: str
    format: EvidenceExportFormat
    filename: str
    content: str


class PolicyItemListResponse(BaseModel):
    """Collection response for KB-scoped policy items."""

    items: list[PolicyItemSummaryResponse] = Field(
        default_factory=lambda: cast(list[PolicyItemSummaryResponse], [])
    )
    total: int = 0
    status_counts: dict[str, int] = Field(
        default_factory=lambda: cast(dict[str, int], {}),
        description=(
            "Item counts per status across the whole knowledge base, ignoring "
            "the active filter. The filter UI shows a count beside every status "
            "option; tallying the filtered page instead would collapse every "
            "other option to zero the moment one was selected (UXA-401)."
        ),
    )


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


class FeatureSourceMappingResponse(BaseModel):
    """A source path used to derive a normalized feature value."""

    source_type: str
    source_ref: str
    raw_fields: list[str] = Field(default_factory=lambda: cast(list[str], []))


class FeatureDefinitionResponse(BaseModel):
    """A reusable, domain-neutral feature definition."""

    id: str
    label: str
    description: str
    value_type: Literal["boolean", "integer", "decimal", "string", "categorical"]
    entity_types: list[str] = Field(default_factory=lambda: cast(list[str], []))
    source_mappings: list[FeatureSourceMappingResponse] = Field(
        default_factory=lambda: cast(list[FeatureSourceMappingResponse], [])
    )
    peer_dimensions: list[str] = Field(default_factory=lambda: cast(list[str], []))
    threshold_hints: dict[str, float] = Field(default_factory=dict)
    transformation_version: str
    typology_ids: list[str] = Field(default_factory=lambda: cast(list[str], []))


class FraudTypologyResponse(BaseModel):
    """A versioned fraud-pattern label described by a domain pack."""

    id: str
    label: str
    description: str
    entity_types: list[str] = Field(default_factory=lambda: cast(list[str], []))
    severity_hint: Literal["low", "medium", "high", "critical"] | None = None
    feature_ids: list[str] = Field(default_factory=lambda: cast(list[str], []))
    policy_rule_ids: list[str] = Field(default_factory=lambda: cast(list[str], []))
    playbook_ids: list[str] = Field(default_factory=lambda: cast(list[str], []))


class FeatureCatalogResponse(BaseModel):
    """Feature catalog metadata scoped to a knowledge base."""

    knowledge_base_id: str
    catalog_version: str
    typologies: list[FraudTypologyResponse] = Field(
        default_factory=lambda: cast(list[FraudTypologyResponse], [])
    )
    features: list[FeatureDefinitionResponse] = Field(
        default_factory=lambda: cast(list[FeatureDefinitionResponse], [])
    )


class EntityFeatureValueResponse(BaseModel):
    """One normalized feature value for an entity."""

    feature_id: str
    entity_type: str
    entity_id: str
    value: str | int | float | bool | None = None
    normalized_value: float | None = Field(default=None, ge=0.0, le=1.0)
    catalog_version: str
    transformation_version: str
    source_refs: list[str] = Field(default_factory=lambda: cast(list[str], []))
    observed_at: datetime | None = None
    score_run_id: str | None = None


class EntityFeatureValueListResponse(BaseModel):
    """Feature values for one entity in a knowledge base."""

    knowledge_base_id: str
    entity_type: str
    entity_id: str
    items: list[EntityFeatureValueResponse] = Field(
        default_factory=lambda: cast(list[EntityFeatureValueResponse], [])
    )


IdentityMatchConfidenceValue = Literal["high", "medium", "low"]
IdentityReviewStateValue = Literal["auto_linkable", "steward_review", "needs_review"]
IdentityLinkReviewStateValue = Literal[
    "auto_linkable",
    "steward_review",
    "needs_review",
    "merged",
    "rejected",
    "split",
]
IdentityLinkDecisionValue = Literal["approve_merge", "reject_merge", "split_identity"]


class IdentityMatchReasonResponse(BaseModel):
    """One reason contributing to an identity candidate score."""

    field: str
    reason: str
    source_value: str
    candidate_value: str
    score_contribution: float = Field(ge=0.0, le=1.0)


class IdentityCandidateEntityRequest(BaseModel):
    """Candidate canonical entity scoped to one knowledge base."""

    knowledge_base_id: str = Field(min_length=1)
    entity: Entity


class IdentityResolutionRequestPayload(BaseModel):
    """Payload for scoring a source identity against canonical candidates."""

    knowledge_base_id: str = Field(min_length=1)
    source_entity: Entity
    candidates: list[IdentityCandidateEntityRequest] = Field(
        default_factory=lambda: cast(list[IdentityCandidateEntityRequest], [])
    )
    natural_key_fields: list[str] = Field(default_factory=lambda: cast(list[str], []))
    identifier_fields: list[str] = Field(default_factory=lambda: cast(list[str], []))
    address_fields: list[str] = Field(default_factory=lambda: cast(list[str], []))


class IdentityCandidateScoreResponse(BaseModel):
    """Scored canonical identity candidate."""

    knowledge_base_id: str
    entity_id: str
    entity_type: str
    score: float = Field(ge=0.0, le=1.0)
    confidence: IdentityMatchConfidenceValue
    review_state: IdentityReviewStateValue
    match_reasons: list[IdentityMatchReasonResponse] = Field(
        default_factory=lambda: cast(list[IdentityMatchReasonResponse], [])
    )


class IdentityResolutionResponse(BaseModel):
    """Ranked identity candidates for a source entity."""

    knowledge_base_id: str
    source_entity_id: str
    candidates: list[IdentityCandidateScoreResponse] = Field(
        default_factory=lambda: cast(list[IdentityCandidateScoreResponse], [])
    )
    excluded_candidate_ids: list[str] = Field(default_factory=lambda: cast(list[str], []))


class IdentityLinkDecisionRecordResponse(BaseModel):
    """One steward decision recorded against an identity link."""

    decision: IdentityLinkDecisionValue
    actor_user_id: str
    comment: str | None = None
    created_at: datetime


class IdentityLinkResponse(BaseModel):
    """Stored identity link returned by the API."""

    id: str
    knowledge_base_id: str
    canonical_entity_id: str
    source_entity_id: str
    relationship_type: str
    confidence: IdentityMatchConfidenceValue
    score: float = Field(ge=0.0, le=1.0)
    review_state: IdentityLinkReviewStateValue
    decision_source: str
    source_refs: list[str] = Field(default_factory=lambda: cast(list[str], []))
    match_reasons: list[dict[str, Any]] = Field(
        default_factory=lambda: cast(list[dict[str, Any]], [])
    )
    decision_history: list[IdentityLinkDecisionRecordResponse] = Field(
        default_factory=lambda: cast(list[IdentityLinkDecisionRecordResponse], [])
    )
    created_at: datetime
    updated_at: datetime


class CanonicalIdentityDetailResponse(BaseModel):
    """Source identities linked to one canonical entity."""

    knowledge_base_id: str
    canonical_entity_id: str
    links: list[IdentityLinkResponse] = Field(
        default_factory=lambda: cast(list[IdentityLinkResponse], [])
    )
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class IdentityLinkDecisionRequestPayload(BaseModel):
    """Payload for recording a steward identity-link decision."""

    knowledge_base_id: str = Field(min_length=1)
    decision: IdentityLinkDecisionValue
    tenant_id: str = Field(default="platform", min_length=1)
    correlation_id: str | None = Field(default=None, min_length=1)
    comment: str | None = None


ScoreRunStatusValue = Literal["queued", "running", "completed", "failed", "canceled", "replayed"]
ScoreBatchStatusValue = Literal["queued", "running", "completed", "failed", "canceled", "replayed"]


class ScoreRunStartRequest(BaseModel):
    """Payload for starting a KB-scoped score-all run."""

    entity_ids: list[str] | None = Field(default=None, min_length=1)
    requested_by: str | None = None
    model_version: str
    catalog_version: str
    idempotency_key: str | None = None
    batch_size: int = Field(default=100, gt=0, le=1000)


class ScoreRunReplayRequest(BaseModel):
    """Payload for replaying failed score batches."""

    requested_by: str | None = None
    idempotency_key: str | None = None


class ScoreBatchResponse(BaseModel):
    """Score-all batch state."""

    id: str
    run_id: str
    knowledge_base_id: str
    batch_number: int = Field(ge=0)
    status: ScoreBatchStatusValue
    entity_ids: list[str] = Field(default_factory=lambda: cast(list[str], []))
    attempts: int = Field(ge=0)
    error_summary: str | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ScoreRunResponse(BaseModel):
    """Score-all run state."""

    id: str
    knowledge_base_id: str
    status: ScoreRunStatusValue
    requested_by: str | None = None
    idempotency_key: str | None = None
    model_version: str
    catalog_version: str
    replay_of_run_id: str | None = None
    total_entities: int = Field(ge=0)
    scored_entities: int = Field(ge=0)
    failed_entities: int = Field(ge=0)
    error_summary: str | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ScoreRunDetailResponse(BaseModel):
    """Score run plus current batches."""

    run: ScoreRunResponse
    batches: list[ScoreBatchResponse] = Field(
        default_factory=lambda: cast(list[ScoreBatchResponse], [])
    )
    created: bool = False


class ScoreRunListResponse(BaseModel):
    """Page of score-all runs for one knowledge base."""

    items: list[ScoreRunResponse] = Field(default_factory=lambda: cast(list[ScoreRunResponse], []))
    total: int = Field(ge=0)
    limit: int = Field(ge=0)
    offset: int = Field(ge=0)


PlaybookStatusValue = Literal["draft", "published", "retired"]
PlaybookSnapshotSourceValue = Literal["domain_config", "api_import", "api_publish"]


class PlaybookEvidenceRequirementResponse(BaseModel):
    """Evidence requirement configured for one fraud playbook."""

    id: str
    label: str
    description: str = ""
    source_types: list[str] = Field(default_factory=lambda: cast(list[str], []))
    required: bool = True


class PlaybookWorkflowStepResponse(BaseModel):
    """Workflow template step configured for one fraud playbook."""

    id: str
    label: str
    capability_ref: str
    input_refs: list[str] = Field(default_factory=lambda: cast(list[str], []))
    output_refs: list[str] = Field(default_factory=lambda: cast(list[str], []))
    requires_human_approval: bool = False


class PlaybookRagPromptResponse(BaseModel):
    """RAG prompt template configured for one fraud playbook."""

    id: str
    model_ref: str
    prompt_version: str
    system_prompt: str
    user_prompt: str


class PlaybookResponse(BaseModel):
    """Config-authored fraud playbook definition."""

    id: str
    version: str
    title: str
    summary: str = ""
    status: PlaybookStatusValue
    typology_ids: list[str] = Field(default_factory=lambda: cast(list[str], []))
    feature_ids: list[str] = Field(default_factory=lambda: cast(list[str], []))
    policy_rule_ids: list[str] = Field(default_factory=lambda: cast(list[str], []))
    evidence_requirements: list[PlaybookEvidenceRequirementResponse] = Field(
        default_factory=lambda: cast(list[PlaybookEvidenceRequirementResponse], [])
    )
    workflow_steps: list[PlaybookWorkflowStepResponse] = Field(
        default_factory=lambda: cast(list[PlaybookWorkflowStepResponse], [])
    )
    rag_prompts: list[PlaybookRagPromptResponse] = Field(
        default_factory=lambda: cast(list[PlaybookRagPromptResponse], [])
    )
    decision_guidance: list[str] = Field(default_factory=lambda: cast(list[str], []))
    export_tags: list[str] = Field(default_factory=lambda: cast(list[str], []))


class PlaybookSnapshotResponse(BaseModel):
    """Immutable published playbook snapshot."""

    snapshot_id: str
    domain_name: str
    playbook_id: str
    version: str
    status: PlaybookStatusValue
    definition: PlaybookResponse
    source: PlaybookSnapshotSourceValue
    published_by: str
    published_at: datetime
    created_at: datetime
    updated_at: datetime


class PlaybookListResponse(BaseModel):
    """KB-scoped playbook catalog page plus published snapshots."""

    items: list[PlaybookResponse] = Field(
        default_factory=lambda: cast(list[PlaybookResponse], [])
    )
    published: list[PlaybookSnapshotResponse] = Field(
        default_factory=lambda: cast(list[PlaybookSnapshotResponse], [])
    )
    total: int = Field(ge=0)
    limit: int = Field(ge=0)
    offset: int = Field(ge=0)
    published_total: int = Field(ge=0)
    published_limit: int = Field(ge=0)
    published_offset: int = Field(ge=0)


class PlaybookPublishRequestPayload(BaseModel):
    """Payload for publishing a config-authored playbook seed."""

    version: str = Field(default="v1", min_length=1)


class PlaybookImportRequestPayload(BaseModel):
    """Payload for importing portable domain playbooks."""

    artifact: dict[str, object]


class PlaybookImportResponse(BaseModel):
    """Import result summary."""

    domain_name: str
    imported_count: int = Field(ge=0)
    snapshot_ids: list[str] = Field(default_factory=lambda: cast(list[str], []))


class PlaybookExportResponse(BaseModel):
    """Portable playbook artifact wrapper."""

    artifact: dict[str, object]


class NarrativeSectionResponse(BaseModel):
    """A titled prose section of a generated evidence narrative."""

    heading: str
    body: str
    evidence_refs: list[str] = Field(default_factory=lambda: cast(list[str], []))


class EvidenceProvenanceReferenceResponse(BaseModel):
    """A normalized source reference supporting an evidence pack assertion."""

    reference_type: str = Field(min_length=1)
    reference_id: str = Field(min_length=1)
    label: str = ""
    source_system: str | None = None
    source_version: str | None = None
    transformation_version: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    route_target: str | None = None
    metadata: dict[str, object | None] = Field(default_factory=dict)


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
    provenance: list[EvidenceProvenanceReferenceResponse] = Field(
        default_factory=lambda: cast(list[EvidenceProvenanceReferenceResponse], [])
    )
    # When the explanation was generated and what it was drawn from. Both are
    # already on the persisted pack; without them the narrative is an
    # unattributed, undated assertion (UXA-405).
    created_at: datetime
    source_documents: list[str] = Field(default_factory=lambda: cast(list[str], []))


class EvidenceProvenanceListResponse(BaseModel):
    """Structured provenance references for one evidence pack."""

    knowledge_base_id: str
    evidence_pack_id: str
    items: list[EvidenceProvenanceReferenceResponse] = Field(
        default_factory=lambda: cast(list[EvidenceProvenanceReferenceResponse], [])
    )


ExplanationReviewTargetType = Literal[
    "narrative",
    "narrative_section",
    "feature_attribution",
    "evidence_item",
    "provenance_reference",
]
ExplanationReviewState = Literal[
    "useful",
    "incomplete",
    "misleading",
    "unsupported",
    "approved",
    "rejected",
    "regeneration_requested",
]
ExplanationReviewReason = Literal[
    "missing_source",
    "wrong_peer_group",
    "stale_data",
    "unsupported_claim",
    "contradicts_evidence",
    "unclear_rationale",
    "other",
]
_EXPLANATION_REVIEW_REASON_REQUIRED_STATES: set[ExplanationReviewState] = {
    "incomplete",
    "misleading",
    "unsupported",
    "rejected",
    "regeneration_requested",
}


class ExplanationReviewTargetResponse(BaseModel):
    """One reviewable subtarget inside an evidence pack."""

    target_type: ExplanationReviewTargetType
    target_id: str = Field(min_length=1)


class ExplanationReviewCreateRequest(BaseModel):
    """Create or update one analyst review of an explanation target."""

    target: ExplanationReviewTargetResponse
    state: ExplanationReviewState
    reasons: list[ExplanationReviewReason] = Field(
        default_factory=lambda: cast(list[ExplanationReviewReason], [])
    )
    comment: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _validate_reason_codes(self) -> ExplanationReviewCreateRequest:
        if self.state in _EXPLANATION_REVIEW_REASON_REQUIRED_STATES and not self.reasons:
            raise ValueError(f"Review state '{self.state}' requires at least one reason.")
        return self


class ExplanationReviewResponse(BaseModel):
    """Stored analyst review state for one explanation target."""

    id: str
    knowledge_base_id: str
    evidence_pack_id: str
    target: ExplanationReviewTargetResponse
    state: ExplanationReviewState
    reasons: list[ExplanationReviewReason] = Field(
        default_factory=lambda: cast(list[ExplanationReviewReason], [])
    )
    comment: str | None = None
    actor_user_id: str
    actor_email: str | None = None
    created_at: datetime
    updated_at: datetime
    update_count: int = Field(ge=0)


class ExplanationReviewListResponse(BaseModel):
    """Page of review state for one evidence pack."""

    knowledge_base_id: str
    evidence_pack_id: str
    items: list[ExplanationReviewResponse] = Field(
        default_factory=lambda: cast(list[ExplanationReviewResponse], [])
    )
    page: PageInfo


class CaseExplanationReviewSummaryResponse(BaseModel):
    """Sanitized case-dossier summary for one explanation review."""

    evidence_pack_id: str
    review_id: str
    target: ExplanationReviewTargetResponse
    state: ExplanationReviewState
    reason_count: int = Field(ge=0)
    updated_at: datetime


class EntityLocationResponse(BaseModel):
    """One knowledge base that holds a given entity (UXA-104)."""

    knowledge_base_id: str
    knowledge_base_name: str


class EntityLocationListResponse(BaseModel):
    """Where an entity lives, so a deep link with no `?kb=` can recover."""

    items: list[EntityLocationResponse] = Field(
        default_factory=lambda: cast(list[EntityLocationResponse], [])
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


class CaseDossierExportMetadataResponse(BaseModel):
    """Export affordances advertised with a case dossier."""

    formats: list[EvidenceExportFormat] = Field(
        default_factory=lambda: cast(list[EvidenceExportFormat], ["markdown", "json"])
    )
    default_filename: str


class CaseDossierResponse(BaseModel):
    """Case-level dossier preserving alerts, evidence, chronology, and decisions."""

    case: CaseSummaryResponse
    alerts: list[AlertListItem] = Field(default_factory=lambda: cast(list[AlertListItem], []))
    evidence_packs: list[EvidencePackResponse] = Field(
        default_factory=lambda: cast(list[EvidencePackResponse], [])
    )
    explanation_review_summaries: list[CaseExplanationReviewSummaryResponse] = Field(
        default_factory=lambda: cast(list[CaseExplanationReviewSummaryResponse], [])
    )
    entity_timeline: list[CaseTimelineEventResponse] = Field(
        default_factory=lambda: cast(list[CaseTimelineEventResponse], [])
    )
    feedback_history: list[AnalystFeedbackResponse] = Field(default_factory=lambda: cast(list[AnalystFeedbackResponse], []))
    audit_events: list[AuditEventResponse] = Field(
        default_factory=lambda: cast(list[AuditEventResponse], [])
    )
    export: CaseDossierExportMetadataResponse


class CaseDossierExportResponse(BaseModel):
    """Portable case dossier rendering for reviewer handoff."""

    case_id: str
    knowledge_base_id: str
    format: EvidenceExportFormat
    filename: str
    content: str


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


RiskProjectionLevelValue = Literal["low", "medium", "high", "critical"]
RiskProjectionStatusValue = Literal["active", "case_open", "resolved", "suppressed", "stale"]
RiskProjectionRebuildStatusValue = Literal["completed"]


class RiskProjectionItemResponse(BaseModel):
    """Projection-backed risk row for queue/dashboard/entity consumers."""

    knowledge_base_id: str
    entity_id: str
    entity_type: str
    overall_score: float = Field(ge=0.0, le=1.0)
    risk_level: RiskProjectionLevelValue
    top_typology_ids: list[str] = Field(default_factory=lambda: cast(list[str], []))
    alert_ids: list[str] = Field(default_factory=lambda: cast(list[str], []))
    case_ids: list[str] = Field(default_factory=lambda: cast(list[str], []))
    evidence_pack_ids: list[str] = Field(default_factory=lambda: cast(list[str], []))
    score_run_id: str | None = None
    model_version: str
    catalog_version: str
    scored_at: datetime
    updated_at: datetime
    status: RiskProjectionStatusValue


class RiskProjectionListResponse(BaseModel):
    """Paginated risk projections for one knowledge base."""

    knowledge_base_id: str
    items: list[RiskProjectionItemResponse] = Field(
        default_factory=lambda: cast(list[RiskProjectionItemResponse], [])
    )
    total: int = Field(ge=0)
    limit: int = Field(ge=0)
    offset: int = Field(ge=0)


class RiskProjectionRebuildRequest(BaseModel):
    """Operator request to rebuild risk projections for one knowledge base."""

    knowledge_base_id: str = Field(min_length=1)


class RiskProjectionRebuildResponse(BaseModel):
    """Outcome of an in-process projection rebuild request."""

    knowledge_base_id: str
    changed: bool
    deleted: int = Field(ge=0)
    upserted: int = Field(ge=0)
    status: RiskProjectionRebuildStatusValue = "completed"


PeerAnalysisConfidenceValue = Literal["normal", "low"]


class PeerDistributionSummaryResponse(BaseModel):
    """Metric distribution summary for one peer group."""

    count: int = Field(ge=0)
    minimum: float
    p50: float
    p90: float
    maximum: float


class PeerCohortExclusionResponse(BaseModel):
    """Configured cohort exclusion rule."""

    field: str
    operator: str
    values: list[str] = Field(default_factory=lambda: cast(list[str], []))
    reason: str


class PeerCohortContextResponse(BaseModel):
    """Cohort definition and membership context for one comparison."""

    id: str
    label: str
    version: str
    entity_type: str
    peer_metric: str
    group_by: list[str] = Field(default_factory=lambda: cast(list[str], []))
    group_values: dict[str, str] = Field(default_factory=dict[str, str])
    exclusions: list[PeerCohortExclusionResponse] = Field(
        default_factory=lambda: cast(list[PeerCohortExclusionResponse], [])
    )
    member_entity_ids: list[str] = Field(default_factory=lambda: cast(list[str], []))
    member_count: int = Field(ge=0)


class PeerMetricComparisonResponse(BaseModel):
    """One peer-metric comparison for an entity."""

    metric_name: str
    entity_type: str
    interval_start: datetime
    peer_group_key: str
    entity_value: float
    peer_mean: float
    peer_std: float = Field(ge=0.0)
    z_score: float
    signal_value: float = Field(ge=0.0, le=1.0)
    cohort_size: int = Field(ge=0)
    percentile: float = Field(ge=0.0, le=100.0)
    rationale: str
    confidence: PeerAnalysisConfidenceValue = "normal"
    confidence_reason: str | None = None
    distribution: PeerDistributionSummaryResponse | None = None
    cohort: PeerCohortContextResponse | None = None


class PeerAnalysisResponse(BaseModel):
    """Peer-analysis context for one entity."""

    knowledge_base_id: str
    entity_id: str
    metrics: list[PeerMetricComparisonResponse] = Field(
        default_factory=lambda: cast(list[PeerMetricComparisonResponse], [])
    )


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


class CaseAttachAlertRequest(BaseModel):
    """Payload for attaching an alert to a case that already exists (UXA-405)."""

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
    "AuditEventListResponse",
    "AuditEventResponse",
    "AuditStatusResponse",
    "AuditWriteFailureResponse",
    "AlertAssignmentRequest",
    "AlertBulkRejection",
    "AlertBulkStatusUpdateRequest",
    "AlertBulkStatusUpdateResponse",
    "AlertDetailResponse",
    "AlertListItem",
    "AlertListResponse",
    "AlertOperationResponse",
    "AlertStatusUpdateRequest",
    "AlertTriageEventResponse",
    "AnalystFeedbackResponse",
    "AnalyticsOverviewResponse",
    "CaseCreateRequest",
    "CaseDossierExportMetadataResponse",
    "CaseDossierExportResponse",
    "CaseDossierResponse",
    "CaseExplanationReviewSummaryResponse",
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
    "EvidenceProvenanceListResponse",
    "EvidenceProvenanceReferenceResponse",
    "ExplanationReviewCreateRequest",
    "ExplanationReviewListResponse",
    "ExplanationReviewReason",
    "ExplanationReviewResponse",
    "ExplanationReviewState",
    "ExplanationReviewTargetResponse",
    "ExplanationReviewTargetType",
    "EntityFeatureValueListResponse",
    "EntityFeatureValueResponse",
    "EntityTimeseriesPointResponse",
    "EntityTimeseriesResponse",
    "FeatureCatalogResponse",
    "FeatureDefinitionResponse",
    "FeatureSourceMappingResponse",
    "FraudTypologyResponse",
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
    "PeerAnalysisConfidenceValue",
    "PeerAnalysisResponse",
    "PeerCohortContextResponse",
    "PeerCohortExclusionResponse",
    "PeerDistributionSummaryResponse",
    "PeerMetricComparisonResponse",
    "PolicyItemDetailResponse",
    "PolicyItemListResponse",
    "PolicyItemSummaryResponse",
    "PolicyTriageRequest",
    "PlaybookEvidenceRequirementResponse",
    "PlaybookExportResponse",
    "PlaybookImportRequestPayload",
    "PlaybookImportResponse",
    "PlaybookListResponse",
    "PlaybookPublishRequestPayload",
    "PlaybookRagPromptResponse",
    "PlaybookResponse",
    "PlaybookSnapshotResponse",
    "PlaybookSnapshotSourceValue",
    "PlaybookStatusValue",
    "PlaybookWorkflowStepResponse",
    "RealtimeSnapshotResponse",
    "RiskFactorResponse",
    "RiskProjectionItemResponse",
    "RiskProjectionLevelValue",
    "RiskProjectionListResponse",
    "RiskProjectionRebuildRequest",
    "RiskProjectionRebuildResponse",
    "RiskProjectionRebuildStatusValue",
    "RiskProjectionStatusValue",
    "RiskScoreResponse",
    "ScoreBatchResponse",
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
    "ScoreRunDetailResponse",
    "ScoreRunListResponse",
    "ScoreRunReplayRequest",
    "ScoreRunResponse",
    "ScoreRunStartRequest",
    "WorkflowRunListResponse",
    "WorkflowRunResponse",
]
