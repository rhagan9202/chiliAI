# BL-023 Event Replay Operationalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dead-lettered events become durable `event_dlq` rows written at retry exhaustion, listable/inspectable/replayable/discardable through role-gated `/events/dlq` API routes, with the repo's first operator runbook — per `docs/superpowers/specs/2026-07-15-bl023-event-replay-design.md`.

**Architecture:** A `DlqRecord` Pydantic model + `DlqRecordStore` protocol (in-memory + Postgres adapters, following the BL-041 `SourceDocumentStatusStore` exemplar) is written by `run_handler_with_retry` alongside the existing Redis `.dlq` publish (best-effort — a store failure never masks the handler error or breaks the ACK contract). The API decodes stored payloads through the normal codec and republishes on the regular stream; CAS status transitions make replay/discard race-safe.

**Tech Stack:** Python 3.12, Pydantic v2, Alembic (migration `0010` + snapshot refresh), FastAPI DI + role gates, OpenAPI codegen.

## Global Constraints

- Product-owner rulings: replay surface = API routes on `/events`; **admin** replays/discards, **analyst** reads (viewer excluded — tracebacks may leak internals).
- `event_dlq` columns (spec §1): `dlq_id` text PK, `event_type` text, `correlation_id` text, `payload` JSONB (exactly `encode_event(event)`), `error_message` text, `error_traceback` text, `retry_count` int, `failed_at` timestamptz, `status` text (`pending`|`replayed`|`discarded`), `replayed_at` timestamptz null, `created_at` timestamptz default now; index `(status, created_at DESC)`.
- `mark_replayed`/`mark_discarded` are CAS on `status='pending'`, returning the updated record or `None` (⇒ API 409).
- Wrapper ordering: existing `publish_to_dlq` FIRST (its raise-propagates ACK contract is unchanged), then best-effort store persist (log + swallow store errors).
- Redaction explicitly skipped (spec §3) — do not add redaction machinery.
- Migration lands with refreshed `backend/database/migrations/snapshots/head.sql` in the same commit (`make migrate-snapshot`); `make migrate-check` green.
- Contracts: after the router lands, `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json` (repo root) then `cd chili_app && npm run codegen:api`; CI fails on drift.
- Gates from `/home/rdhagan92/chiliAI/backend`: `.venv/bin/pytest tests/events tests/agent tests/api -q`; full runs with `DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test`; bare `.venv/bin/pyright` 0 errors; `.venv/bin/ruff check --no-cache .` clean. New files strict-clean standalone (`pyright <files>`).
- All commits end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Live verification (Task 5 Step 5) is RESERVED FOR THE CONTROLLER (no Docker in subagents).

---

### Task 1: `DlqRecord` model, `DlqRecordStore` protocol, in-memory adapter

**Files:**
- Create: `backend/events/dlq_models.py`
- Modify: `backend/events/protocols.py` (append protocol + `__all__`)
- Create: `backend/events/adapters/dlq_in_memory.py`
- Test: `backend/tests/events/test_dlq_store.py` (new)

**Interfaces:**
- Produces (consumed verbatim by Tasks 2–4):

```python
DlqRecordStatus = Literal["pending", "replayed", "discarded"]

class DlqRecord(BaseModel):
    dlq_id: str
    event_type: str
    correlation_id: str
    payload: dict[str, str]          # exactly encode_event(event)
    error_message: str
    error_traceback: str
    retry_count: int
    failed_at: datetime
    status: DlqRecordStatus = "pending"
    replayed_at: datetime | None = None
    created_at: datetime             # Field(default_factory=utc_now)

class DlqRecordListResponse(BaseModel):
    items: list[DlqRecord]
    total: int

class DlqRecordStore(Protocol):
    def persist(self, record: DlqRecord) -> DlqRecord: ...
    def list(self, *, status: DlqRecordStatus | None = None, event_type: str | None = None,
             limit: int = 50, offset: int = 0) -> tuple[list[DlqRecord], int]: ...
    def get(self, dlq_id: str) -> DlqRecord | None: ...
    def mark_replayed(self, dlq_id: str) -> DlqRecord | None: ...
    def mark_discarded(self, dlq_id: str) -> DlqRecord | None: ...
```

- [ ] **Step 1: Write the failing tests** — create `backend/tests/events/test_dlq_store.py`:

