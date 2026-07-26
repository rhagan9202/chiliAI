"""Tests for the records→analytics fan-out (analytics.34).

A structured-records batch whose entities are risk-assessable runs Flow B
(GNN → risk → explainability → alerts) in-process at the end of
``handle_records_ingested`` — gated on ``RecordsConfig.analytics_trigger``,
throttled per KB, and capped to the batch's top-N entities by risk score.
No ``graph.updated`` event is published: the fan-out is a direct call with
inline ``upserted_entity_ids``, so Flow A never re-runs.

The fixtures mirror ``test_peerstats_integration_stage.py``: peerstats
produces the ``affected`` entity set, a static risk-signal source makes the
providers assessable, and the graph repository is shared with the GNN
snapshot source so the ingested entities form a real analyzable graph.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

pytest.importorskip("networkx")
pytest.importorskip("numpy")

from agent.coordinator import handle_records_ingested
from analytics.explainability.models import (
    ExplanationContext,
    ExplanationItem,
    ExplanationSubgraph,
)
from analytics.explainability.service import create_explainability_service
from analytics.gnn.adapters.cluster_store import InMemoryClusterSummaryStore
from analytics.gnn.adapters.graph_repository_source import GraphRepositorySnapshotSource
from analytics.gnn.service import GnnService, create_gnn_service
from analytics.gnn.service_models import GnnAnalysisRequest, GnnAnalysisResponse
from analytics.metrics.throttle import MetricsRecomputeThrottle
from analytics.peerstats.adapters.in_memory import (
    InMemoryDerivedRiskSignalWriter,
    InMemoryRecordColumnSource,
)
from analytics.peerstats.adapters.protocols import ColumnRow
from analytics.peerstats.service import PeerStatsService, create_peerstats_service
from analytics.risk.adapters.in_memory import InMemoryRiskSignalSource
from analytics.risk.models import RiskProfile, RiskSignal
from analytics.risk.service import RiskService, create_risk_service
from config.schema import (
    PeerMetricSpec,
    PeerStatsConfig,
    RecordEntityMapping,
    RecordFeedConfig,
    RecordRelationshipMapping,
    RecordsAnalyticsTriggerConfig,
    RecordsConfig,
)
from events.adapters.in_memory import InMemoryEventBus
from events.types import AlertsCreatedEvent, AnalysisFailedEvent, RecordsIngestedEvent
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.service import GraphService, create_graph_service
from monitoring.adapters.in_memory import InMemoryObservationWriter
from records.adapters.in_memory import InMemoryRawRecordStore
from records.models import RawRecord, content_hash_for
from storage.adapters.in_memory import InMemoryObjectStore

MONDAY = datetime(2026, 1, 5, tzinfo=timezone.utc)


def _records_config(
    *, trigger: RecordsAnalyticsTriggerConfig | None = None
) -> RecordsConfig:
    return RecordsConfig(
        feeds=[
            RecordFeedConfig(
                name="claims_feed",
                record_type="claim_record",
                source="file_upload",
                id_field="claim_id",
                entities=[
                    RecordEntityMapping(
                        entity_type="claim",
                        id_field="claim_id",
                        property_fields={"amount": "billed_amount"},
                    ),
                    RecordEntityMapping(
                        entity_type="provider",
                        id_field="provider_npi",
                        property_fields={"npi": "provider_npi"},
                    ),
                ],
                relationships=[
                    RecordRelationshipMapping(
                        relationship_type="submitted_by",
                        source_entity_type="claim",
                        target_entity_type="provider",
                    )
                ],
            )
        ],
        analytics_trigger=trigger or RecordsAnalyticsTriggerConfig(),
    )


def _enabled_trigger(
    *, max_entities_per_batch: int = 25
) -> RecordsAnalyticsTriggerConfig:
    return RecordsAnalyticsTriggerConfig(
        enabled=True, max_entities_per_batch=max_entities_per_batch
    )


def _peer_stats_config() -> PeerStatsConfig:
    return PeerStatsConfig(
        metrics=[
            PeerMetricSpec(
                name="weekly_billing",
                record_type="claim_record",
                entity_type="provider",
                entity_id_field="provider_npi",
                value_column="billed_amount",
                aggregation="sum",
                interval="week",
                min_peers=2,
            )
        ]
    )


def _seed_store(store: InMemoryRawRecordStore) -> None:
    for npi in ("1", "2"):
        payload: dict[str, object] = {
            "claim_id": f"c{npi}",
            "provider_npi": npi,
            "billed_amount": float(npi) * 10.0,
        }
        store.persist(
            [
                RawRecord(
                    knowledge_base_id="kb-1",
                    record_type="claim_record",
                    record_id=f"c{npi}",
                    payload=payload,
                    source_type="file_upload",
                    source_ref="claims.csv",
                    correlation_id="corr-1",
                    content_hash=content_hash_for(payload),
                )
            ]
        )


def _peerstats_service() -> PeerStatsService:
    source = InMemoryRecordColumnSource()
    source.add_rows(
        "kb-1",
        "claim_record",
        [
            ColumnRow(
                entity_id="provider:1",
                entity_type="provider",
                group_values=(),
                value=10.0,
                observed_at=MONDAY,
            ),
            ColumnRow(
                entity_id="provider:2",
                entity_type="provider",
                group_values=(),
                value=20.0,
                observed_at=MONDAY,
            ),
        ],
    )
    return create_peerstats_service(source, writer=InMemoryDerivedRiskSignalWriter())


def _risk_service(event_bus: InMemoryEventBus) -> RiskService:
    # provider:1 scores high, provider:2 low — the cap test relies on the
    # ordering being deterministic from these profiles.
    profiles = [
        RiskProfile(
            knowledge_base_id="kb-1",
            entity_id="provider:1",
            signals=[
                RiskSignal(signal_name="a", value=0.9, weight=1.0),
                RiskSignal(signal_name="b", value=0.8, weight=1.0),
            ],
        ),
        RiskProfile(
            knowledge_base_id="kb-1",
            entity_id="provider:2",
            signals=[
                RiskSignal(signal_name="a", value=0.1, weight=1.0),
                RiskSignal(signal_name="b", value=0.2, weight=1.0),
            ],
        ),
    ]
    return create_risk_service(
        InMemoryRiskSignalSource(profiles=profiles), event_bus=event_bus
    )


class _AcceptingExplainabilityContextSource:
    """Deterministic context per alert (mirrors test_coordinator's double)."""

    def load_context(
        self, *, knowledge_base_id: str, alert_id: str
    ) -> ExplanationContext:
        from shared.types import Alert

        return ExplanationContext(
            knowledge_base_id=knowledge_base_id,
            alert=Alert(
                id=alert_id,
                entity_type="provider",
                entity_id="provider:1",
                severity="high",
                title="Outlier",
                reasoning="Detected by analytics pipeline.",
                created_at=datetime.now(timezone.utc),
            ),
            explanation_items=[
                ExplanationItem(
                    source_id="signal-1",
                    source_type="risk_signal",
                    quote="High anomaly score.",
                    rationale="Anomaly score exceeds baseline.",
                    score=0.9,
                )
            ],
            subgraph=ExplanationSubgraph(node_ids=["provider:1"], edge_ids=[]),
            confidence=0.8,
        )


class _Harness:
    """One assembled records+analytics fixture set sharing a graph repo."""

    def __init__(self) -> None:
        self.event_bus = InMemoryEventBus()
        self.store = InMemoryRawRecordStore()
        _seed_store(self.store)
        self.graph_repository = InMemoryGraphRepository()
        self.graph_service: GraphService = create_graph_service(
            self.graph_repository,
            object_store=InMemoryObjectStore(),
            event_bus=self.event_bus,
        )
        self.cluster_store = InMemoryClusterSummaryStore()
        self.gnn_service: GnnService = create_gnn_service(
            GraphRepositorySnapshotSource(self.graph_repository, self.cluster_store),
            event_bus=self.event_bus,
        )
        self.risk_service = _risk_service(self.event_bus)
        self.explainability_service = create_explainability_service(
            _AcceptingExplainabilityContextSource(),
            event_bus=self.event_bus,
        )

    def run(
        self,
        *,
        records_config: RecordsConfig,
        correlation_id: str = "corr-1",
        gnn_service: GnnService | None = None,
        analytics_trigger_throttle: MetricsRecomputeThrottle | None = None,
    ) -> int:
        return handle_records_ingested(
            RecordsIngestedEvent(
                correlation_id=correlation_id,
                knowledge_base_id="kb-1",
                feed_name="claims_feed",
                record_type="claim_record",
                record_count=2,
            ),
            records_config=records_config,
            raw_record_store=self.store,
            graph_service=self.graph_service,
            observation_writer=InMemoryObservationWriter(),
            peerstats_service=_peerstats_service(),
            peer_stats_config=_peer_stats_config(),
            risk_service=self.risk_service,
            peer_stats_enabled=True,
            event_bus=self.event_bus,
            gnn_service=gnn_service or self.gnn_service,
            explainability_service=self.explainability_service,
            gnn_cluster_store=self.cluster_store,
            analytics_trigger_throttle=analytics_trigger_throttle,
        )

    def alerts_created(self) -> list[AlertsCreatedEvent]:
        return [
            event
            for event in self.event_bus.published_events
            if isinstance(event, AlertsCreatedEvent)
        ]


def test_records_only_kb_produces_clusters_and_alerts_when_trigger_enabled() -> None:
    harness = _Harness()
    processed = harness.run(
        records_config=_records_config(trigger=_enabled_trigger())
    )

    assert processed == 2
    # Flow B ran natively: GNN communities persisted for the records-only KB…
    assert harness.cluster_store.load_clusters(knowledge_base_id="kb-1")
    # …and both assessable providers raised alerts.
    alerts_events = harness.alerts_created()
    assert len(alerts_events) == 1
    alert_entities = {alert.entity_id for alert in alerts_events[0].alerts}
    assert alert_entities == {"provider:1", "provider:2"}


def test_trigger_disabled_runs_no_analytics() -> None:
    harness = _Harness()
    processed = harness.run(records_config=_records_config())

    assert processed == 2
    assert not harness.cluster_store.load_clusters(knowledge_base_id="kb-1")
    assert harness.alerts_created() == []


def test_trigger_caps_to_top_n_by_score() -> None:
    harness = _Harness()
    harness.run(
        records_config=_records_config(
            trigger=_enabled_trigger(max_entities_per_batch=1)
        )
    )

    alerts_events = harness.alerts_created()
    assert len(alerts_events) == 1
    assert [alert.entity_id for alert in alerts_events[0].alerts] == ["provider:1"]


def test_trigger_throttle_suppresses_second_batch() -> None:
    harness = _Harness()
    throttle = MetricsRecomputeThrottle(min_interval_seconds=3600)
    config = _records_config(trigger=_enabled_trigger())

    harness.run(records_config=config, analytics_trigger_throttle=throttle)
    harness.run(
        records_config=config,
        correlation_id="corr-2",
        analytics_trigger_throttle=throttle,
    )

    assert len(harness.alerts_created()) == 1


class _ExplodingGnnService:
    def analyze(self, request: GnnAnalysisRequest) -> GnnAnalysisResponse:
        raise RuntimeError("gnn exploded")


def test_trigger_failure_never_breaks_ingest() -> None:
    harness = _Harness()
    processed = harness.run(
        records_config=_records_config(trigger=_enabled_trigger()),
        gnn_service=_ExplodingGnnService(),  # type: ignore[arg-type]
    )

    # Ingest completed despite the analytics failure…
    assert processed == 2
    assert harness.alerts_created() == []
    # …and the failure is visible, not swallowed silently.
    failures = [
        event
        for event in harness.event_bus.published_events
        if isinstance(event, AnalysisFailedEvent)
        and event.stage == "analytics_fanout"
    ]
    assert failures
    assert {failure.entity_id for failure in failures} == {
        "provider:1",
        "provider:2",
    }
