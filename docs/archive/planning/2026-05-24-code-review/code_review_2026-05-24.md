# Code Review Action Plan — 2026-05-24

> Scope: full-codebase snapshot review across 5 module groups (core orchestration, data ingestion, knowledge & retrieval, analytics & monitoring, frontend).
> Verification status: each Critical below has been read against the cited file:line. Findings labelled **CONFIRMED**, **PARTIAL** (real but severity is narrower than the reviewer reported), or **DOWNGRADED** (test-only / overstated).
> Packaging: one commit per theme (themes match the section headings); themes are independently shippable.

## Cross-cutting summary

| # | Theme | Status | Files touched (rough count) |
|---|---|---|---|
| 1 | Fix architectural cross-module imports | All findings verified | 2 source files + new `shared/` types |
| 2 | Drive analytics behavior from DomainConfig | Tracked from prior wave | `api/routers/analytics.py`, `api/dependencies.py`, schemas |
| 3 | Frontend domain-reconfigurability + duplicate code | All findings verified | 4 frontend files |
| 4 | Harden LLM fallback chain | All findings verified | `llm/adapters/ollama_adapter.py` (+ optional fallback widen) |
| 5 | Fix data-integrity blockers | 3 confirmed, 1 partial (DLQ) | Neo4j adapter, monitoring service, gnn service, coordinator |
| 6 | Important follow-ups (lower severity) | Tracked for the next wave | scattered |

Two findings were verified to be **not Criticals** in their reviewer-reported form (Postgres `count_for_kb` and a misread comprehension scope); they are tracked in § Findings adjusted after verification.

---

## Theme 1 — Fix architectural cross-module imports

**Commit hint:** `fix(arch): remove cross-module imports forbidden by CLAUDE.md`

CLAUDE.md Hard Rule 1: cross-module interaction is restricted to FastAPI gateway, agent coordinator (via Redis), and `shared/`. A repo-wide grep confirms exactly two violations exist today.

### 1.1 `agent/coordinator.py:116` imports `KnowledgeBaseRepository` from `api/`  — **CONFIRMED**

```
backend/agent/coordinator.py:116: from api._kb_store import KnowledgeBaseRepository
```

The worker is depending on a type defined inside the gateway. `KnowledgeBaseRepository` is a Protocol; its in-memory and object-store implementations live in `api/_kb_store.py`. Both layers need it.

**Fix:** Move the `KnowledgeBaseRepository` Protocol and its `InMemoryKnowledgeBaseRepository` / `ObjectStoreKnowledgeBaseRepository` implementations into a new `backend/knowledgebases/` module (with the standard `protocols.py` + `adapters/` layout) — or into `shared/` if the contract is pure interface. `api/` and `agent/` both depend on that new module.

**Acceptance criteria:**
- `grep -rn "from api\." backend/agent/ backend/records/ backend/ingestion/ backend/monitoring/ backend/rag/ backend/graph/ backend/llm/ backend/embeddings/ backend/vectorstore/ backend/analytics/` returns no matches in production code.
- `pyright --strict` and `pytest --cov` remain green.
- `api/routers/knowledgebases.py` and `agent/coordinator.py` both import from the new shared module.

### 1.2 `records/mappers/feed_mapper.py:14` imports `MonitoringObservation` from `monitoring/` — **CONFIRMED**

```
backend/records/mappers/feed_mapper.py:14: from monitoring.models import MonitoringObservation
```

`records/` (data ingestion) directly imports a type defined in `monitoring/` (alerting), making the two modules' release cycles share a hard dependency.