```python
"""Tests for the durable DLQ record store (BL-023, events.10)."""

from __future__ import annotations

import pytest

from events.adapters.dlq_in_memory import InMemoryDlqRecordStore
from events.dlq_models import DlqRecord
from shared.utils import utc_now


def _record(dlq_id: str, *, event_type: str = "documents.uploaded") -> DlqRecord:
    return DlqRecord(
        dlq_id=dlq_id,
        event_type=event_type,
        correlation_id=f"corr-{dlq_id}",
        payload={"event_type": event_type, "event_body": "{}"},
        error_message="boom",
        error_traceback="Traceback: boom",
        retry_count=3,
        failed_at=utc_now(),
        created_at=utc_now(),
    )


def test_persist_and_get_roundtrip() -> None:
    store = InMemoryDlqRecordStore()
    stored = store.persist(_record("d-1"))
    assert stored.status == "pending"
    fetched = store.get("d-1")
    assert fetched is not None
    assert fetched.error_message == "boom"
    assert store.get("missing") is None


def test_list_filters_and_paginates_newest_first() -> None:
    store = InMemoryDlqRecordStore()
    for i in range(5):
        store.persist(_record(f"d-{i}", event_type="a.x" if i % 2 == 0 else "b.y"))
    items, total = store.list(event_type="a.x")
    assert total == 3
    assert [r.dlq_id for r in items] == ["d-4", "d-2", "d-0"]  # newest first
    page, total = store.list(limit=2, offset=1)
    assert total == 5
    assert len(page) == 2


def test_mark_replayed_is_cas_on_pending() -> None:
    store = InMemoryDlqRecordStore()
    store.persist(_record("d-1"))
    updated = store.mark_replayed("d-1")
    assert updated is not None
    assert updated.status == "replayed"
    assert updated.replayed_at is not None
    assert store.mark_replayed("d-1") is None       # already replayed
    assert store.mark_discarded("d-1") is None      # not pending anymore
    assert store.mark_replayed("missing") is None


def test_mark_discarded_is_cas_on_pending() -> None:
    store = InMemoryDlqRecordStore()
    store.persist(_record("d-1"))
    updated = store.mark_discarded("d-1")
    assert updated is not None
    assert updated.status == "discarded"
    assert updated.replayed_at is None
    assert store.mark_replayed("d-1") is None


def test_list_status_filter() -> None:
    store = InMemoryDlqRecordStore()
    store.persist(_record("d-1"))
    store.persist(_record("d-2"))
    store.mark_discarded("d-1")
    pending, total = store.list(status="pending")
    assert total == 1 and pending[0].dlq_id == "d-2"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /home/rdhagan92/chiliAI/backend && .venv/bin/pytest tests/events/test_dlq_store.py -q`
Expected: FAIL with `ModuleNotFoundError` (`events.dlq_models` / adapter missing).

- [ ] **Step 3: Implement.** Create `backend/events/dlq_models.py`:

```python
"""Durable dead-letter-queue record models (BL-023, events.10)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from shared.utils import utc_now

DlqRecordStatus = Literal["pending", "replayed", "discarded"]


class DlqRecord(BaseModel):
    """One dead-lettered event captured at retry exhaustion."""

    dlq_id: str
    event_type: str
    correlation_id: str
    payload: dict[str, str]
    error_message: str
    error_traceback: str
    retry_count: int
    failed_at: datetime
    status: DlqRecordStatus = "pending"
    replayed_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)


class DlqRecordListResponse(BaseModel):
    """Paginated DLQ listing for the operator API."""

    items: list[DlqRecord]
    total: int


__all__ = ["DlqRecord", "DlqRecordListResponse", "DlqRecordStatus"]
```

Append to `backend/events/protocols.py` (import `DlqRecord`, `DlqRecordStatus` from `events.dlq_models`; extend `__all__` case-sensitively):

```python
@runtime_checkable
class DlqRecordStore(Protocol):
    """Durable operational ledger of dead-lettered events (BL-023)."""

    def persist(self, record: DlqRecord) -> DlqRecord: ...

    def list(
        self,
        *,
        status: DlqRecordStatus | None = None,
        event_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[DlqRecord], int]: ...

    def get(self, dlq_id: str) -> DlqRecord | None: ...

    def mark_replayed(self, dlq_id: str) -> DlqRecord | None: ...

    def mark_discarded(self, dlq_id: str) -> DlqRecord | None: ...
```

