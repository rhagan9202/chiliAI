# Connector Sync Executor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `POST /knowledgebases/{kb}/connectors/{id}/sync-runs` actually pull data — reading a filesystem source page by page and publishing the same durable ingestion events a manual upload publishes.

**Architecture:** Reuses the `execution/` dispatch seam built for score-all. Adds Postgres persistence for connectors and sync runs, a `ConnectorSourceAdapter` protocol with one filesystem implementation, and a page-at-a-time executor. `source_cursor` advances only after the ingest event is durably published, so a crash cannot skip records.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, psycopg, Alembic, Redis Streams, pytest.

**Spec:** `docs/superpowers/specs/2026-08-06-execution-engines-design.md` §4.2

**Depends on:** `2026-08-06-score-all-executor.md` Tasks 1–6 (the `execution/` module must exist).

## Global Constraints

- Python 3.12. Full type annotations; **no `Any`**. Bare `backend/.venv/bin/pyright` must report 0 errors.
- `backend/.venv/bin/ruff check --no-cache .` must pass.
- Tests run from `backend/`. **Never use a cwd-relative path in a test** — use `Path(__file__).resolve().parents[2]`.
- Never point `DATABASE_URL` at the dev `chili` database; `tests/conftest.py` defaults to `chili_test`.
- Coverage ≥ 85% per package.
- Executors **raise**; `run_handler_with_retry` owns retry vs dead-letter.
- Credentials are referenced, never stored or returned. `ConnectorDefinition.credentials_ref` names an env var; the value must never appear in a response, log, or audit record.
- Any frontend-consumed Pydantic change requires OpenAPI export + `npm run codegen:api`.

## File Structure

| File | Responsibility |
|---|---|
| `backend/connectors/adapters/postgres.py` | `PostgresConnectorRepository` |
| `backend/connectors/sources/protocols.py` | `ConnectorSourceAdapter` protocol + `SourcePage` |
| `backend/connectors/sources/filesystem.py` | `FilesystemSourceAdapter` |
| `backend/connectors/executor.py` | The page handler |
| `backend/database/migrations/versions/0025_connectors.py` | `connectors` + `connector_sync_runs` tables |
| `backend/events/types.py` | `ConnectorPageQueuedEvent` |

---

### Task 1: Migration for `connectors` and `connector_sync_runs`

**Files:**
- Create: `backend/database/migrations/versions/0025_connectors.py`
- Test: `backend/tests/database/test_connectors_migration.py`

**Interfaces:**
- Produces: revision `"0025_connectors"`, `down_revision = "0024_score_runs"`.

- [ ] **Step 1: Write the failing test**

```python
"""Migration shape tests for connector persistence."""

from __future__ import annotations

from pathlib import Path


def test_connectors_migration_declares_tables() -> None:
    migration = (
        Path(__file__).resolve().parents[2]
        / "database/migrations/versions/0025_connectors.py"
    ).read_text(encoding="utf-8")

    assert 'revision: str = "0025_connectors"' in migration
    assert 'down_revision: str | None = "0024_score_runs"' in migration
    assert "CREATE TABLE IF NOT EXISTS connectors" in migration
    assert "CREATE TABLE IF NOT EXISTS connector_sync_runs" in migration
    assert "source_cursor text" in migration
    assert "ix_connector_sync_runs_connector_status" in migration
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/database/test_connectors_migration.py -v`
Expected: FAIL — `FileNotFoundError`

- [ ] **Step 3: Write the migration**

