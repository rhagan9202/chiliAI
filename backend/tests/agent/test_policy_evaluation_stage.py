"""Tests for the policy-evaluation step folded into handle_records_ingested (BL-011)."""

from __future__ import annotations

from agent.coordinator import build_worker_dependencies, handle_records_ingested
from config.schema import (
    PolicyPredicate,
    PolicyPredicateValue,
    PolicyRule,
    PolicyRulePack,
    RecordEntityMapping,
    RecordFeedConfig,
    RecordsConfig,
)
from events.adapters.in_memory import InMemoryEventBus
from events.types import RecordsIngestedEvent
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.service import GraphService, create_graph_service
from monitoring.adapters.in_memory import InMemoryObservationWriter
from policy.adapters.in_memory import InMemoryPolicyItemRepository
from policy.service import PolicyService, create_policy_service
from records.adapters.in_memory import InMemoryRawRecordStore
from records.models import RawRecord, content_hash_for
from storage.adapters.in_memory import InMemoryObjectStore


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
                        entity_type="claim",
                        id_field="claim_id",
                        property_fields={"amount": "billed_amount"},
                    ),
                ],
            )
        ]
    )


def _billing_pack() -> PolicyRulePack:
    return PolicyRulePack(
        id="billing_thresholds",
        name="Billing thresholds",
        thresholds={"max_billed_amount": 1000.0},
        rules=[
            PolicyRule(
                id="claim_over_billed",
                title_template="Claim {target_ref} exceeds the billing threshold",
                severity="high",
                target_kind="entity",
                target_selector={"entity_type": "claim"},
                predicate=PolicyPredicate(
                    field="properties.amount",
                    op="gt",
                    value=PolicyPredicateValue(config_ref="max_billed_amount"),
                ),
            )
        ],
    )


def _seed_store(store: InMemoryRawRecordStore, *, billed_amount: float) -> None:
    payload: dict[str, object] = {
        "claim_id": "c1",
        "billed_amount": billed_amount,
    }
    store.persist(
        [
            RawRecord(
                knowledge_base_id="kb-1",
                record_type="claim_record",
                record_id="c1",
                payload=payload,
                source_type="file_upload",
                source_ref="claims.csv",
                correlation_id="corr-1",
                content_hash=content_hash_for(payload),
            )
        ]
    )


def _graph_service() -> GraphService:
    return create_graph_service(
        InMemoryGraphRepository(),
        object_store=InMemoryObjectStore(),
        event_bus=InMemoryEventBus(),
    )


def _policy_service() -> PolicyService:
    return create_policy_service(InMemoryPolicyItemRepository())


def _event() -> RecordsIngestedEvent:
    return RecordsIngestedEvent(
        correlation_id="corr-1",
        knowledge_base_id="kb-1",
        feed_name="claims_feed",
        record_type="claim_record",
        record_count=1,
    )


def test_records_ingested_generates_policy_items() -> None:
    store = InMemoryRawRecordStore()
    _seed_store(store, billed_amount=1500.0)
    policy_service = _policy_service()

    processed = handle_records_ingested(
        _event(),
        records_config=_records_config(),
        raw_record_store=store,
        graph_service=_graph_service(),
        observation_writer=InMemoryObservationWriter(),
        policy_rules=[_billing_pack()],
        policy_service=policy_service,
    )

    assert processed == 1
    items, total = policy_service.list(knowledge_base_id="kb-1", limit=10, offset=0)
    assert total == 1
    assert items[0].rule_id == "claim_over_billed"
    assert items[0].target_ref == "claim:c1"
    assert items[0].status == "open"


def test_no_policy_items_when_under_threshold() -> None:
    store = InMemoryRawRecordStore()
    _seed_store(store, billed_amount=10.0)
    policy_service = _policy_service()

    handle_records_ingested(
        _event(),
        records_config=_records_config(),
        raw_record_store=store,
        graph_service=_graph_service(),
        observation_writer=InMemoryObservationWriter(),
        policy_rules=[_billing_pack()],
        policy_service=policy_service,
    )

    _items, total = policy_service.list(knowledge_base_id="kb-1", limit=10, offset=0)
    assert total == 0


def test_policy_evaluation_is_skipped_when_unwired() -> None:
    store = InMemoryRawRecordStore()
    _seed_store(store, billed_amount=1500.0)

    processed = handle_records_ingested(
        _event(),
        records_config=_records_config(),
        raw_record_store=store,
        graph_service=_graph_service(),
        observation_writer=InMemoryObservationWriter(),
    )

    assert processed == 1


def test_policy_metrics_throttle_is_independent_from_metrics_throttle() -> None:
    """BL-011: policy-eval and graph-metrics must use separate throttle instances."""
    deps = build_worker_dependencies()
    assert deps.policy_metrics_throttle is not deps.metrics_throttle
