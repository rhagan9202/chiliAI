# Score-All Executor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `POST /knowledgebases/{kb}/score-runs` actually score entities — durably, resumably, and without double-counting on replay.

**Architecture:** A new `backend/execution/` module dispatches executor events behind a typed handler registry; the worker keeps owning consume/reclaim/retry/DLQ/ack. Score runs gain Postgres persistence, and entity enumeration moves out of the HTTP request into the executor so a large KB does not fail before execution starts. One event per batch, so retry and DLQ granularity match the replayable unit.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, psycopg (via `database.ConnectionProvider`), Alembic, Redis Streams, pytest.

**Spec:** `docs/superpowers/specs/2026-08-06-execution-engines-design.md`

## Global Constraints

- Python 3.12. Full type annotations; **no `Any`**. `backend/.venv/bin/pyright` must report 0 errors (bare `pyright`, no path argument — `tool.pyright.include` scoping is the real gate).
- `backend/.venv/bin/ruff check --no-cache .` must pass. The ruff cache dir is not writable in sandboxed runs.
- Tests run from `backend/` (`make test` does `cd backend && .venv/bin/pytest`). **Never use a cwd-relative path in a test** — use `Path(__file__).resolve().parents[2]`. Five surge tests shipped unrunnable because of this.
- Never point `DATABASE_URL` at the dev `chili` database when running tests; `tests/conftest.py` defaults to `chili_test`.
- Coverage ≥ 85% per package.
- Cross-module imports only via `api/`, `agent/`, or `shared/`. `execution/` may import from the subsystem modules it dispatches to; subsystem modules must not import `execution/`.
- Executors **raise**; they must never catch their own exceptions and return normally. `run_handler_with_retry` owns retry vs dead-letter.
- Any change to a frontend-consumed Pydantic model requires `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json` then `cd chili_app && npm run codegen:api`.

## File Structure

| File | Responsibility |
|---|---|
| `backend/execution/__init__.py` | Public surface: `dispatch`, `ExecutionDeps`, `register_handler` |
| `backend/execution/deps.py` | `ExecutionDeps` frozen dataclass + `from_worker_dependencies()` |
| `backend/execution/registry.py` | `event_type → handler` map, `dispatch()` |
| `backend/analytics/score_runs/executor.py` | The score-batch handler |
| `backend/analytics/score_runs/adapters/postgres.py` | `PostgresScoreRunRepository` |
| `backend/database/migrations/versions/0024_score_runs.py` | `score_runs` + `score_batches` tables |
| `backend/events/types.py` | `ScoreBatchQueuedEvent` |

---

### Task 1: Add `get_batch` and an atomic claim to the repository protocol

The executor loads one batch by id and must claim it atomically, or two workers reclaiming the same event both execute it. Neither primitive exists today.

**Files:**
- Modify: `backend/analytics/score_runs/protocols.py:58`
- Modify: `backend/analytics/score_runs/adapters/in_memory.py`
- Test: `backend/tests/analytics/score_runs/test_in_memory.py`

**Interfaces:**
- Produces: `ScoreRunRepositoryProtocol.get_batch(batch_id: str) -> ScoreBatch | None` and `claim_batch(batch_id: str, *, now: datetime) -> ScoreBatch | None` (returns `None` when the batch is not in `queued` status — i.e. someone else claimed it).

- [ ] **Step 1: Write the failing test**

```python
def test_claim_batch_returns_none_when_already_claimed() -> None:
    repo = InMemoryScoreRunRepository()
    run = repo.save_run(_run())
    batch = repo.upsert_batch(_batch(run_id=run.id, batch_number=0))
    now = datetime(2026, 8, 6, tzinfo=timezone.utc)

    first = repo.claim_batch(batch.id, now=now)
    second = repo.claim_batch(batch.id, now=now)

    assert first is not None
    assert first.status == "running"
    assert first.attempts == 1
    assert second is None


def test_get_batch_returns_none_for_unknown_id() -> None:
    repo = InMemoryScoreRunRepository()
    assert repo.get_batch("missing") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/analytics/score_runs/test_in_memory.py -k "claim_batch or get_batch" -v`