```python
"""Add connector definitions and sync runs.

Revision ID: 0025_connectors
Revises: 0024_score_runs
Create Date: 2026-08-06
"""

from __future__ import annotations

from alembic import op

revision: str = "0025_connectors"
down_revision: str | None = "0024_score_runs"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS connectors (
            connector_id text PRIMARY KEY,
            knowledge_base_id text NOT NULL,
            name text NOT NULL,
            source_type text NOT NULL,
            status text NOT NULL,
            schedule_mode text NOT NULL,
            credentials_ref text,
            config jsonb NOT NULL DEFAULT '{}'::jsonb,
            mapping jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_by text NOT NULL,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            CONSTRAINT ck_connectors_source_type CHECK (
                source_type IN ('filesystem', 'object_store', 'http')
            )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_connectors_kb
        ON connectors (knowledge_base_id, status, updated_at DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS connector_sync_runs (
            run_id text PRIMARY KEY,
            connector_id text NOT NULL
                REFERENCES connectors(connector_id) ON DELETE CASCADE,
            knowledge_base_id text NOT NULL,
            requested_by text NOT NULL,
            status text NOT NULL,
            counters jsonb NOT NULL DEFAULT '{}'::jsonb,
            idempotency_key text,
            ingest_correlation_id text,
            source_cursor text,
            error_message text,
            started_at timestamptz NOT NULL,
            completed_at timestamptz,
            updated_at timestamptz NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_connector_sync_runs_idempotency
        ON connector_sync_runs (connector_id, idempotency_key)
        WHERE idempotency_key IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_connector_sync_runs_connector_status
        ON connector_sync_runs (connector_id, status, started_at DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_connector_sync_runs_connector_status")
    op.execute("DROP INDEX IF EXISTS ux_connector_sync_runs_idempotency")
    op.execute("DROP TABLE IF EXISTS connector_sync_runs")
    op.execute("DROP INDEX IF EXISTS ix_connectors_kb")
    op.execute("DROP TABLE IF EXISTS connectors")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/database/test_connectors_migration.py -v`
Expected: PASS

- [ ] **Step 5: Regenerate the schema snapshot**

Run: `cd backend && .venv/bin/alembic upgrade head` then regenerate `database/migrations/snapshots/head.sql` per `backend/database/README.md`. CI's migrations job fails on snapshot drift.

- [ ] **Step 6: Commit**

```bash
git add backend/database/migrations/versions/0025_connectors.py backend/tests/database/test_connectors_migration.py backend/database/migrations/snapshots/head.sql
git commit -m "feat(database): add connectors and connector_sync_runs tables (migration 0025)"
```

---

### Task 2: `PostgresConnectorRepository` and DI wiring

**Files:**
- Create: `backend/connectors/adapters/postgres.py`
- Modify: `backend/api/dependencies.py:2745`
- Test: `backend/tests/connectors/test_postgres.py`

**Interfaces:**
- Consumes: `ConnectorRepositoryProtocol`, `database.protocols.ConnectionProvider`.
- Produces: `PostgresConnectorRepository(connection_provider: ConnectionProvider)`, plus `claim_sync_run(run_id: str, *, now: datetime) -> ConnectorSyncRun | None` (atomic `queued → running`).

- [ ] **Step 1: Write the failing test**

```python
import pytest

pytestmark = pytest.mark.integration


def test_claim_sync_run_is_atomic(postgres_provider) -> None:
    repo = PostgresConnectorRepository(postgres_provider)
    connector = repo.save_connector(_connector())
    run = repo.create_run(_run_create(connector_id=connector.connector_id))
    now = datetime(2026, 8, 6, tzinfo=timezone.utc)

    assert repo.claim_sync_run(run.run_id, now=now) is not None
    assert repo.claim_sync_run(run.run_id, now=now) is None


def test_connector_response_never_exposes_credentials(postgres_provider) -> None:
    repo = PostgresConnectorRepository(postgres_provider)
    stored = repo.save_connector(_connector(credentials_ref="CHILI_SFTP_PASSWORD"))
    assert "CHILI_SFTP_PASSWORD" not in stored.credentials_display
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/connectors/test_postgres.py -v -m integration`
Expected: FAIL — module not found

- [ ] **Step 3: Implement the adapter**

Mirror `backend/governance/adapters/postgres.py`. The claim is a conditional UPDATE:

```python
                cursor.execute(
                    f"""
                    UPDATE connector_sync_runs
                       SET status = 'running', updated_at = %s
                     WHERE run_id = %s AND status = 'queued'
                    RETURNING {_RUN_COLUMNS}
                    """,
                    (now, run_id),
                )
```

When decoding `counters`/`config`/`mapping` from jsonb, pin the decoded value as `object` and `cast(dict[str, object], …)` after the `isinstance` guard — `json.loads` returns `Any` and iterating a narrowed unknown is a pyright strict error.

- [ ] **Step 4: Wire DI**