Create `backend/events/adapters/dlq_in_memory.py`:

```python
"""In-memory DLQ record store for tests and local scaffolding (BL-023)."""

from __future__ import annotations

from events.dlq_models import DlqRecord, DlqRecordStatus
from events.protocols import DlqRecordStore
from shared.utils import utc_now

__all__ = ["InMemoryDlqRecordStore"]


class InMemoryDlqRecordStore(DlqRecordStore):
    """Process-local DLQ record ledger mirroring the Postgres adapter contract."""

    def __init__(self) -> None:
        self._records: dict[str, DlqRecord] = {}
        self._order: list[str] = []

    def persist(self, record: DlqRecord) -> DlqRecord:
        self._records[record.dlq_id] = record
        self._order.append(record.dlq_id)
        return record

    def list(
        self,
        *,
        status: DlqRecordStatus | None = None,
        event_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[DlqRecord], int]:
        matched = [
            self._records[dlq_id]
            for dlq_id in reversed(self._order)  # newest first
            if (status is None or self._records[dlq_id].status == status)
            and (event_type is None or self._records[dlq_id].event_type == event_type)
        ]
        return matched[offset : offset + limit], len(matched)

    def get(self, dlq_id: str) -> DlqRecord | None:
        return self._records.get(dlq_id)

    def mark_replayed(self, dlq_id: str) -> DlqRecord | None:
        return self._transition(dlq_id, "replayed", stamp_replayed=True)

    def mark_discarded(self, dlq_id: str) -> DlqRecord | None:
        return self._transition(dlq_id, "discarded", stamp_replayed=False)

    def _transition(
        self, dlq_id: str, status: DlqRecordStatus, *, stamp_replayed: bool
    ) -> DlqRecord | None:
        existing = self._records.get(dlq_id)
        if existing is None or existing.status != "pending":
            return None
        updated = existing.model_copy(
            update={
                "status": status,
                "replayed_at": utc_now() if stamp_replayed else None,
            }
        )
        self._records[dlq_id] = updated
        return updated
```

- [ ] **Step 4: Run tests + gates**

Run: `cd /home/rdhagan92/chiliAI/backend && .venv/bin/pytest tests/events -q && .venv/bin/pyright && .venv/bin/pyright events/dlq_models.py events/adapters/dlq_in_memory.py tests/events/test_dlq_store.py && .venv/bin/ruff check --no-cache .`
Expected: all PASS / 0 errors / clean.

- [ ] **Step 5: Commit**

