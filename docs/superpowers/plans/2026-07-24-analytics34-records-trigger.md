# analytics.34 — Records→Analytics Trigger + Demo De-Triggering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Records-only KBs trigger Flow B analytics (GNN → risk → explainability → alerts) naturally on ingest, so the D1 demo's explicit `demo_trigger_analytics` workaround — and the two live-confirmed defects it carries (DLQ poison via `graph-updates/` key, degenerate placeholder embeddings) — can be deleted at the root; ship the verified standalone fixes alongside.

**Architecture:** Option B from `docs/backlog/analytics.md` analytics.34 — a **direct in-process call** to `handle_graph_updated_for_analytics` at the end of `handle_records_ingested`, using an in-memory `GraphUpdatedEvent` whose document reference carries **inline `upserted_entity_ids`** (the resolver `_resolve_upserted_entity_ids` at `coordinator.py:2190` already duck-types this field before falling back to storage keys). No event is published, so Flow A's storage-key `ValueError` path and redundant re-embedding are never touched. Cost is bounded two ways: a per-KB `MetricsRecomputeThrottle` window, and a top-N-by-risk-score cap over the batch's just-assessed entities (`assess_entities` gains a scored return). Fan-out is best-effort-wrapped exactly like the document dispatch (`coordinator.py:3846-3875`) so an analytics failure can never make the retry/DLQ wrapper replay the records ingest.

**Tech Stack:** Python 3.12 / Pydantic v2 / pytest; bash for demo scripts; Playwright (TS) for e2e; no new dependencies.

## Global Constraints

