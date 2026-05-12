"""Seeded application state and orchestration helpers for frontend-facing API reads."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Literal, cast

from analytics.explainability.adapters.in_memory import InMemoryExplainabilityContextSource
from analytics.explainability.models import ExplanationContext, ExplanationItem, ExplanationSubgraph
from analytics.explainability.service import create_explainability_service
from analytics.explainability.service_models import ExplainabilityRequest, ExplainabilityResponse
from analytics.risk.adapters.in_memory import InMemoryRiskSignalSource
from analytics.risk.models import RiskProfile, RiskSignal
from analytics.risk.service import create_risk_service
from analytics.risk.service_models import RiskAssessmentRequest
from analytics.timeseries.adapters.in_memory import InMemoryTimeSeriesHistorySource
from analytics.timeseries.models import TimeSeriesObservation, TimeSeriesSeries
from analytics.timeseries.service import create_timeseries_service
from analytics.timeseries.service_models import TimeseriesAnalysisRequest
from config.loader import load_config
from config.schema import DomainConfig
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
    KnowledgeBaseCreateRequest,
    KnowledgeBaseDocumentListResponse,
    KnowledgeBaseDocumentResponse,
    KnowledgeBaseListResponse,
    KnowledgeBaseSummaryResponse,
    PageInfo,
    PolicyBriefCreateRequest,
    PolicyBriefResponse,
    PolicyCitation,
    PolicyGapCaseListResponse,
    PolicyGapDetailResponse,
    PolicyGapListResponse,
    PolicyGapSummaryResponse,
    PolicyTrendPointResponse,
    RealtimeSnapshotResponse,
    RiskFactorResponse,
    RiskScoreResponse,
    TimeseriesPointResponse,
    TimeseriesResponse,
    WorkflowRunListResponse,
    WorkflowRunResponse,
)
from events.adapters.in_memory import InMemoryEventBus
from graph import InMemoryGraphRepository, create_graph_service
from ingestion.service_models import DocumentReceipt, DocumentSubmission
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
from rag.protocols import RagServiceProtocol
from rag.service import create_rag_service
from rag.service_models import RagQueryRequest
from shared.types import Alert, Entity, EntityDefinition, Relationship
from shared.utils import generate_id
from storage.adapters.in_memory import InMemoryObjectStore

__all__ = ["ApiState", "create_api_state"]


AlertStatus = str


@dataclass(slots=True)
class CaseRecord:
    id: str
    title: str
    status: Literal["open", "in_review", "closed"]
    priority: Literal["low", "medium", "high", "critical"]
    assignee: str | None
    alert_ids: list[str]
    updated_at: datetime


@dataclass(slots=True)
class ConversationRecord:
    id: str
    title: str
    knowledge_base_id: str
    messages: list[ChatMessageResponse] = field(default_factory=lambda: cast(list[ChatMessageResponse], []))


@dataclass(slots=True)
class KnowledgeBaseRecord:
    id: str
    name: str
    description: str
    status: str
    entity_count: int
    relationship_count: int
    document_count: int
    created_at: datetime
    last_ingested_at: datetime | None = None


@dataclass(slots=True)
class DocumentTimelineEntryRecord:
    stage: str
    status: str
    updated_at: datetime
    message: str


@dataclass(slots=True)
class KnowledgeBaseDocumentRecord:
    id: str
    knowledge_base_id: str
    filename: str
    content_type: str | None
    size_bytes: int | None
    status: str
    uploaded_at: datetime
    timeline: list[DocumentTimelineEntryRecord] = field(default_factory=lambda: cast(list[DocumentTimelineEntryRecord], []))


@dataclass(slots=True)
class PolicyGapRecord:
    id: str
    title: str
    status: Literal["monitoring", "drafting", "recommended"]
    severity: Literal["medium", "high", "critical"]
    impacted_entities: int
    affected_case_ids: list[str]
    knowledge_base_id: str
    updated_at: datetime
    summary: str
    impact_statement: str
    recommendation: str
    policy_citations: list[PolicyCitation] = field(default_factory=lambda: cast(list[PolicyCitation], []))
    trend: list[PolicyTrendPointResponse] = field(default_factory=lambda: cast(list[PolicyTrendPointResponse], []))


class ApiState:
    """Own seeded services and mutable UI-facing state for local API reads and writes."""

    def __init__(self, domain_config: DomainConfig | None = None) -> None:
        self._lock = Lock()
        self._domain_config = domain_config or load_config()
        self._entity_definitions = list(self._domain_config.entities)
        self._entity_definition_by_type = {
            definition.name: definition for definition in self._entity_definitions
        }
        self._knowledge_base_id = "kb-1"
        self._primary_entity_id = "provider-204"
        self._secondary_entity_id = "provider-118"
        self._tertiary_entity_id = "claim-8821"
        self._quaternary_entity_id = "beneficiary-771"
        self._event_bus = InMemoryEventBus()
        self._graph_repository = InMemoryGraphRepository()
        self._graph_service = create_graph_service(
            self._graph_repository,
            object_store=InMemoryObjectStore(),
            event_bus=self._event_bus,
        )
        self._seed_graph()
        self._knowledge_base_documents = self._seed_knowledge_base_documents()
        self._knowledge_bases = self._seed_knowledge_bases()

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

        self._workflow_runs = self._seed_workflows()
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
        self._policy_gaps = self._seed_policy_gaps()
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
            related_entity_ids=[
                item.entity_id,
                self._tertiary_entity_id,
                self._quaternary_entity_id,
            ],
            policy_citations=cast(list[PolicyCitation], metadata["policy_citations"]),
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

    def list_policy_gaps(self) -> PolicyGapListResponse:
        items = [self._to_policy_gap_summary(record) for record in self._sorted_policy_gaps()]
        return PolicyGapListResponse(
            items=items,
            page=PageInfo(page=1, page_size=len(items), total_items=len(items)),
        )

    def get_policy_gap_detail(self, gap_id: str) -> PolicyGapDetailResponse:
        gap = self._policy_gaps[gap_id]
        return PolicyGapDetailResponse(
            gap=self._to_policy_gap_summary(gap),
            summary=gap.summary,
            impact_statement=gap.impact_statement,
            recommendation=gap.recommendation,
            policy_citations=list(gap.policy_citations),
            trend=list(gap.trend),
        )

    def list_policy_gap_cases(self, gap_id: str) -> PolicyGapCaseListResponse:
        gap = self._policy_gaps[gap_id]
        items = [self._to_case_summary(self._cases[case_id]) for case_id in gap.affected_case_ids]
        return PolicyGapCaseListResponse(
            gap_id=gap_id,
            items=items,
            page=PageInfo(page=1, page_size=len(items), total_items=len(items)),
        )

    def create_policy_brief(self, request: PolicyBriefCreateRequest) -> PolicyBriefResponse:
        gap = self._policy_gaps[request.gap_id]
        created_at = self._now()
        recommendations = [
            gap.recommendation,
            "Route the resulting guidance through triage support workflows rather than automated enforcement.",
            "Prioritize provenance-linked evidence before closing affected supervisor cases.",
        ]
        return PolicyBriefResponse(
            id=generate_id(),
            gap_id=gap.id,
            title=f"{gap.title} brief",
            audience=request.audience,
            objective=request.objective,
            narrative=(
                f"Audience: {request.audience}. Objective: {request.objective}. "
                f"{gap.summary} {gap.impact_statement} Recommended next step: {gap.recommendation}"
            ),
            recommendations=recommendations,
            policy_citations=list(gap.policy_citations),
            created_at=created_at,
        )

    def get_realtime_snapshot(self, sequence: int) -> RealtimeSnapshotResponse:
        return RealtimeSnapshotResponse(
            sequence=sequence,
            emitted_at=self._now(),
            active_alerts=sum(
                1
                for metadata in self._alert_metadata.values()
                if metadata["status"] in {"open", "acknowledged", "investigating"}
            ),
            running_workflows=sum(
                1 for workflow in self._workflow_runs if workflow.status in {"queued", "running"}
            ),
            knowledge_base_statuses={
                knowledge_base.id: knowledge_base.status
                for knowledge_base in self._knowledge_bases.values()
            },
        )

    def list_knowledge_bases(self) -> KnowledgeBaseListResponse:
        items = [self._to_knowledge_base_summary(record) for record in self._sorted_knowledge_bases()]
        return KnowledgeBaseListResponse(
            items=items,
            total=len(items),
        )

    def get_knowledge_base_detail(self, knowledge_base_id: str) -> KnowledgeBaseSummaryResponse:
        record = self._knowledge_bases[knowledge_base_id]
        return self._to_knowledge_base_summary(record)

    def create_knowledge_base(self, request: KnowledgeBaseCreateRequest) -> KnowledgeBaseSummaryResponse:
        with self._lock:
            knowledge_base_id = generate_id()
            record = KnowledgeBaseRecord(
                id=knowledge_base_id,
                name=request.name,
                description=request.description,
                status="ready",
                entity_count=0,
                relationship_count=0,
                document_count=0,
                created_at=self._now(),
            )
            self._knowledge_bases[knowledge_base_id] = record
            self._knowledge_base_documents[knowledge_base_id] = {}
        return self.get_knowledge_base_detail(knowledge_base_id)

    def delete_knowledge_base(self, knowledge_base_id: str) -> None:
        with self._lock:
            del self._knowledge_bases[knowledge_base_id]
            self._knowledge_base_documents.pop(knowledge_base_id, None)
            self._workflow_runs = [
                workflow for workflow in self._workflow_runs if workflow.knowledge_base_id != knowledge_base_id
            ]

    def list_knowledge_base_documents(self, knowledge_base_id: str) -> KnowledgeBaseDocumentListResponse:
        documents = [
            self._to_knowledge_base_document(document)
            for document in self._sorted_knowledge_base_documents(knowledge_base_id)
        ]
        return KnowledgeBaseDocumentListResponse(
            items=documents,
            total=len(documents),
        )

    def register_knowledge_base_documents(
        self,
        knowledge_base_id: str,
        receipts: list[DocumentReceipt],
        submissions: list[DocumentSubmission],
    ) -> None:
        with self._lock:
            knowledge_base = self._knowledge_bases[knowledge_base_id]
            knowledge_base.status = "indexing"
            uploaded_at = self._now()
            for receipt, submission in zip(receipts, submissions, strict=False):
                filename = receipt.filename or receipt.source_document_id
                document = KnowledgeBaseDocumentRecord(
                    id=receipt.source_document_id,
                    knowledge_base_id=knowledge_base_id,
                    filename=filename,
                    content_type=submission.content_type,
                    size_bytes=len(submission.content) if submission.content is not None else None,
                    status="pending",
                    uploaded_at=receipt.created_at,
                    timeline=self._build_registered_timeline(filename=filename, created_at=receipt.created_at),
                )
                self._knowledge_base_documents.setdefault(knowledge_base_id, {})[document.id] = document
                uploaded_at = max(uploaded_at, receipt.created_at)
            knowledge_base.document_count = len(self._knowledge_base_documents.get(knowledge_base_id, {}))
            knowledge_base.last_ingested_at = uploaded_at
            self._workflow_runs.insert(
                0,
                WorkflowRunResponse(
                    id=generate_id(),
                    workflow_type="ingestion",
                    status="queued",
                    knowledge_base_id=knowledge_base_id,
                    started_at=uploaded_at,
                    updated_at=uploaded_at,
                    current_step="document_registration",
                ),
            )

    def delete_knowledge_base_document(self, knowledge_base_id: str, document_id: str) -> None:
        with self._lock:
            documents = self._knowledge_base_documents[knowledge_base_id]
            del documents[document_id]
            knowledge_base = self._knowledge_bases[knowledge_base_id]
            knowledge_base.document_count = len(documents)
            knowledge_base.status = "ready" if documents else "ready"

    def rebuild_knowledge_base(self, knowledge_base_id: str) -> WorkflowRunResponse:
        now = self._now()
        with self._lock:
            knowledge_base = self._knowledge_bases[knowledge_base_id]
            knowledge_base.status = "rebuilding"
            workflow = WorkflowRunResponse(
                id=generate_id(),
                workflow_type="graph_build",
                status="queued",
                knowledge_base_id=knowledge_base_id,
                started_at=now,
                updated_at=now,
                current_step="rebuild_requested",
            )
            self._workflow_runs.insert(0, workflow)
        return workflow.model_copy(deep=True)

    def list_workflows(self) -> WorkflowRunListResponse:
        return WorkflowRunListResponse(
            items=[workflow.model_copy(deep=True) for workflow in self._workflow_runs]
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

    @property
    def rag_service(self) -> RagServiceProtocol:
        """The RAG service backing chat conversations and streaming responses."""
        return self._rag_service

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
                id=self._primary_entity_id,
                type=self._entity_type_at(0),
                properties={
                    "npi": "1234567890",
                    "specialty": "Pain Management",
                    "region": "Northwest",
                    "display_name": "Advanced Pain Specialists",
                },
            ),
            Entity(
                id=self._secondary_entity_id,
                type=self._entity_type_at(0),
                properties={
                    "npi": "9988776655",
                    "specialty": "Imaging",
                    "region": "Northeast",
                    "display_name": "North Harbor Imaging",
                },
            ),
            Entity(
                id=self._tertiary_entity_id,
                type=self._entity_type_at(2),
                properties={"claim_amount": 4812.5, "service_month": "2026-04", "display_name": "Claim 8821"},
            ),
            Entity(
                id=self._quaternary_entity_id,
                type=self._entity_type_at(1),
                properties={"county": "King", "age_band": "65-74", "display_name": "Beneficiary 771"},
            ),
        ]
        relationships = [
            Relationship(
                id="relationship-claim-provider-1",
                type=self._relationship_type_at(0),
                source_id=self._tertiary_entity_id,
                target_id=self._primary_entity_id,
            ),
            Relationship(
                id="relationship-beneficiary-claim-1",
                type=self._relationship_type_at(1),
                source_id=self._quaternary_entity_id,
                target_id=self._tertiary_entity_id,
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
                    entity_id=self._primary_entity_id,
                    entity_type=self._entity_type_at(0),
                    metric_name="billing_intensity",
                    score=0.93,
                    rationale="Billing volume and unit intensity diverge from peer cohort baselines across three consecutive review windows.",
                    evidence_pack_id="evidence-seed-1",
                ),
                MonitoringObservation(
                    entity_id=self._secondary_entity_id,
                    entity_type=self._entity_type_at(0),
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
            self._primary_entity_id: "Advanced Pain Specialists",
            self._secondary_entity_id: "North Harbor Imaging",
        }
        tags = {
            self._primary_entity_id: ["peer-group-outlier", "procedure-spike"],
            self._secondary_entity_id: ["network-pattern", "referral-cluster"],
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
                entity_id=self._primary_entity_id,
                signals=[
                    RiskSignal(signal_name="peer_group_deviation", value=0.94, weight=2.0, rationale="Procedure mix exceeds peer benchmark."),
                    RiskSignal(signal_name="network_concentration", value=0.78, weight=1.3, rationale="A narrow referral cluster contributes outsized volume."),
                    RiskSignal(signal_name="temporal_drift", value=0.81, weight=1.2, rationale="Abnormal utilization persisted across multiple windows."),
                ],
            ),
            RiskProfile(
                knowledge_base_id=self._knowledge_base_id,
                entity_id=self._secondary_entity_id,
                signals=[
                    RiskSignal(signal_name="referral_density", value=0.76, weight=1.8, rationale="Referrals are overly concentrated."),
                    RiskSignal(signal_name="peer_deviation", value=0.62, weight=1.2, rationale="Peer utilization exceeded expected range."),
                ],
            ),
            RiskProfile(
                knowledge_base_id=self._knowledge_base_id,
                entity_id=self._tertiary_entity_id,
                signals=[
                    RiskSignal(signal_name="claim_amount", value=0.88, weight=1.6, rationale="Claim amount exceeds cohort norm."),
                    RiskSignal(signal_name="linked_provider", value=0.92, weight=1.4, rationale="Claim is linked to a high-risk provider."),
                ],
            ),
            RiskProfile(
                knowledge_base_id=self._knowledge_base_id,
                entity_id=self._quaternary_entity_id,
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
                entity_id=self._primary_entity_id,
                metric_name="normalized_alert_pressure",
                observations=[
                    TimeSeriesObservation(observed_at=start + timedelta(days=index * 7), value=value)
                    for index, value in enumerate([0.41, 0.49, 0.55, 0.64, 0.78, 0.91])
                ],
            ),
            TimeSeriesSeries(
                knowledge_base_id=self._knowledge_base_id,
                entity_id=self._secondary_entity_id,
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
                        node_ids=[
                            alert.entity_id,
                            self._tertiary_entity_id,
                            self._quaternary_entity_id,
                        ],
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

    def _seed_policy_gaps(self) -> dict[str, PolicyGapRecord]:
        now = self._now()
        return {
            "policy-gap-001": PolicyGapRecord(
                id="policy-gap-001",
                title="Repeated injection exception language creates inconsistent triage evidence",
                status="recommended",
                severity="critical",
                impacted_entities=14,
                affected_case_ids=["case-1001"],
                knowledge_base_id=self._knowledge_base_id,
                updated_at=now - timedelta(minutes=42),
                summary="Current coverage guidance leaves exception handling fragmented across utilization review notes, which reduces citation consistency for high-cost injection alerts.",
                impact_statement="Supervisors reviewing critical provider alerts receive incomplete policy context and need manual cross-referencing before escalation.",
                recommendation="Publish a concise exception matrix that links coverage criteria, allowable repeat windows, and required documentation artifacts.",
                policy_citations=[
                    PolicyCitation(
                        citation_id="policy-brief-001",
                        title="Injection coverage repeat-window criteria",
                        excerpt="Repeated injections beyond the documented treatment window require escalated review and physician justification.",
                        source_document_id="doc-policy-2026-04",
                    ),
                    PolicyCitation(
                        citation_id="policy-brief-002",
                        title="Manual review exception requirements",
                        excerpt="Cases routed for manual review must include the specific exception path and supporting documentation class.",
                        source_document_id="doc-policy-2026-05",
                    ),
                ],
                trend=[
                    PolicyTrendPointResponse(label="Jan", value=2),
                    PolicyTrendPointResponse(label="Feb", value=3),
                    PolicyTrendPointResponse(label="Mar", value=6),
                    PolicyTrendPointResponse(label="Apr", value=9),
                ],
            ),
            "policy-gap-002": PolicyGapRecord(
                id="policy-gap-002",
                title="Referral disclosure guidance does not clearly define narrow-network concentration thresholds",
                status="drafting",
                severity="high",
                impacted_entities=8,
                affected_case_ids=["case-1002"],
                knowledge_base_id=self._knowledge_base_id,
                updated_at=now - timedelta(hours=3, minutes=10),
                summary="Referral concentration alerts are surfacing faster than the current policy language can explain acceptable network concentration versus suspicious steering.",
                impact_statement="Analysts can identify the graph pattern, but policy escalation packets still require manual interpretation before a brief can be shared with operations leadership.",
                recommendation="Draft a threshold reference for referral concentration and include examples of acceptable specialist routing versus suspicious loop formation.",
                policy_citations=[
                    PolicyCitation(
                        citation_id="policy-brief-003",
                        title="Referral disclosure requirements",
                        excerpt="Disclosures must identify ownership, referral rationale, and any repeated downstream utilization concentrations.",
                        source_document_id="doc-policy-2026-05",
                    )
                ],
                trend=[
                    PolicyTrendPointResponse(label="Jan", value=1),
                    PolicyTrendPointResponse(label="Feb", value=2),
                    PolicyTrendPointResponse(label="Mar", value=4),
                    PolicyTrendPointResponse(label="Apr", value=5),
                ],
            ),
        }

    def _seed_knowledge_base_documents(self) -> dict[str, dict[str, KnowledgeBaseDocumentRecord]]:
        now = self._now()
        return {
            self._knowledge_base_id: {
                "doc-policy-2026-04": KnowledgeBaseDocumentRecord(
                    id="doc-policy-2026-04",
                    knowledge_base_id=self._knowledge_base_id,
                    filename="medicare-injection-coverage.pdf",
                    content_type="application/pdf",
                    size_bytes=482_112,
                    status="validated",
                    uploaded_at=now - timedelta(days=2, hours=1),
                    timeline=self._build_completed_timeline(
                        filename="medicare-injection-coverage.pdf",
                        created_at=now - timedelta(days=2, hours=1),
                    ),
                ),
                "doc-policy-2026-05": KnowledgeBaseDocumentRecord(
                    id="doc-policy-2026-05",
                    knowledge_base_id=self._knowledge_base_id,
                    filename="peer-benchmark-guidance.docx",
                    content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    size_bytes=167_004,
                    status="validated",
                    uploaded_at=now - timedelta(days=1, hours=6),
                    timeline=self._build_completed_timeline(
                        filename="peer-benchmark-guidance.docx",
                        created_at=now - timedelta(days=1, hours=6),
                    ),
                ),
                "doc-status-2026-05": KnowledgeBaseDocumentRecord(
                    id="doc-status-2026-05",
                    knowledge_base_id=self._knowledge_base_id,
                    filename="review-window-anomalies.csv",
                    content_type="text/csv",
                    size_bytes=24_871,
                    status="parsing",
                    uploaded_at=now - timedelta(hours=3, minutes=20),
                    timeline=self._build_in_progress_timeline(
                        filename="review-window-anomalies.csv",
                        created_at=now - timedelta(hours=3, minutes=20),
                    ),
                ),
            },
            "kb-2": {
                "doc-dental-001": KnowledgeBaseDocumentRecord(
                    id="doc-dental-001",
                    knowledge_base_id="kb-2",
                    filename="dental-provider-network.pdf",
                    content_type="application/pdf",
                    size_bytes=301_442,
                    status="validated",
                    uploaded_at=now - timedelta(days=4),
                    timeline=self._build_completed_timeline(
                        filename="dental-provider-network.pdf",
                        created_at=now - timedelta(days=4),
                    ),
                )
            },
        }

    def _seed_knowledge_bases(self) -> dict[str, KnowledgeBaseRecord]:
        primary_documents = self._knowledge_base_documents[self._knowledge_base_id]
        secondary_documents = self._knowledge_base_documents["kb-2"]
        return {
            self._knowledge_base_id: KnowledgeBaseRecord(
                id=self._knowledge_base_id,
                name=f"{self._domain_config.domain.display_name} Knowledge Base",
                description=f"Primary {self._domain_config.domain.display_name} knowledge base for triage, graph analytics, and RAG retrieval.",
                status="indexing",
                entity_count=len(self._graph_repository.get_entities(self._knowledge_base_id)),
                relationship_count=len(self._graph_repository.get_relationships(self._knowledge_base_id)),
                document_count=len(primary_documents),
                created_at=self._now() - timedelta(days=14),
                last_ingested_at=max(document.uploaded_at for document in primary_documents.values()),
            ),
            "kb-2": KnowledgeBaseRecord(
                id="kb-2",
                name="Medicaid Dental Signals",
                description="Secondary domain pack used to validate cross-program ingestion and document readiness.",
                status="ready",
                entity_count=16,
                relationship_count=28,
                document_count=len(secondary_documents),
                created_at=self._now() - timedelta(days=21),
                last_ingested_at=max(document.uploaded_at for document in secondary_documents.values()),
            ),
        }

    def _seed_workflows(self) -> list[WorkflowRunResponse]:
        now = self._now()
        return [
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
            WorkflowRunResponse(
                id="workflow-2026-05-07-014",
                workflow_type="graph_build",
                status="completed",
                knowledge_base_id="kb-2",
                started_at=now - timedelta(days=1, hours=2),
                updated_at=now - timedelta(days=1, hours=1, minutes=31),
                current_step="completed",
            ),
        ]

    def _build_context_records(self) -> list[ContextRecord]:
        return [
            ContextRecord(
                record_id="record-1",
                content_id="content-1",
                embedding=[20.0, 16.0, 3.0, 4.0],
                content="Provider 204 shows repeated injection billing patterns with peer cohort deviation and graph-linked concentration.",
                metadata={"entity_id": self._primary_entity_id, "category": "alerts"},
            ),
            ContextRecord(
                record_id="record-2",
                content_id="content-2",
                embedding=[18.0, 15.0, 2.0, 4.0],
                content="North Harbor Imaging referral traffic is overly concentrated and linked to elevated utilization.",
                metadata={"entity_id": self._secondary_entity_id, "category": "network"},
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
            severity=_normalize_severity(alert.severity, cast(float, metadata["confidence"])),
            status=cast(Literal["open", "acknowledged", "investigating", "resolved", "dismissed"], metadata["status"]),
            title=alert.title,
            reasoning=alert.reasoning,
            confidence=cast(float, metadata["confidence"]),
            evidence_pack_id=evidence_pack_id,
            created_at=alert.created_at,
            tags=cast(list[str], metadata["tags"]),
        )

    def _to_graph_node(self, entity: Entity, *, risk_score: float) -> GraphNodeResponse:
        label = str(entity.properties.get("display_name", entity.id))
        summary = self._entity_summary(entity)
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
            policy_citations=cast(list[PolicyCitation], metadata["policy_citations"]),
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

    def _to_policy_gap_summary(self, record: PolicyGapRecord) -> PolicyGapSummaryResponse:
        return PolicyGapSummaryResponse(
            id=record.id,
            title=record.title,
            status=record.status,
            severity=record.severity,
            impacted_entities=record.impacted_entities,
            affected_case_count=len(record.affected_case_ids),
            knowledge_base_id=record.knowledge_base_id,
            updated_at=record.updated_at,
        )

    def _to_knowledge_base_summary(self, record: KnowledgeBaseRecord) -> KnowledgeBaseSummaryResponse:
        return KnowledgeBaseSummaryResponse(
            id=record.id,
            name=record.name,
            description=record.description,
            status=_normalize_knowledge_base_status(record.status),
            document_count=record.document_count,
            entity_count=record.entity_count,
            relationship_count=record.relationship_count,
            created_at=record.created_at,
        )

    def _to_knowledge_base_document(
        self,
        record: KnowledgeBaseDocumentRecord,
    ) -> KnowledgeBaseDocumentResponse:
        return KnowledgeBaseDocumentResponse(
            id=record.id,
            knowledge_base_id=record.knowledge_base_id,
            filename=record.filename,
            content_type=record.content_type,
            size_bytes=record.size_bytes,
            status=_normalize_document_status(record.status),
            created_at=record.uploaded_at,
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

    def _sorted_knowledge_bases(self) -> list[KnowledgeBaseRecord]:
        return sorted(
            self._knowledge_bases.values(),
            key=lambda knowledge_base: knowledge_base.last_ingested_at or knowledge_base.created_at,
            reverse=True,
        )

    def _sorted_knowledge_base_documents(
        self,
        knowledge_base_id: str,
    ) -> list[KnowledgeBaseDocumentRecord]:
        return sorted(
            self._knowledge_base_documents.get(knowledge_base_id, {}).values(),
            key=lambda document: document.uploaded_at,
            reverse=True,
        )

    def _sorted_policy_gaps(self) -> list[PolicyGapRecord]:
        severity_rank = {"critical": 0, "high": 1, "medium": 2}
        return sorted(
            self._policy_gaps.values(),
            key=lambda gap: (severity_rank.get(gap.severity, 3), -gap.updated_at.timestamp()),
        )

    def _build_registered_timeline(self, *, filename: str, created_at: datetime) -> list[DocumentTimelineEntryRecord]:
        return [
            DocumentTimelineEntryRecord(
                stage="registered",
                status="completed",
                updated_at=created_at,
                message=f"{filename} registered and queued for ingestion.",
            ),
            DocumentTimelineEntryRecord(
                stage="parser_dispatch",
                status="pending",
                updated_at=created_at + timedelta(minutes=1),
                message="Waiting for parser worker assignment.",
            ),
            DocumentTimelineEntryRecord(
                stage="graph_and_index",
                status="pending",
                updated_at=created_at + timedelta(minutes=2),
                message="Graph extraction and vector indexing will start after parsing completes.",
            ),
        ]

    def _build_completed_timeline(self, *, filename: str, created_at: datetime) -> list[DocumentTimelineEntryRecord]:
        return [
            DocumentTimelineEntryRecord(
                stage="registered",
                status="completed",
                updated_at=created_at,
                message=f"{filename} registered for ingestion.",
            ),
            DocumentTimelineEntryRecord(
                stage="parsed",
                status="completed",
                updated_at=created_at + timedelta(minutes=6),
                message="Structured text extraction completed.",
            ),
            DocumentTimelineEntryRecord(
                stage="extracted",
                status="completed",
                updated_at=created_at + timedelta(minutes=12),
                message="Entity and relationship extraction completed.",
            ),
            DocumentTimelineEntryRecord(
                stage="indexed",
                status="completed",
                updated_at=created_at + timedelta(minutes=18),
                message="Vector index and graph provenance updated.",
            ),
        ]

    def _build_in_progress_timeline(self, *, filename: str, created_at: datetime) -> list[DocumentTimelineEntryRecord]:
        return [
            DocumentTimelineEntryRecord(
                stage="registered",
                status="completed",
                updated_at=created_at,
                message=f"{filename} registered for ingestion.",
            ),
            DocumentTimelineEntryRecord(
                stage="parsed",
                status="running",
                updated_at=created_at + timedelta(minutes=8),
                message="Parser is normalizing tabular anomalies into a typed intermediate form.",
            ),
            DocumentTimelineEntryRecord(
                stage="extracted",
                status="pending",
                updated_at=created_at + timedelta(minutes=11),
                message="Entity extraction will start after parsing is complete.",
            ),
        ]

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _entity_type_at(self, index: int) -> str:
        if not self._entity_definitions:
            return "entity"
        return self._entity_definitions[index % len(self._entity_definitions)].name

    def _relationship_type_at(self, index: int) -> str:
        relationships = list(self._domain_config.relationships)
        if not relationships:
            return "related_to"
        return relationships[index % len(relationships)].name

    def _entity_definition_for(self, entity_type: str) -> EntityDefinition | None:
        return self._entity_definition_by_type.get(entity_type)

    def _entity_summary(self, entity: Entity) -> str:
        definition = self._entity_definition_for(entity.type)
        label = definition.display_label if definition is not None else entity.type.title()
        display_name = entity.properties.get("display_name")
        if isinstance(display_name, str) and display_name.strip():
            return f"{label} entity named {display_name} in the active knowledge base."
        return f"{label} entity in the active knowledge base."


def create_api_state(domain_config: DomainConfig | None = None) -> ApiState:
    """Create the seeded API application state."""
    return ApiState(domain_config)


def _normalize_severity(severity: str, confidence: float) -> Literal["low", "medium", "high", "critical"]:
    if severity == "high" and confidence >= 0.9:
        return "critical"
    if severity in {"high", "medium", "low", "critical"}:
        return cast(Literal["low", "medium", "high", "critical"], severity)
    return "medium"


def _normalize_risk_level(risk_level: str, overall_score: float) -> Literal["low", "medium", "high", "critical"]:
    if overall_score >= 0.9:
        return "critical"
    if risk_level in {"high", "medium", "low", "critical"}:
        return cast(Literal["low", "medium", "high", "critical"], risk_level)
    return "medium"


def _normalize_knowledge_base_status(status: str) -> Literal["active", "building", "ready", "error", "archived"]:
    if status in {"active", "ready", "error", "archived"}:
        return cast(Literal["active", "building", "ready", "error", "archived"], status)
    if status in {"indexing", "rebuilding", "building"}:
        return "building"
    return "active"


def _normalize_document_status(status: str) -> Literal["pending", "registered", "building", "ready", "failed", "error"]:
    if status in {"pending", "registered", "building", "ready", "failed", "error"}:
        return cast(Literal["pending", "registered", "building", "ready", "failed", "error"], status)
    if status in {"parsing", "parsed", "chunked", "extracted"}:
        return "building"
    if status == "validated":
        return "ready"
    return "pending"


