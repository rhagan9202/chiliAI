"""Unit tests for the KB-delete cascade step list (`api._kb_cleanup`)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock

from analytics.timeseries.adapters.in_memory import InMemoryTimeseriesAnomalyStore
from analytics.timeseries.models import TimeseriesAnomalyRecord
from api._kb_cleanup import KbDeletionStores, kb_deletion_steps
from shared.utils import utc_now

_STORE_FIELDS = [
    "graph_service",
    "vector_service",
    "raw_record_store",
    "derived_signal_store",
    "risk_history_writer",
    "risk_projection_repository",
    "observation_writer",
    "alert_history_writer",
    "entity_metric_repository",
    "conversation_repository",
    "case_repository",
    "policy_item_repository",
    "evidence_pack_repository",
    "scorecard_run_repository",
    "document_status_store",
    "object_store",
    "gnn_cluster_store",
    "timeseries_anomaly_store",
]

_EXPECTED_STEP_NAMES = [
    "graph",
    "vector",
    "raw_records",
    "derived_signals",
    "timeseries_anomalies",
    "risk_history",
    "risk_projections",
    "observations",
    "alert_history",
    "gnn_clusters",
    "metrics",
    "conversations",
    "cases",
    "policy",
    "evidence",
    "scorecards",
    "document_status",
    "object_store",
]


def test_kb_deletion_steps_purges_every_durable_store() -> None:
    mocks = {field: MagicMock() for field in _STORE_FIELDS}
    mocks["object_store"].list_keys.return_value = []
    stores = cast(KbDeletionStores, SimpleNamespace(**mocks))

    steps = kb_deletion_steps(stores, "kb-1")

    # Every per-KB store has a step, in a stable order.
    assert [name for name, _ in steps] == _EXPECTED_STEP_NAMES

    # Running each step purges the right store for the right KB.
    for _name, deletion in steps:
        deletion()

    mocks["graph_service"].delete_knowledge_base.assert_called_once_with("kb-1")
    mocks["vector_service"].delete_knowledge_base.assert_called_once_with("kb-1")
    mocks["object_store"].list_keys.assert_called_once_with("knowledgebases/kb-1/")
    # All the delete_by_kb-backed stores.
    for field in (
        "raw_record_store",
        "derived_signal_store",
        "risk_history_writer",
        "risk_projection_repository",
        "observation_writer",
        "alert_history_writer",
        "entity_metric_repository",
        "conversation_repository",
        "case_repository",
        "policy_item_repository",
        "evidence_pack_repository",
        "scorecard_run_repository",
        "document_status_store",
        "gnn_cluster_store",
        "timeseries_anomaly_store",
    ):
        mocks[field].delete_by_kb.assert_called_once_with("kb-1")


def test_kb_delete_purges_timeseries_anomalies() -> None:
    """The timeseries anomaly store is purged by the cascade like every other
    per-KB durable store (Task 5, B2)."""
    mocks = {field: MagicMock() for field in _STORE_FIELDS if field != "timeseries_anomaly_store"}
    mocks["object_store"].list_keys.return_value = []
    timeseries_anomaly_store = InMemoryTimeseriesAnomalyStore()
    timeseries_anomaly_store.write_anomalies(
        [
            TimeseriesAnomalyRecord(
                knowledge_base_id="kb-1",
                entity_id="provider:1",
                metric_name="claims_per_week",
                observed_at=utc_now(),
                observed_value=42.0,
                expected_value=10.0,
                z_score=3.2,
                severity=0.8,
                detection_strategy="zscore",
                correlation_id="corr-1",
            )
        ]
    )
    stores = cast(
        KbDeletionStores,
        SimpleNamespace(
            **mocks, timeseries_anomaly_store=timeseries_anomaly_store
        ),
    )

    for _name, deletion in kb_deletion_steps(stores, "kb-1"):
        deletion()

    assert (
        timeseries_anomaly_store.load_anomalies(
            knowledge_base_id="kb-1",
            entity_id="provider:1",
            metric_name="claims_per_week",
        )
        == []
    )