Expected: FAIL — `AttributeError: 'InMemoryScoreRunRepository' object has no attribute 'claim_batch'`

- [ ] **Step 3: Add the protocol methods**

In `backend/analytics/score_runs/protocols.py`, after `upsert_batch`:

```python
    def get_batch(self, batch_id: str) -> ScoreBatch | None: ...

    def claim_batch(self, batch_id: str, *, now: datetime) -> ScoreBatch | None:
        """Transition a `queued` batch to `running` and increment attempts.

        Returns None when the batch is absent or not `queued` — the caller must
        treat that as "another worker owns this unit" and stop, not as an error.
        """
        ...
```

- [ ] **Step 4: Implement in the in-memory adapter**

```python
    def get_batch(self, batch_id: str) -> ScoreBatch | None:
        return self._batches.get(batch_id)

    def claim_batch(self, batch_id: str, *, now: datetime) -> ScoreBatch | None:
        batch = self._batches.get(batch_id)
        if batch is None or batch.status != "queued":
            return None
        claimed = batch.model_copy(
            update={
                "status": "running",
                "attempts": batch.attempts + 1,
                "started_at": batch.started_at or now,
                "updated_at": now,
            }
        )
        self._batches[batch_id] = claimed
        return claimed
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/analytics/score_runs/ -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/analytics/score_runs/protocols.py backend/analytics/score_runs/adapters/in_memory.py backend/tests/analytics/score_runs/test_in_memory.py
git commit -m "feat(score-runs): add get_batch and atomic claim_batch to the repository protocol"
```

---

### Task 2: Migration for `score_runs` and `score_batches`

**Files:**
- Create: `backend/database/migrations/versions/0024_score_runs.py`
- Test: `backend/tests/database/test_score_runs_migration.py`

**Interfaces:**
- Produces: revision id `"0024_score_runs"`, `down_revision = "0023_eval_dataset_refs"`.

- [ ] **Step 1: Write the failing test**

```python
"""Migration shape tests for score-run persistence."""

from __future__ import annotations

from pathlib import Path


def test_score_runs_migration_declares_tables() -> None:
    migration = (
        Path(__file__).resolve().parents[2]
        / "database/migrations/versions/0024_score_runs.py"
    ).read_text(encoding="utf-8")

    assert 'revision: str = "0024_score_runs"' in migration
    assert 'down_revision: str | None = "0023_eval_dataset_refs"' in migration
    assert "CREATE TABLE IF NOT EXISTS score_runs" in migration
    assert "CREATE TABLE IF NOT EXISTS score_batches" in migration
    assert "run_id text NOT NULL REFERENCES score_runs(id) ON DELETE CASCADE" in migration
    assert "ix_score_runs_kb_status" in migration
    assert "ix_score_batches_run_status" in migration
```

Note the `Path(__file__).resolve().parents[2]` — a cwd-relative path here will not resolve under `make test`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/database/test_score_runs_migration.py -v`
Expected: FAIL — `FileNotFoundError`

- [ ] **Step 3: Write the migration**

```python
"""Add durable score-all run tracking.

Revision ID: 0024_score_runs
Revises: 0023_eval_dataset_refs
Create Date: 2026-08-06
"""

from __future__ import annotations

from alembic import op