```bash
cd /home/rdhagan92/chiliAI
git add backend/events/dlq_models.py backend/events/protocols.py backend/events/adapters/dlq_in_memory.py backend/tests/events/test_dlq_store.py
git commit -m "feat(events): DlqRecord model, DlqRecordStore protocol, in-memory adapter (BL-023)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Postgres adapter + migration 0010 + snapshot refresh

**Files:**
- Create: `backend/events/adapters/dlq_postgres.py`
- Create: `backend/database/migrations/versions/0010_event_dlq.py`
- Modify: `backend/database/migrations/snapshots/head.sql` (regenerated via `make migrate-snapshot`)
- Test: `backend/tests/events/test_dlq_store.py` (add `@pytest.mark.integration` Postgres cases)

**Interfaces:**
- Consumes: Task 1's protocol/model; `database`'s `ConnectionProvider` (read `backend/ingestion/adapters/postgres.py` — `PostgresSourceDocumentStatusStore` is the exemplar for connection handling, SQL style, and JSONB round-tripping; mirror it).
- Produces: `PostgresDlqRecordStore(provider: ConnectionProvider)` implementing `DlqRecordStore`; CAS transitions implemented in SQL (`UPDATE ... SET status=%s ... WHERE dlq_id=%s AND status='pending' RETURNING ...`).

- [ ] **Step 1: Write the migration** — `backend/database/migrations/versions/0010_event_dlq.py` (mirror 0009's raw-SQL style):

```python
"""Durable event dead-letter-queue records (BL-023, events.10).

Revision ID: 0010_event_dlq
Revises: 0009_document_status
Create Date: 2026-07-15
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0010_event_dlq"
down_revision: str | None = "0009_document_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS event_dlq (
            dlq_id text PRIMARY KEY,
            event_type text NOT NULL,
            correlation_id text NOT NULL,
            payload jsonb NOT NULL,
            error_message text NOT NULL,
            error_traceback text NOT NULL,
            retry_count integer NOT NULL,
            failed_at timestamptz NOT NULL,
            status text NOT NULL DEFAULT 'pending',
            replayed_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_event_dlq_status_created
        ON event_dlq (status, created_at DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_event_dlq_status_created")
    op.execute("DROP TABLE IF EXISTS event_dlq")
```

- [ ] **Step 2: Write the failing integration tests** — append to `backend/tests/events/test_dlq_store.py` (read how `backend/tests/ingestion/` or `tests/database/` integration tests obtain a `ConnectionProvider` fixture — reuse that pattern; the assertions are normative):

```python
@pytest.mark.integration
class TestPostgresDlqRecordStore:
    def test_roundtrip_and_cas(self, connection_provider) -> None:  # fixture per repo pattern
        from events.adapters.dlq_postgres import PostgresDlqRecordStore

        store = PostgresDlqRecordStore(connection_provider)
        record = _record("pg-d-1")
        store.persist(record)
        fetched = store.get("pg-d-1")
        assert fetched is not None
        assert fetched.payload == record.payload
        assert fetched.status == "pending"
        assert store.mark_replayed("pg-d-1") is not None
        assert store.mark_replayed("pg-d-1") is None       # CAS: already replayed
        assert store.mark_discarded("pg-d-1") is None

    def test_list_filters_and_total(self, connection_provider) -> None:
        from events.adapters.dlq_postgres import PostgresDlqRecordStore

        store = PostgresDlqRecordStore(connection_provider)
        for i in range(3):
            store.persist(_record(f"pg-l-{i}", event_type="x.y"))
        items, total = store.list(event_type="x.y", limit=2)
        assert total >= 3
        assert len(items) == 2
        assert items[0].created_at >= items[1].created_at  # newest first
```

- [ ] **Step 3: Implement `PostgresDlqRecordStore`** — mirror `PostgresSourceDocumentStatusStore`'s structure exactly (connection acquisition, cursor usage, JSONB serialization via `json.dumps`/deserialization, row→model mapping). Columns map 1:1 to `DlqRecord` fields. `persist` = plain INSERT; `list` = `SELECT ... WHERE (%s IS NULL OR status = %s) AND (%s IS NULL OR event_type = %s) ORDER BY created_at DESC LIMIT %s OFFSET %s` plus a `COUNT(*)` with the same filters; `get` by PK; transitions:

```sql
UPDATE event_dlq
SET status = %s, replayed_at = %s
WHERE dlq_id = %s AND status = 'pending'
RETURNING dlq_id, event_type, correlation_id, payload, error_message,
          error_traceback, retry_count, failed_at, status, replayed_at, created_at
```

(`replayed_at` = `utc_now()` for replay, `NULL` for discard; return `None` when no row comes back.)

- [ ] **Step 4: Refresh the schema snapshot**

Run from repo root: `make migrate-snapshot` then `make migrate-check`
Expected: snapshot rewritten to include `event_dlq`; check green. (Uses the compose Postgres — the dev stack is running; the script uses a scratch DB.)

- [ ] **Step 5: Run tests + gates**

Run: `cd /home/rdhagan92/chiliAI/backend && DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest tests/events -q -m "not integration" && DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest tests/events -q -m integration && .venv/bin/pyright && .venv/bin/ruff check --no-cache .`
Expected: unit green; integration green against the live DB (chili_test gets `alembic upgrade head` per the repo's integration-test fixtures — check `tests/database` conftest for the migration-application pattern and reuse); pyright 0; ruff clean.

- [ ] **Step 6: Commit**

```bash
cd /home/rdhagan92/chiliAI
git add backend/events/adapters/dlq_postgres.py backend/database/migrations/versions/0010_event_dlq.py backend/database/migrations/snapshots/head.sql backend/tests/events/test_dlq_store.py
git commit -m "feat(events,database): Postgres DLQ record store + 0010_event_dlq migration with snapshot refresh (BL-023)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Retry-wrapper persistence + worker wiring

**Files:**
- Modify: `backend/agent/coordinator.py` (`run_handler_with_retry` ~line 3560; the drain-loop call site ~line 3783; `build_worker_dependencies` + `WorkerDependencies`; a `build_dlq_record_store(config)` selector next to `build_document_status_store`)
- Test: `backend/tests/agent/test_coordinator.py`

**Interfaces:**
- Consumes: Task 1's `DlqRecord`/`DlqRecordStore`/`InMemoryDlqRecordStore`, Task 2's `PostgresDlqRecordStore`; existing `DlqErrorInfo`, `encode_event`, `generate_id`.
- Produces: `run_handler_with_retry(..., dlq_record_store: DlqRecordStore | None = None)` — after a SUCCESSFUL `publish_to_dlq`, best-effort `persist` of a `DlqRecord` (store errors logged + swallowed). `build_dlq_record_store(config) -> DlqRecordStore` (Postgres when a database is configured, else in-memory — mirror `build_document_status_store`'s selection). `WorkerDependencies.dlq_record_store` threaded to the call site.

- [ ] **Step 1: Write the failing tests** — append to `backend/tests/agent/test_coordinator.py` (mirror the module's existing `run_handler_with_retry` tests — read them first for the async invocation + no-sleep pattern):

```python
def test_retry_exhaustion_persists_dlq_record() -> None:
    event_bus = InMemoryEventBus()
    dlq_store = InMemoryDlqRecordStore()
    event = _sample_event()  # reuse the module's existing event builder for these tests

    def failing_handler() -> int:
        raise RuntimeError("boom")

    asyncio.run(
        run_handler_with_retry(
            failing_handler,
            event=event,
            event_bus=event_bus,
            retry_policy=RetryPolicy(max_retries=1, base_delay_seconds=0),
            sleep=_no_sleep,  # module's existing injected sleep
            dlq_record_store=dlq_store,
        )
    )
    records, total = dlq_store.list()
    assert total == 1
    record = records[0]
    assert record.event_type == event.event_type
    assert record.correlation_id == event.correlation_id
    assert record.payload == encode_event(event)
    assert record.error_message == "boom"
    assert record.retry_count == 1
    assert record.status == "pending"
    assert len(event_bus.dlq_entries) == 1  # stream publish still happened


def test_dlq_store_failure_does_not_mask_handler_error() -> None:
    event_bus = InMemoryEventBus()

    class ExplodingStore(InMemoryDlqRecordStore):
        def persist(self, record: DlqRecord) -> DlqRecord:
            raise RuntimeError("store down")

    def failing_handler() -> int:
        raise RuntimeError("boom")

    result = asyncio.run(
        run_handler_with_retry(
            failing_handler,
            event=_sample_event(),
            event_bus=event_bus,
            retry_policy=RetryPolicy(max_retries=0, base_delay_seconds=0),
            sleep=_no_sleep,
            dlq_record_store=ExplodingStore(),
        )
    )
    assert result == 0                      # ACK contract preserved
    assert len(event_bus.dlq_entries) == 1  # stream DLQ still succeeded


def test_no_store_is_a_noop() -> None:
    event_bus = InMemoryEventBus()

    def failing_handler() -> int:
        raise RuntimeError("boom")

    result = asyncio.run(
        run_handler_with_retry(
            failing_handler,
            event=_sample_event(),
            event_bus=event_bus,
            retry_policy=RetryPolicy(max_retries=0, base_delay_seconds=0),
            sleep=_no_sleep,
        )
    )
    assert result == 0
```

(Adapt `_sample_event`/`_no_sleep`/`RetryPolicy` argument names to the module's actual helpers and `RetryPolicy` field names — read them first; assertions are normative.)

- [ ] **Step 2: Run to verify failure**

Run: `cd /home/rdhagan92/chiliAI/backend && .venv/bin/pytest tests/agent/test_coordinator.py -q -k dlq_record or -k dlq_store` (use one `-k "dlq_record or dlq_store or noop"` expression)
Expected: FAIL (`dlq_record_store` unexpected kwarg).

- [ ] **Step 3: Implement.** In `run_handler_with_retry`: add the kwarg `dlq_record_store: DlqRecordStore | None = None`; after the existing `event_bus.publish_to_dlq(event, error_info)` line (keep it first — its exception contract is unchanged), insert:

```python
    if dlq_record_store is not None:
        try:
            dlq_record_store.persist(
                DlqRecord(
                    dlq_id=generate_id(),
                    event_type=event.event_type,
                    correlation_id=event.correlation_id,
                    payload=encode_event(event),
                    error_message=error_info.error_message,
                    error_traceback=error_info.traceback,
                    retry_count=error_info.retry_count,
                    failed_at=error_info.failed_at,
                )
            )
        except Exception:  # noqa: BLE001 - never mask the original handler error
            logger.exception(
                "Failed to persist durable DLQ record; the Redis DLQ entry "
                "still exists. event_type=%s correlation_id=%s",
                event.event_type,
                event.correlation_id,
            )
```

Add `build_dlq_record_store(config: DomainConfig) -> DlqRecordStore` next to `build_document_status_store` (same database-configured selection, returning `PostgresDlqRecordStore(provider)` or `InMemoryDlqRecordStore()`), add `dlq_record_store` to `WorkerDependencies`, construct it in `build_worker_dependencies`, and pass `dlq_record_store=deps.dlq_record_store` at the single `run_handler_with_retry(` call site (~line 3783; verify how other deps reach that loop and match).

- [ ] **Step 4: Run tests + gates**

Run: `cd /home/rdhagan92/chiliAI/backend && .venv/bin/pytest tests/agent tests/events -q && .venv/bin/pyright && .venv/bin/ruff check --no-cache .`
Expected: PASS / 0 / clean.

- [ ] **Step 5: Commit**

```bash
cd /home/rdhagan92/chiliAI
git add backend/agent/coordinator.py backend/tests/agent/test_coordinator.py
git commit -m "feat(agent): persist durable DLQ records at retry exhaustion (BL-023)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: `/events/dlq` API routes + DI + contracts regen

**Files:**
- Modify: `backend/api/routers/events.py`, `backend/api/dependencies.py`
- Modify: `chili_app/openapi.json`, `chili_app/src/lib/api/schema.ts` (generated — never hand-edit)
- Test: `backend/tests/api/test_events_dlq.py` (new)

**Interfaces:**
- Consumes: Tasks 1–2 (`DlqRecord`, `DlqRecordListResponse`, `DlqRecordStatus`, stores), existing `get_event_bus`, `require_role`, `decode_event`.
- Produces: `get_dlq_record_store()` in `api/dependencies.py` (lru_cache, Postgres-when-configured — mirror `get_document_status_store` at `dependencies.py:1336`, and register it in the module's dependency map like `dependencies.py:1717`); four routes:
  - `GET /events/dlq` → `DlqRecordListResponse`, query `status: DlqRecordStatus | None`, `event_type: str | None`, `limit: int = Query(50, ge=1, le=500)`, `offset: int = Query(0, ge=0)` — `require_role("analyst")`
  - `GET /events/dlq/{dlq_id}` → `DlqRecord` or 404 — `require_role("analyst")`
  - `POST /events/dlq/{dlq_id}/replay` → `DlqRecord`; 404 unknown; 409 non-pending; 422 undecodable payload (record left pending) — `require_role("admin")`
  - `POST /events/dlq/{dlq_id}/discard` → `DlqRecord`; 404/409 — `require_role("admin")`

- [ ] **Step 1: Verify the role literal.** `grep -n 'require_role("admin")' backend/api/routers/*.py` — confirm "admin" is used elsewhere (config apply/switch). If the repo uses a different admin-tier literal, use that one and note it in your report.

- [ ] **Step 2: Write the failing tests** — create `backend/tests/api/test_events_dlq.py`, mirroring the construction style of the module's other router tests (app factory + dependency overrides; read `backend/tests/api/test_config_router.py` for the override pattern and whatever role-override helper the API tests use):

```python
"""Tests for the /events/dlq operator surface (BL-023)."""
# Imports/fixtures per the api test conventions — read a sibling router test first.


def test_list_dlq_returns_paginated_records(...) -> None:
    # seed InMemoryDlqRecordStore with 2 records via dependency override
    # GET /events/dlq -> 200, total == 2, items newest-first, NO error_traceback key in list items? --
    # NOTE: list returns full DlqRecord models (traceback included) — the spec's
    # "summary shape" was refined at plan time to full records for YAGNI; analysts
    # may read tracebacks by ruling. Assert items[0]["status"] == "pending".
    ...


def test_get_dlq_record_and_404(...) -> None: ...


def test_replay_publishes_and_marks_replayed(...) -> None:
    # seed a record whose payload = encode_event(<real event>) built with the events fixtures;
    # override get_event_bus with InMemoryEventBus.
    # POST /events/dlq/{id}/replay -> 200, body status == "replayed"
    # assert the InMemoryEventBus.published_events contains the decoded event
    # POST again -> 409


def test_replay_undecodable_payload_is_422_and_stays_pending(...) -> None:
    # payload {"event_type": "nope.unknown", "event_body": "{}"} -> 422; GET shows status pending


def test_discard_marks_discarded_and_409_on_repeat(...) -> None: ...


def test_role_gates(...) -> None:
    # viewer -> 403 on GET list; analyst -> 403 on replay/discard; admin -> 200s
    # (use the repo's established role-override mechanism — CHILI_DEV_ANONYMOUS_ROLE
    # or dependency override, whichever sibling tests use)
```

Write these as REAL tests (the sketch above shows required behavior — flesh out with the module's actual fixtures; every branch listed must be asserted).

- [ ] **Step 3: Run to verify failure**

Run: `cd /home/rdhagan92/chiliAI/backend && .venv/bin/pytest tests/api/test_events_dlq.py -q`
Expected: FAIL (routes missing → 404s).

- [ ] **Step 4: Implement** the DI provider + routes:

```python
@router.get("/dlq", response_model=DlqRecordListResponse, dependencies=[Depends(require_role("analyst"))])
async def list_dlq_records(
    status_filter: DlqRecordStatus | None = Query(default=None, alias="status"),
    event_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    store: DlqRecordStore = Depends(get_dlq_record_store),
) -> DlqRecordListResponse:
    items, total = store.list(status=status_filter, event_type=event_type, limit=limit, offset=offset)
    return DlqRecordListResponse(items=items, total=total)


@router.get("/dlq/{dlq_id}", response_model=DlqRecord, dependencies=[Depends(require_role("analyst"))])
async def get_dlq_record(
    dlq_id: str,
    store: DlqRecordStore = Depends(get_dlq_record_store),
) -> DlqRecord:
    record = store.get(dlq_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"DLQ record '{dlq_id}' not found.")
    return record


@router.post("/dlq/{dlq_id}/replay", response_model=DlqRecord, dependencies=[Depends(require_role("admin"))])
async def replay_dlq_record(
    dlq_id: str,
    store: DlqRecordStore = Depends(get_dlq_record_store),
    event_bus: EventBus = Depends(get_event_bus),
) -> DlqRecord:
    record = store.get(dlq_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"DLQ record '{dlq_id}' not found.")
    if record.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"DLQ record '{dlq_id}' is '{record.status}', not pending.")
    try:
        event = decode_event(record.payload)
    except Exception as exc:  # noqa: BLE001 - codec drift surfaces as 422
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Stored payload no longer decodes: {exc}",
        ) from exc
    event_bus.publish(event)
    updated = store.mark_replayed(dlq_id)
    if updated is None:  # raced with another operator between get and CAS
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"DLQ record '{dlq_id}' was transitioned concurrently.")
    return updated


@router.post("/dlq/{dlq_id}/discard", response_model=DlqRecord, dependencies=[Depends(require_role("admin"))])
async def discard_dlq_record(
    dlq_id: str,
    store: DlqRecordStore = Depends(get_dlq_record_store),
) -> DlqRecord:
    updated = store.mark_discarded(dlq_id)
    if updated is not None:
        return updated
    if store.get(dlq_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"DLQ record '{dlq_id}' not found.")
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"DLQ record '{dlq_id}' is not pending.")
```

(Adapt imports to the router's existing style; `get_dlq_record_store` in `api/dependencies.py` mirrors `get_document_status_store` verbatim with the DLQ classes.)

- [ ] **Step 5: Regenerate contracts**

Run from repo root: `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json && cd chili_app && npm run codegen:api`
Expected: openapi.json + schema.ts updated; `git diff --stat chili_app` shows only generated files.

- [ ] **Step 6: Run tests + gates**

Run: `cd /home/rdhagan92/chiliAI/backend && .venv/bin/pytest tests/api tests/events -q && .venv/bin/pyright && .venv/bin/ruff check --no-cache .` and `cd /home/rdhagan92/chiliAI/chili_app && npm run lint && npm run test:run`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
cd /home/rdhagan92/chiliAI
git add backend/api backend/tests/api/test_events_dlq.py chili_app/openapi.json chili_app/src/lib/api/schema.ts
git commit -m "feat(api): /events/dlq operator surface — list/inspect/replay/discard with role gates (BL-023)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Runbook + docs + closeout (+ controller-run live verification)

**Files:**
- Create: `docs/runbooks/event-replay.md` (new directory)
- Create: `backend/events/README.md` (module has none — cover: module purpose, bus adapters, DLQ streams + durable records, the shared-Postgres constraint for the API surface, codec)
- Modify: `backend/README.md` (Current State + commands if touched), `docs/architecture.md` (events section: DLQ persistence + replay surface), `backend/agent/README.md` (retry/DLQ paragraph gains the durable-record sentence), `docs/backlog/events.md` (events.10 → done with the redaction deviation; annotate the live-replay story that DLQ replay shipped here), `docs/project/planning/backlog.md` (BL-023 + BL-022 stretch status), `docs/project/planning/sprints/2026-27.md` (progress entry)

- [ ] **Step 1: Write the runbook** per spec §4 — every section listed there, with real curl examples for all four routes (use `:8000`, note the dev `CHILI_DEV_ANONYMOUS_ROLE` requirement for admin actions), the replay-of-unfixed-event-dead-letters-again loop, discard semantics, and the `event_dlq`-table-vs-`.dlq`-streams relationship.

- [ ] **Step 2: Update module/architecture docs** (list above). Search for contradictions: `grep -rn "dlq\|dead-letter" docs/architecture.md backend/README.md .github/ CLAUDE.md -i` and reconcile any statement that says DLQ records are not durable / not replayable.

- [ ] **Step 3: Story + backlog closeout.** `docs/backlog/events.md`: events.10 → `done` (Done line `**Done:** 2026-07-15 · BL-023 (Sprint 2026-27) · feat/sprint-2026-27-event-replay`; all AC boxes checked with the redaction deviation noted inline — "no existing redaction conventions; payloads reference-shaped by construction; deliberate skip per design"). Planning backlog: BL-023 → done (live-verification wording per what has actually run at commit time: pending, controller runs it). Sprint file: progress entry. `backend/.venv/bin/python scripts/backlog_consistency.py` + `--check` exit 0.

- [ ] **Step 4: Full gates**

Run: `cd /home/rdhagan92/chiliAI/backend && DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest --cov -m "not integration" -q && .venv/bin/pyright && .venv/bin/ruff check --no-cache .`
Expected: full pass, `events` package ≥ 85%, 0 errors, clean.

- [ ] **Step 5: Live verification — RESERVED FOR THE CONTROLLER (main session).** Against `make dev` (worker+api restarted onto this branch): (1) force a poison event (e.g. upload a document, then break its extraction artifact — or inject a crafted event whose handler raises deterministically) → DLQ record appears in `GET /events/dlq` with traceback; (2) `POST .../replay` while still broken → 200, original flips `replayed`, and a NEW pending record appears after the worker exhausts retries again; (3) discard the new record → `discarded`; (4) fixable case: repair the cause, replay, pipeline completes; (5) role gates live: viewer 403 on list, analyst 403 on replay.

- [ ] **Step 6: Commit**

```bash
cd /home/rdhagan92/chiliAI
git add docs/ backend/README.md backend/events/README.md backend/agent/README.md
git commit -m "docs(events): operator replay runbook, events README, BL-023 closeout

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Self-review notes (already applied)

- Spec coverage: §1→Tasks 1-3, §2→Task 4, §3→Task 5 Step 3 (deviation note), §4→Task 5 Step 1, §5→Tasks 3-4 (wiring), §6→every task + Task 5 Steps 4-5. One refinement made at plan time: the list route returns full `DlqRecord` models rather than a separate summary shape (YAGNI — analysts may read tracebacks by ruling; noted in Task 4's test sketch).
- Type consistency: `DlqRecord`/`DlqRecordStore`/`DlqRecordStatus`/`InMemoryDlqRecordStore`/`PostgresDlqRecordStore` names identical across Tasks 1-4; wrapper kwarg `dlq_record_store` matches Task 3's production and Task 4 never touches it.
- Helper stand-ins (`_sample_event`, `_no_sleep`, `connection_provider`, api test fixtures) follow the established convention: read the module first, assertions are normative.
- Task 4 Step 2's test code is deliberately a specified-behavior sketch (module fixture styles vary) — every listed branch is mandatory; implementers flesh out with real fixtures.