Replace the unconditional `InMemoryConnectorRepository()` at `backend/api/dependencies.py:2745` with the same connection-provider branch used by `get_playbook_repository`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/connectors/ tests/api/test_connectors_router.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/connectors/adapters/postgres.py backend/api/dependencies.py backend/tests/connectors/test_postgres.py
git commit -m "feat(connectors): add PostgresConnectorRepository and select it via DI"
```

---

### Task 3: `ConnectorSourceAdapter` protocol and the filesystem source

**Files:**
- Create: `backend/connectors/sources/protocols.py`, `backend/connectors/sources/filesystem.py`
- Test: `backend/tests/connectors/test_filesystem_source.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass(frozen=True)
  class SourcePage:
      rows: list[dict[str, object]]
      next_cursor: str | None      # None means "no more pages"

  class ConnectorSourceAdapter(Protocol):
      def read_page(
          self, *, config: Mapping[str, object], cursor: str | None, limit: int
      ) -> SourcePage: ...
  ```

- [ ] **Step 1: Write the failing tests**

```python
def test_filesystem_source_pages_a_csv_directory(tmp_path: Path) -> None:
    (tmp_path / "a.csv").write_text("id,amount\n1,10\n2,20\n", encoding="utf-8")
    adapter = FilesystemSourceAdapter()

    page = adapter.read_page(config={"path": str(tmp_path)}, cursor=None, limit=1)

    assert page.rows == [{"id": "1", "amount": "10"}]
    assert page.next_cursor is not None


def test_filesystem_source_returns_none_cursor_at_the_end(tmp_path: Path) -> None:
    (tmp_path / "a.csv").write_text("id\n1\n", encoding="utf-8")
    adapter = FilesystemSourceAdapter()

    page = adapter.read_page(config={"path": str(tmp_path)}, cursor=None, limit=10)

    assert len(page.rows) == 1
    assert page.next_cursor is None


def test_filesystem_source_rejects_a_path_outside_the_configured_root(tmp_path: Path) -> None:
    adapter = FilesystemSourceAdapter(allowed_root=tmp_path)
    with pytest.raises(ConnectorSourceError, match="outside the allowed root"):
        adapter.read_page(config={"path": "/etc"}, cursor=None, limit=1)
```

The third test is not optional. A connector path is operator-supplied; without a root guard this reads arbitrary host files.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/connectors/test_filesystem_source.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement the adapter**

Cursor format: `"<filename>:<row_offset>"` — stable, human-readable, and resumable across files in sorted order. Resolve the configured path with `Path.resolve()` and verify `allowed_root` is one of its parents before opening anything.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/connectors/test_filesystem_source.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/connectors/sources/ backend/tests/connectors/test_filesystem_source.py
git commit -m "feat(connectors): add the source adapter protocol and a path-guarded filesystem source"
```

---

### Task 4: `ConnectorPageQueuedEvent`

**Files:**
- Modify: `backend/events/types.py`, `backend/events/codec.py`, `docs/ledger/event-catalog.md`
- Test: `backend/tests/events/test_codec.py`

**Interfaces:**
- Produces: `ConnectorPageQueuedEvent(event_type="connector.page.queued", knowledge_base_id, connector_id, run_id, cursor: str | None)`.

- [ ] **Step 1: Write the failing test**

```python
def test_event_codec_round_trips_connector_page_queued_event() -> None:
    event = ConnectorPageQueuedEvent(
        correlation_id="corr-1",
        knowledge_base_id="kb-1",
        connector_id="conn-1",
        run_id="run-1",
        cursor=None,
    )
    decoded = decode_event(encode_event(event))
    assert decoded.event_type == "connector.page.queued"
    assert isinstance(decoded, ConnectorPageQueuedEvent)
    assert decoded.cursor is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/events/test_codec.py -k connector_page -v`
Expected: FAIL — import error

- [ ] **Step 3: Add the event type**

Add the class, the `AnyEvent` member, `__all__`, the codec map entry, and `"connector.page.queued"` to `WORKER_EVENT_TYPES`. Bump the event-catalog member count from 33 to 34.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/events/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/events/ backend/agent/coordinator.py backend/tests/events/test_codec.py docs/ledger/event-catalog.md
git commit -m "feat(events): add connector.page.queued"
```

---

### Task 5: The connector page executor

**Files:**
- Create: `backend/connectors/executor.py`
- Modify: `backend/execution/deps.py` (add `connector_repository`, `record_store`, `source_adapters`)
- Test: `backend/tests/connectors/test_executor.py`

**Interfaces:**
- Consumes: `claim_sync_run` (Task 2), `ConnectorSourceAdapter` (Task 3), `ConnectorPageQueuedEvent` (Task 4), `ExecutionDeps`.
- Produces: `handle_connector_page_queued(event: AnyEvent, deps: ExecutionDeps) -> int`, registered for `"connector.page.queued"`.

- [ ] **Step 1: Write the failing tests**

```python
def test_executor_publishes_the_same_event_the_manual_path_publishes() -> None:
    deps, repo = _deps_with_source(rows=[{"id": "1"}, {"id": "2"}])
    handle_connector_page_queued(_event(cursor=None), deps)

    ingested = [e for e in deps.event_bus.published_events
                if e.event_type == "records.ingested"]
    assert len(ingested) == 1
    assert ingested[0].record_count == 2
    assert ingested[0].knowledge_base_id == "kb-1"