revision: str = "0024_score_runs"
down_revision: str | None = "0023_eval_dataset_refs"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS score_runs (
            id text PRIMARY KEY,
            knowledge_base_id text NOT NULL,
            status text NOT NULL,
            requested_by text,
            idempotency_key text,
            model_version text NOT NULL,
            catalog_version text NOT NULL,
            replay_of_run_id text,
            entity_cursor text,
            total_entities integer NOT NULL DEFAULT 0,
            scored_entities integer NOT NULL DEFAULT 0,
            failed_entities integer NOT NULL DEFAULT 0,
            error_summary text,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            started_at timestamptz,
            finished_at timestamptz
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_score_runs_kb_idempotency
        ON score_runs (knowledge_base_id, idempotency_key)
        WHERE idempotency_key IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_score_runs_kb_status
        ON score_runs (knowledge_base_id, status, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS score_batches (
            id text PRIMARY KEY,
            run_id text NOT NULL REFERENCES score_runs(id) ON DELETE CASCADE,
            knowledge_base_id text NOT NULL,
            batch_number integer NOT NULL,
            status text NOT NULL,
            entity_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
            attempts integer NOT NULL DEFAULT 0,
            error_summary text,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            started_at timestamptz,
            finished_at timestamptz,
            UNIQUE (run_id, batch_number)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_score_batches_run_status
        ON score_batches (run_id, status, batch_number)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_score_batches_run_status")
    op.execute("DROP TABLE IF EXISTS score_batches")
    op.execute("DROP INDEX IF EXISTS ix_score_runs_kb_status")
    op.execute("DROP INDEX IF EXISTS ux_score_runs_kb_idempotency")
    op.execute("DROP TABLE IF EXISTS score_runs")
```

`entity_cursor` supports Task 7 (enumeration in the executor). The partial unique index enforces idempotency at the database rather than trusting a read-then-write race.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/database/test_score_runs_migration.py -v`
Expected: PASS

- [ ] **Step 5: Regenerate the schema snapshot**

Run: `cd backend && .venv/bin/alembic upgrade head && .venv/bin/python -m database.migrations.snapshot`
If no snapshot module exists, follow `backend/database/README.md` § snapshot regeneration. The CI "Migrations (replay + snapshot drift)" job fails without it — BL-042 shipped red for exactly this reason.

- [ ] **Step 6: Commit**

```bash
git add backend/database/migrations/versions/0024_score_runs.py backend/tests/database/test_score_runs_migration.py backend/database/migrations/snapshots/head.sql
git commit -m "feat(database): add score_runs and score_batches tables (migration 0024)"
```

---

### Task 3: `PostgresScoreRunRepository`

**Files:**
- Create: `backend/analytics/score_runs/adapters/postgres.py`
- Test: `backend/tests/analytics/score_runs/test_postgres.py`

**Interfaces:**
- Consumes: `ScoreRunRepositoryProtocol` incl. `get_batch`/`claim_batch` from Task 1; `database.protocols.ConnectionProvider`.
- Produces: `PostgresScoreRunRepository(connection_provider: ConnectionProvider)`.

- [ ] **Step 1: Write the failing test**

```python
import pytest

pytestmark = pytest.mark.integration


def test_claim_batch_is_atomic_across_two_reads(postgres_provider) -> None:
    repo = PostgresScoreRunRepository(postgres_provider)
    run = repo.save_run(_run())
    batch = repo.upsert_batch(_batch(run_id=run.id, batch_number=0))
    now = datetime(2026, 8, 6, tzinfo=timezone.utc)

    first = repo.claim_batch(batch.id, now=now)
    second = repo.claim_batch(batch.id, now=now)

    assert first is not None and first.status == "running"
    assert second is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/analytics/score_runs/test_postgres.py -v -m integration`
Expected: FAIL — module not found

- [ ] **Step 3: Implement the adapter**

Mirror `backend/governance/adapters/postgres.py` for structure. The claim must be a single conditional UPDATE, not read-then-write:

```python
    def claim_batch(self, batch_id: str, *, now: datetime) -> ScoreBatch | None:
        with self._provider.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    UPDATE score_batches
                       SET status = 'running',
                           attempts = attempts + 1,
                           started_at = COALESCE(started_at, %s),
                           updated_at = %s
                     WHERE id = %s AND status = 'queued'
                    RETURNING {_BATCH_COLUMNS}
                    """,
                    (now, now, batch_id),
                )
                row = cursor.fetchone()
        return None if row is None else _batch_from_row(row)
```

`WHERE status = 'queued'` is what makes it atomic: a second caller matches zero rows and gets `None`.

When decoding `entity_ids` from jsonb, pin the decoded value as `object` and `cast(list[object], …)` after the `isinstance` guard — `json.loads` returns `Any`, and iterating a narrowed `list[Unknown]` is a pyright strict error. This exact pattern broke CI for nine sprints.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/analytics/score_runs/ -v` then `-m integration` with the stack up.
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/analytics/score_runs/adapters/postgres.py backend/tests/analytics/score_runs/test_postgres.py
git commit -m "feat(score-runs): add PostgresScoreRunRepository with an atomic batch claim"
```

---

### Task 4: Wire the Postgres adapter into DI

**Files:**
- Modify: `backend/api/dependencies.py:2708`
- Test: `backend/tests/api/test_dependencies_backends.py`

**Interfaces:**
- Consumes: `PostgresScoreRunRepository` from Task 3.

- [ ] **Step 1: Write the failing test**

```python
def test_score_run_repository_uses_postgres_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    request = _request_with_config(database_backend="postgres")
    repository = get_score_run_repository(request)
    assert isinstance(repository, PostgresScoreRunRepository)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/api/test_dependencies_backends.py -k score_run -v`
Expected: FAIL — returns `InMemoryScoreRunRepository`

- [ ] **Step 3: Add the Postgres branch**

Follow the shape of `get_playbook_repository` (`backend/api/dependencies.py:2713`), which already selects on the database backend:

```python
def get_score_run_repository(request: Request) -> ScoreRunRepositoryProtocol:
    """Return the score-run repository selected by database backend."""

    def _build() -> ScoreRunRepositoryProtocol:
        provider = _connection_provider_or_none(request)
        if provider is None:
            return InMemoryScoreRunRepository()
        return PostgresScoreRunRepository(provider)

    return _memoize_config_derived(
        request.app,
        "score_run_repository",
        _build,
        guard=lambda value: isinstance(value, ScoreRunRepositoryProtocol),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/api/test_dependencies_backends.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/api/dependencies.py backend/tests/api/test_dependencies_backends.py
git commit -m "feat(score-runs): select the Postgres repository when a connection provider exists"
```

---

### Task 5: `ScoreBatchQueuedEvent`

**Files:**
- Modify: `backend/events/types.py`
- Modify: `backend/events/codec.py`
- Modify: `docs/ledger/event-catalog.md`
- Test: `backend/tests/events/test_codec.py`

**Interfaces:**
- Produces: `ScoreBatchQueuedEvent(event_type="score.batch.queued", knowledge_base_id, run_id, batch_id, batch_number)`.

- [ ] **Step 1: Write the failing test**

```python
def test_event_codec_round_trips_score_batch_queued_event() -> None:
    event = ScoreBatchQueuedEvent(
        correlation_id="corr-1",
        knowledge_base_id="kb-1",
        run_id="run-1",
        batch_id="batch-1",
        batch_number=0,
    )
    decoded = decode_event(encode_event(event))
    assert decoded.event_type == "score.batch.queued"
    assert isinstance(decoded, ScoreBatchQueuedEvent)
    assert decoded.batch_id == "batch-1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/events/test_codec.py -k score_batch -v`
Expected: FAIL — import error

- [ ] **Step 3: Add the event type**

```python
class ScoreBatchQueuedEvent(EventBase):
    """One score-all batch is ready to execute.

    Carries identifiers only. The executor reloads batch state from the
    repository, so a redelivered event can never resurrect a stale snapshot.
    """

    event_type: Literal["score.batch.queued"] = "score.batch.queued"
    knowledge_base_id: str
    run_id: str
    batch_id: str
    batch_number: int
```

Add to the `AnyEvent` union, to `__all__`, and to the codec map as `"score.batch.queued": ScoreBatchQueuedEvent`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/events/ -v`
Expected: PASS

- [ ] **Step 5: Update the event catalog**

Add a row to `docs/ledger/event-catalog.md` and bump the stated member count from 32 to 33.

- [ ] **Step 6: Commit**

```bash
git add backend/events/types.py backend/events/codec.py backend/tests/events/test_codec.py docs/ledger/event-catalog.md
git commit -m "feat(events): add score.batch.queued"
```

---

### Task 6: The `execution/` module and worker delegation

**Files:**
- Create: `backend/execution/__init__.py`, `backend/execution/deps.py`, `backend/execution/registry.py`
- Modify: `backend/agent/coordinator.py` (`WORKER_EVENT_TYPES`, and the `_run_handler` closure inside `drain_ingestion_events`)
- Test: `backend/tests/execution/test_registry.py`

**Interfaces:**
- Produces: `ExecutionDeps` (frozen dataclass), `from_worker_dependencies(deps: WorkerDependencies) -> ExecutionDeps`, `register_handler(event_type: str, handler: ExecutionHandler)`, `dispatch(event: AnyEvent, deps: ExecutionDeps) -> int` returning the number of units processed (0 when no handler is registered).
- `ExecutionHandler` is `Callable[[AnyEvent, ExecutionDeps], int]`.

- [ ] **Step 1: Write the failing test**

```python
def test_dispatch_returns_zero_when_no_handler_registered() -> None:
    deps = _execution_deps()
    event = KnowledgeBaseReadyEvent(correlation_id="c1", knowledge_base_id="kb-1")
    assert dispatch(event, deps) == 0


def test_dispatch_routes_to_the_registered_handler() -> None:
    seen: list[str] = []

    def _handler(event: AnyEvent, deps: ExecutionDeps) -> int:
        seen.append(event.event_type)
        return 1

    register_handler("score.batch.queued", _handler)
    event = ScoreBatchQueuedEvent(
        correlation_id="c1", knowledge_base_id="kb-1",
        run_id="r1", batch_id="b1", batch_number=0,
    )
    assert dispatch(event, _execution_deps()) == 1
    assert seen == ["score.batch.queued"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/execution/test_registry.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement `deps.py`**

```python
@dataclass(frozen=True, slots=True)
class ExecutionDeps:
    """Dependencies executors need, derived from the worker's container.

    Deliberately narrow: an executor that needs a dependency not listed here
    should have it added explicitly rather than being handed the full
    45-field WorkerDependencies.
    """

    event_bus: EventBus
    risk_service: RiskService | None
    score_run_repository: ScoreRunRepositoryProtocol | None
    graph_repository: GraphRepository | None
    domain_config: DomainConfig | None
```

Plus `from_worker_dependencies(deps: WorkerDependencies) -> ExecutionDeps` copying those fields.

- [ ] **Step 4: Implement `registry.py`**

```python
ExecutionHandler = Callable[[AnyEvent, ExecutionDeps], int]

_HANDLERS: dict[str, ExecutionHandler] = {}


def register_handler(event_type: str, handler: ExecutionHandler) -> None:
    _HANDLERS[event_type] = handler


def dispatch(event: AnyEvent, deps: ExecutionDeps) -> int:
    """Route one executor event. Returns 0 when nothing is registered.

    Exceptions propagate: run_handler_with_retry owns retry and DLQ, and an
    executor that swallows its own errors makes failures invisible.
    """

    handler = _HANDLERS.get(event.event_type)
    if handler is None:
        return 0
    return handler(event, deps)
```

- [ ] **Step 5: Delegate from the worker**

Add `"score.batch.queued"` to `WORKER_EVENT_TYPES` (`backend/agent/coordinator.py:393`). In the `_run_handler` closure inside `drain_ingestion_events`, after the existing `handle_event(...)` call:

```python
        def _run_handler(captured: EventDelivery = delivery) -> int:
            processed = handle_event(captured, ingestion_service, ...)
            processed += execution_dispatch(
                captured.event, from_worker_dependencies(deps)
            )
            return processed
```

`drain_ingestion_events` currently receives loose arguments rather than the `WorkerDependencies` object. Build the `ExecutionDeps` in `_drain_once` (which does have `deps`) and pass it into `drain_ingestion_events` as a single new parameter — do not re-thread five more loose kwargs.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/execution/ tests/agent/ -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/execution/ backend/agent/coordinator.py backend/tests/execution/
git commit -m "feat(execution): add the executor dispatch seam and delegate from the worker"
```

---

### Task 7: The score-batch executor

**Files:**
- Create: `backend/analytics/score_runs/executor.py`
- Test: `backend/tests/analytics/score_runs/test_executor.py`

**Interfaces:**
- Consumes: `claim_batch`/`get_batch` (Task 1), `ScoreBatchQueuedEvent` (Task 5), `ExecutionDeps` (Task 6), `assess_entities` (`backend/agent/coordinator.py:3026`), `ScoreRunService.score_request_id`.
- Produces: `handle_score_batch_queued(event: AnyEvent, deps: ExecutionDeps) -> int`, registered for `"score.batch.queued"`.

- [ ] **Step 1: Write the failing tests**

```python
def test_executor_scores_the_batch_and_advances_counters() -> None:
    repo, deps = _deps_with_batch(entity_ids=["e1", "e2"])
    event = _event(batch_number=0)

    processed = handle_score_batch_queued(event, deps)

    run = repo.get_run(event.run_id)
    assert processed == 1
    assert run is not None and run.scored_entities == 2


def test_executor_is_idempotent_under_duplicate_delivery() -> None:
    repo, deps = _deps_with_batch(entity_ids=["e1", "e2"])
    event = _event(batch_number=0)

    handle_score_batch_queued(event, deps)
    handle_score_batch_queued(event, deps)   # redelivered

    run = repo.get_run(event.run_id)
    assert run is not None and run.scored_entities == 2   # NOT 4


def test_executor_stops_when_the_run_is_cancelled() -> None:
    repo, deps = _deps_with_batch(entity_ids=["e1"])
    repo.update_run(_RUN_ID, status="canceled")
    event = _event(batch_number=0)

    processed = handle_score_batch_queued(event, deps)

    assert processed == 0
    batch = repo.get_batch(event.batch_id)
    assert batch is not None and batch.status == "queued"


def test_executor_enqueues_the_next_queued_batch() -> None:
    repo, deps = _deps_with_batches(count=2)
    handle_score_batch_queued(_event(batch_number=0), deps)

    published = [e for e in deps.event_bus.published_events
                 if e.event_type == "score.batch.queued"]
    assert [e.batch_number for e in published] == [1]


def test_executor_completes_the_run_when_no_batches_remain() -> None:
    repo, deps = _deps_with_batches(count=1)
    handle_score_batch_queued(_event(batch_number=0), deps)

    run = repo.get_run(_RUN_ID)
    assert run is not None and run.status == "completed"
    assert run.finished_at is not None


def test_executor_fails_the_run_when_the_catalog_version_changed_mid_run() -> None:
    """Spec 6.5 — a pack hot-swap between drains must not silently change meaning.

    Dependencies rebuild between drain iterations, so a run started under pack A
    can be resumed under pack B. Scoring the remaining batches against a
    different feature catalogue would make the run's own recorded
    catalog_version a lie.
    """
    repo, deps = _deps_with_batch(entity_ids=["e1"], catalog_version="cms-v1")
    deps = _with_active_catalog_version(deps, "cms-v2")

    processed = handle_score_batch_queued(_event(batch_number=0), deps)

    run = repo.get_run(_RUN_ID)
    assert processed == 0
    assert run is not None and run.status == "failed"
    assert run.error_summary == "catalog_version_changed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/analytics/score_runs/test_executor.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement the executor**

```python
def handle_score_batch_queued(event: AnyEvent, deps: ExecutionDeps) -> int:
    if not isinstance(event, ScoreBatchQueuedEvent):
        return 0
    repository = deps.score_run_repository
    risk_service = deps.risk_service
    if repository is None or risk_service is None:
        return 0

    run = repository.get_run(event.run_id)
    if run is None or run.status in {"canceled", "completed", "failed"}:
        return 0                                    # cancelled or already done

    # Spec 6.5: a pack hot-swap between drain iterations can resume this run
    # under a different feature catalogue. Fail loudly rather than scoring the
    # tail of a run against a catalogue it did not start with.
    active_catalog = _active_catalog_version(deps)
    if active_catalog is not None and active_catalog != run.catalog_version:
        repository.update_run(
            run.id,
            status="failed",
            error_summary="catalog_version_changed",
            finished_at=utc_now(),
            updated_at=utc_now(),
        )
        return 0

    now = utc_now()
    batch = repository.claim_batch(event.batch_id, now=now)
    if batch is None:
        return 0                                    # another worker owns it

    assessments = assess_entities(
        risk_service=risk_service,
        knowledge_base_id=batch.knowledge_base_id,
        entity_ids=list(batch.entity_ids),
        correlation_id=_batch_correlation_id(run.id, batch.batch_number),
    )
    scored = len(assessments)
    failed = len(batch.entity_ids) - scored

    repository.upsert_batch(
        batch.model_copy(update={
            "status": "completed",
            "finished_at": utc_now(),
            "updated_at": utc_now(),
        })
    )
    _reconcile_run_counters(repository, run_id=run.id)
    _enqueue_next_batch_or_complete(repository, deps, run_id=run.id)
    return 1
```

**Counters are derived, never incremented** (spec §6.1). `_reconcile_run_counters` sums completed/failed batch state and writes the totals, so a replayed batch cannot double-count:

```python
def _reconcile_run_counters(
    repository: ScoreRunRepositoryProtocol, *, run_id: str
) -> None:
    batches = repository.list_batches(run_id=run_id)
    scored = sum(len(b.entity_ids) for b in batches if b.status == "completed")
    failed = sum(len(b.entity_ids) for b in batches if b.status == "failed")
    repository.update_run(
        run_id,
        scored_entities=scored,
        failed_entities=failed,
        updated_at=utc_now(),
    )
```

- [ ] **Step 4: Register the handler**

In `backend/analytics/score_runs/executor.py` module scope:

```python
register_handler("score.batch.queued", handle_score_batch_queued)
```

Import the module from `backend/execution/__init__.py` so registration happens on import.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/analytics/score_runs/ -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/analytics/score_runs/executor.py backend/tests/analytics/score_runs/test_executor.py backend/execution/__init__.py
git commit -m "feat(score-runs): execute score batches with derived, replay-safe counters"
```

---

### Task 8: Move enumeration into the executor and reject concurrent runs

Closes risk R2 (the route enumerating every entity synchronously) and spec decisions D2 and D3.

**Files:**
- Modify: `backend/api/routers/score_runs.py:96-99`
- Modify: `backend/analytics/score_runs/service.py:41`
- Test: `backend/tests/api/test_score_runs_router.py`

**Interfaces:**
- Produces: `ScoreRunService.start_score_all(..., entity_ids: Sequence[str] | None = None)` — `None` means "enumerate in the executor". Raises `ScoreRunConflictError` when a `queued`/`running` run exists for the KB.

- [ ] **Step 1: Write the failing tests**

```python
def test_start_score_run_does_not_enumerate_entities_in_the_request() -> None:
    graph_repository = _tracking_graph_repository()
    _start_run(graph_repository=graph_repository)
    assert graph_repository.get_entities_call_count == 0


def test_second_concurrent_run_for_the_same_kb_returns_409() -> None:
    _start_run()
    response = _start_run_response()
    assert response.status_code == 409
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/api/test_score_runs_router.py -k "enumerate or concurrent" -v`
Expected: FAIL — `get_entities_call_count == 1`, and the second start returns 200

- [ ] **Step 3: Remove enumeration from the route**

Replace `backend/api/routers/score_runs.py:96-99` with a pass-through of `payload.entity_ids` (which may be `None`). Delete the `graph_repository` dependency from the route if nothing else uses it.

- [ ] **Step 4: Add the conflict guard and cursor-driven start**

In `start_score_all`, before creating the run:

```python
        active = self.repository.list_runs(
            knowledge_base_id=knowledge_base_id, status="running", limit=1
        )
        queued = self.repository.list_runs(
            knowledge_base_id=knowledge_base_id, status="queued", limit=1
        )
        if active.items or queued.items:
            raise ScoreRunConflictError(
                f"A score run is already active for knowledge base "
                f"'{knowledge_base_id}'."
            )
```

When `entity_ids is None`, create the run with `total_entities=0` and no batches; the executor pages entities via `graph_repository` and creates batches as it goes, incrementing `total_entities` per batch. Per D2, `total_entities` is authoritative only at completion.

Map `ScoreRunConflictError` to HTTP 409 in the router.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/api/test_score_runs_router.py tests/analytics/score_runs/ -v`
Expected: PASS

- [ ] **Step 6: Regenerate contracts**

```bash
PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json
cd chili_app && npm run codegen:api
```

- [ ] **Step 7: Commit**

```bash
git add backend/api/routers/score_runs.py backend/analytics/score_runs/service.py backend/tests/api/test_score_runs_router.py chili_app/openapi.json chili_app/src/lib/api/schema.ts
git commit -m "feat(score-runs): enumerate entities in the executor and reject concurrent runs"
```

---

### Task 9: Stale-run reconciliation

A dropped chain link leaves a run `running` forever. This is the mitigation named in spec §3.3.

**Files:**
- Modify: `backend/agent/workflow_tracking.py:198`
- Test: `backend/tests/agent/test_workflow_tracking.py`

- [ ] **Step 1: Write the failing test**

```python
def test_reconcile_fails_a_score_run_with_no_in_flight_batch() -> None:
    repo = InMemoryScoreRunRepository()
    run = repo.save_run(_run(status="running", updated_at=_hours_ago(3)))
    reconciler = ScoreRunReconciler(repo)

    assert reconciler.reconcile_stale_runs(max_age_seconds=3600) == 1
    reloaded = repo.get_run(run.id)
    assert reloaded is not None and reloaded.status == "failed"
    assert reloaded.error_summary == "stale_score_run_reconciled"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/agent/test_workflow_tracking.py -k stale_score -v`
Expected: FAIL — `ScoreRunReconciler` not defined

- [ ] **Step 3: Implement the reconciler**

Add `ScoreRunReconciler` alongside the existing workflow reconciler, following its shape: page `queued`/`running` runs older than the cutoff, mark them `failed` with `error_summary="stale_score_run_reconciled"`. Call it from the same `run_worker` reconcile tick that already calls `reconcile_stale_runs`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/agent/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/agent/workflow_tracking.py backend/agent/coordinator.py backend/tests/agent/test_workflow_tracking.py
git commit -m "feat(score-runs): reconcile stale score runs so a dropped chain link cannot hang a run"
```

---

### Task 10: Live-stack verification and docs

**Files:**
- Modify: `docs/ledger/module-map.md` (the `analytics/score_runs/` entry currently says "state machine only. Nothing executes batches")
- Modify: `docs/backlog/analytics.md` / `docs/project/planning/backlog.md` (SAFE-CMS-002 row)
- Test: `backend/tests/e2e/test_score_all_flow.py`

- [ ] **Step 1: Write the integration test**

```python
pytestmark = pytest.mark.integration


def test_score_all_run_reaches_completed_against_the_live_stack() -> None:
    """Start a run on a seeded KB and poll until terminal."""
    run_id = _start_score_all(kb_id=_seeded_kb())
    run = _poll_until_terminal(run_id, timeout_seconds=120)

    assert run["status"] == "completed"
    assert run["scored_entities"] + run["failed_entities"] == run["total_entities"]
    assert run["total_entities"] > 0
```

- [ ] **Step 2: Run it with the stack up**

```bash
make dev                      # from the repo root, in the controller session
cd backend && .venv/bin/pytest tests/e2e/test_score_all_flow.py -v -m integration
```

Expected: PASS. Docker commands must run in the main session, not a subagent.

- [ ] **Step 3: Kill the worker mid-run and assert resume**

```bash
docker restart chiliai-worker-1
```

Re-poll the run; it must still reach `completed`. This exercises `reclaim_stale_pending` (XPENDING/XCLAIM). Record the observed behaviour in the story closeout.

- [ ] **Step 4: Update the docs that currently say this does not work**

`docs/ledger/module-map.md` — replace the `analytics/score_runs/` "Status: state machine only. Nothing executes batches" note with the shipped behaviour, including that runs are now Postgres-backed.

- [ ] **Step 5: Run the full gates**

```bash
cd backend && .venv/bin/pytest --cov -q && .venv/bin/pyright && .venv/bin/ruff check --no-cache .
cd ../ && ./backend/.venv/bin/python scripts/backlog_consistency.py --check
```

- [ ] **Step 6: Commit**

```bash
git add backend/tests/e2e/test_score_all_flow.py docs/ledger/module-map.md docs/backlog/analytics.md docs/project/planning/backlog.md
git commit -m "test(score-runs): live-stack score-all verification; close SAFE-CMS-002 executor gap"
```
