"""Every KB-scoped Postgres table is purged by the KB-delete cascade.

Reads the Alembic migrations for tables carrying a ``knowledge_base_id``
column, so a new per-KB table fails here until it either gets a step in
``knowledgebases.cleanup.kb_deletion_steps`` or is listed as retained.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock

from knowledgebases.cleanup import KbDeletionStores, kb_deletion_steps

_VERSIONS_DIR = Path(__file__).resolve().parents[2] / "database" / "migrations" / "versions"

# Table -> the cascade step that purges it (directly or by FK cascade).
_PURGED_BY_STEP = {
    "raw_records": "raw_records",
    "record_submissions": "raw_records",
    "entity_derived_signals": "derived_signals",
    "timeseries_anomalies": "timeseries_anomalies",
    "risk_score_history": "risk_history",
    "risk_projections": "risk_projections",
    "observations": "observations",
    "alert_history": "alert_history",
    "entity_metric_history": "metrics",
    "entity_metrics_current": "metrics",
    "conversations": "conversations",
    "cases": "cases",
    "policy_items": "policy",
    "scorecard_runs": "scorecards",
    "score_runs": "score_runs",
    "score_batches": "score_runs",
    "identity_links": "identity_links",
    "explanation_reviews": "explanation_reviews",
    "workflow_definition_snapshots": "workflow_definitions",
    "governance_eval_runs": "governance_evals",
    "connectors": "connectors",
    "connector_sync_runs": "connectors",
    "connector_quarantine_records": "connectors",
    "fraud_playbook_snapshots": "playbooks",
    "source_document_status": "document_status",
}

# Deliberately outlive the KB: the audit log is the append-only record of
# material actions, including the deletion itself.
_RETAINED = {"audit_log"}

_CREATE_TABLE = re.compile(
    r"CREATE TABLE (?:IF NOT EXISTS )?(\w+) \((.*?)\n\s*\)\s*\n", re.DOTALL
)
_ADD_KB_COLUMN = re.compile(
    r"ALTER TABLE (\w+)\s+ADD COLUMN (?:IF NOT EXISTS )?knowledge_base_id\b"
)


def _kb_scoped_tables() -> set[str]:
    tables: set[str] = set()
    for path in sorted(_VERSIONS_DIR.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        for name, body in _CREATE_TABLE.findall(source):
            if re.search(r"^\s*knowledge_base_id\s", body, re.MULTILINE):
                tables.add(name)
        tables.update(_ADD_KB_COLUMN.findall(source))
    return tables


def test_migrations_are_parsed() -> None:
    # Guards the regexes: a parse that finds nothing would pass vacuously.
    assert {"raw_records", "audit_log", "fraud_playbook_snapshots"} <= _kb_scoped_tables()


def test_every_kb_scoped_table_is_purged_or_retained() -> None:
    unaccounted = _kb_scoped_tables() - _PURGED_BY_STEP.keys() - _RETAINED

    assert unaccounted == set(), (
        "KB-scoped tables with no KB-delete step: add a delete_by_kb step to "
        "knowledgebases/cleanup.py, or list the table in _RETAINED with a reason."
    )


def test_mapped_steps_exist_in_the_cascade() -> None:
    stores = cast(KbDeletionStores, SimpleNamespace(**_mock_fields()))
    step_names = {name for name, _ in kb_deletion_steps(stores, "kb-1")}

    assert set(_PURGED_BY_STEP.values()) <= step_names


def _mock_fields() -> dict[str, MagicMock]:
    return {field: MagicMock() for field in KbDeletionStores.__dataclass_fields__}
