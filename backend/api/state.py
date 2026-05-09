"""Seeded application state and orchestration helpers for frontend-facing API reads."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import Lock

from analytics.explainability.adapters.in_memory import InMemoryExplainabilityContextSource
from analytics.explainability.models import ExplanationContext, ExplanationItem, ExplanationSubgraph
from analytics.explainability.service import create_explainability_service
from analytics.explainability.service_models import ExplainabilityRequest, ExplainabilityResponse
from analytics.risk.adapters.in_memory import InMemoryRiskSignalSource
from analytics.risk.models import RiskProfile, RiskSignal
from analytics.risk.service import create_risk_service
from analytics.risk.service_models import RiskAssessmentRequest, RiskAssessmentResponse
from analytics.timeseries.adapters.in_memory import InMemoryTimeSeriesHistorySource
from analytics.timeseries.models import TimeSeriesObservation, TimeSeriesSeries
from analytics.timeseries.service import create_timeseries_service
from analytics.timeseries.service_models import TimeseriesAnalysisRequest, TimeseriesAnalysisResponse
from api.contracts import (
    AlertDetailResponse,
    AlertListItem,
    AlertListResponse,
    AnalyticsOverviewResponse,
    AnalystFeedbackResponse,
    CaseCreateRequest,
    CaseDetailResponse,
    CaseFeedbackCreateRequest,
    CaseListResponse,
    CaseSummaryResponse,
    CaseUpdateRequest,
    ChatConversationCreateRequest,
    ChatConversationResponse,
    ChatMessageCreateRequest,
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
from events.adapters.in_memory import InMemoryEventBus
from graph import InMemoryGraphRepository, create_graph_service
from monitoring.adapters.in_memory import InMemoryObservationSource
from monitoring.models import MonitoringBatch, MonitoringObservation
from monitoring.service import create_monitoring_service
from monitoring.service_models import MonitoringEvaluationRequest
from rag.adapters.in_memory import (
    InMemoryAnswerGenerator,
    InMemoryContextRetriever,
    InMemoryGraphContextExpander,
    InMemoryQueryEmbedder,
)
from rag.models import ContextRecord
from rag.service import create_rag_service
from rag.service_models import RagQueryRequest
from shared.types import Alert, Entity, Relationship
from shared.utils import generate_id
from storage.adapters.in_memory import InMemoryObjectStore

__all__ = ["ApiState", "create_api_state"]


AlertStatus = str


@dataclass(slots=True)
class CaseRecord:
    id: str
    title: str
    status: str
    priority: str
    assignee: str | None
    alert_ids: list[str]
    updated_at: datetime


@dataclass(slots=True)
class ConversationRecord:
    id: str
    title: str
    knowledge_base_id: str
    messages: list[ChatMessageResponse] = field(default_factory=list)


class ApiState:
    """Own seeded services and mutable UI-facing state for local API reads and writes."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._knowledge_base_id = "kb-1"
        self._event_bus = InMemoryEventBus()
        self._graph_repository = InMemoryGraphRepository()
        self._graph_service = create_graph_service(
            self._graph_repository,
            object_store=InMemoryObjectStore(),
            event_bus=self._event_bus,
        )
        self._seed_graph()

        self._monitoring_service = create_monitoring_service(
            InMemoryObservationSource(batches=[self._build_monitoring_batch()]),
            event_bus=self._event_bus,
        )
        self._alerts, self._alert_metadata = self._seed_alerts()

        self._risk_service = create_risk_service(
            InMemoryRiskSignalSource(profiles=self._build_risk_profiles()),
            event_bus=self._event_bus,
        )

        self._timeseries_source = InMemoryTimeSeriesHistorySource(series=self._build_timeseries_series())
        self._timeseries_service = create_timeseries_service(
            self._timeseries_source,
            event_bus=self._event_bus,
        )

        self._explainability_service = create_explainability_service(
            InMemoryExplainabilityContextSource(contexts=self._build_explainability_contexts()),
            event_bus=self._event_bus,
        )
        self._evidence_packs = self._seed_evidence_packs()

        self._rag_service = create_rag_service(
            InMemoryQueryEmbedder(),
            InMemoryContextRetriever(records=self._build_context_records()),
            InMemoryAnswerGenerator(provider="in-memory", model_name="seeded-rag-model"),
            event_bus=self._event_bus,
            graph_context_expander=InMemoryGraphContextExpander(),
        )

        self._cases = self._seed_cases()
        self._feedback: dict[str, list[AnalystFeedbackResponse]] = {
            "case-1001": [
                AnalystFeedbackResponse(
                    case_id="case-1001",
                    label="insufficient_evidence",
                    evidence_adequacy="medium",
                    missing_evidence=["medical_record_excerpt", "policy_exception_note"],
                    notes="Need direct clinical documentation before escalation.",
                    submitted_at=self._now() - timedelta(hours=1),
                )
            ]
        }
        self._conversations = self._seed_conversations()

    def list_alerts(self) -> AlertListResponse:
        items = [self._to_alert_item(alert_id) for alert_id in self._sorted_alert_ids()]
        return AlertListResponse(
            items=items,
            page=PageInfo(page=1, page_size=len(items), total_items=len(items)),
        )

    def get_alert_detail(self, alert_id: str) -> AlertDetailResponse:
        item = self._to_alert_item(alert_id)
        metadata = self._alert_metadata[alert_id]
        return AlertDetailResponse(
            alert=item,
            related_entity_ids=[item.entity_id, "claim-8821", "beneficiary-771"],
            policy_citations=list(metadata["policy_citations"]),
        )

    def acknowledge_alert(self, alert_id: str) -> AlertListItem:
        with self._lock:
            self._alert_metadata[alert_id]["status"] = "acknowledged"
        return self._to_alert_item(alert_id)

    def get_graph_entity_detail(self, entity_id: str) -> GraphEntityDetailResponse:
        entity = self._graph_service.get_entity(self._knowledge_base_id, entity_id)
        if entity is None:
            raise KeyError(entity_id)
        neighbors, relationships = self._graph_service.get_neighbors(self._knowledge_base_id, entity_id)
        risk_score = self._safe_risk_score(entity_id)
        return GraphEntityDetailResponse(
            entity=self._to_graph_node(entity, risk_score=risk_score),
            neighbors=[self._to_graph_node(neighbor, risk_score=self._safe_risk_score(neighbor.id)) for neighbor in neighbors],
            relationships=[self._to_graph_edge(relationship) for relationship in relationships],
            related_alert_ids=[alert_id for alert_id, alert in self._alerts.items() if alert.entity_id == entity_id],
        )

    def get_evidence_pack(self, evidence_pack_id: str) -> EvidencePackResponse:
        return self._evidence_packs[evidence_pack_id]

    def list_cases(self) -> CaseListResponse:
        items = [self._to_case_summary(record) for record in self._sorted_cases()]
        return CaseListResponse(
            items=items,
            page=PageInfo(page=1, page_size=len(items), total_items=len(items)),
        )

    def get_case_detail(self, case_id: str) -> CaseDetailResponse:
        record = self._cases[case_id]
        return CaseDetailResponse(
            case=self._to_case_summary(record),
            alerts=[self._to_alert_item(alert_id) for alert_id in record.alert_ids],
            feedback_history=list(self._feedback.get(case_id, [])),
        )

    def create_case(self, request: CaseCreateRequest) -> CaseDetailResponse:
        with self._lock:
            case_id = generate_id()
            record = CaseRecord(
                id=case_id,
                title=request.title,
                status="open",
                priority=request.priority,
                assignee=request.assignee,
                alert_ids=list(request.alert_ids),
                updated_at=self._now(),
            )
            self._cases[case_id] = record
        return self.get_case_detail(case_id)

    def update_case(self, case_id: str, request: CaseUpdateRequest) -> CaseDetailResponse:
        with self._lock:
            record = self._cases[case_id]
            if request.title is not None:
                record.title = request.title
            if request.status is not None:
                record.status = request.status
            if request.priority is not None:
                record.priority = request.priority
            if request.assignee is not None:
                record.assignee = request.assignee
            record.updated_at = self._now()
        return self.get_case_detail(case_id)

    def add_feedback(self, case_id: str, request: CaseFeedbackCreateRequest) -> CaseDetailResponse:
        feedback = AnalystFeedbackResponse(
            case_id=case_id,
            label=request.label,
            evidence_adequacy=request.evidence_adequacy,
            missing_evidence=list(request.missing_evidence),
            notes=request.notes,
            submitted_at=self._now(),
        )
        with self._lock:
            self._feedback.setdefault(case_id, []).append(feedback)
            self._cases[case_id].updated_at = self._now()
        return self.get_case_detail(case_id)

    def list_workflows(self) -> WorkflowRunListResponse:
        now = self._now()
        return WorkflowRunListResponse(
            items=[
                WorkflowRunResponse(
                    id="workflow-2026-05-08-001",
                    workflow_type="analytics",
                    status="running",
                    knowledge_base_id=self._knowledge_base_id,
                    started_at=now - timedelta(minutes=12),
                    updated_at=now - timedelta(minutes=1),
                    current_step="risk_scoring",
                ),
                WorkflowRunResponse(
                    id="workflow-2026-05-08-000",
                    workflow_type="ingestion",
                    status="completed",
                    knowledge_base_id=self._knowledge_base_id,
                    started_at=now - timedelta(hours=2),
                    updated_at=now - timedelta(hours=2) + timedelta(minutes=18),
                    current_step="completed",
                ),
            ]
        )

    def get_analytics_overview(self) -> AnalyticsOverviewResponse:
        cases = list(self._cases.values())
        return AnalyticsOverviewResponse(
            active_alerts=sum(1 for metadata in self._alert_metadata.values() if metadata["status"] in {"open", "acknowledged", "investigating"}),
            open_cases=sum(1 for case in cases if case.status != "closed"),
            entities_monitored=len(self._graph_repository.get_entities(self._knowledge_base_id)),
            high_risk_entities=sum(1 for entity in self._graph_repository.get_entities(self._knowledge_base_id) if self._safe_risk_score(entity.id) >= 0.8),
        )

    def get_risk_score(self, entity_id: str) -> RiskScoreResponse:
        response = self._risk_service.assess(
            RiskAssessmentRequest(knowledge_base_id=self._knowledge_base_id, entity_id=entity_id)
        )
        return RiskScoreResponse(
            entity_id=response.entity_id,
            overall_score=response.overall_score,
            risk_level=_normalize_risk_level(response.risk_level, response.overall_score),
            factors=[
                RiskFactorResponse(
                    factor_name=factor.factor_name,
                    contribution=factor.contribution,
                    rationale=factor.rationale,
                )
                for factor in response.factors
            ],
        )

    def get_timeseries(self, entity_id: str) -> TimeseriesResponse:
        series = self._timeseries_source.load_series(
            knowledge_base_id=self._knowledge_base_id,
            entity_id=entity_id,
            metric_name="normalized_alert_pressure",
        )
        analysis = self._timeseries_service.analyze(
            TimeseriesAnalysisRequest(
                knowledge_base_id=self._knowledge_base_id,
                entity_id=entity_id,
                metric_name=series.metric_name,
                baseline_window=3,
                min_history=5,
                z_threshold=2.0,
            )
        )
        anomaly_timestamps = {anomaly.observed_at for anomaly in analysis.anomalies}
        return TimeseriesResponse(
            entity_id=entity_id,
            metric_name=series.metric_name,
            points=[
                TimeseriesPointResponse(
                    timestamp=observation.observed_at,
                    value=observation.value,
                    label=observation.observed_at.strftime("%b %d"),
                    is_anomaly=observation.observed_at in anomaly_timestamps,
                )
                for observation in series.observations
            ],
        )

    def create_conversation(self, request: ChatConversationCreateRequest) -> ChatConversationResponse:
        with self._lock:
            conversation_id = generate_id()
            record = ConversationRecord(
                id=conversation_id,
                title=request.title or "Untitled investigation chat",
                knowledge_base_id=request.knowledge_base_id,
            )
            self._conversations[conversation_id] = record
        return self.get_conversation(conversation_id)

    def get_conversation(self, conversation_id: str) -> ChatConversationResponse:
        record = self._conversations[conversation_id]
        return ChatConversationResponse(
            id=record.id,
            title=record.title,
            knowledge_base_id=record.knowledge_base_id,
            messages=list(record.messages),
        )

    def add_message(self, conversation_id: str, request: ChatMessageCreateRequest) -> ChatConversationResponse:
        with self._lock:
            record = self._conversations[conversation_id]
            user_message = ChatMessageResponse(
                id=generate_id(),
                role="user",
                content=request.content,
                created_at=self._now(),
            )
            record.messages.append(user_message)
            rag_response = self._rag_service.answer(
                RagQueryRequest(
                    knowledge_base_id=record.knowledge_base_id,
                    question=request.content,
                    include_graph_context=request.include_graph_context,
                    filters=request.filters,
                )
            )
            assistant_message = ChatMessageResponse(
                id=generate_id(),
                role="assistant",
                content=rag_response.answer,
                created_at=self._now(),
                citation_ids=[citation.content_id for citation in rag_response.citations],
            )
            record.messages.append(assistant_message)
        return self.get_conversation(conversation_id)

    def _seed_graph(self) -> None:
        entities = [
            Entity(
                id="provider-204",
                type="provider",
                properties={
                    "npi": "1234567890",
                    "specialty": "Pain Management",
                    "region": "Northwest",
                    "display_name": "Advanced Pain Specialists",
                },
            ),
            Entity(
                id="provider-118",
                type="provider",
                properties={
                    "npi": "9988776655",
                    "specialty": "Imaging",
                    "region": "Northeast",
                    "display_name": "North Harbor Imaging",
                },
            ),
            Entity(
                id="claim-8821",
                type="claim",
                properties={"claim_amount": 4812.5, "service_month": "2026-04", "display_name": "Claim 8821"},
            ),
            Entity(
                id="beneficiary-771",
                type="beneficiary",
                properties={"county": "King", "age_band": "65-74", "display_name": "Beneficiary 771"},
            ),
        ]
        relationships = [
            Relationship(
                id="relationship-claim-provider-1",
                type="submitted_by",
                source_id="claim-8821",
                target_id="provider-204",
            ),
            Relationship(
                id="relationship-beneficiary-claim-1",
                type="received_service",
                source_id="beneficiary-771",
                target_id="claim-8821",
            ),
        ]
        self._graph_repository.upsert_entities(self._knowledge_base_id, entities)
        self._graph_repository.upsert_relationships(self._knowledge_base_id, relationships)

    def _build_monitoring_batch(self) -> MonitoringBatch:
        return MonitoringBatch(
            knowledge_base_id=self._knowledge_base_id,
            batch_id="batch-phase-5",
            observations=[
                MonitoringObservation(
                    entity_id="provider-204",
                    entity_type="provider",
                    metric_name="billing_intensity",
                    score=0.93,
                    rationale="Billing volume and unit intensity diverge from peer cohort baselines across three consecutive review windows.",
                    evidence_pack_id="evidence-seed-1",
                ),
                MonitoringObservation(
                    entity_id="provider-118",
                    entity_type="provider",
                    metric_name="referral_concentration",
                    score=0.84,
                    rationale="Referral traffic is concentrated through a narrow cluster with elevated downstream utilization.",
                    evidence_pack_id="evidence-seed-2",
                ),
            ],
        )

    def _seed_alerts(self) -> tuple[dict[str, Alert], dict[str, dict[str, object]]]:
        response = self._monitoring_service.evaluate(
            MonitoringEvaluationRequest(knowledge_base_id=self._knowledge_base_id, batch_id="batch-phase-5")
        )
        stable_ids = ["alert-001", "alert-002"]
        labels = {
            "provider-204": "Advanced Pain Specialists",
            "provider-118": "North Harbor Imaging",
        }
        tags = {
            "provider-204": ["peer-group-outlier", "procedure-spike"],
            "provider-118": ["network-pattern", "referral-cluster"],
        }
        alerts: dict[str, Alert] = {}
        metadata: dict[str, dict[str, object]] = {}
        for index, alert in enumerate(response.alerts):
            stable_id = stable_ids[index]
            stable_alert = alert.model_copy(update={"id": stable_id})
            alerts[stable_id] = stable_alert
            metadata[stable_id] = {
                "entity_label": labels.get(alert.entity_id, alert.entity_id),
                "confidence": min(0.99, 0.7 + (0.1 * (index + 1)) + (0.1 if alert.severity == "high" else 0.0)),
                "status": "open",
                "tags": tags.get(alert.entity_id, []),
                "policy_citations": [
                    PolicyCitation(
                        citation_id=f"policy-{index + 17}",
                        title="Coverage criteria for repeated high-cost procedures",
                        excerpt="Repeated utilization beyond the documented treatment window requires escalated review.",
                        source_document_id="doc-policy-2026-04",
                    )
                ],
            }
        return alerts, metadata

    def _build_risk_profiles(self) -> list[RiskProfile]:
        return [
            RiskProfile(
                knowledge_base_id=self._knowledge_base_id,
                entity_id="provider-204",
                signals=[
                    RiskSignal(signal_name="peer_group_deviation", value=0.94, weight=2.0, rationale="Procedure mix exceeds peer benchmark."),
                    RiskSignal(signal_name="network_concentration", value=0.78, weight=1.3, rationale="A narrow referral cluster contributes outsized volume."),
                    RiskSignal(signal_name="temporal_drift", value=0.81, weight=1.2, rationale="Abnormal utilization persisted across multiple windows."),
                ],
            ),
            RiskProfile(
                knowledge_base_id=self._knowledge_base_id,
                entity_id="provider-118",
                signals=[
                    RiskSignal(signal_name="referral_density", value=0.76, weight=1.8, rationale="Referrals are overly concentrated."),
                    RiskSignal(signal_name="peer_deviation", value=0.62, weight=1.2, rationale="Peer utilization exceeded expected range."),
                ],
            ),
            RiskProfile(
                knowledge_base_id=self._knowledge_base_id,
                entity_id="claim-8821",
                signals=[
                    RiskSignal(signal_name="claim_amount", value=0.88, weight=1.6, rationale="Claim amount exceeds cohort norm."),
                    RiskSignal(signal_name="linked_provider", value=0.92, weight=1.4, rationale="Claim is linked to a high-risk provider."),
                ],
            ),
            RiskProfile(
                knowledge_base_id=self._knowledge_base_id,
                entity_id="beneficiary-771",
                signals=[
                    RiskSignal(signal_name="utilization_pattern", value=0.67, weight=1.1, rationale="Repeated high-intensity utilization."),
                    RiskSignal(signal_name="network_affinity", value=0.58, weight=1.0, rationale="Services are clustered in a narrow provider network."),
                ],
            ),
        ]

    def _build_timeseries_series(self) -> list[TimeSeriesSeries]:
        start = self._now() - timedelta(days=35)
        return [
            TimeSeriesSeries(
                knowledge_base_id=self._knowledge_base_id,
                entity_id="provider-204",
                metric_name="normalized_alert_pressure",
                observations=[
                    TimeSeriesObservation(observed_at=start + timedelta(days=index * 7), value=value)
                    for index, value in enumerate([0.41, 0.49, 0.55, 0.64, 0.78, 0.91])
                ],
            ),
            TimeSeriesSeries(
                knowledge_base_id=self._knowledge_base_id,
                entity_id="provider-118",
                metric_name="normalized_alert_pressure",
                observations=[
                    TimeSeriesObservation(observed_at=start + timedelta(days=index * 7), value=value)
                    for index, value in enumerate([0.38, 0.42, 0.48, 0.51, 0.61, 0.68])
                ],
            ),
        ]

    def _build_explainability_contexts(self) -> list[ExplanationContext]:
        contexts: list[ExplanationContext] = []
        for alert_id, alert in self._alerts.items():
            contexts.append(
                ExplanationContext(
                    knowledge_base_id=self._knowledge_base_id,
                    alert=alert,
                    explanation_items=[
                        ExplanationItem(
                            source_id=f"doc-{alert_id}",
                            source_type="document",
                            quote="Procedure frequency exceeded the specialty cohort mean during the review period.",
                            rationale="Supports the longitudinal outlier conclusion.",
                            score=0.92,
                        ),
                        ExplanationItem(
                            source_id=f"timeseries-{alert_id}",
                            source_type="timeseries",
                            quote="Three consecutive windows show sustained upward drift rather than a one-off spike.",
                            rationale="Indicates persistent abnormal behavior.",
                            score=0.87,
                        ),
                    ],
                    subgraph=ExplanationSubgraph(
                        node_ids=[alert.entity_id, "claim-8821", "beneficiary-771"],
                        edge_ids=["relationship-claim-provider-1", "relationship-beneficiary-claim-1"],
                    ),
                    confidence=0.9,
                    scores={"peer_deviation": 0.94, "graph_signal": 0.86, "timeseries_signal": 0.89},
                )
            )
        return contexts

    def _seed_evidence_packs(self) -> dict[str, EvidencePackResponse]:
        packs: dict[str, EvidencePackResponse] = {}
        stable_ids = {"alert-001": "evidence-001", "alert-002": "evidence-002"}
        for alert_id, evidence_id in stable_ids.items():
            response = self._explainability_service.generate(
                ExplainabilityRequest(knowledge_base_id=self._knowledge_base_id, alert_id=alert_id)
            )
            packs[evidence_id] = self._to_evidence_pack_response(response, evidence_id)
        return packs

    def _seed_cases(self) -> dict[str, CaseRecord]:
        now = self._now()
        return {
            "case-1001": CaseRecord(
                id="case-1001",
                title="Advanced Pain Specialists review",
                status="in_review",
                priority="critical",
                assignee="A. Rivera",
                alert_ids=["alert-001"],
                updated_at=now - timedelta(minutes=35),
            ),
            "case-1002": CaseRecord(
                id="case-1002",
                title="North Harbor Imaging referral cluster",
                status="open",
                priority="high",
                assignee=None,
                alert_ids=["alert-002"],
                updated_at=now - timedelta(hours=3),
            ),
        }

    def _seed_conversations(self) -> dict[str, ConversationRecord]:
        now = self._now()
        return {
            "conversation-001": ConversationRecord(
                id="conversation-001",
                title="Provider anomaly review",
                knowledge_base_id=self._knowledge_base_id,
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
                        citation_ids=["content-1"],
                    ),
                ],
            )
        }

    def _build_context_records(self) -> list[ContextRecord]:
        return [
            ContextRecord(
                record_id="record-1",
                content_id="content-1",
                embedding=[20.0, 16.0, 3.0, 4.0],
                content="Provider 204 shows repeated injection billing patterns with peer cohort deviation and graph-linked concentration.",
                metadata={"entity_id": "provider-204", "category": "alerts"},
            ),
            ContextRecord(
                record_id="record-2",
                content_id="content-2",
                embedding=[18.0, 15.0, 2.0, 4.0],
                content="North Harbor Imaging referral traffic is overly concentrated and linked to elevated utilization.",
                metadata={"entity_id": "provider-118", "category": "network"},
            ),
        ]

    def _to_alert_item(self, alert_id: str) -> AlertListItem:
        alert = self._alerts[alert_id]
        metadata = self._alert_metadata[alert_id]
        evidence_pack_id = next(
            (evidence_id for evidence_id, pack in self._evidence_packs.items() if pack.alert_id == alert_id),
            None,
        )
        return AlertListItem(
            id=alert_id,
            entity_id=alert.entity_id,
            entity_type=alert.entity_type,
            entity_label=str(metadata["entity_label"]),
            severity=_normalize_severity(alert.severity, float(metadata["confidence"])),
            status=str(metadata["status"]),
            title=alert.title,
            reasoning=alert.reasoning,
            confidence=float(metadata["confidence"]),
            evidence_pack_id=evidence_pack_id,
            created_at=alert.created_at,
            tags=list(metadata["tags"]),
        )

    def _to_graph_node(self, entity: Entity, *, risk_score: float) -> GraphNodeResponse:
        label = str(entity.properties.get("display_name", entity.id))
        summary = _entity_summary(entity)
        return GraphNodeResponse(
            id=entity.id,
            type=entity.type,
            label=label,
            summary=summary,
            risk_score=risk_score,
            properties={key: value for key, value in entity.properties.items() if isinstance(value, (str, int, float, bool))},
        )

    def _to_graph_edge(self, relationship: Relationship) -> GraphEdgeResponse:
        return GraphEdgeResponse(
            id=relationship.id,
            type=relationship.type,
            source_id=relationship.source_id,
            target_id=relationship.target_id,
            summary=f"{relationship.type.replace('_', ' ')} between {relationship.source_id} and {relationship.target_id}.",
        )

    def _to_evidence_pack_response(
        self,
        response: ExplainabilityResponse,
        evidence_pack_id: str,
    ) -> EvidencePackResponse:
        metadata = self._alert_metadata[response.alert_id]
        return EvidencePackResponse(
            id=evidence_pack_id,
            alert_id=response.alert_id,
            reasoning=response.evidence_pack.reasoning,
            confidence=response.evidence_pack.confidence,
            scores=dict(response.evidence_pack.scores),
            subgraph_node_ids=list(response.evidence_pack.subgraph_nodes),
            subgraph_edge_ids=list(response.evidence_pack.subgraph_edges),
            items=[
                EvidenceItemResponse(
                    source_id=item.source_id,
                    source_type=item.source_type,
                    quote=item.quote,
                    rationale=item.rationale,
                    score=item.score,
                )
                for item in response.evidence_items
            ],
            policy_citations=list(metadata["policy_citations"]),
        )

    def _to_case_summary(self, record: CaseRecord) -> CaseSummaryResponse:
        return CaseSummaryResponse(
            id=record.id,
            title=record.title,
            status=record.status,
            priority=record.priority,
            assignee=record.assignee,
            alert_ids=list(record.alert_ids),
            updated_at=record.updated_at,
        )

    def _safe_risk_score(self, entity_id: str) -> float:
        try:
            return self._risk_service.assess(
                RiskAssessmentRequest(knowledge_base_id=self._knowledge_base_id, entity_id=entity_id)
            ).overall_score
        except ValueError:
            return 0.0

    def _sorted_alert_ids(self) -> list[str]:
        return sorted(self._alerts.keys(), key=lambda alert_id: self._alerts[alert_id].created_at, reverse=True)

    def _sorted_cases(self) -> list[CaseRecord]:
        return sorted(self._cases.values(), key=lambda case: case.updated_at, reverse=True)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)


def create_api_state() -> ApiState:
    """Create the seeded API application state."""
    return ApiState()


def _normalize_severity(severity: str, confidence: float) -> str:
    if severity == "high" and confidence >= 0.9:
        return "critical"
    if severity in {"high", "medium", "low", "critical"}:
        return severity
    return "medium"


def _normalize_risk_level(risk_level: str, overall_score: float) -> str:
    if overall_score >= 0.9:
        return "critical"
    if risk_level in {"high", "medium", "low", "critical"}:
        return risk_level
    return "medium"


def _entity_summary(entity: Entity) -> str:
    if entity.type == "provider":
        return "Provider entity with concentrated procedure mix and elevated longitudinal risk."
    if entity.type == "claim":
        return "Recent claim linked to high-dollar utilization in the flagged review window."
    if entity.type == "beneficiary":
        return "Beneficiary with repeated high-intensity utilization routed through the same provider cluster."
    return f"{entity.type.title()} entity in the active knowledge base."