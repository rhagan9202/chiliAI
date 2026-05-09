"""Deterministic read-model fixtures used by scaffold API routes.

These payload builders provide stable contracts for the frontend while the
underlying capability modules are still being wired into production reads.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from api.contracts import (
    AlertDetailResponse,
    AlertListItem,
    AlertListResponse,
    AnalyticsOverviewResponse,
    ApiEnvelope,
    AnalystFeedbackResponse,
    CaseDetailResponse,
    CaseListResponse,
    CaseSummaryResponse,
    ChatConversationResponse,
    ChatMessageResponse,
    EvidenceItemResponse,
    EvidencePackResponse,
    GraphEdgeResponse,
    GraphEntityDetailResponse,
    GraphNodeResponse,
    PageInfo,
    PolicyCitation,
    RiskFactorResponse,
    RiskScoreResponse,
    TimeseriesPointResponse,
    TimeseriesResponse,
    WorkflowRunListResponse,
    WorkflowRunResponse,
)

__all__ = [
    "build_acknowledge_response",
    "build_alert_detail",
    "build_alert_list",
    "build_analytics_overview",
    "build_case_detail",
    "build_case_list",
    "build_chat_conversation",
    "build_evidence_pack",
    "build_graph_entity_detail",
    "build_risk_score",
    "build_timeseries",
    "build_workflow_runs",
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _policy_citations() -> list[PolicyCitation]:
    return [
        PolicyCitation(
            citation_id="policy-17",
            title="Coverage criteria for repeated high-cost injections",
            excerpt="Repeated injections beyond the documented treatment window require escalated review.",
            source_document_id="doc-policy-2026-04",
        )
    ]


def _alert_items() -> list[AlertListItem]:
    now = _now()
    return [
        AlertListItem(
            id="alert-001",
            entity_id="provider-204",
            entity_type="provider",
            entity_label="Advanced Pain Specialists",
            severity="critical",
            status="open",
            title="Escalating injection billing pattern",
            reasoning="Billing volume and unit intensity diverge from peer cohort baselines across three consecutive review windows.",
            confidence=0.93,
            evidence_pack_id="evidence-001",
            created_at=now - timedelta(hours=2),
            tags=["peer-group-outlier", "procedure-spike"],
        ),
        AlertListItem(
            id="alert-002",
            entity_id="provider-118",
            entity_type="provider",
            entity_label="North Harbor Imaging",
            severity="high",
            status="acknowledged",
            title="Referral concentration anomaly",
            reasoning="Referral traffic is concentrated through a narrow cluster with elevated downstream utilization.",
            confidence=0.84,
            evidence_pack_id="evidence-002",
            created_at=now - timedelta(hours=6),
            tags=["network-pattern", "referral-cluster"],
        ),
    ]


def build_alert_list() -> AlertListResponse:
    items = _alert_items()
    return AlertListResponse(
        items=items,
        page=PageInfo(page=1, page_size=len(items), total_items=len(items)),
    )


def build_alert_detail(alert_id: str) -> AlertDetailResponse:
    alert = next((item for item in _alert_items() if item.id == alert_id), _alert_items()[0])
    return AlertDetailResponse(
        alert=alert,
        related_entity_ids=[alert.entity_id, "claim-8821", "beneficiary-771"],
        policy_citations=_policy_citations(),
    )


def build_acknowledge_response(alert_id: str) -> ApiEnvelope:
    return ApiEnvelope(
        status="accepted",
        message=f"Alert '{alert_id}' queued for acknowledgement.",
    )


def build_graph_entity_detail(entity_id: str) -> GraphEntityDetailResponse:
    entity = GraphNodeResponse(
        id=entity_id,
        type="provider",
        label="Advanced Pain Specialists",
        summary="Provider entity with concentrated procedure mix and elevated longitudinal risk.",
        risk_score=0.91,
        properties={"npi": "1234567890", "specialty": "pain_management", "region": "northwest"},
    )
    neighbors = [
        GraphNodeResponse(
            id="claim-8821",
            type="claim",
            label="Claim 8821",
            summary="Recent claim linked to high-dollar injection sequence.",
            risk_score=0.88,
            properties={"claim_amount": 4812.5, "service_month": "2026-04"},
        ),
        GraphNodeResponse(
            id="beneficiary-771",
            type="beneficiary",
            label="Beneficiary 771",
            summary="Beneficiary with repeated high-intensity utilization routed through the same provider cluster.",
            risk_score=0.72,
            properties={"county": "King", "age_band": "65-74"},
        ),
    ]
    relationships = [
        GraphEdgeResponse(
            id="relationship-claim-provider-1",
            type="submitted_by",
            source_id="claim-8821",
            target_id=entity_id,
            summary="Claim submitted by provider during the flagged review window.",
        ),
        GraphEdgeResponse(
            id="relationship-beneficiary-claim-1",
            type="received_service",
            source_id="beneficiary-771",
            target_id="claim-8821",
            summary="Beneficiary received the billed service represented by the flagged claim.",
        ),
    ]
    return GraphEntityDetailResponse(
        entity=entity,
        neighbors=neighbors,
        relationships=relationships,
        related_alert_ids=["alert-001"],
    )


def build_evidence_pack(evidence_pack_id: str) -> EvidencePackResponse:
    return EvidencePackResponse(
        id=evidence_pack_id,
        alert_id="alert-001",
        reasoning="The evidence pack combines utilization drift, peer-cohort deviation, and graph-neighborhood concentration signals.",
        confidence=0.9,
        scores={"peer_deviation": 0.94, "graph_signal": 0.86, "timeseries_signal": 0.89},
        subgraph_node_ids=["provider-204", "claim-8821", "beneficiary-771"],
        subgraph_edge_ids=["relationship-claim-provider-1", "relationship-beneficiary-claim-1"],
        items=[
            EvidenceItemResponse(
                source_id="doc-review-note-12",
                source_type="document",
                quote="Procedure frequency exceeded the specialty cohort mean by 3.4x during the review period.",
                rationale="Supports the longitudinal outlier conclusion.",
                score=0.92,
            ),
            EvidenceItemResponse(
                source_id="timeseries-window-2026-04",
                source_type="timeseries",
                quote="Three consecutive windows show sustained upward drift rather than a one-off spike.",
                rationale="Indicates persistent abnormal behavior.",
                score=0.87,
            ),
        ],
        policy_citations=_policy_citations(),
    )


def _case_items() -> list[CaseSummaryResponse]:
    now = _now()
    return [
        CaseSummaryResponse(
            id="case-1001",
            title="Advanced Pain Specialists review",
            status="in_review",
            priority="critical",
            assignee="A. Rivera",
            alert_ids=["alert-001"],
            updated_at=now - timedelta(minutes=35),
        ),
        CaseSummaryResponse(
            id="case-1002",
            title="North Harbor Imaging referral cluster",
            status="open",
            priority="high",
            assignee=None,
            alert_ids=["alert-002"],
            updated_at=now - timedelta(hours=3),
        ),
    ]


def build_case_list() -> CaseListResponse:
    items = _case_items()
    return CaseListResponse(
        items=items,
        page=PageInfo(page=1, page_size=len(items), total_items=len(items)),
    )


def build_case_detail(case_id: str) -> CaseDetailResponse:
    case = next((item for item in _case_items() if item.id == case_id), _case_items()[0])
    return CaseDetailResponse(
        case=case,
        alerts=[build_alert_detail(alert_id).alert for alert_id in case.alert_ids],
        feedback_history=[
            AnalystFeedbackResponse(
                case_id=case.id,
                label="insufficient_evidence",
                evidence_adequacy="medium",
                missing_evidence=["medical_record_excerpt", "policy_exception_note"],
                notes="Need direct clinical documentation before escalation.",
                submitted_at=_now() - timedelta(hours=1),
            )
        ],
    )


def build_chat_conversation(conversation_id: str) -> ChatConversationResponse:
    now = _now()
    return ChatConversationResponse(
        id=conversation_id,
        title="Provider anomaly review",
        knowledge_base_id="kb-1",
        messages=[
            ChatMessageResponse(
                id="msg-1",
                role="user",
                content="Summarize why provider-204 is considered high risk.",
                created_at=now - timedelta(minutes=4),
            ),
            ChatMessageResponse(
                id="msg-2",
                role="assistant",
                content="Provider-204 is flagged due to sustained utilization drift, peer-group deviation, and graph-linked claim concentration.",
                created_at=now - timedelta(minutes=3),
                citation_ids=["policy-17", "evidence-001"],
            ),
        ],
    )


def build_workflow_runs() -> WorkflowRunListResponse:
    now = _now()
    return WorkflowRunListResponse(
        items=[
            WorkflowRunResponse(
                id="workflow-2026-05-08-001",
                workflow_type="analytics",
                status="running",
                knowledge_base_id="kb-1",
                started_at=now - timedelta(minutes=12),
                updated_at=now - timedelta(minutes=1),
                current_step="risk_scoring",
            ),
            WorkflowRunResponse(
                id="workflow-2026-05-08-000",
                workflow_type="ingestion",
                status="completed",
                knowledge_base_id="kb-1",
                started_at=now - timedelta(hours=2),
                updated_at=now - timedelta(hours=2) + timedelta(minutes=18),
                current_step="completed",
            ),
        ]
    )


def build_risk_score(entity_id: str) -> RiskScoreResponse:
    return RiskScoreResponse(
        entity_id=entity_id,
        overall_score=0.91,
        risk_level="critical",
        factors=[
            RiskFactorResponse(
                factor_name="peer_group_deviation",
                contribution=0.42,
                rationale="Procedure mix and units materially exceed the peer benchmark.",
            ),
            RiskFactorResponse(
                factor_name="network_concentration",
                contribution=0.31,
                rationale="A narrow referral cluster contributes outsized downstream volume.",
            ),
            RiskFactorResponse(
                factor_name="temporal_drift",
                contribution=0.18,
                rationale="Abnormal utilization persisted across multiple review windows.",
            ),
        ],
    )


def build_timeseries(entity_id: str) -> TimeseriesResponse:
    now = _now()
    return TimeseriesResponse(
        entity_id=entity_id,
        metric_name="normalized_alert_pressure",
        points=[
            TimeseriesPointResponse(timestamp=now - timedelta(days=28), value=0.41, label="W-4"),
            TimeseriesPointResponse(timestamp=now - timedelta(days=21), value=0.55, label="W-3"),
            TimeseriesPointResponse(timestamp=now - timedelta(days=14), value=0.74, label="W-2"),
            TimeseriesPointResponse(timestamp=now - timedelta(days=7), value=0.89, label="W-1"),
        ],
    )


def build_analytics_overview() -> AnalyticsOverviewResponse:
    return AnalyticsOverviewResponse(
        active_alerts=142,
        open_cases=23,
        entities_monitored=1842,
        high_risk_entities=37,
    )