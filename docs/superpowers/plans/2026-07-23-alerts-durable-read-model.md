# Alerts Durable Read Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve `GET /alerts` (and ack/SSE counts/KB cleanup) from the durable Postgres `alert_history` store that the worker already writes for every real alert (Flow B + monitoring), retiring the dev-seed-only projection blob — closing monitoring.md's "empty alert feed in a fresh deployment" gap for real analysts. Plus: remove the analyst-role dashboard exclusion in the CMS/food packs.

**Architecture:** The sole `alerts.created` consumer (`handle_alerts_created_for_graph`) already idempotently writes `alert_history` (PK `(kb, alert_id)`). We extend the table with the three read-model fields (`entity_label`, `confidence`, `tags`), extend the event/record to carry them, promote the monitoring-owned store to a full read/mutate protocol (list/get/acknowledge/count/remove-by-kb) with Postgres + in-memory adapters, and DI-switch the API onto it (Postgres when a connection provider exists — same pattern as risk/timeseries stores). `api/_alert_store.py`'s object-store adapter and snapshot format are retired; the API-facing `AlertProjectionRecord`/`project_alert_feed` response shaping stays (contract unchanged).

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI, Postgres via the existing connection provider, pytest; frontend untouched (wire contract `AlertListItem` unchanged).

## Global Constraints

- Host venv gates: `backend/.venv/bin/pytest`, bare `backend/.venv/bin/pyright` (0 errors), `backend/.venv/bin/ruff check --no-cache .`. Tests vs `chili_test` only — NEVER export `DATABASE_URL` at the dev `chili` DB; PG integration tests follow the existing `tests/analytics/timeseries/test_anomaly_store_postgres.py` pattern (`@pytest.mark.integration`).
- Cross-module rule: the store lives in `backend/monitoring/` (it already owns the `alert_history` adapters). The API consumes it ONLY via DI in `api/dependencies.py`; the worker keeps consuming via its existing writer protocol. No api→monitoring business logic, no monitoring→api imports.
- Wire contract unchanged: `AlertListItem` / `AlertListResponse` / ack response shapes stay byte-identical (no OpenAPI drift — verify with the export at the end; zero-diff expected).
- Event schema change (`AlertCreatedReference` gains fields with defaults) is backward-compatible: old events in streams/DLQ must still decode (all new fields default).
- Every task: TDD (failing test first), commit messages end `(alerts.36)` — this work is chartered as the new story `monitoring` gap closure; Task 5 records it properly in the backlog.
- Idempotency and multi-writer safety are the point: ack = SQL `UPDATE ... SET status='acknowledged'` by `(kb, alert_id)`... note the API ack route receives only `alert_id` — the store's `acknowledge(alert_id)` updates by `alert_id` alone (alert ids are UUIDs, globally unique; PK stays composite for the writer's idempotency).

---

### Task 1: Migration 0012 — read-model columns on `alert_history`

