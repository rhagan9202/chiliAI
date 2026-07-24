# Wiki CHANGELOG

---

## 2026-07-24 — Sprint 2026-28 D1 scripted demo closeout

### Changes

**Code files read:** `git log`/`git diff 2865ce7..HEAD` (14 commits on `feat/sprint-2026-28-d1-demo`, BL-051 scripted CMS demo); `backend/config/defaults/medicare_fraud_cms_desynpuf.yaml` (the `policy_rules` diff), `backend/config/schema.py` (`PolicyRulePack`/`PolicyRule`/`PolicyPredicate`/`PolicyPredicateValue`/`PolicyCitationRef`, and the full `DomainConfig` field list — confirming `policy_rules`/`gnn`/`peer_stats`/`timeseries`/`scorecards`/`default_reference_kb_id` all already exist there), `backend/tests/config/test_policy_rules_demo.py`, `backend/tools/demo_trigger_analytics.py` + `backend/tools/__init__.py`, `backend/agent/coordinator.py` (confirmed `_select_upserted_entities` exists), `backend/pyproject.toml` + `tools/pyrightconfig.json` + `tools/__init__.py` + `.github/workflows/ci.yml` (the pyright package-name-collision split), `chili_app/src/pages/KnowledgeBaseManagerPage.tsx` + its test file (`?kb=` deep-link + fallback), `chili_app/e2e/demo-walkthrough.spec.ts`, `backend/events/types.py` (`GraphUpdatedDocumentReference`). Also checked `backend/tests/conftest.py`: its `_ensure_migrated_test_database` autouse fixture predates this branch (commit `f843973`, 2026-07-16) and is not part of `2865ce7..HEAD` — the task brief's summary was wrong on this point; no wiki change attributed to it here.

**Wiki pages updated:**