- `pyright` strict clean on BOTH configs (bare `pyright` in `backend/`, plus standalone `tools/pyrightconfig.json`); no `Any`.
- Backend coverage ≥ 85%; run against `chili_test` only (never dev `chili`).
- `ruff check --no-cache .` clean (import order is the only ignorable class, but don't introduce new issues).
- `GET /config/domain` exposes `DomainConfig` → any `RecordsConfig` change alters OpenAPI → MUST regen: `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json` then `cd chili_app && npm run codegen:api`. CI fails on drift.
- e2e runs against the real running stack; `page.route` patterns `/api/`-anchored; no mocking the subject under test.
- Backlog edits must pass the validator (run in Task 9); analytics.34 has no prerequisites so `planned → done` is legal with delivered evidence.
- Event-contract changes must be additive/optional (stored DLQ payloads and old producers must still parse).
- Never point `DATABASE_URL` at dev `chili` when testing.

---

### Task 1: Inline entity ids on the graph.updated contract

**Files:**
- Modify: `backend/events/types.py:144-153` (`GraphUpdatedDocumentReference`)
- Test: `backend/tests/events/test_types.py` (add to existing file)

**Interfaces:**
- Produces: `GraphUpdatedDocumentReference.upserted_entity_ids: list[str] | None = None` — consumed by Task 4's fan-out and (already) by `_resolve_upserted_entity_ids`.

- [ ] **Step 1: Write the failing tests** (append to `backend/tests/events/test_types.py`):

```python
def test_graph_updated_document_reference_accepts_inline_entity_ids() -> None:
    ref = GraphUpdatedDocumentReference(
        knowledge_base_id="kb-1",
        source_document_id="records:claims",
        parsed_document_id="records:claims",
        extraction_result_id="records:claims",
        validation_report_id="records:claims",
        upserted_entity_count=2,
        upserted_relationship_count=0,
        upserted_entity_ids=["provider:1", "provider:2"],
    )
    assert ref.upserted_entity_ids == ["provider:1", "provider:2"]


def test_graph_updated_document_reference_entity_ids_default_none() -> None:
    ref = GraphUpdatedDocumentReference(
        knowledge_base_id="kb-1",
        source_document_id="doc-1",
        parsed_document_id="parsed-1",
        extraction_result_id="ext-1",
        validation_report_id="val-1",
        upserted_entity_count=0,
        upserted_relationship_count=0,
    )
    assert ref.upserted_entity_ids is None
```

- [ ] **Step 2: Run to verify failure** — `cd backend && .venv/bin/pytest tests/events/test_types.py -q -k inline_entity or entity_ids_default` → FAIL (unexpected keyword / attribute).
- [ ] **Step 3: Implement** — add to `GraphUpdatedDocumentReference` after `graph_update_storage_key`:

```python
    # analytics.34: records-driven fan-out passes upserted ids inline instead
    # of via a stored GraphUpsertResult artifact; the analytics resolver
    # prefers this field when present (see _resolve_upserted_entity_ids).
    upserted_entity_ids: list[str] | None = None
```

- [ ] **Step 4: Run tests** → PASS. Also `.venv/bin/pytest tests/events -q` stays green.
- [ ] **Step 5: Commit** — `feat(events): inline upserted_entity_ids on GraphUpdatedDocumentReference (analytics.34)`

### Task 2: RecordsConfig analytics-trigger gate + CMS pack + contract regen

**Files:**
- Modify: `backend/config/schema.py:382-385` (`RecordsConfig`)
- Modify: `backend/config/defaults/medicare_fraud_cms_desynpuf.yaml` (records section)
- Modify: `chili_app/openapi.json`, `chili_app/src/lib/api/schema.ts` (generated)
- Test: `backend/tests/config/test_schema.py` (add), existing pack-load tests must stay green

**Interfaces:**
- Produces: `RecordsAnalyticsTriggerConfig(enabled: bool = False, max_entities_per_batch: int = 25, min_interval_seconds: int = 600)`; `RecordsConfig.analytics_trigger: RecordsAnalyticsTriggerConfig` — consumed by Tasks 3–4.

- [ ] **Step 1: Failing tests** (append to `backend/tests/config/test_schema.py`):

```python
def test_records_analytics_trigger_defaults_off() -> None:
    config = RecordsConfig()
    assert config.analytics_trigger.enabled is False
    assert config.analytics_trigger.max_entities_per_batch == 25
    assert config.analytics_trigger.min_interval_seconds == 600


def test_records_analytics_trigger_rejects_nonpositive_cap() -> None:
    with pytest.raises(ValidationError):
        RecordsAnalyticsTriggerConfig(max_entities_per_batch=0)
```

- [ ] **Step 2: Verify FAIL**, then implement in `backend/config/schema.py` immediately above `RecordsConfig`:

```python
class RecordsAnalyticsTriggerConfig(BaseModel):
    """Gate for the records→analytics fan-out (analytics.34).

    When enabled, a structured-records batch that produced risk-assessable
    entities runs Flow B (GNN → risk → explainability → alerts) in-process,
    throttled per KB and capped to the batch's top-N entities by risk score.
    """

    enabled: bool = False
    max_entities_per_batch: int = Field(default=25, ge=1, le=500)
    min_interval_seconds: int = Field(default=600, ge=1)


class RecordsConfig(BaseModel):
    """Structured-ingestion feed configuration for the domain."""

    feeds: list[RecordFeedConfig] = Field(default_factory=lambda: [])
    analytics_trigger: RecordsAnalyticsTriggerConfig = Field(
        default_factory=RecordsAnalyticsTriggerConfig
    )
```

- [ ] **Step 3: CMS pack** — in `backend/config/defaults/medicare_fraud_cms_desynpuf.yaml` under the existing `records:` key (sibling of `feeds:`):

```yaml
  analytics_trigger:
    enabled: true
    # Top-3 preserves the established demo narrative (same selection the
    # removed demo trigger used); one window per hour ≈ one fan-out per
    # full TN-subset ingest.
    max_entities_per_batch: 3
    min_interval_seconds: 3600
```

- [ ] **Step 4: Run** `cd backend && .venv/bin/pytest tests/config -q` → green.
- [ ] **Step 5: Regen contracts** — `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json && cd chili_app && npm run codegen:api` (from repo root); `git diff --stat` shows only generated files + yaml + schema.
- [ ] **Step 6: Commit** — `feat(config): RecordsConfig.analytics_trigger gate; enabled top-3/1h in CMS pack (analytics.34)`

### Task 3: `assess_entities` returns scored responses

**Files:**
- Modify: `backend/agent/coordinator.py:2913-2951` (`assess_entities`), `:3131-3137` (caller)
- Test: `backend/tests/agent/test_peerstats_stage.py:268,294` (two existing callsites)

**Interfaces:**
- Produces: `assess_entities(...) -> list[RiskAssessmentResponse]` (was `int`; responses carry `entity_id`, `overall_score`, `request_id`). Consumed by Task 4's top-N ranking.

- [ ] **Step 1:** Change signature/return: collect each successful `risk_service.assess(...)` response into `assessed: list[RiskAssessmentResponse]`, `assessed.append(response)`, return the list. Update docstring line "Assess each entity once" to note the scored return.
- [ ] **Step 2:** Caller in `handle_records_ingested`: bind the list (Task 4 consumes it); behavior otherwise unchanged. Update `test_peerstats_stage.py` callsites: `count = assess_entities(...)` → `count = len(assess_entities(...))`; the assertion at :294 wraps `assess_entities` in `pytest.raises` — unchanged.
- [ ] **Step 3:** `cd backend && .venv/bin/pytest tests/agent -q -k "peerstats or records"` → green. Commit — `refactor(agent): assess_entities returns scored responses (analytics.34 prep)`

### Task 4: The fan-out — records ingest runs Flow B in-process

**Files:**
- Modify: `backend/agent/coordinator.py` — `handle_records_ingested` (signature + tail), `build_worker_dependencies` (~:1184), `WorkerDependencies`, `handle_event` signature + records dispatch (:3926-3958)
- Test: `backend/tests/agent/test_handle_records_ingested.py` (new tests; follow the file's existing fixture style)

**Interfaces:**
- Consumes: Task 1 field, Task 2 config, Task 3 return.
- Produces: `handle_records_ingested(..., gnn_service: GnnService | None = None, explainability_service: ExplainabilityService | None = None, entity_metric_repository: EntityMetricRepository | None = None, gnn_cluster_store: ClusterSummaryStoreProtocol | None = None, object_store: ObjectStore | None = None, graph_metrics_throttle: MetricsRecomputeThrottle | None = None, analytics_trigger_throttle: MetricsRecomputeThrottle | None = None)`.

- [ ] **Step 1: Failing tests** (names; bodies follow the file's existing in-memory fixture pattern — real in-memory graph/risk/gnn services, no mocks of the subject):
  - `test_records_only_kb_produces_clusters_and_alerts_when_trigger_enabled` — toggle on: after `handle_records_ingested`, GNN cluster store has ≥1 summary for the KB AND an `AlertsCreatedEvent` was published with ≥1 alert (assert via the in-memory event bus). **This is the story's headline AC.**
  - `test_trigger_disabled_runs_no_analytics` — default config: no `AlertsCreatedEvent`, cluster store empty.
  - `test_trigger_caps_to_top_n_by_score` — `max_entities_per_batch=1`, two assessable entities with distinct scores: exactly the higher-scored entity id reaches the risk stage of Flow B (assert on the alert's `entity_id`).
  - `test_trigger_throttle_suppresses_second_batch` — same throttle instance, two consecutive calls: second call publishes no new `AlertsCreatedEvent`.
  - `test_trigger_failure_never_breaks_ingest` — `gnn_service` raising unexpectedly: `handle_records_ingested` still returns `len(records)` and an `analysis`-failure visibility event is published (mirror `_publish_analytics_fanout_failed` assertion style from the existing graph.updated dispatch tests).
- [ ] **Step 2: Verify FAIL**, then implement the tail of `handle_records_ingested` (after the `assess_entities` block; `scored` from Task 3):

```python
    trigger = records_config.analytics_trigger
    if (
        trigger.enabled
        and scored
        and event_bus is not None
        and gnn_service is not None
        and risk_service is not None
        and explainability_service is not None
        and (
            analytics_trigger_throttle is None
            or analytics_trigger_throttle.should_recompute(
                event.knowledge_base_id, now=datetime.now(tz=timezone.utc)
            )
        )
    ):
        ranked = sorted(scored, key=lambda r: r.overall_score, reverse=True)
        top_ids = [r.entity_id for r in ranked[: trigger.max_entities_per_batch]]
        marker = f"records:{event.feed_name}"
        fanout_event = GraphUpdatedEvent(
            correlation_id=event.correlation_id,
            documents=[
                GraphUpdatedDocumentReference(
                    knowledge_base_id=event.knowledge_base_id,
                    source_document_id=marker,
                    parsed_document_id=marker,
                    extraction_result_id=marker,
                    validation_report_id=marker,
                    upserted_entity_count=len(top_ids),
                    upserted_relationship_count=0,
                    upserted_entity_ids=top_ids,
                )
            ],
        )
        # In-process call, NOT a publish: publishing graph.updated would run
        # Flow A, which requires storage-key artifacts and would redundantly
        # re-embed entities this handler already indexed. Best-effort like the
        # document dispatch: an analytics failure must not make the retry/DLQ
        # wrapper replay the whole records ingest.
        try:
            handle_graph_updated_for_analytics(
                fanout_event,
                gnn_service=gnn_service,
                risk_service=risk_service,
                explainability_service=explainability_service,
                graph_service=graph_service,
                event_bus=event_bus,
                object_store=object_store,
                entity_metric_repository=entity_metric_repository,
                metrics_throttle=graph_metrics_throttle,
                gnn_cluster_store=gnn_cluster_store,
                is_cancelled=is_cancelled,
            )
        except Exception as exc:  # noqa: BLE001 - analytics must not re-run Flow 1
            logger.warning(
                "Records analytics fan-out raised; ingest already completed. error=%s",
                exc,
            )
            _publish_analytics_fanout_failed(
                event=fanout_event,
                event_bus=event_bus,
                object_store=object_store,
                error_message=str(exc),
            )
```

- [ ] **Step 3: Wiring** — `build_worker_dependencies` (~:1184): `records_analytics_throttle = MetricsRecomputeThrottle(min_interval_seconds=records_config.analytics_trigger.min_interval_seconds)`; add field to `WorkerDependencies`; thread through `handle_event` (new optional param `records_analytics_throttle: MetricsRecomputeThrottle | None = None`) and the records dispatch (:3936-3958): pass `gnn_service`, `explainability_service`, `entity_metric_repository`, `gnn_cluster_store`, `object_store`, `graph_metrics_throttle=metrics_throttle`, `analytics_trigger_throttle=records_analytics_throttle` — all already in `handle_event` scope. Find every `handle_event(` construction site (worker service loop, tests) and thread the new dep.
- [ ] **Step 4:** `cd backend && .venv/bin/pytest tests/agent -q` → green; `.venv/bin/pytest --cov -q` ≥85%.
- [ ] **Step 5: Commit** — `feat(agent): records ingest triggers Flow B analytics in-process — gated, throttled, top-N (analytics.34)`

### Task 5: Delete the demo trigger (tool, tests, wiring)

**Files:**
- Delete: `backend/tools/` (whole dir — contains only `__init__.py` + `demo_trigger_analytics.py`), `backend/tests/tools/` (whole dir)
- Modify: `Makefile:104-114` (drop `DEMO_ANALYTICS_TRIGGER_CMD` env + the explanatory comment; target body becomes plain `scripts/demo_cms.sh`), `scripts/demo_cms.sh` block 4.5 (~:185-216, the trigger exec) and its "analytics trigger" mentions in header comments, `backend/pyproject.toml` (`include`: remove `"tools"` and `"tests/tools"`; remove the `[[tool.pyright.executionEnvironments]] root = "tests/tools"` stanza + its comment block :193-208; `packages.find`: remove `"tools*"`)

- [ ] **Step 1:** Delete + edit per above. The repo-root `tools/` (export_openapi, sample_data) and its `tools/pyrightconfig.json` are a DIFFERENT package — do not touch.
- [ ] **Step 2:** `bash -n scripts/demo_cms.sh`; `cd backend && .venv/bin/pytest tests -q` green (deleted tests gone); bare `.venv/bin/pyright` clean; `ruff check --no-cache .` clean; `make -n demo-cms` shows plain `scripts/demo_cms.sh`.
- [ ] **Step 3: Commit** — `feat(demo): delete demo_trigger_analytics — records ingest now triggers analytics natively (analytics.34)`

### Task 6: Demo script hardening (standalone fixes)

**Files:**
- Modify: `scripts/demo_ingest_tn_subset.sh:6,9,23` (guard every curl inside `post_with_retry` so a transient failure feeds the retry loop instead of killing `set -e`: `resp=$(curl ... ) || resp=""` pattern, matching `demo_cms.sh`'s own probe guards)
- Modify: `scripts/demo_cms.sh:33` probe helper (attempt count: `attempts=$(( timeout / interval ))` → `attempts=$(( timeout / interval )); [ "$attempts" -lt 1 ] && attempts=1`)

- [ ] **Step 1:** Apply both; `bash -n` on both scripts.
- [ ] **Step 2:** Behavioral check of the retry guard without the stack: `DEMO_API_URL=http://localhost:1 bash scripts/demo_ingest_tn_subset.sh` must exhaust retries with an explicit error (not an instant silent `set -e` death). Verify exit message mentions retries.
- [ ] **Step 3: Commit** — `fix(demo): ingest curl survives transient failures; probe floor of one attempt`

### Task 7: e2e demo-walkthrough parity fixes

**Files:**
- Modify: `chili_app/e2e/demo-walkthrough.spec.ts`

**Changes (from the adjudicated review):**
- Add a reference-mode Dashboard test (Scene 2.1): navigate `/dashboard`, assert the KPI/stat region and at least one chart container render for the active KB.
- In the workbench test, open the **Policy** tab and assert ≥1 policy item row renders (deep-linked KB).
- Live-mode EVIDENCE test: select the target alert with the **same ordering the alert feed page uses** (severity/created ordering from the API response, not the spec's own re-sort) so attribution bars are asserted for an alert the UI would actually surface first.
- Align skip semantics with the discovery-comment: live tests 1 and 4 `test.skip()` (not hard-fail) when the discovered TN KB has no alerts.

- [ ] **Step 1:** Implement; `cd chili_app && npx tsc -b && npm run lint` clean.
- [ ] **Step 2:** Run reference mode against the running stack: `npm run test:e2e -- demo-walkthrough` → green (live mode auto-engages only when a TN KB with alerts exists; final live verification happens in Task 10).
- [ ] **Step 3: Commit** — `test(e2e): demo walkthrough covers Dashboard + Policy tab; live-mode selection + skip semantics fixed`

### Task 8: Docs, wiki, backlog reconciliation

**Files:**
- Modify: `docs/demo/README.md` (rewrite the trigger-disclosure block: trigger deleted, analytics fire natively via `records.analytics_trigger` config; "never runs docker compose itself" is now literally true — keep it; update alert-count expectations to Task 10 actuals), `docs/demo/presenter-script.md` (fourth pack display name → **"Graph growth watch"** exactly as configured; drop/correct the every-item-has-citation claim — the graph-growth-watch item has none; alert-count language matches Task 10 actuals), `docs/architecture.md` (§6.3 ~:772/:800 — records flow now includes the gated in-process Flow B fan-out; note no event is published), `backend/records/README.md` + `backend/analytics/README.md` (per story AC: analytics fire for records-ingested KBs; cross-ref config gate), `docs/wiki/modules/agent.md` + `docs/wiki/contracts/events.md` (remove "demo trigger as second graph.updated producer standing in for analytics.34"; document the in-process fan-out + inline `upserted_entity_ids`), `docs/wiki/CHANGELOG.md` (entry), `docs/backlog/analytics.md` (analytics.34 → `done` with delivered notes incl. the leading-edge-throttle tradeoff and cross-batch re-alert behavior), `docs/backlog/records.md` (records.12: note analytics fan-out shipped as direct call, re-scope its toggle to Flow 2/3 consumers; fix stale coordinator line citations ~:497), `docs/superpowers/specs/2026-07-16-sprint28-cms-fraud-workbench-design.md` (correction note at the ~:111 flow claim: records→GraphUpdated was a false premise, closed 2026-07-24 by analytics.34; fix the "CI runs make test-e2e" claim — no CI job runs e2e; local `make test-e2e` is the gate), `CLAUDE.md` + `.github/copilot-instructions.md` demo-cms lines if they mention the trigger.

- [ ] **Step 1:** Apply all; grep repo for `demo_trigger_analytics` and `DEMO_ANALYTICS_TRIGGER_CMD` → zero hits outside archives/plan docs.
- [ ] **Step 2:** `python3 docs/backlog/validate.py` (or the repo's validator entrypoint — see `docs/backlog/README.md`) → green.
- [ ] **Step 3: Commit** — `docs: analytics.34 done — natural records analytics; demo docs/wiki/backlog reconciled`

### Task 9: Full gate run

- [ ] Backend: `cd backend && .venv/bin/pytest --cov -q` (≥85%), bare `.venv/bin/pyright` clean, standalone `cd tools && ../backend/.venv/bin/pyright -p pyrightconfig.json` clean (repo root), `backend/.venv/bin/ruff check --no-cache .` clean.
- [ ] Contracts drift: re-run export + codegen; `git diff --exit-code chili_app/openapi.json chili_app/src/lib/api/schema.ts` → clean.
- [ ] Frontend: `cd chili_app && npm run lint && npm run test:run && npm run build` → clean.
- [ ] Commit any stragglers.

### Task 10: Live DoD — fresh-stack demo with NO explicit trigger

- [ ] `make clean && make dev` (wait healthy) — destroys the two duplicate TN Demo KBs and the 2 DLQ poison records along with all volumes.
- [ ] `make demo-cms` → RC=0, all five probes PASS **with no trigger step in the log**.
- [ ] Verify natural closure: `redis-cli XLEN chili.embeddings.complete.dlq` → **0** (stream absent or empty); alerts total ≥1 sourced from the fan-out; record actual alert/cluster/policy counts.
- [ ] `cd chili_app && npm run test:e2e -- demo-walkthrough` → live mode engages against the fresh KB, green.
- [ ] Update `docs/demo/README.md` / `presenter-script.md` numbers to the observed actuals (Task 8 left placeholders only if counts shifted).
- [ ] Full `make test` (backend, against chili_test) + full Playwright suite → green.
- [ ] Commit — `docs(demo): DoD numbers from natural-trigger fresh run (analytics.34)`
