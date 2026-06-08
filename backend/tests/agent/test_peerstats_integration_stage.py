"""End-to-end tests for the peerstats stage folded into handle_records_ingested.

The worker's in-memory ``RecordColumnSource`` is empty by default (real data
flows through the Postgres adapter, which reads ``raw_records`` directly), so
these tests seed the column source directly to exercise the STAGE WIRING:
that handle_records_ingested runs run_peerstats_stage, persists signals, and
assesses the deduped affected entities — best-effort, gated on the flag.
"""

from __future__ import annotations

from datetime import datetime, timezone

from agent.coordinator import handle_records_ingested
from analytics.peerstats.adapters.in_memory import (
    InMemoryDerivedRiskSignalWriter,
    InMemoryRecordColumnSource,
)
from analytics.peerstats.adapters.protocols import ColumnRow, RecordColumnSourceProtocol
from analytics.peerstats.models import PeerAggregate
from analytics.peerstats.service import PeerStatsService, create_peerstats_service
from analytics.risk.adapters.in_memory import InMemoryRiskSignalSource
from analytics.risk.models import RiskProfile, RiskSignal
from analytics.risk.service import RiskService, create_risk_service
from config.schema import (
    PeerMetricSpec,
    PeerStatsConfig,
    RecordEntityMapping,
    RecordFeedConfig,
    RecordsConfig,
)
from events.adapters.in_memory import InMemoryEventBus
from events.types import RecordsIngestedEvent, RiskScoredEvent
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.service import GraphService, create_graph_service
from monitoring.adapters.in_memory import InMemoryObservationWriter
from records.adapters.in_memory import InMemoryRawRecordStore
from records.models import RawRecord, content_hash_for
from storage.adapters.in_memory import InMemoryObjectStore

MONDAY = datetime(2026, 1, 5, tzinfo=timezone.utc)


def _records_config() -> RecordsConfig:
    return RecordsConfig(
        feeds=[
            RecordFeedConfig(
                name="claims_feed",
                record_type="claim_record",
                source="file_upload",
                id_field="claim_id",
                entities=[
                    RecordEntityMapping(
                        entity_type="provider",
                        id_field="provider_npi",
                        property_fields={"npi": "provider_npi"},
                    ),
                ],
            )
        ]
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


def _peerstats_service(
    writer: InMemoryDerivedRiskSignalWriter,
) -> PeerStatsService:
    source = InMemoryRecordColumnSource()
    source.add_rows(
        "kb-1",
        "claim_record",
        [
            ColumnRow(entity_id="provider:1", entity_type="provider",
                      group_values=(), value=10.0, observed_at=MONDAY),
            ColumnRow(entity_id="provider:2", entity_type="provider",
                      group_values=(), value=20.0, observed_at=MONDAY),
        ],
    )
    return create_peerstats_service(source, writer=writer)


def _graph_service() -> GraphService:
    return create_graph_service(
        InMemoryGraphRepository(),
        object_store=InMemoryObjectStore(),
        event_bus=InMemoryEventBus(),
    )


def _risk_service(event_bus: InMemoryEventBus) -> RiskService:
    # provider:1 has a profile (>=2 signals) so assess succeeds; provider:2 has
    # none, so assess raises RiskError and is skipped — covering both branches.
    profile = RiskProfile(
        knowledge_base_id="kb-1",
        entity_id="provider:1",
        signals=[
            RiskSignal(signal_name="a", value=0.5, weight=1.0),
            RiskSignal(signal_name="b", value=0.3, weight=1.0),
        ],
    )
    return create_risk_service(
        InMemoryRiskSignalSource(profiles=[profile]), event_bus=event_bus
    )


def _event() -> RecordsIngestedEvent:
    return RecordsIngestedEvent(
        correlation_id="corr-1",
        knowledge_base_id="kb-1",
        feed_name="claims_feed",
        record_type="claim_record",
        record_count=2,
    )


def test_peerstats_stage_runs_persists_and_assesses_when_enabled() -> None:
    store = InMemoryRawRecordStore()
    _seed_store(store)
    writer = InMemoryDerivedRiskSignalWriter()
    risk_event_bus = InMemoryEventBus()

    processed = handle_records_ingested(
        _event(),
        records_config=_records_config(),
        raw_record_store=store,
        graph_service=_graph_service(),
        observation_writer=InMemoryObservationWriter(),
        peerstats_service=_peerstats_service(writer),
        peer_stats_config=_peer_stats_config(),
        risk_service=_risk_service(risk_event_bus),
        peer_stats_enabled=True,
    )

    assert processed == 2
    # Peerstats ran: both providers received a derived signal.
    assert (
        writer.latest_signals(knowledge_base_id="kb-1", entity_id="provider:1")[0].metric_name
        == "weekly_billing"
    )
    assert writer.latest_signals(knowledge_base_id="kb-1", entity_id="provider:2")
    # The affected entity with a profile was assessed → exactly one RiskScoredEvent.
    scored = [e for e in risk_event_bus.published_events if isinstance(e, RiskScoredEvent)]
    assert len(scored) == 1


def test_peerstats_stage_skipped_when_disabled() -> None:
    store = InMemoryRawRecordStore()
    _seed_store(store)
    writer = InMemoryDerivedRiskSignalWriter()

    processed = handle_records_ingested(
        _event(),
        records_config=_records_config(),
        raw_record_store=store,
        graph_service=_graph_service(),
        observation_writer=InMemoryObservationWriter(),
        peerstats_service=_peerstats_service(writer),
        peer_stats_config=_peer_stats_config(),
        risk_service=_risk_service(InMemoryEventBus()),
        peer_stats_enabled=False,
    )

    assert processed == 2
    # Stage gated off: nothing written.
    assert writer.latest_signals(knowledge_base_id="kb-1", entity_id="provider:1") == []


class _RaisingColumnSource:
    """A column source that always fails, to exercise the best-effort swallow."""

    def load_interval_aggregates(
        self,
        *,
        knowledge_base_id: str,
        spec: PeerMetricSpec,
        interval_starts: list[datetime],
    ) -> list[PeerAggregate]:
        raise RuntimeError("boom")


def test_peerstats_stage_swallows_errors_and_completes_ingest() -> None:
    store = InMemoryRawRecordStore()
    _seed_store(store)
    source: RecordColumnSourceProtocol = _RaisingColumnSource()
    service = create_peerstats_service(
        source, writer=InMemoryDerivedRiskSignalWriter()
    )

    # Must NOT raise — the stage is best-effort.
    processed = handle_records_ingested(
        _event(),
        records_config=_records_config(),
        raw_record_store=store,
        graph_service=_graph_service(),
        observation_writer=InMemoryObservationWriter(),
        peerstats_service=service,
        peer_stats_config=_peer_stats_config(),
        risk_service=_risk_service(InMemoryEventBus()),
        peer_stats_enabled=True,
    )
    assert processed == 2