**Fix (preferred):** Move `MonitoringObservation` to `shared/types.py` (it's a generic scored-observation tuple — `entity_id`, `entity_type`, `metric_name`, `score`, `observed_at`, `rationale` — and has no business logic).
**Fix (alternative):** Have `map_observations` return a plain dict payload and let `monitoring/` deserialize it on the event bus.

**Acceptance criteria:**
- `grep -rn "from monitoring" backend/records/ backend/ingestion/ backend/rag/ backend/graph/` returns no matches in production code.
- Existing monitoring + records tests stay green.

---

## Theme 2 — Drive analytics behavior from DomainConfig

**Commit hint:** `fix(analytics): wire risk/timeseries/gnn services through DomainConfig`

This theme partially overlaps with the existing `docs/planning/p3_watch_items_2026-05-12.md` § "Analytics dual-path" item — see that doc for related context before starting.

### 2.1 Analytics router serves Medicare-flavored stubs from `@lru_cache` singletons — **CONFIRMED**

```
backend/api/routers/analytics.py:40-91   # @lru_cache _stub_* factories
backend/api/routers/analytics.py:98-119  # get_*_service() return stubs
```

`/analytics/risk-scores`, `/analytics/timeseries`, `/analytics/gnn/clusters` are wired to `_stub_risk_signal_source()` / `_stub_timeseries_history_source()` / `_stub_graph_snapshot_source()` with hardcoded `kb-demo` / `provider` / `claim` data. The docstring at line 109-114 acknowledges tests override the GNN dep — but in production, the live router still returns Medicare-shaped fixture data.

**Fix:** Add `get_risk_service` / `get_timeseries_service` / `get_gnn_service` to `api/dependencies.py` following the same pattern as `get_graph_service` and `get_monitoring_service`. Build them from `DomainConfig` adapters at startup. Remove the `_stub_*` lru_cached factories from the router; relocate the fixture data into the analytics test conftest if anything still needs it.

**Acceptance criteria:**
- `backend/api/routers/analytics.py` contains no `_stub_*` factories and no literal `kb-demo`/`provider`/`claim` strings.
- The three router endpoints resolve their service from `DomainConfig` via `api/dependencies.py`.
- New tests verify the router returns empty results when no analytics data has been written for the active domain.

### 2.2 Risk + monitoring thresholds hardcoded in service models — **CONFIRMED (Important, bundled here)**

```
backend/monitoring/service_models.py:16-17     # medium=0.6, high=0.85
backend/analytics/risk/service_models.py:18-19 # medium=0.5, high=0.8
```

Pydantic field defaults bypass `DomainConfig`. CLAUDE.md Hard Rule 4 requires config-driven thresholds.

**Fix:** Read thresholds in the factory functions (`create_monitoring_service`, `create_risk_service`) from `DomainConfig` and inject them into the request construction. Keep Pydantic defaults as a final fallback only when no config is loaded.

**Acceptance criteria:**
- `DomainConfig` schema includes (or already includes) per-domain threshold fields; loader populates them.
- Factories pass config-derived thresholds to request construction.
- Tests cover threshold-from-config and threshold-fallback paths.

---

## Theme 3 — Frontend domain-reconfigurability + duplicate code

**Commit hint:** `fix(frontend): remove hardcoded domain values and consolidate alerts hook`

### 3.1 `DashboardPage.tsx:28-32` hardcodes Medicare/Medicaid filter labels — **CONFIRMED**

```
chili_app/src/pages/DashboardPage.tsx:28-32
const dashboardFilters = [
  { id: 'all', label: 'All Programs' },
  { id: 'medicare', label: 'Medicare FFS' },
  { id: 'medicaid', label: 'Medicaid' },
]
```

Direct violation of "Adding a domain should not require frontend code changes." Compounded by the fact that `activeFilterId` is set into `<FilterBar>` but **never applied to any query or data array** — the filter is also functionally inert.

**Fix:** Either (a) drive the filter list from a new optional `DomainConfig.ui.dashboard.filters` field and wire the value into the alerts query, or (b) remove the filter entirely until there's a use case. Option (b) is YAGNI-correct since the filter doesn't filter anything today.

**Acceptance criteria:**
- No literal `Medicare`/`Medicaid` strings in `chili_app/src/`.
- If the filter survives, it actually filters the alerts list; if it's removed, the dashboard layout regression-tests cleanly.

### 3.2 Duplicate `useAlerts` hooks with conflicting endpoints — **CONFIRMED (with nuance)**

```
chili_app/src/hooks/useAlerts.ts:64         (requires filters arg, query key includes filters)
chili_app/src/api/alerts.ts:24              (no args, query key = ['alerts'])
```

Both hooks key off `['alerts']` (the api/ version as bare key; the hooks/ version as `['alerts', {...filters}]`). TypeScript's required `filters` arg in `hooks/useAlerts.ts` prevents accidental confusion at call sites today — but `useAcknowledgeAlerts` (hooks) calls `POST /alerts/:id/acknowledge` while `useDismissAlerts` (hooks) calls `POST /alerts/:id/resolve`, and `useAcknowledgeAlert` (api) calls `POST /alerts/:id/acknowledge`. Two sources of truth for the same surface.

**Fix:** Pick one. The `api/alerts.ts` style matches the rest of the new contract layer (`api/contracts.ts`); the `hooks/` directory and `types/api.ts` are leftover from an earlier shape. Delete `src/hooks/useAlerts.ts`, migrate any consumer of `types/api.ts::Alert` to `api/contracts.ts::AlertListItem`, then delete `types/api.ts`.

**Acceptance criteria:**
- One canonical `useAlerts`/`useAcknowledgeAlert` per concern.
- `src/types/api.ts` deleted (or shrunk to types not duplicated in `api/contracts.ts`).
- `npm run lint` and `npm run test:run` green.

### 3.3 `validateIngestion.ts:210` `Date.parse` fallback contradicts the lock-step comment — **CONFIRMED**

```
chili_app/src/lib/ingestion/validateIngestion.ts:175-177  // comment: "Kept in lock-step here..."
chili_app/src/lib/ingestion/validateIngestion.ts:210      return !Number.isNaN(Date.parse(text))
```

Backend `_coerce_value` (records/validation.py) accepts only `YYYY-MM-DD`, `YYYYMMDD`, and `MM/DD/YYYY` — no `Date.parse` fallback. The client validator accepts strings like `"2024"`, `"Jan 1"`, locale-dependent forms that the server will reject, producing confusing UX where the client passes a value the server then rejects.

**Fix:** Remove the `Date.parse` fallback at line 210. Also remove the fallback in the non-string branch at line 196 — same rationale.

**Acceptance criteria:**
- Vitest test confirming `isValidDateValue("2024") === false`, `isValidDateValue("Jan 1") === false`, `isValidDateValue("2024-01-15") === true`.
- E2E test that uploads a record with a date format the server rejects passes the existing assertion that the client also rejects it.

### 3.4 `TopBar.tsx:31-35` inert global search input — **CONFIRMED**

```
chili_app/src/components/layout/TopBar.tsx:31-35
<input placeholder="Entity, case, or document ID" type="search" />
```

No `onChange`, no state, no query. Visible on every authenticated page; users will type and get nothing.

**Fix:** Two options.
- **YAGNI:** Remove the search input until it has a target.
- **Wire it:** On Enter, navigate to `/investigation?q=<term>` and let the existing investigation entity search handle it.

Pair with a cleanup of the leftover scaffold text `<div className="app-topbar__eyebrow">Production UI foundation</div>` at line 27 — replace with the active role/domain context or remove.

**Acceptance criteria:**
- Either the input is removed from the DOM or it dispatches a real query on Enter.
- Playwright e2e of `TopBar` covers the chosen path.

---

## Theme 4 — Harden LLM fallback chain

**Commit hint:** `fix(llm): ensure adapter errors stay inside the fallback chain`

### 4.1 Ollama `response.json()` can throw outside the fallback's catch — **CONFIRMED**

```
backend/llm/adapters/ollama_adapter.py:54   body = response.json()   # not in try/except
backend/llm/adapters/fallback.py:37         except LlmProviderError as exc:
```

If Ollama returns a 2xx with malformed JSON (it can — e.g., a streamed-by-mistake response), `httpx.Response.json()` raises `json.JSONDecodeError`. `FallbackLlmClient.generate` only catches `LlmProviderError`, so the decode error escapes and breaks the fallback chain entirely.

**Fix:** Wrap `response.json()` in `try/except` and raise `LlmProviderError` with the response body prefix. Same audit should be applied to other adapters' JSON paths (`openai_adapter.py`, `anthropic_adapter.py` — likely safe because they use the provider SDK, but worth confirming).

**Optional broaden:** Change `FallbackLlmClient.generate`'s `except LlmProviderError` to `except Exception` and re-raise after wrapping as `LlmProviderError`. This is more defensive but loses error-class precision; defer unless we see another instance of this bug.

**Acceptance criteria:**
- `OllamaLlmClient.generate` raises `LlmProviderError` for both transport errors AND JSON decode errors.
- New unit test confirming a 200 + non-JSON body propagates as `LlmProviderError`.
- New integration test confirming a JSON-decode failure on the primary client causes the fallback client to be tried.

---

## Theme 5 — Fix data-integrity blockers

**Commit hint:** `fix(reliability): bound monitoring dedup, clamp GNN score, index graph search`

### 5.1 `MonitoringService._dedup_index` is an unbounded dict with no eviction — **CONFIRMED**

```
backend/monitoring/service.py:77    self._dedup_index: dict[tuple[str, str], datetime] = {}
backend/monitoring/service.py:152   self._dedup_index[key] = now    # only ever inserts/updates
```

No deletion path. Long-running worker accumulates one entry per unique `(entity_id, metric_name)` forever. Also lost on restart so duplicates can fire.

**Fix:** Either
- bound the dict with periodic eviction (drop entries older than `dedup_window_seconds`), invoked at the start of each `evaluate()`, or
- delegate dedup to the Postgres `alert_history` table (which is already written at the same time) and remove the in-memory index entirely.

The second option also fixes the restart-loses-state half of the bug.

**Acceptance criteria:**
- New test that runs `evaluate()` 1000 times with distinct keys and confirms `_dedup_index` size stays bounded (or that there is no in-memory index).
- New test confirming dedup persists across `MonitoringService` instance recreation (if delegating to Postgres).

### 5.2 GNN `_score_nodes` returns an unbounded score consumed as if 0–1 — **CONFIRMED**

```
backend/analytics/gnn/service.py:195   score=_feature_magnitude(...) + weights_by_node.get(...)
backend/analytics/gnn/models.py:51     score: float = Field(ge=0.0)   # no upper bound
backend/analytics/gnn/models.py:89     anomaly_score: float = Field(ge=0.0, le=1.0)   # contrast
```

`ScoredNode.score` is passed through to `GnnNodeScore` (service.py:109, 268) and into the API response. Nearby fields use `le=1.0` so callers will reasonably assume this one does too.

**Fix:** Inside `_score_nodes`, compute the max raw score across all nodes and divide each entry by that max (or apply `tanh`/sigmoid). Add `le=1.0` to `ScoredNode.score`. Document the normalization.

**Acceptance criteria:**
- New test confirming `_score_nodes` output is bounded `[0.0, 1.0]` for arbitrary graphs.
- `ScoredNode.score` has `Field(ge=0.0, le=1.0)`.

### 5.3 Neo4j `search_entities` runs unindexed `CONTAINS` over `properties_json` — **CONFIRMED**

```
backend/graph/adapters/neo4j_adapter.py:418-431
WHERE entity.knowledge_base_id IN $knowledge_base_ids
  AND toLower(coalesce(entity.properties_json, "")) CONTAINS $normalized_query
```

`properties_json` is a serialized string; no Neo4j fulltext index is created in `_ensure_schema`. This is a sequential scan over every entity in the KB.

**Fix:** Two viable approaches.
- Add a Neo4j fulltext index on `properties_json` and rewrite the query to use `db.index.fulltext.queryNodes`. Update `_ensure_schema` accordingly.
- Promote `name`/`label` from `properties_json` into a top-level node property at upsert time and add a regular index on it. The TODO in `delete_by_source_document` already references this pattern.

**Acceptance criteria:**
- `_ensure_schema` creates the new index.
- `search_entities` no longer does a full-label scan in `EXPLAIN` output.
- Integration test confirms search results match the prior implementation for small KBs.

### 5.4 DLQ-failure path may leave ACK semantics broken — **PARTIAL (needs deeper read)**

```
backend/agent/coordinator.py:2510   ackable.append(delivery)   # unconditional
backend/agent/coordinator.py:2513-14 event_bus.ack(ackable)
```

The reviewer claimed that if `publish_to_dlq` throws inside `run_handler_with_retry`, the delivery still gets ACKed and the message is permanently lost. This is true **only** if `run_handler_with_retry` swallows DLQ-publish errors. I didn't read the body of that helper during verification; the claim is plausible but unverified.

**Action:** Before fixing, read `run_handler_with_retry` (same file, earlier in coordinator.py) and confirm whether DLQ-publish errors are re-raised. Three outcomes:
- If re-raised: `ackable.append` is reached only on success/DLQ-routed-success. No fix needed; close as not a bug. Add a comment documenting the contract.
- If swallowed: wrap the `processed +=` line and the `ackable.append` in a try/except that does not ACK on DLQ failure, and add a test that simulates DLQ publish failure.
- If ambiguous: refactor `run_handler_with_retry` to return a tri-state (success / DLQ-routed / DLQ-publish-failed) and gate the ACK on that.

**Acceptance criteria:**
- A docstring or test makes the DLQ-failure ACK contract explicit and verifiable.

---

## Theme 6 — Important follow-ups (next wave, not blocking)

Listed for the next plan cycle. Each is a one- or two-commit fix on its own.

- **`backend/database/engine.py:68`** — `conn.execute(f"SET statement_timeout = {statement_timeout_ms}")` uses f-string interpolation. `statement_timeout_ms` is Pydantic-typed `int`, so the practical risk is low, but the pattern is unsafe. Replace with `conn.execute("SET statement_timeout = %s", (int(statement_timeout_ms),))` or `f"SET statement_timeout = {int(statement_timeout_ms)}"` with the explicit cast.
- **`backend/database/migrations/versions/0001_persistence_baseline.py:154-160`** — Alembic downgrade uses plain `DROP TABLE` on TimescaleDB hypertables; will fail on real instances. Switch to `DROP TABLE IF EXISTS … CASCADE`.
- **`backend/events/adapters/redis_streams.py:99`** — TODO for `XPENDING`/`XCLAIM` recovery is real and the pipeline depends on it for crash-safety.
- **`backend/analytics/timeseries/service.py:421`** — population-vs-sample stdev in `_standard_deviation`. Switch divisor to `max(1, n-1)`.
- **GNN sub-package test coverage gap** — `list_clusters`, `_compute_embeddings`, `_detect_communities` are untested per the reviewer. Confirm via `pytest --cov=backend/analytics/gnn` and fill gaps before this module ships.
- **`backend/llm/adapters/openai_adapter.py:128` + `anthropic_adapter.py:130`** — retry backoff has no jitter, thundering-herd risk under sustained rate-limiting.
- **`backend/llm/models.py:60`** — `GenerationRequest.max_tokens` default 256 vs `LlmConfig.max_tokens` default 4096. Mismatch can silently truncate when callers don't override. Align defaults.
- **`backend/api/dependencies.py:299+`** — multiple stateful service factories are `@lru_cache`'d, creating process-global singletons. Audit which need request-scoping when Neo4j/Qdrant are live.
- **`backend/graph/adapters/neo4j_adapter.py:512-524`** — `delete_by_source_document` count-then-delete pattern uses four separate sessions; wrap in a single transaction or use a single Cypher with `DELETE r RETURN count(r)`.
- **`backend/records/validation.py:140`** — `coerced_rows.append(coerced)` happens before entity validation; the resulting invariant survives only because of the raise-on-any-error flow. Tighten to append only on `not row_errors`.
- **`backend/records/adapters/sources/file_source.py:39-44`** — `CsvFileSource` pre-filters empty strings; duplicates `required`-aware logic that lives in `coerce_row`. Drop the pre-filter; let `coerce_row` decide.
- **`chili_app/src/components/layout/AppShell.tsx:47`** — RBAC route guard evaluates `routeAllowed` while config queries are still loading; can flash restricted content. Show a loading state instead.
- **`chili_app/src/api/alerts.ts:13`** — `getAlerts()` is unpaginated. Add a `limit` default (25) for dashboard usage.

---

## Findings adjusted after verification

These reviewer claims were re-verified and changed in severity:

- **`PostgresRawRecordStore` missing `count_for_kb`** — originally flagged Critical with the claim "production code calls it." Verified: `count_for_kb` is referenced **only** from tests (`tests/api/test_kb_delete_cascade.py`, `tests/e2e/test_full_pipeline.py`); no production caller exists, the `RawRecordStore` Protocol does not declare it, and the tests instantiate `InMemoryRawRecordStore` concretely. **Downgrade to Minor / docs cleanup:** either add `count_for_kb` to the Protocol + Postgres adapter to keep parity, or rename the helper on the in-memory adapter to make its test-only nature obvious. Not a blocker.
- **`MonitoringService.evaluate` comprehension variable scoping** — the originating reviewer flagged then retracted this in their own report. Mentioned only so the retraction stays visible in the plan.

---

## Suggested execution order

1. **Theme 1** (architecture): smallest scope, highest priority, unblocks future work.
2. **Theme 4** (LLM fallback): tiny diff, prevents silent failure of a real production path.
3. **Theme 5.1, 5.2, 5.3** (data integrity): high-impact, narrow scope each.
4. **Theme 5.4** (DLQ): only after the read-confirms-or-refutes step above.
5. **Theme 3** (frontend): can run in parallel with backend themes if multiple agents.
6. **Theme 2** (analytics + thresholds): largest scope; touches dependency wiring; depends on Theme 1 finishing (`shared/` may grow).
7. **Theme 6**: schedule into the next planning cycle (`docs/planning/`).

## Cross-references

- `docs/planning/p3_watch_items_2026-05-12.md` — § "Analytics dual-path" is directly related to Theme 2.
- `CLAUDE.md` § "Architecture: Hard Rules" — the standard Themes 1, 2, and 3.1 are measured against.
- `docs/architecture.md` — should be updated after Theme 1 to reflect the new module location for `KnowledgeBaseRepository`/`MonitoringObservation`.
