"""Unit tests for the KB-delete cascade step list (`api._kb_cleanup`)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock

from api._kb_cleanup import KbDeletionStores, kb_deletion_steps

_STORE_FIELDS = [
    "graph_service",
    "vector_service",
    "raw_record_store",
    "derived_signal_store",
    "risk_history_writer",
    "observation_writer",
    "alert_history_writer",
    "entity_metric_repository",
    "conversation_repository",
    "case_repository",
    "policy_item_repository",
    "evidence_pack_repository",
    "scorecard_run_repository",
    "object_store",
]

_EXPECTED_STEP_NAMES = [
    "graph",
    "vector",
    "raw_records",
    "derived_signals",
    "risk_history",
    "observations",
    "alert_history",
    "metrics",
    "conversations",
    "cases",
    "policy",
    "evidence",
    "scorecards",
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
        "observation_writer",
        "alert_history_writer",
        "entity_metric_repository",
        "conversation_repository",
        "case_repository",
        "policy_item_repository",
        "evidence_pack_repository",
        "scorecard_run_repository",
    ):
        mocks[field].delete_by_kb.assert_called_once_with("kb-1")
