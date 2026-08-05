"""Integration tests for SAFE-CMS-020 Postgres governance eval storage."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import pytest

from config.schema import DatabaseConfig
from database.protocols import ConnectionProvider
from database.runtime import create_connection_provider
from governance.adapters.postgres import PostgresGovernanceEvalRepository
from governance.models import (
    GovernanceDriftSummary,
    GovernanceEvalRun,
    GovernanceMetricResult,
)

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_KB_ID = "kb-safe-cms-020-pg"

pytestmark = pytest.mark.integration


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set; skipping governance eval integration tests.")
    return url


@pytest.fixture
def provider(database_url: str) -> Iterator[ConnectionProvider]:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=_BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": database_url},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    connection_provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert connection_provider is not None
    with connection_provider.connection() as conn:
        conn.execute(
            "DELETE FROM governance_eval_runs WHERE knowledge_base_id LIKE %s",
            (_KB_ID + "%",),
        )
        conn.commit()
    yield connection_provider
    with connection_provider.connection() as conn:
        conn.execute(
            "DELETE FROM governance_eval_runs WHERE knowledge_base_id LIKE %s",
            (_KB_ID + "%",),
        )
        conn.commit()
    connection_provider.close()


def test_postgres_governance_eval_repository_round_trips_run(
    provider: ConnectionProvider,
) -> None:
    repository = PostgresGovernanceEvalRepository(provider)
    run = _run()

    stored = repository.save_eval_run(run)
    found = repository.get_eval_run(run.run_id)

    assert found is not None
    assert stored == found
    assert found.metrics[0].name == "precision"
    assert found.metrics[0].passed is True
    assert found.drift_summary.failed_metric_count == 0
    assert found.dataset_source_refs == [
        "explanation_review:pack-1:narrative:narrative"
    ]


def test_postgres_governance_eval_repository_lists_by_kb_and_updates(
    provider: ConnectionProvider,
) -> None:
    repository = PostgresGovernanceEvalRepository(provider)
    repository.save_eval_run(_run("model-a", created_at=datetime(2026, 8, 5, 13, tzinfo=timezone.utc)))
    repository.save_eval_run(_run("model-b", created_at=datetime(2026, 8, 5, 14, tzinfo=timezone.utc)))
    repository.save_eval_run(_run("model-c", knowledge_base_id=_KB_ID + "-other"))

    page = repository.list_eval_runs(knowledge_base_id=_KB_ID, limit=1, offset=1)

    assert page.total_items == 2
    assert [item.artifact_id for item in page.items] == ["model-b"]

    updated = page.items[0].model_copy(update={"status": "approved"})
    repository.update_eval_run(updated)

    found = repository.get_eval_run(updated.run_id)
    assert found is not None
    assert found.status == "approved"


def _run(
    artifact_id: str = "risk-scorer",
    *,
    knowledge_base_id: str = _KB_ID,
    created_at: datetime = datetime(2026, 8, 5, 12, tzinfo=timezone.utc),
) -> GovernanceEvalRun:
    return GovernanceEvalRun(
        run_id=f"{knowledge_base_id}:model:{artifact_id}:candidate-v2:tn-demo-1pct",
        knowledge_base_id=knowledge_base_id,
        artifact_kind="model",
        artifact_id=artifact_id,
        artifact_version="candidate-v2",
        baseline_version="prod-v1",
        dataset_id="tn-demo-1pct",
        status="candidate",
        metrics=[
            GovernanceMetricResult(
                name="precision",
                baseline_value=0.72,
                candidate_value=0.78,
                threshold=0.0,
                direction="higher",
                delta=0.06,
                passed=True,
            )
        ],
        drift_summary=GovernanceDriftSummary(
            metric_count=1,
            failed_metric_count=0,
            max_abs_delta=0.06,
        ),
        dataset_source_refs=["explanation_review:pack-1:narrative:narrative"],
        affected_alert_ids=["alert-1"],
        affected_case_ids=["case-1"],
        created_by="model-owner-1",
        created_at=created_at,
    )