def test_executor_does_not_publish_when_nothing_was_accepted() -> None:
    deps, _ = _deps_with_source(rows=[])
    handle_connector_page_queued(_event(cursor=None), deps)

    assert not [e for e in deps.event_bus.published_events
                if e.event_type == "records.ingested"]


def test_cursor_advances_only_after_the_ingest_event_is_published() -> None:
    deps, repo = _deps_with_source(rows=[{"id": "1"}])
    deps.event_bus.fail_next_publish()          # crash between persist and publish

    with pytest.raises(EventPublishError):
        handle_connector_page_queued(_event(cursor=None), deps)

    run = repo.get_run(_RUN_ID)
    assert run is not None and run.source_cursor is None   # NOT advanced


def test_invalid_rows_are_quarantined_not_dropped() -> None:
    deps, repo = _deps_with_source(rows=[{"id": "1"}, {"bad": "row"}])
    handle_connector_page_queued(_event(cursor=None), deps)

    run = repo.get_run(_RUN_ID)
    assert run is not None
    assert run.counters.accepted == 1
    assert run.counters.quarantined == 1


def test_executor_completes_the_run_at_the_final_page() -> None:
    deps, repo = _deps_with_source(rows=[{"id": "1"}], final_page=True)
    handle_connector_page_queued(_event(cursor=None), deps)

    run = repo.get_run(_RUN_ID)
    assert run is not None and run.status == "completed"
    assert run.completed_at is not None


def test_executor_is_idempotent_under_duplicate_delivery() -> None:
    """Spec 6.4 — Redis Streams is at-least-once, including after a reclaim.

    The same page event redelivered must not double-count counters or publish
    a second ingest event for records already persisted.
    """
    deps, repo = _deps_with_source(rows=[{"id": "1"}, {"id": "2"}])
    event = _event(cursor=None)

    handle_connector_page_queued(event, deps)
    handle_connector_page_queued(event, deps)      # redelivered

    run = repo.get_run(_RUN_ID)
    assert run is not None and run.counters.accepted == 2   # NOT 4
    ingested = [e for e in deps.event_bus.published_events
                if e.event_type == "records.ingested"]
    assert len(ingested) == 1
```

Row persistence already dedups per row by `record_id` (`records/` store), so re-persisting is safe; the counters are what must be derived rather than incremented. Compute `accepted` from the store's reported accepted count for this cursor, not by adding to the previous value.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/connectors/test_executor.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement the executor**

Order is load-bearing — this is spec §4.2 and §6.6:

```python
def handle_connector_page_queued(event: AnyEvent, deps: ExecutionDeps) -> int:
    if not isinstance(event, ConnectorPageQueuedEvent):
        return 0
    repository = deps.connector_repository
    if repository is None:
        return 0

    run = repository.get_run(event.run_id)
    if run is None or run.status in {"canceled", "completed", "failed"}:
        return 0

    now = utc_now()
    claimed = run if run.status == "running" else repository.claim_sync_run(
        run.run_id, now=now
    )
    if claimed is None:
        return 0

    connector = repository.get_connector(event.connector_id)
    if connector is None:
        raise ConnectorNotFoundError(event.connector_id)   # fatal: do not retry

    adapter = deps.source_adapters[connector.source_type]
    page = adapter.read_page(
        config=connector.config, cursor=event.cursor, limit=_PAGE_LIMIT
    )

    accepted, quarantined = _persist_rows(deps, connector, page.rows)

    # 1. persist  2. PUBLISH  3. advance cursor.  Advancing before the publish
    #    means a crash here skips these records forever.
    if accepted > 0:
        deps.event_bus.publish(
            RecordsIngestedEvent(
                correlation_id=claimed.ingest_correlation_id or event.correlation_id,
                knowledge_base_id=connector.knowledge_base_id,
                feed_name=connector.mapping.feed_name,
                record_type=connector.mapping.record_type,
                record_count=accepted,
            )
        )

    repository.update_run(
        claimed.run_id,
        source_cursor=page.next_cursor,
        counters=_advance(claimed.counters, accepted=accepted, quarantined=quarantined),
        updated_at=utc_now(),
    )

    if page.next_cursor is None:
        repository.update_run(claimed.run_id, status="completed", completed_at=utc_now())
    else:
        deps.event_bus.publish(
            ConnectorPageQueuedEvent(
                correlation_id=event.correlation_id,
                knowledge_base_id=connector.knowledge_base_id,
                connector_id=connector.connector_id,
                run_id=claimed.run_id,
                cursor=page.next_cursor,
            )
        )
    return 1