| Page | Gap closed |
|------|-----------|
| `contracts/domain-config.md` | Added the previously-undocumented `policy_rules: list[PolicyRulePack]` field to the top-level `DomainConfig` block, plus a new `PolicyRulePack`/`PolicyRule`/`PolicyPredicate`/`PolicyPredicateValue`/`PolicyCitationRef` sub-model section (this page carried zero policy-rule schema coverage before this pass, despite the field predating D1). Documented the CMS pack's two new demo-tuned rule packs — `outlier_billing_concentration` (`risk_score gte 0.35`, `high`) and `referral_ring_exposure` (`properties.active_alert_count gte 2`, `critical`) — alongside the two pre-existing ones, carrying forward the YAML's own "DEMO-tuned, raise for production" caveat. Flagged, but did not fix, that `gnn`/`peer_stats`/`timeseries`/`scorecards`/`default_reference_kb_id` are also missing from the top-level field list — confirmed present in `schema.py`, pre-existing gaps unrelated to D1, out of this pass's scope. Bumped verified date to 2026-07-24. |
| `modules/agent.md` | Added a gap note under `handle_records_ingested` naming the `analytics.34` gap this branch's demo trigger works around (a natural records ingest computes derived risk signals but never publishes `graph.updated`, so Flow B — GNN → risk → explainability → `alerts.created` — never runs off it) and how `backend/tools/demo_trigger_analytics.py` stands in: selects top-N risk-ranked entities via the real `GET /analytics/risk-scores`, stages synthetic `GraphUpsertResult`/`ValidationReport` artifacts satisfying the BL-017 `_select_upserted_entities` guard, then publishes a real `graph.updated` event onto the worker's own event bus. Added a Tests-section note that `backend/tests/tools/` covers this CLI separately from `tests/agent/`, plus the pyright-split rationale (the repo-root `tools/` package and `backend/tools/` share the bare name `tools`; pyright resolves a dotted module name once per Program, so `backend/pyproject.toml` now typechecks `tools*` at `.` only, `tests/tools` needs its own `executionEnvironments` entry ahead of the broader `tests` one, and the repo-root `tools/` package gets its own standalone `tools/pyrightconfig.json` + CI step instead). |
| `contracts/events.md` | Added a second-producer note to `GraphUpdatedEvent`: `backend/tools/demo_trigger_analytics.py` publishes it directly from outside the normal pipeline dispatch, for the same `analytics.34` reason recorded in `modules/agent.md`. |
| `modules/frontend.md` | `KnowledgeBaseManagerPage.tsx` row: documented the new `?kb=` deep-link initial-selection behavior (falls back to the existing in-scope auto-select when the requested id isn't in the visible KB list), matching the convention already noted on `AlertFeedPage`/`PolicyIntelligencePage`/`InvestigationWorkbenchPage`. Bumped the e2e spec-file count 22 → 23 for the new `demo-walkthrough.spec.ts` (reference-mode dev-seed walkthrough plus live-mode TN-KB assertions that self-skip when no TN KB is discovered). |

**Pages checked, found already accurate, not changed:** `modules/config.md`, `modules/records.md`, `modules/monitoring.md`, `modules/analytics.md`, `contracts/api-routes.md`, `contracts/shared-types.md`, `flows/records-ingestion-flow.md`, `flows/query-flow.md` — this branch added no new API routes, event types, or Pydantic response/request shapes (confirmed via the diffstat: no changes under `backend/api/`, `backend/events/types.py` besides the demo CLI reusing existing `GraphUpdatedEvent`, or `backend/*/service_models.py`).

**Out of scope, deliberately not built this pass:** an entire `backend/policy/` module (the rule-evaluation engine — `evaluation.py`, `service.py`, `models.py`, `adapters/`, own `README.md`) has no `modules/policy.md` wiki page at all; this predates D1 (the module wasn't touched by `2865ce7..HEAD`) and building a first module page is a larger initiative than a demo closeout — flagged here so a future pass picks it up, not silently skipped. Repo-root `scripts/demo_cms.sh`, the `demo-cms` Makefile target, and `docs/demo/{README.md,presenter-script.md}` were read but not given wiki pages — they are demo orchestration/run-book content already owned by `backend/README.md`/`Makefile`/`docs/demo/` per this wiki's README "Relationship to Other Docs" table, not code contracts.

**Drift log:** No new architectural violations observed. The two new rule packs, the `?kb=` deep-link, and the pyright split are all additive/config/dev-tooling changes; `backend/tools/demo_trigger_analytics.py` reuses existing `GraphUpsertResult`/`ValidationReport`/`GraphUpdatedEvent` shapes rather than inventing new ones, and its own docstring explains why hardcoding `DEFAULT_ENTITY_TYPE = "provider"` there does not violate the "no hardcoded domain types" rule (it is a demo-scoped CLI, not `shared/types.py`) — read and agree with that reasoning. `docs/backlog/analytics.md`'s `analytics.34` story (already chartered before this branch per the tool's own docstring) is the tracked production fix for the gap this CLI works around.

## 2026-07-23 — Durable alert feed + analyst dashboard reconciliation (alerts.36, Task 5)

### Changes

**Code files read:** `backend/api/dependencies.py`, `backend/api/routers/alerts.py`, `backend/api/routers/events.py`, `backend/api/_analytics_overview.py`, `backend/api/_graph_entity_payload.py`, `backend/monitoring/adapters/protocols.py`, `backend/monitoring/adapters/postgres.py`, `backend/agent/coordinator.py`, `backend/knowledgebases/cleanup.py`, `backend/config/defaults/{medicare_fraud,medicare_fraud_cms_desynpuf,food_supply_chain}.yaml` — Tasks 1–4 of `feat/alerts-durable-read-model` (commits `0ce4ae2`..`53545af`): migration `0012` read-model columns, the promoted `AlertFeedStoreProtocol` (Postgres + in-memory), producers populating `entity_label`/`confidence`/`tags`, and the API serving `/alerts` (+ ack/SSE/cleanup/promote/overview/graph-detail) from `alert_history` with the projection blob (`api/_alert_store.py`, `AlertProjectionRepository`) retired. This pass (Task 5) closes the doc/backlog gap left open for the controller and adds the analyst-role dashboard config change.

**Config:** `backend/config/defaults/medicare_fraud_cms_desynpuf.yaml`, `food_supply_chain.yaml`, and `medicare_fraud.yaml` — `roles.analyst.pages` gains `dashboard` (landing page stays `alerts`); the durable alert feed makes dashboard metrics meaningful for analysts, not just supervisors. Housing pack and supervisor roles untouched (housing has no `dashboard` nav page). New parametrized test `test_analyst_role_includes_dashboard` (`backend/tests/config/test_loader.py`) pins this for the three edited packs; the frozen-history overlay snapshot fixture (`backend/tests/config/fixtures/medicare_fraud_dev_full_snapshot.yaml`) updated in step per that test's documented equivalence-pinning contract.

**Wiki pages updated:**

| Page | Gap closed |
|------|-----------|
| `modules/api.md` | Removed the retired `api/_alert_store.py` from the directory tree and the "In-process Read Models" table; added a note that the alert feed is not an in-process projection but a direct `alert_history` read through `AlertFeedStoreProtocol`. Route → Service Dispatch table's `alerts`/`events` rows and the `get_alert_repository` dependency signature updated to `AlertFeedStoreProtocol`/`get_alert_feed_store`. Bumped "Verified against codebase" to 2026-07-23. |
| `contracts/domain-config.md` | Removed the retired `CHILI_ALERT_REPOSITORY_BACKEND` env var row; added a note that alerts have no dedicated backend-selection env var — the store picks Postgres automatically from the connection provider, like `CaseRepository`. |

**`docs/architecture.md`:** removed `_alert_store.py` from the `api/` package tree (file deleted); the KB-delete operations table and the "Deleting a KB executes a full cascade…" paragraph both still said "alert read projection (API bundle only)" — corrected to describe the single `alert_history` step now shared by both bundles (alerts.36 retired the API-owned projection step). The Flow 4 / alert-persistence paragraph (Task 4) was already accurate — re-verified, no changes needed.

**`backend/README.md`:** removed the retired `CHILI_ALERT_REPOSITORY_BACKEND` env var row; replaced the stale "Alert Projection Notes" section with "Alert Feed Notes (alerts.36)" describing the durable `AlertFeedStoreProtocol` read model, the real `entity_label`/`confidence`/`tags` columns (with a pointer to the `analytics.36` follow-up for a true Flow B `entity_label`), durable acknowledge, and the shared KB-delete cascade step. Corrected the "Current State" paragraph and the `api/_alert_store.py` and `database/` bullets, which still described the projection as in-progress/API-owned.

**`docs/backlog/monitoring.md`:** closed story monitoring.02 ("Wire AlertProjectionRepository upserts on AlertsCreatedEvent") — `Status: done`, `Done: 2026-07-23 · alerts.36 · feat/alerts-durable-read-model` — with a "Current State (shipped)" deviation note explaining the actual fix (retire the projection, serve `/alerts` from `alert_history` directly) differs from the story's original AC shape (a second worker handler upserting a parallel projection), and updated Acceptance Criteria/Verification/Code touch points to match. This was the "empty alert feed in a fresh deployment" gap referenced by the alerts.36 plan.

**`docs/backlog/analytics.md`:** chartered new story analytics.36 ("True `entity_label` on Flow B (analytics-pipeline) alerts") — `Status: planned`, prerequisite `monitoring.02` — for widening `build_explanation_context`'s already-fetched focal entity into a real display label for `_run_explainability_stage`'s `AlertCreatedReference.entity_label` (currently falls back to `entity_id`), without an extra graph read. `MonitoringService.evaluate()`'s `entity_label=""` case is out of scope for this story (would need a new graph read).

**`docs/backlog/frontend.md`:** two corrections. (1) Frontend.27's "Config discovery (not a defect)" note recorded the analyst role excluding Dashboard on the CMS pack — now factually superseded by this pass's config change, annotated as historical and not to be re-flagged. (2) frontend.02's Current State gained a "Superseded" note: the U2-era observation that the workbench EVIDENCE tab renders `EmptyState` for real entities because the alert feed's backing store was blind in a fresh deployment no longer applies at the code level now that `GET /alerts` reads `alert_history` directly — live-verification against a real browser session is pending Task 6's live pass of `feat/alerts-durable-read-model`, not yet run. The story's remaining gap (no independent evidence-pack list/load-by-id entry point) is unchanged and still open.

**Backlog rollup:** `scripts/backlog_consistency.py` (no `--check`) regenerated `docs/backlog/README.md`'s status-rollup and ready-set sections and auto-added `analytics.36` to monitoring.02's `Unblocks` list; `--check` exits 0.

**Drift log:** No new architectural violations observed. This pass is documentation/config-only (plus the accompanying `test_analyst_role_includes_dashboard` test) — no production code touched beyond the three domain-pack YAMLs. Live full-stack verification of the durable alert feed (migration apply, Flow B alert visibility, Evidence-tab resolution, ack durability across an API restart, SSE count, KB-delete cascade, analyst Dashboard route) remains Task 6, reserved for the controller per the `alerts-durable-read-model` plan.

**Task 6 (controller live pass, ran 2026-07-23):** verified the durable alert feed end-to-end against a running stack. A synthetic Flow B (analytics-pipeline) alert landed in `alert_history` with `confidence=0.419` and kebab-cased factor tags; `GET /alerts` returned 7 analytics alerts for the TN KB, including backfilled B3-era rows; acknowledging an alert survived an API-container restart (durable `alert_history` write, no in-process state lost); the workbench Evidence tab rendered an AI NARRATIVE band plus 2 SHAP attribution rows for a real alert; the analyst role saw the Dashboard nav item on the `medicare_fraud_cms_desynpuf` pack, confirming the Task 5 config change. Full-suite gates: Playwright e2e 31 passed / 2 skipped, `make test` 2660 passed / 97% coverage, `pyright` (bare) 0 errors, `ruff check --no-cache .` clean, `backlog_consistency.py --check` exit 0, zero browser console errors, OpenAPI export zero-drift against the committed `chili_app/src/lib/api/schema.ts`. This closes out alerts.36's live-verification gap; no implementation defects were found — the follow-up items are the SQL-filter story chartered in `docs/backlog/monitoring.md` (`monitoring.21`, "Alert feed listing filters in SQL, not client-side") plus the pre-existing `analytics.36` true-`entity_label` story.

---

## 2026-07-23 — U2 whole-branch final review closeout: signals-tab gating fix + live-pass reconciliation (BL-050, Task 11)

### Changes

**Code files read:** `chili_app/src/pages/InvestigationWorkbenchPage.tsx`, `chili_app/src/pages/__tests__/InvestigationWorkbenchPage.test.tsx`, `chili_app/src/pages/AlertFeedPage.tsx`, `docs/backlog/frontend.md`, `docs/project/planning/backlog.md`, `docs/project/planning/sprints/2026-28.md`, `docs/wiki/modules/frontend.md` — code commit `dec68ef` on `feat/sprint-2026-28-u2-workbench-reshape` fixing the whole-branch final review's three Important findings plus three sanctioned minors, followed by this docs commit.

**Wiki pages updated:**

| Page | Gap closed |
|------|-----------|
| `modules/frontend.md` | Moved the "Since U2 (Sprint 2026-28)…" paragraph out of the middle of the Pages table — it previously sat between the `InvestigationWorkbenchPage` row and the remaining five rows, breaking the table into two disconnected fragments; it now sits directly below the complete table. Updated the paragraph itself to record the Signals-tab capability gate fix (present only when `risk_scoring` or `timeseries` is on, not unconditional) and the collapsed-strip-renders-the-surviving-panel-directly behavior, now regression-covered by a unit test. Corrected the `AttributionBars` consumer claim in the "Investigation dossier components" table — it is consumed only by `EvidencePackViewer`, not the dossier (the dossier's risk-factor band is `SignalBand`). |

**Drift log:** No new architectural violations observed. This closes out BL-050/frontend.27: Task 11 (controller live pass, ran 2026-07-23) verified the full stack — Playwright 31 passed/2 skipped incl. new tab-aware workbench + triage/narrative-band evidence assertions, browser pass on the TN KB (dossier/clusters/dashboard swatches), housing pack untouched with zero CMS strings, zero console errors — and surfaced one real implementation gap (the Signals tab was rendering unconditionally instead of gating per the plan's Global Constraints), fixed in the code commit alongside the two sanctioned minors (dossier-header remount `key`, dead `alert.tags ?? []` fallbacks). `docs/backlog/frontend.md` story frontend.27 flipped to `Status: done` with a `Done:` provenance line; `docs/project/planning/backlog.md` BL-050 row and `docs/project/planning/sprints/2026-28.md`'s U2 progress section both updated to reflect live-verified status and the final review verdict (READY to merge). Recorded a live-pass config discovery, not a defect: the `medicare_fraud_cms_desynpuf` pack's analyst role deliberately excludes the Dashboard page (`enabled_pages`) — the supervisor role owns it.

---

## 2026-07-23 — U2 workbench reshape: orphan-panel deletion + dossier component inventory (BL-050, Task 10 closeout)

### Changes

**Code files read:** `chili_app/src/pages/InvestigationWorkbenchPage.tsx`, `AlertFeedPage.tsx`, `DashboardPage.tsx`, `chili_app/src/components/investigation/*` (including the deleted `EntityDetailPanel.tsx`/`EvidencePanel.tsx`/`TimelinePanel.tsx`), `chili_app/src/components/charts/AttributionBars.tsx` — commits `500ebe0`..`f6f893d` on `feat/sprint-2026-28-u2-workbench-reshape` (Tasks 1–9), plus this pass's cleanup commit (`triageNumeralColor` extraction, orphaned `.investigation-layout` selector removal).

**Wiki pages updated:**

| Page | Gap closed |
|------|-----------|
| `modules/frontend.md` | Grepped for `EntityDetailPanel`/`EvidencePanel`/`TimelinePanel` (zero hits — this page never catalogued them, so no dangling reference existed to fix). Re-verified the Dashboard/Alert Feed/Investigation Workbench rows of the Pages table against the reshaped code: none of the three uses `appStore`/`uiStore` any more (KB id and entity id are URL-driven); added the new API calls the reshape introduced (`useGnnClusters`, `usePolicyItems`, `useInvestigationNeighborhood` on the Alert Feed evidence expansion). Added a new "Investigation dossier components" table listing the six components U2 added (`EntityDossierHeader`, `SignalBand`, `AnomalyTrendPanel`, `EntityPolicyPanel`, `ClusterMembershipPanel`, `AttributionBars`) and the three it deleted, with a note that the rest of the page's inventory (dated 2026-05-28) was not re-verified in this pass. Corrected the e2e spec-file count (17 → 22). |

**Drift log:** No new architectural violations observed. The reshape is frontend-only (no backend/contract changes); `EvidencePackResponse.attribution`/`narrative_sections` (added by B3, already documented in `contracts/api-routes.md`) are consumed as-is by the reshaped `EvidencePackViewer`, closing the "U2 (not yet built) is the first consumer" note left by the 2026-07-23 B3 entry below. `docs/backlog/frontend.md` gained the U2 implementation record (frontend.27, `in-progress` — browser/e2e verification pending Task 11, not claimed live-verified) plus three phase-2/dependency records (frontend.28: Timeline tab, peer-comparison bars, cluster-centrality ordering; frontend.29: dormant predicted-link rendering waiting on `analytics.24`'s write-back) and two stale-claim corrections (frontend.01's "GraphCanvas has zero imports" claim; frontend.02's AC referencing the now-deleted `EvidencePanel.tsx`, redirected to the live `EvidencePackViewer.tsx`).

---

## 2026-07-23 — B3 review follow-ups: blank-summary/section-less degrade + live-pass reconciliation

### Changes

**Code files read:** `backend/analytics/explainability/adapters/llm_narrative.py`, `backend/agent/service.py` — commits `8326488` (agent: adopt a workflow run created between find and save), `9e68277` (analytics: degrade section-less LLM narratives to the deterministic fallback) on `feat/sprint-2026-28-b3-explainability`, and `e8f1b30` (analytics: degrade blank-summary LLM narratives; guard request construction) on `fix/b3-review-followups`.

**Wiki pages updated:**

| Page | Gap closed |
|------|-----------|
| `modules/analytics.md` | Corrected the `LlmNarrativeGenerator` row: the 2026-07-23 Task 8 entry (below) staled once `9e68277`/`e8f1b30` landed — heading-less completions no longer parse as a summary-only narrative, and a completion opening directly with a heading (empty summary) now also degrades. Both malformed shapes degrade to `DeterministicNarrativeGenerator`, alongside `LlmError`, any unexpected exception (including `GenerateRequest` construction, now inside the never-raise guard), and an empty completion. |

**Drift log:** No new architectural violations observed. This entry corrects staleness introduced by the prior Task 8 pass below, which predated two late fix commits; `docs/backlog/analytics.md`, `docs/project/planning/backlog.md`, and `docs/project/planning/sprints/2026-28.md` were reconciled in the same pass (Task 9 live-pass + final-review status), and `docs/superpowers/specs/2026-07-23-sprint28-b3-explainability-design.md` §3.2/§4 gained dated amendment notes rather than silently rewriting the original design text.

---

## 2026-07-23 — B3 explainability: LLM narratives + SHAP attribution seams (BL-048, Task 8 reconciliation)

### Changes

**Code files read:** `backend/analytics/explainability/service.py`, `protocols.py`, `models.py`, `adapters/deterministic.py`, `adapters/llm_narrative.py`, `adapters/shap_attribution.py`, `adapters/shap_adapter.py`, `backend/shared/types.py`, `backend/api/contracts.py`, `backend/api/dependencies.py` (`_evidence_pack_to_response`) — commits `4366b1c`..`5194342` on `feat/sprint-2026-28-b3-explainability` (config fields, `EvidencePack`/`EvidencePackResponse` enrichment, narrative + attribution seams, worker wiring).

**Wiki pages updated:**

| Page | Gap closed |
|------|-----------|
| `modules/analytics.md` | Rewrote the `explainability/` section: added `NarrativeGeneratorProtocol`/`FeatureAttributorProtocol` to the protocol block, documented `ExplainabilityService`'s new `narrative_generator`/`feature_attributor` constructor keywords and composition, split the adapters table into context-source / narrative-generator / feature-attributor tables (deterministic + LLM generators, noop + SHAP attributors), and noted `adapters/shap_attribution.py::ShapRiskAttributor` is a distinct seam from the pre-existing, still-DI-unwired `adapters/shap_adapter.py::ShapExplainabilityContextSource`. Updated the module summary table row. Bumped section-level verified date to 2026-07-23. |
| `contracts/shared-types.md` | Added `FeatureAttribution` and `EvidenceNarrativeSection` type blocks; added their `attribution`/`narrative_sections` fields (both default `[]`) to `EvidencePack`. Bumped file-level verified date to 2026-07-23. |
| `contracts/api-routes.md` | Added `attribution`/`narrative_sections` fields plus `FeatureAttributionResponse`/`NarrativeSectionResponse` to the `EvidencePackResponse` block; noted the 1:1 mapper passthrough and legacy-pack `[]` default. Bumped file-level verified date to 2026-07-23. |

**Drift log:** No new architectural violations observed. `EvidencePack`/`EvidencePackResponse` enrichment is additive-with-default, so pre-B3 persisted object-store packs deserialize unchanged (confirmed by `tests/shared/test_types.py::TestEvidencePackEnrichment::test_defaults_empty_for_legacy_payloads`). Frontend contract regen (`chili_app/src/lib/api/schema.ts`) already carries both new response models — no additional frontend doc drift; U2 (not yet built) is the first consumer.

---

## 2026-07-19 — Risk detail route de-seeded from ApiState; Qdrant upsert chunking (Dev-Wiki-Curator)

### Changes

**Code files read:** `backend/api/dependencies.py`, `backend/api/state.py`, `backend/vectorstore/adapters/qdrant_adapter.py` (commits `42ef186` "fix(api): serve risk detail route from the DI risk service, not seeded ApiState (B2)" and `00f7fa8` "fix(vectorstore): chunk Qdrant upserts under the 32MB request limit (B2)")

**Wiki pages updated:**

| Page | Gap closed |
|------|-----------|
| `modules/analytics.md` | `GET /analytics/risk-scores/{entity_id}` no longer reads `ApiState`: documented `get_risk_score_payload(entity_id, kb_id, risk_service)` assessing via the DI `get_risk_service()` (same factory as the list route), the `RiskConfigurationError`/`RiskInsufficientSignalsError`/`ValueError` → `availability_status="unavailable"` mapping, infra-error propagation, and `_normalize_risk_level`'s move into `api/dependencies.py`. Replaced the "remaining static read-model gap" language — no analytics route reads `ApiState` anymore. Bumped verified date to 2026-07-19. |
| `modules/api.md` | Route → Service Dispatch table: `analytics` row no longer lists "remaining `ApiState` entity risk-score composition"; both risk-score routes now attributed to `RiskServiceProtocol` via DI. |
| `contracts/api-routes.md` | Updated analytics wiring-status paragraph, the `RiskScoreResponse` static-shape code block (added the `availability_status`/`unavailable_reason` fields that were already on the real Pydantic model but missing from the wiki), and the dependency-chain bullet for `/analytics/risk-scores/{entity_id}` to reflect DI `risk_service` instead of `state.get_risk_score(...)`. Bumped file-level verified date to 2026-07-19. |
| `modules/vectorstore.md` | Documented `QdrantVectorStore.upsert_records()` splitting point batches into `UPSERT_MAX_POINTS_PER_REQUEST = 1000`-point requests (order preserved) to stay under Qdrant's 32MB actix payload limit — large record feeds (47k CMS carrier claims → ~100k entity vectors) previously exceeded it in one request and DLQ'd `records.ingested` workflows. |

**Drift log:** No new architectural violations observed. `ApiState` now demonstrably owns only the RAG service handle, matching its updated module docstring in `backend/api/state.py`.

---

## 2026-05-28 — Pass 6: Docs/Wiki Cleanup Validation

### Changes

**Code files read:** `backend/ingestion/parsers/registry.py`, `backend/ingestion/parsers/html.py`, `backend/api/routers/analytics.py`, `backend/api/dependencies.py`, `backend/events/types.py`, `backend/events/codec.py`, `backend/api/routers/rag.py`, `backend/api/app.py`, `backend/api/middleware/metrics.py`, `backend/api/routers/events.py`, `backend/api/routers/ws.py`, `backend/api/routers/policy.py`, `backend/agent/adapters/protocols.py`, `backend/agent/adapters/redis_store.py`, `backend/agent/workflow_tracking.py`, `backend/monitoring/service.py`, `backend/monitoring/service_models.py`, `backend/config/schema.py`, `backend/knowledgebases/`, `chili_app/src/app/router.tsx`, `chili_app/src/app/providers.tsx`, `chili_app/src/api/contracts.ts`, `chili_app/src/api/analytics.ts`, `chili_app/src/api/realtime.ts`, `chili_app/src/stores/uiStore.ts`

**Wiki pages updated:**

| Page | Gap closed |
|------|-----------|
| `modules/knowledgebases.md` | Added dedicated module page for `backend/knowledgebases/`, including repository protocol, document metadata model, in-memory/object-store adapters, and test locations |
| `modules/api.md` | Removed retired `_kb_store.py` ownership, documented `knowledgebases/` repository dependency, refreshed metrics/realtime route notes, and updated DI service list |
| `modules/ingestion.md` | Corrected HTML parser status: `HtmlParser` is registered; remaining backlog is richer heading/link/table fidelity |
| `modules/analytics.md` | Replaced stale router-local stub factory description with current `api/dependencies.py` analytics service wiring and remaining `ApiState` read-model gap |
| `modules/agent.md` | Added `update_run_if_current`, stale workflow reconciliation, and corrected Redis workflow-store status |
| `modules/monitoring.md` | Corrected threshold source: request overrides or `MonitoringConfig` defaults, not `AlertsConfig.thresholds` |
| `modules/frontend.md` | Replaced obsolete frontend type-drift table with generated OpenAPI contract status and refreshed router/provider/API notes |
| `modules/events.md` and `contracts/events.md` | Added `VectorsDeletedEvent` / `vectors.deleted` to the registered event surfaces |
| `contracts/api-routes.md` | Corrected analytics route paths/query parameters, `/events`/`/ws` paths, `/metrics`, and current analytics wiring status |
| `contracts/domain-config.md` | Added current repository/event/workflow runtime environment variables |
| `README.md` | Added the new `modules/knowledgebases.md` page to wiki navigation |

---

## 2026-05-22 — Pass 5: Refresh 10 Backlog Pages (Dev-Wiki-Curator)

### Changes

**Code files read:** `backend/shared/provenance.py`, `backend/ingestion/extractor.py`, `backend/ingestion/validator.py`, `backend/ingestion/service_models.py`, `backend/graph/protocols.py`, `backend/graph/models.py`, `backend/vectorstore/protocols.py`, `backend/vectorstore/service_models.py`, `backend/records/adapters/protocols.py`, `backend/records/mappers/feed_mapper.py`, `backend/agent/coordinator.py`, `backend/agent/workflow_tracking.py`, `backend/llm/factory.py`, `backend/llm/adapters/ollama_adapter.py`, `backend/llm/adapters/fallback.py`, `backend/api/routers/knowledgebases.py`, `backend/api/_kb_busy.py`, `backend/config/schema.py`, `backend/config/defaults/medicare_fraud_cms_desynpuf.yaml`, `backend/shared/types.py`

**Wiki pages updated:**

| Page | Gap closed |
|------|-----------|
| `modules/shared.md` | Added `shared/provenance.py` section with all 6 key constants and 2 value constants; documented usage pattern in document and records paths |
| `modules/graph.md` | Added `delete_by_source_document` to `GraphServiceProtocol`; fixed `get_entity`/`search_entities` to use `list[str]` KB IDs; added `GraphDeleteByProvenance` model; bumped date |
| `modules/vectorstore.md` | Added full `VectorServiceProtocol` surface (batch_search, get_record, count, delete_record, delete_knowledge_base, delete_by_source_document); added `VectorDeleteResponse` model; fixed `VectorSearchRequest.knowledge_base_ids` (now list); bumped date |
| `modules/records.md` | Added `RawRecordStore` adapter protocol section with `delete_by_kb`; updated `map_batch` docstring to note provenance stamping; added provenance table; bumped date |
| `modules/ingestion.md` | Added full `PatternDocumentExtractor` and `LlmDocumentExtractor` class docs with constructors; added `create_document_extractor` factory; added provenance stamping section; updated `DocumentReceipt` with `replaced_document_id`; bumped date |
| `modules/agent.md` | Expanded coordinator section with `create_llm_client` factory usage and `"kb.delete"` subscription; documented `handle_records_ingested` (embed-and-index step) and new `handle_knowledge_base_deleted` handler with full signatures; expanded `WorkflowEventTracker` with `is_busy` method; bumped date |
| `contracts/api-routes.md` | Updated `DELETE /knowledgebases/{kb_id}` to document 207/409 semantics and per-step body; documented idempotent re-upload flow and `replaced_document_id`; documented busy/pending_cleanup 409 guard and `api/_kb_busy.py`; bumped date |
| `contracts/domain-config.md` | Updated `LlmConfig` with `provider="ollama"`, `base_url`, `fallback`; added `medicare_fraud_cms_desynpuf.yaml` feed inventory, natural_key table, and llm section example; bumped date |
| `flows/ingestion-flow.md` | Updated step 4 to document `LlmDocumentExtractor` alongside `PatternDocumentExtractor`; updated step 5 to document provenance stamping; added "Idempotent Re-upload" section; updated source files list; bumped date |
| `flows/records-ingestion-flow.md` | Updated mapping phase to show provenance metadata on entities/relationships; added optional embed-and-index step in worker handler; updated Key Differences table with new Embedding and Provenance rows; updated source files list; bumped date |

---

## 2026-05-22 — Pass 4: Ingestion Pipeline E2E Demo Merge (feature/ingestion-pipeline-e2e-demo)

### Changes

**Code changes merged:** 47 commits covering LLM extractor, Ollama adapter, FallbackLlmClient, KB delete 5-step cascade, document re-upload idempotency, `delete_by_source_document` on graph+vector, `delete_by_kb` on raw records, provenance constants, NPPES/DE-SynPUF feed configs, vector embed+index in `handle_records_ingested`, and Tennessee subset tooling.

**Wiki pages updated:**

| Page | Changes |
|------|---------|
| `modules/llm.md` | Added Ollama adapter row to adapters table; added `FallbackLlmClient` and `create_llm_client` factory sections; updated verification date |
| `contracts/events.md` | Added `cleanup_pending: bool = False` field to `KnowledgeBaseDeletedEvent`; updated verification date |
| `contracts/shared-types.md` | Added `natural_key: list[str] = []` field to `EntityDefinition` with usage note; updated verification date |

**Ledger created:** `docs/ledger/` — module map, protocol contracts, event catalog, HTTP routes, config schema, tooling inventory.

### Deferred wiki updates (for next pass)

The following wiki pages are now stale against the 2026-05-22 merge and should be updated in a dedicated wiki-curator pass:

- `modules/ingestion.md` — should document `LlmDocumentExtractor`, `create_document_extractor` dispatcher, natural-key dedup
- `modules/agent.md` — should document enhanced `handle_records_ingested` (embed+index step) and `handle_knowledge_base_deleted` retry handler
- `modules/graph.md` — should document `delete_by_source_document` on service + adapter protocols
- `modules/vectorstore.md` — should document `delete_by_source_document` on service + adapter protocols
- `modules/records.md` — should document `delete_by_kb` on `RawRecordStore` + the 9-feed DE-SynPUF/NPPES config
- `modules/shared.md` — should document `shared/provenance.py` constants
- `contracts/api-routes.md` — should document 207 partial-failure semantics on `DELETE /knowledgebases/{id}`, `replaced_document_id` on document upload, `pending_cleanup` 409 guard
- `contracts/domain-config.md` — should document `LlmConfig.fallback`, `LlmConfig.base_url`, `LlmConfig.provider="ollama"`, `EntityDefinition.natural_key`
- `flows/ingestion-flow.md` — should add LLM extractor path and provenance metadata section
- `flows/records-ingestion-flow.md` — should add embed+index step to the handler description

---

## 2026-05-20 — Pass 3: Flow Refresh, AlertGroup, Risk Models, API Contracts, Frontend Drift

### Changes

**Code files read:** `backend/api/contracts.py`, `backend/api/dependencies.py`, `backend/monitoring/models.py`, `backend/analytics/risk/models.py`, `backend/records/service.py`, `backend/records/service_models.py`, `backend/records/mappers/feed_mapper.py`, `backend/events/types.py`, `backend/rag/service_models.py`, `backend/shared/types.py`, `backend/vectorstore/service_models.py` (partial), `chili_app/src/types/api.ts`, `chili_app/src/api/contracts.ts` (partial)

**Wiki pages updated:**

| Page | Changes |
|------|---------|
| `modules/monitoring.md` | Added full "Internal Models" section documenting `MonitoringObservation`, `MonitoringBatch`, `AlertCandidate`, `SuppressionRule`, `AlertGroup`, `AlertHistoryRecord` from `monitoring/models.py`; clarified `AlertGroup` reference in `MonitoringEvaluationResponse` |
| `modules/analytics.md` | Added "Internal Models" sub-section under `risk/` documenting `RiskSignal`, `RiskProfile`, `RiskFactor`, `RiskAssessmentResult`, `RankedRiskEntry`, `RiskAssessmentRecord` from `analytics/risk/models.py`; cross-linked to event wire shape `RiskFactorReference`; added cross-link from "Current Wiring Status" to `contracts/api-routes.md` static payload shapes section |
| `contracts/api-routes.md` | Added "Static payload shapes (api/contracts.py)" subsection under Analytics documenting `AnalyticsOverviewResponse`, `RiskFactorResponse`, `RiskScoreResponse`, `EntityTimeseriesPointResponse`, `EntityTimeseriesResponse`; documented `api/dependencies.py` dependency chain for entity-scoped routes; noted `RiskFactorResponse` drops `raw_value`/`weight` vs internal `RiskFactor` |
| `modules/frontend.md` | Added "Frontend ↔ Backend Type Drift" table comparing `src/types/api.ts` vs `shared/types.py` + `api/contracts.py`; documents 8 drift cases (3 safe optional extensions, 2 wire mismatches: `AlertListResponse` shape, `EvidencePack` vs `EvidencePackResponse`) |
| `flows/ingestion-flow.md` | Added "Event Payload Reference" table with exact wire shapes for all 9 document-pipeline events; added "Structured Records Path" section documenting the parallel synchronous records ingest flow; updated source files list |
| `flows/query-flow.md` | Fixed `RagQueryResponse` field list (added `knowledge_base_id`, `graph_summary`); clarified `RagAnswer.content` mapping from `RagQueryResponse.answer`; fixed `RagCompletedEvent` wire shape (event_type literal + `RagCompletionReference` fields) |
| `README.md` | Added `flows/records-ingestion-flow.md` to the Flows navigation table |

**Wiki pages created:**

| Page | Purpose |
|------|---------|
| `flows/records-ingestion-flow.md` | Full step-by-step flow for structured records ingestion: API → `RecordsService.register_records()` → `RecordsIngestedEvent` → worker mapper (`map_batch`, `map_observations`) → graph upsert + monitoring |

### Drift discovered

1. **`AlertListResponse` shape mismatch** (`chili_app/src/types/api.ts` vs `backend/api/contracts.py`): Frontend expects `{ items: Alert[], total: number }`; backend returns `{ items: list[AlertListItem], page: PageInfo }`. Frontend `Alert` is also missing `entity_label`, `confidence`, `tags` fields that backend `AlertListItem` carries. Documented in `modules/frontend.md` drift table.

2. **`EvidencePack` wire mismatch** (`chili_app/src/types/api.ts` vs `backend/api/contracts.py::EvidencePackResponse`): Frontend `EvidencePack` uses `subgraph_nodes`/`subgraph_edges` (matching internal `shared/types.py`), but the API route `/evidence-packs/{id}` returns `EvidencePackResponse` which uses `subgraph_node_ids`/`subgraph_edge_ids`. Frontend will read `undefined` for those fields. Also missing `items: list[EvidenceItemResponse]` and `policy_citations`. Documented in `modules/frontend.md` drift table.

3. **`RiskFactorResponse` field reduction** (`api/contracts.py`): The frontend-facing `RiskFactorResponse` exposes only `factor_name`, `contribution`, `rationale` — dropping `raw_value` and `weight` from internal `RiskFactor`. This is intentional API-boundary narrowing, not a bug. Noted in `contracts/api-routes.md`.

4. **`RecordsIngestedEvent` missing from flow docs** (prior gap): The structured records path had no flow documentation. Now covered in new `flows/records-ingestion-flow.md`.

---

## 2026-05-20 — Pass 2: UNVERIFIED Resolution + Frontend Decomposition + Investigation Router

### Changes

**Code files read:** `backend/graph/service_models.py`, `backend/graph/models.py`, `backend/vectorstore/service_models.py`, `backend/llm/service_models.py`, `backend/monitoring/service_models.py`, `backend/agent/models.py`, `backend/agent/adapters/protocols.py`, `backend/analytics/timeseries/protocols.py`, `backend/analytics/timeseries/service_models.py`, `backend/analytics/gnn/protocols.py`, `backend/analytics/gnn/service_models.py`, `backend/analytics/risk/protocols.py`, `backend/analytics/risk/service_models.py`, `backend/analytics/explainability/protocols.py`, `backend/analytics/explainability/service_models.py`, `backend/analytics/metrics/models.py`, `backend/analytics/metrics/adapters/protocols.py`, `backend/api/routers/analytics.py`, `backend/api/routers/investigation.py`, `backend/records/mappers/feed_mapper.py`, `backend/shared/exceptions.py`, `backend/shared/alerts.py`, `backend/events/codec.py`, `backend/rag/service_models.py`, `chili_app/src/app/router.tsx`, `chili_app/src/stores/appStore.ts`, `chili_app/src/stores/chatStore.ts`, `chili_app/src/stores/ingestionStudioStore.ts`, `chili_app/src/stores/uiStore.ts`, `chili_app/src/api/client.ts`, `chili_app/src/api/contracts.ts`, `chili_app/src/api/investigation.ts`

**Wiki pages updated:**

| Page | Changes |
|------|---------|
| `modules/graph.md` | Replaced UNVERIFIED service_models and models blocks with exact Pydantic field signatures for `GraphBuildTask`, `GraphBuildReceipt`, `NeighborhoodRequest`, `EntityDetailResponse`, `NeighborhoodResponse`, `EntitySearchResponse`, `GraphMetricsResult`, `GraphUpsertResult`, `SubgraphResult`, `GraphMetrics` |
| `modules/vectorstore.md` | Replaced UNVERIFIED service_models block with exact fields for `VectorIndexSubmission`, `VectorIndexRequest`, `VectorIndexReceipt`, `VectorSearchRequest`, `VectorSearchMatch`, `VectorSearchResponse` |
| `modules/llm.md` | Replaced UNVERIFIED service_models block with exact fields for `ChatMessageInput`, `PromptTemplate`, `GenerateRequest`, `CompletionResponse` |
| `modules/monitoring.md` | Replaced UNVERIFIED service_models block with exact fields for `MonitoringEvaluationRequest`, `MonitoringEvaluationResponse`, `AlertListRequest`, `AlertListResponse`, `ResolutionRequest`, `AlertActionResponse` |
| `modules/agent.md` | Replaced UNVERIFIED workflow run state block with exact Pydantic models (`RetryPolicy`, `HealthSettings`, `WorkflowStepStatus`, `WorkflowRunStatus`, `TERMINAL_RUN_STATUSES`, `WorkflowStepState`, `WorkflowRun`, `WorkflowRunUpdate`) and exact `WorkflowRunStoreProtocol` with all 6 methods |
| `modules/analytics.md` | Replaced all 5 UNVERIFIED protocol blocks and all UNVERIFIED model blocks; added exact service model shapes for all 5 sub-modules; added "Current Wiring Status" section documenting `@lru_cache` stub routing pattern and production gap |
| `modules/rag.md` | Replaced UNVERIFIED service_models block with exact fields for `RagQueryRequest`, `RagCitation`, `RagQueryResponse`, `RagAnswer`, `RagStreamChunk` |
| `modules/shared.md` | Replaced UNVERIFIED exceptions block (only `ConfigurationError` exists); replaced UNVERIFIED alerts block with exact `AlertSeverity` type and `normalize_severity` signature |
| `modules/events.md` | Replaced UNVERIFIED codec block with exact `encode_event`/`decode_event` signatures and full `EVENT_TYPE_REGISTRY` key list |
| `modules/records.md` | Added new "Mappers" section documenting `map_batch()`, `map_observations()`, `MappedGraph`, entity/relationship ID format, deduplication semantics; expanded directory structure listing |
| `modules/frontend.md` | Expanded from single-table treatment to full decomposition: exact Zustand store interface shapes (all 4 stores), page inventory with API calls and stores per page, API client function/hook list per module, shared component inventory by category |
| `contracts/api-routes.md` | Replaced UNVERIFIED investigation block with full route table (3 routes), request/response shapes, and drift note on `total` field; updated analytics wiring note with cross-link |

**Wiki pages created:**

| Page | Purpose |
|------|---------|
| `CHANGELOG.md` | This file — dated change log of wiki updates |

### UNVERIFIED markers resolved: 33 of 33 (all markers cleared)

### Drift discovered

1. **`EntitySearchResponse.total` in investigation router** (`api/routers/investigation.py:87`): `total` is set to `len(items)` — it reflects the returned slice count, not the true total match count. This breaks pagination use-cases. Documented as drift note in `contracts/api-routes.md`.

2. **Duplicate `selectedEntityId` across `appStore` and `uiStore`**: Both Zustand stores track this field independently. Potential for stale-state divergence in components that read from different stores. Documented as drift note in `modules/frontend.md`.

3. **Analytics router stub wiring** (`api/routers/analytics.py`): `@lru_cache(maxsize=1)` stub factories hardcode `kb-demo` data. The real analytics services are not wired to the API layer. Now documented in `modules/analytics.md — Current Wiring Status` and cross-linked from `contracts/api-routes.md`.

4. **`WorkflowRunStoreProtocol` TODO** (`agent/adapters/protocols.py:24`): Code comment explicitly notes durable adapters (`PostgresWorkflowRunStore`, `RedisWorkflowRunStore`) are not yet implemented. Documented as drift note in `modules/agent.md`.

---

## 2026-05-20 — Pass 1: Initial Wiki Build

Created 25 files under `docs/wiki/`: 17 module pages, 4 contract pages, 3 flow pages, 1 index (README.md). All pages stamped "Verified against codebase: 2026-05-20" with 33 UNVERIFIED markers deferred to Pass 2.
