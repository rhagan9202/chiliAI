"""Application state for analytics read services backing frontend API reads.

BL-012 de-seeded this object: alerts, cases, conversations, workflows, evidence
packs, and the investigation graph are now served from durable stores (see
``api/dependencies.py`` and the per-domain repositories). What remains here is
the risk/timeseries analytics composition plus the RAG service handle used by
the chat streaming path — none of which read ``_seed_*`` data.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal, cast

from analytics.risk.exceptions import RiskConfigurationError, RiskInsufficientSignalsError
from analytics.risk.adapters.in_memory import InMemoryRiskSignalSource
from analytics.risk.models import RiskProfile, RiskSignal
from analytics.risk.service import create_risk_service
from analytics.risk.service_models import RiskAssessmentRequest
from analytics.timeseries.adapters.in_memory import InMemoryTimeSeriesHistorySource
from analytics.timeseries.exceptions import TimeseriesConfigurationError, TimeseriesInsufficientHistoryError
from analytics.timeseries.models import TimeSeriesObservation, TimeSeriesSeries
from analytics.timeseries.service import create_timeseries_service
from analytics.timeseries.service_models import TimeseriesAnalysisRequest
from config.loader import load_config
from config.schema import DomainConfig
from api.contracts import (
    EntityTimeseriesPointResponse,
    EntityTimeseriesResponse,
    RiskFactorResponse,
    RiskScoreResponse,
)
from events.adapters.in_memory import InMemoryEventBus
from rag.adapters.in_memory import (
    InMemoryAnswerGenerator,
    InMemoryContextRetriever,
    InMemoryGraphContextExpander,
    InMemoryQueryEmbedder,
)
from rag.models import ContextRecord
from rag.protocols import RagServiceProtocol
from rag.service import create_rag_service

__all__ = ["ApiState", "create_api_state"]


class ApiState:
    """Own the risk/timeseries analytics services and the RAG service handle."""

    def __init__(
        self,
        domain_config: DomainConfig | None = None,
        *,
        rag_service: RagServiceProtocol | None = None,
    ) -> None:
        self._domain_config = domain_config or load_config()
        self._entity_definitions = list(self._domain_config.entities)
        self._knowledge_base_id = "kb-1"
        self._primary_entity_id = "provider-204"
        self._secondary_entity_id = "provider-118"
        self._tertiary_entity_id = "claim-8821"
        self._quaternary_entity_id = "beneficiary-771"
        self._event_bus = InMemoryEventBus()

        self._risk_service = create_risk_service(
            InMemoryRiskSignalSource(profiles=self._build_risk_profiles()),
            event_bus=self._event_bus,
        )

        self._timeseries_source = InMemoryTimeSeriesHistorySource(series=self._build_timeseries_series())
        self._timeseries_service = create_timeseries_service(
            self._timeseries_source,
            event_bus=self._event_bus,
        )

        # When the gateway supplies a fully-wired RAG service we use it directly
        # (live embeddings/vectorstore/graph/LLM composition — see BL-001).
        # Falling back to the seeded in-memory pipeline keeps ApiState
        # self-contained for unit tests that construct it without DI.
        if rag_service is not None:
            self._rag_service = rag_service
        else:
            self._rag_service = create_rag_service(
                InMemoryQueryEmbedder(),
                InMemoryContextRetriever(records=self._build_context_records()),
                InMemoryAnswerGenerator(provider="in-memory", model_name="seeded-rag-model"),
                event_bus=self._event_bus,
                graph_context_expander=InMemoryGraphContextExpander(),
                domain_config=self._domain_config,
            )

    @property
    def rag_service(self) -> RagServiceProtocol:
        """The RAG service backing chat conversations and streaming responses."""
        return self._rag_service

    def get_risk_score(self, entity_id: str, *, knowledge_base_id: str | None = None) -> RiskScoreResponse:
        kb_id = knowledge_base_id or self._knowledge_base_id
        try:
            response = self._risk_service.assess(
                RiskAssessmentRequest(knowledge_base_id=kb_id, entity_id=entity_id)
            )
        except (RiskConfigurationError, RiskInsufficientSignalsError, ValueError):
            return RiskScoreResponse(
                entity_id=entity_id,
                overall_score=0.0,
                risk_level="low",
                factors=[],
                availability_status="unavailable",
                unavailable_reason="No risk profile has been generated for this entity.",
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
            availability_status="available",
            unavailable_reason=None,
        )

    def get_timeseries(self, entity_id: str, *, knowledge_base_id: str | None = None) -> EntityTimeseriesResponse:
        kb_id = knowledge_base_id or self._knowledge_base_id
        try:
            series = self._timeseries_source.load_series(
                knowledge_base_id=kb_id,
                entity_id=entity_id,
                metric_name="normalized_alert_pressure",
            )
            analysis = self._timeseries_service.analyze(
                TimeseriesAnalysisRequest(
                    knowledge_base_id=kb_id,
                    entity_id=entity_id,
                    metric_name=series.metric_name,
                    baseline_window=3,
                    min_history=5,
                    z_threshold=2.0,
                )
            )
        except (
            TimeseriesConfigurationError,
            TimeseriesInsufficientHistoryError,
            ValueError,
        ):
            return EntityTimeseriesResponse(
                entity_id=entity_id,
                metric_name="normalized_alert_pressure",
                points=[],
                availability_status="unavailable",
                unavailable_reason="No time series has been generated for this entity.",
            )
        anomaly_timestamps = {anomaly.observed_at for anomaly in analysis.anomalies}
        return EntityTimeseriesResponse(
            entity_id=entity_id,
            metric_name=series.metric_name,
            points=[
                EntityTimeseriesPointResponse(
                    timestamp=observation.observed_at,
                    value=observation.value,
                    label=observation.observed_at.strftime("%b %d"),
                    is_anomaly=observation.observed_at in anomaly_timestamps,
                )
                for observation in series.observations
            ],
            availability_status="available",
            unavailable_reason=None,
        )

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

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)


def create_api_state(
    domain_config: DomainConfig | None = None,
    *,
    rag_service: RagServiceProtocol | None = None,
) -> ApiState:
    """Create the API application state.

    When ``rag_service`` is provided it replaces the seeded in-memory RAG
    pipeline — used by :func:`api.app.create_app` to inject a live
    embeddings → vectorstore → graph → LLM composition (see BL-001).
    """
    return ApiState(domain_config, rag_service=rag_service)


def _normalize_risk_level(risk_level: str, overall_score: float) -> Literal["low", "medium", "high", "critical"]:
    if overall_score >= 0.9:
        return "critical"
    if risk_level in {"high", "medium", "low", "critical"}:
        return cast(Literal["low", "medium", "high", "critical"], risk_level)
    return "medium"