```

Register with `register_handler("connector.page.queued", handle_connector_page_queued)` and import the module from `backend/execution/__init__.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/connectors/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/connectors/executor.py backend/execution/deps.py backend/tests/connectors/test_executor.py
git commit -m "feat(connectors): execute sync runs page by page with publish-before-cursor ordering"
```

---

### Task 6: Reject unimplemented source types and schedule modes

Shipping a `Literal` that accepts values nothing honours is the defect this whole effort exists to remove.

**Files:**
- Modify: `backend/connectors/service.py`
- Test: `backend/tests/connectors/test_service.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_registering_an_unimplemented_source_type_is_rejected() -> None:
    service = _service()
    with pytest.raises(ConnectorValidationError, match="not implemented"):
        service.register_connector(_create(source_type="http"))


def test_registering_a_scheduled_mode_is_rejected() -> None:
    service = _service()
    with pytest.raises(ConnectorValidationError, match="not implemented"):
        service.register_connector(_create(schedule_mode="interval"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/connectors/test_service.py -k unimplemented -v`
Expected: FAIL — both register successfully

- [ ] **Step 3: Add the guards**

```python
_IMPLEMENTED_SOURCE_TYPES: Final[frozenset[str]] = frozenset({"filesystem"})
_IMPLEMENTED_SCHEDULE_MODES: Final[frozenset[str]] = frozenset({"manual"})
```

Raise `ConnectorValidationError` naming what is implemented. Map to HTTP 422 in the router. Widen these sets when `object_store`/`http`/scheduling ship — do not widen the `Literal` first.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/connectors/ tests/api/test_connectors_router.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/connectors/service.py backend/api/routers/connectors.py backend/tests/connectors/test_service.py
git commit -m "feat(connectors): reject source types and schedule modes that are not implemented"
```

---

### Task 7: Live-stack verification and docs

**Files:**
- Test: `backend/tests/e2e/test_connector_sync_flow.py`
- Modify: `docs/ledger/module-map.md`, `docs/backlog/records.md`, `docs/project/planning/backlog.md`

- [ ] **Step 1: Write the integration test**

```python
pytestmark = pytest.mark.integration


def test_connector_sync_ingests_records_end_to_end(tmp_path: Path) -> None:
    _write_csv(tmp_path / "claims.csv", rows=25)
    connector = _register_filesystem_connector(path=tmp_path)
    run_id = _start_sync(connector)

    run = _poll_until_terminal(run_id, timeout_seconds=120)

    assert run["status"] == "completed"
    assert run["counters"]["accepted"] == 25
    assert _records_in_kb(connector["knowledge_base_id"]) == 25
```

- [ ] **Step 2: Run it with the stack up**

```bash
make dev
cd backend && .venv/bin/pytest tests/e2e/test_connector_sync_flow.py -v -m integration
```

Docker commands run in the main session, not a subagent.

- [ ] **Step 3: Verify parity with the manual path**

Confirm the connector-produced `records.ingested` event drives the same downstream flow a manual upload does — records land in `raw_records` and analytics fan-out fires if `RecordsConfig.analytics_trigger` is enabled. Record the observed behaviour in the closeout.

- [ ] **Step 4: Update the docs that say this does not work**

`docs/ledger/module-map.md` — the `connectors/` entry currently reads "metadata only. No source adapter, no scheduler, no ingestion events, no replay." Replace with what shipped, and state plainly that scheduling and the object-store/http adapters remain unimplemented.

- [ ] **Step 5: Run the full gates**

```bash
cd backend && .venv/bin/pytest --cov -q && .venv/bin/pyright && .venv/bin/ruff check --no-cache .
```

- [ ] **Step 6: Commit**

```bash
git add backend/tests/e2e/test_connector_sync_flow.py docs/ledger/module-map.md docs/backlog/records.md docs/project/planning/backlog.md
git commit -m "test(connectors): live-stack sync verification; close the SAFE-CMS-017 executor gap"
```
