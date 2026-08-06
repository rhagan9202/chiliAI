"""Integration tests for durable Postgres score-run storage."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import pytest

from analytics.score_runs.adapters.postgres import PostgresScoreRunRepository
from analytics.score_runs.models import ScoreBatch, ScoreRun
from config.schema import DatabaseConfig
from database.protocols import ConnectionProvider
from database.runtime import create_connection_provider

# parents: [0] score_runs, [1] analytics, [2] tests, [3] backend.
# This file sits one level deeper than tests/governance/, so [3] — not [2] —
# is the backend root alembic must run from.
_BACKEND_DIR = Path(__file__).resolve().parents[3]
_KB_ID = "kb-score-runs-pg"
BASE_TIME = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)

pytestmark = pytest.mark.integration


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set; skipping score-run integration tests.")
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
    _purge(connection_provider)
    yield connection_provider
    _purge(connection_provider)
    connection_provider.close()


def _purge(connection_provider: ConnectionProvider) -> None:
    with connection_provider.connection() as conn:
        # score_batches cascades from score_runs.
        conn.execute(
            "DELETE FROM score_runs WHERE knowledge_base_id LIKE %s", (_KB_ID + "%",)
        )
        conn.commit()


def _run(run_id: str = "score-run-pg-1", *, status: str = "queued") -> ScoreRun:
    return ScoreRun(
        id=run_id,
        knowledge_base_id=_KB_ID,
        status=status,  # type: ignore[arg-type]
        requested_by="operator-1",
        idempotency_key=None,
        model_version="risk-linear-v1",
        catalog_version="cms-desynpuf-features-v1",
        total_entities=2,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def _batch(
    run_id: str = "score-run-pg-1",
    batch_number: int = 0,
    *,
    entity_ids: list[str] | None = None,
) -> ScoreBatch:
    return ScoreBatch(
        id=f"{run_id}-batch-{batch_number}",
        run_id=run_id,
        knowledge_base_id=_KB_ID,
        batch_number=batch_number,
        status="queued",
        entity_ids=entity_ids if entity_ids is not None else ["provider-1", "provider-2"],
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def test_round_trips_a_run_and_its_batches(provider: ConnectionProvider) -> None:
    repository = PostgresScoreRunRepository(provider)
    repository.save_run(_run())
    repository.upsert_batch(_batch(batch_number=0))

    stored = repository.get_run("score-run-pg-1")
    batches = repository.list_batches(run_id="score-run-pg-1")

    assert stored is not None
    assert stored.knowledge_base_id == _KB_ID
    assert stored.catalog_version == "cms-desynpuf-features-v1"
    assert [b.batch_number for b in batches] == [0]
    assert batches[0].entity_ids == ["provider-1", "provider-2"]


def test_claim_batch_is_atomic(provider: ConnectionProvider) -> None:
    """The conditional UPDATE is the concurrency guard.

    Two workers can be handed the same event by reclaim_stale_pending; only one
    may transition the batch out of `queued`.
    """
    repository = PostgresScoreRunRepository(provider)
    repository.save_run(_run())
    repository.upsert_batch(_batch(batch_number=0))

    first = repository.claim_batch(
        run_id="score-run-pg-1", batch_number=0, now=BASE_TIME
    )
    second = repository.claim_batch(
        run_id="score-run-pg-1", batch_number=0, now=BASE_TIME
    )

    assert first is not None
    assert first.status == "running"
    assert first.attempts == 1
    assert second is None


def test_get_batch_returns_none_for_an_unknown_batch(
    provider: ConnectionProvider,
) -> None:
    repository = PostgresScoreRunRepository(provider)
    assert repository.get_batch(run_id="missing", batch_number=0) is None


def test_idempotency_key_is_enforced_by_the_database(
    provider: ConnectionProvider,
) -> None:
    """Two starts with the same key must not both insert."""
    repository = PostgresScoreRunRepository(provider)
    first = _run("score-run-pg-idem-1")
    repository.save_run(first.model_copy(update={"idempotency_key": "same-key"}))

    with pytest.raises(ValueError, match="idempotency"):
        repository.save_run(
            _run("score-run-pg-idem-2").model_copy(
                update={"idempotency_key": "same-key"}
            )
        )


def test_deleting_a_run_cascades_to_its_batches(provider: ConnectionProvider) -> None:
    repository = PostgresScoreRunRepository(provider)
    repository.save_run(_run())
    repository.upsert_batch(_batch(batch_number=0))

    deleted = repository.delete_by_kb(_KB_ID)

    assert deleted == 1
    assert repository.get_run("score-run-pg-1") is None
    assert repository.list_batches(run_id="score-run-pg-1") == []


def test_entity_ids_survive_a_jsonb_round_trip(provider: ConnectionProvider) -> None:
    """Guards the json.loads narrowing pattern that broke CI for nine sprints."""
    repository = PostgresScoreRunRepository(provider)
    repository.save_run(_run())
    repository.upsert_batch(_batch(batch_number=0, entity_ids=[]))

    stored = repository.get_batch(run_id="score-run-pg-1", batch_number=0)

    assert stored is not None
    assert stored.entity_ids == []