**Files:**
- Create: `backend/database/migrations/versions/0012_alert_history_read_model.py`
- Modify: `backend/database/migrations/snapshots/head.sql` (regenerated — see Step 4)
- Test: `backend/tests/database/test_migrations.py` (append assertions to the existing baseline column checks per that file's pattern)

**Interfaces:**
- Produces columns consumed by Tasks 2-3: `entity_label text NOT NULL DEFAULT ''`, `confidence double precision NOT NULL DEFAULT 0`, `tags jsonb NOT NULL DEFAULT '[]'::jsonb` on `alert_history`. Downgrade drops the three columns.

- [ ] **Step 1: Write the failing test** — extend the migrations test that asserts `alert_history` columns (find the existing table-shape assertion; add the three new columns + defaults to its expectation).
- [ ] **Step 2: Run it red** (`.venv/bin/pytest tests/database/test_migrations.py -q` from backend/, against chili_test — confirm it fails on missing columns).
- [ ] **Step 3: Write the migration** (revision `0012`, down_revision `0011`):

```python
"""Alert history read-model columns (alerts feed served from Postgres)."""

from alembic import op
import sqlalchemy as sa

revision = "0012_alert_history_read_model"
down_revision = "0011_timeseries_anomalies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "alert_history",
        sa.Column("entity_label", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "alert_history",
        sa.Column(
            "confidence", sa.Float(), nullable=False, server_default=sa.text("0")
        ),
    )
    op.add_column(
        "alert_history",
        sa.Column(
            "tags",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("alert_history", "tags")
    op.drop_column("alert_history", "confidence")
    op.drop_column("alert_history", "entity_label")
```

(Adapt revision id strings to the repo's actual naming convention — read 0011's header first and mirror it exactly.)
- [ ] **Step 4: Apply + snapshot.** From backend/: `DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/alembic upgrade head`; test green; then from repo root `make migrate-snapshot` and commit the regenerated `head.sql` WITH this task.
- [ ] **Step 5: Gates + commit** — `pytest tests/database -q`, pyright, ruff. Commit `feat(database): alert_history read-model columns (alerts.36)`.

---

### Task 2: Monitoring alert-feed store — full read/mutate protocol + both adapters

**Files:**
- Modify: `backend/monitoring/models.py` (or wherever `AlertHistoryRecord` lives — locate it) — add `entity_label: str = ""`, `confidence: float = 0.0` (ge=0 le=1), `tags: list[str] = []` (default_factory)
- Modify: `backend/monitoring/adapters/protocols.py` — extend/add `AlertFeedStoreProtocol` with: `write_alerts(records) -> int` (existing), `list_alerts(*, statuses: list[str] | None, limit: int, offset: int) -> tuple[list[AlertHistoryRecord], int]`, `get_alert(alert_id: str) -> AlertHistoryRecord | None`, `acknowledge(alert_id: str) -> AlertHistoryRecord | None`, `count_by_statuses(statuses: set[str]) -> int`, `delete_by_kb(knowledge_base_id: str) -> int` (existing)
- Modify: `backend/monitoring/adapters/postgres.py` (`PostgresAlertHistoryStore`) — new columns in `_ALERT_INSERT_SQL`; implement the read/mutate methods (list: `ORDER BY created_at DESC, alert_id DESC LIMIT/OFFSET` + `count(*)` total, optional `status = ANY(...)` filter; acknowledge: `UPDATE alert_history SET status='acknowledged', updated_at=now() WHERE alert_id=%s RETURNING ...`)
- Modify: `backend/monitoring/adapters/in_memory.py` (`InMemoryAlertHistoryWriter` → full store) — same semantics, insertion-ordered dict keyed `(kb, alert_id)`, created_at-desc listing
- Test: extend `backend/tests/monitoring/test_alert_history_writer.py` (in-memory) and `backend/tests/monitoring/test_postgres_alert_history.py` (PG integration, `@pytest.mark.integration`) — parity: same test scenarios both adapters (write→list ordering, status filter, ack persists + returns updated record + None for unknown id, count_by_statuses, idempotent double-write keeps first row, new fields round-trip incl. tags list)

**Interfaces:**
- Produces `AlertFeedStoreProtocol` — Task 4's DI + Task 3's writer both consume. Keep the existing writer protocol name importable (worker construction sites must not break; extend rather than rename where possible).

Steps: TDD per scenario list above (write parity tests first — red on missing methods; implement Postgres + in-memory; green). Gates: `pytest tests/monitoring -q` (+ `-m integration` for the PG file vs chili_test), pyright, ruff. Commit `feat(monitoring): alert feed store — durable list/ack/count on alert_history (alerts.36)`.

---

### Task 3: Event + worker carry the read-model fields

**Files:**
- Modify: `backend/events/types.py` — `AlertCreatedReference` gains `entity_label: str = ""`, `confidence: float = 0.0`, `tags: list[str] = Field(default_factory=list)`
- Modify: `backend/agent/coordinator.py` — `_run_explainability_stage` populates them on the `AlertCreatedReference` (`confidence=risk_response.overall_score`; `entity_label`: resolve via the entity data already in scope if a display value is cheaply available, else `entity_id`; `tags`: top factor names as kebab slugs — `[f.factor_name.replace('_','-') for f in risk_response.factors[:3]]`); `handle_alerts_created_for_graph` maps the three fields onto `AlertHistoryRecord`
- Modify: `backend/monitoring/service.py` — where `evaluate()` builds `AlertsCreatedEvent` alerts, populate `entity_label`/`confidence`/`tags` from what the monitoring alert already carries (read the build site first; map what exists, default the rest)
- Test: append to `backend/tests/agent/test_alerts_created_graph_flow.py` (fields flow event→history record) and the monitoring service test that covers evaluate()'s event publication (fields populated)

**Interfaces:**
- Consumes Task 2's record fields. Backward-compat: all new fields default — old serialized events must still decode (add one decode test with a legacy payload lacking the fields).

Steps: TDD. Gates: `pytest tests/agent tests/monitoring tests/events -q`, pyright, ruff. Commit `feat(agent,monitoring,events): alerts carry entity_label/confidence/tags to history (alerts.36)`.

---

### Task 4: API serves alerts from the durable store; projection retired

**Files:**
- Modify: `backend/api/dependencies.py` — new `get_alert_feed_store()` (config-cache-registered like `get_timeseries_anomaly_store`: Postgres store when `get_connection_provider()` else in-memory); rewire `get_alert_repository` consumers: list/get/ack routes, `count_active_alerts` (SSE), KB-cleanup `remove_by_knowledge_base` → `delete_by_kb`, `get_case_promote_payload`'s alert read — all onto the new store; response shaping maps `AlertHistoryRecord` → existing `AlertListItem` fields (`entity_label`, `confidence`, `tags` now real)
- Modify: `backend/api/routers/alerts.py`, `backend/api/routers/events.py`, `backend/api/routers/dev_seed.py` (seed via the new store — e2e depends on it), `backend/api/_kb_cleanup.py` (cleanup step)
- Delete/reduce: `backend/api/_alert_store.py` — remove `ObjectStoreAlertProjectionRepository` + snapshot format + the old protocol IF no consumer remains (grep first); keep/migrate any response-shaping helpers (`project_alert_feed`) that the routes still use
- Modify: `docker-compose.dev.yaml` — drop the now-dead `CHILI_ALERT_REPOSITORY_BACKEND` env (grep repo-wide for the env var and remove its selection logic)
- Test: update `backend/tests/api/test_read_model_routers.py` / `test_phase5_stateful_routes.py` / `test_events_router.py` / `test_dependencies.py` / `test_kb_cleanup.py` — DI-override with the in-memory store (mirror the risk-route migration pattern from B2's 42ef186: seeded-store overrides, honest-empty default); delete `test_alert_store_object_store.py` with the adapter; ADD a request-level PG integration test (mirror `test_anomaly_store_postgres.py`) proving list+ack durably against chili_test

**Interfaces:**
- Consumes Task 2's protocol. Contract: `AlertListItem` unchanged — after the change run the OpenAPI export; ZERO diff expected (do not commit contract files; assert no drift).

Steps: TDD (rewrite failing route tests first). Gates: `pytest tests/api tests/monitoring -q`, full `make test` (stack's postgres is up), pyright, ruff, OpenAPI zero-drift check. Commit `feat(api): serve alert feed from durable alert_history store; retire projection blob (alerts.36)`.

---

### Task 5: Dashboard exclusion removal + docs/backlog reconciliation

**Files:**
- Modify: `backend/config/defaults/medicare_fraud_cms_desynpuf.yaml` roles.analyst.pages — add `dashboard` (list becomes `[dashboard, alerts, investigation, knowledge_bases, rag_chat]`; landing stays `alerts`); same edit in `backend/config/defaults/food_supply_chain.yaml` (identical template) and `backend/config/defaults/medicare_fraud.yaml` analyst role
- Test: the pack-validation test that loads default YAMLs (grep `tests/config` for it) — add/extend an assertion that every pack's analyst role includes `dashboard` when the pack's nav routes it
- Docs: `backend/monitoring/README.md` (if present) + `backend/README.md` + `docs/architecture.md` (alert flow paragraph) + `docs/wiki/` (alerts flow/contracts pages, api module dispatch table, CHANGELOG) — the projection retirement and durable feed; `docs/backlog/monitoring.md` — close the "empty alert feed" story (~line 65) with provenance, charter `alerts.36`-style story per file conventions if the fix needs an ID; `docs/backlog/frontend.md` — note the workbench Evidence tab now resolves real alerts (the U2 live-pass observation is superseded); rollup via the generator; `--check` exit 0
- Test count guard: full `make test` green

Steps: config edit + test first, then docs. Commits: `feat(config): analyst role gains dashboard across CMS/food packs (alerts.36)` then `docs(monitoring,backlog,wiki): durable alert feed + analyst dashboard reconciliation (alerts.36)`.

---

### Task 6: Live verification — RESERVED FOR THE CONTROLLER

Against the running dev stack (worker+api restarted onto the branch):

- [ ] Apply migration to dev DB (`make migrate` or alembic in-container) AND chili_test.
- [ ] Fire a synthetic Flow B `graph.updated` (the B3 live-pass staging pattern) over a signal-rich TN provider → `alert_history` row gains entity_label/confidence/tags; `GET /alerts?knowledge_base_id=<TN kb>` returns it (THE gap: analytics alerts visible to analysts).
- [ ] Workbench Evidence tab for that entity now resolves the alert → renders the narrative+attribution pack (closes the U2 live-pass EmptyState observation).
- [ ] Ack the alert via the UI; restart the api container; ack state SURVIVES (durability proof the projection never had).
- [ ] SSE `active_alerts` count reflects the store; KB-delete cascade removes the KB's alert rows.
- [ ] Dashboard as ANALYST on the desynpuf pack: sidebar shows Dashboard, route renders (exclusion gone); supervisor unchanged.
- [ ] e2e: full Playwright suite green (dev-seed now seeds through the durable store).
- [ ] Full gates: `make test`, pyright, ruff, backlog `--check`, OpenAPI zero-drift.

## Self-review notes (applied)

- The ack-by-alert_id-only decision (UUID global uniqueness) is stated in Global Constraints; the composite PK stays for writer idempotency.
- Legacy-event decode compatibility is an explicit Task 3 test.
- dev_seed migration keeps the e2e suite meaningful (Task 4), verified live in Task 6.
- The projection's `entity_label/confidence/tags` semantics move source-of-truth from seed fiction to pipeline data; Flow B tag derivation (factor slugs) feeds U2's flag labels with real content.
