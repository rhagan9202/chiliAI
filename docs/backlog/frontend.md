# frontend backlog

> **Scope:** React 19 + Vite 8 analyst workbench SPA — pages, state, API client, realtime, accessibility, i18n, perf, tests.
> **Story format and rules:** see [design spec §5](../superpowers/specs/2026-05-24-complete-backlog-design.md#5-story-format).

---

## Story frontend.01: Mount `GraphCanvas` in the Investigation Workbench

**ID:** frontend.01
**Status:** planned
**Prerequisites:** [api.07, graph.05]
**Unblocks:** [_multitenancy.14, frontend.15]
**Estimated size:** L
**Spec:** docs/superpowers/specs/2026-05-21-kb-contextual-entry-points-design.md
**Status note (2026-07-23, U2 closeout sweep):** left `planned` rather than flipped to `done` — the AC below is substantively satisfied but by a change whose originating commit predates this sweep and isn't cleanly attributable (no `**Done:**` provenance can be written honestly); the one still-open gap (no dedicated `toSubgraphResult` unit test) is real. A future pass that adds that test and records real provenance can flip this to `done`.

**As a** fraud analyst,
**I need** the Investigation Workbench to render the entity neighborhood as an interactive force-directed graph instead of a flat list,
**so that** I can visually pivot through connected providers/beneficiaries/claims and spot ring structures at a glance.

### Current State
**Stale as of Sprint 2026-28 U2 (2026-07-23) — superseded by a different-shaped delivery, swept at U2 closeout (Task 10):** the flat `NeighborhoodList` fallback described below no longer exists. `chili_app/src/pages/InvestigationWorkbenchPage.tsx` imports and renders `GraphCanvas` directly (`GraphCanvas` import + JSX render in the NETWORK tab, U2's dossier restructure); the typed adapter this story called for is `chili_app/src/utils/subgraph.ts`'s `toSubgraphResult(entities, relationships): SubgraphResult`, shared by both the workbench and `AlertFeedPage`'s evidence expansion. Node click still navigates via `navigate(...)` to `/investigation/:entityId?kb=...&depth=...`. `chili_app/e2e/investigation-workbench.spec.ts` asserts `getByTestId('investigation-graph-canvas')` is visible against the real stack — this satisfies the story's e2e intent under a different spec/testid name than originally specified (no separate `investigation-graph-canvas.spec.ts` file, no `data-testid="graph-canvas"`).
- **Original (pre-U2) description, kept for history:** `chili_app/src/pages/InvestigationWorkbenchPage.tsx:262-273` rendered the neighborhood through a local `NeighborhoodList` helper — a flat `<div>` of `metric-row` entries. `chili_app/src/components/investigation/GraphCanvas.tsx:53-227` shipped a complete `react-force-graph-2d`-backed canvas with legend, zoom, hover, and node-click → entity navigation, but a repo-wide grep showed zero imports outside its own `__tests__` file.
- **Still open:** no dedicated unit test file exists for `toSubgraphResult` (`chili_app/src/utils/__tests__/subgraph.test.ts` is absent) — the adapter is only exercised indirectly through page-level tests. `GraphCanvas` itself has no `maxNodes`/decimation story yet (tracked separately as frontend.15).

### Acceptance Criteria
- [x] `InvestigationWorkbenchPage.tsx` imports `GraphCanvas` and renders it (NETWORK tab, since the U2 reshape — no separate "Graph neighborhood" card).
- [x] A typed adapter maps the neighborhood payload (`RuntimeEntity[]`/`RuntimeRelationship[]`) into the `SubgraphResult` shape `GraphCanvas` expects — delivered as the shared `toSubgraphResult` in `src/utils/subgraph.ts` rather than a per-component `NeighborhoodAdapter.ts`. **Gap:** no dedicated unit test file for it yet (see Current State).
- [x] Clicking a node updates the URL (`/investigation/:entityId?kb=...&depth=...`) via `navigate(...)`.
- [x] The flat `NeighborhoodList` fallback was removed outright (no "List view" toggle) — decision implicit in the U2 reshape, not separately documented in `chili_app/README.md` under this story's id.
- [x] Investigation Workbench tests assert the canvas mounts when neighborhood data is present (`chili_app/src/pages/__tests__/InvestigationWorkbenchPage.test.tsx`).
- [x] An e2e Playwright spec loads an investigation and asserts the canvas is in the DOM — delivered as `investigation-workbench.spec.ts`'s `investigation-graph-canvas` testid assertion, not a standalone `investigation-graph-canvas.spec.ts` file.

### Verification
- `cd chili_app && npm run lint && npm run test:run && npm run build`
- `cd chili_app && npm run test:e2e -- investigation-workbench` (the canvas assertion lives in this spec, not a dedicated `investigation-graph-canvas` spec)
- Manual: `make dev`, log in, navigate to `/investigation/:entityId?kb=...`, click a neighbor node and confirm URL + dossier update.

### Code touch points
- `chili_app/src/pages/InvestigationWorkbenchPage.tsx` (delivered)
- `chili_app/src/components/investigation/GraphCanvas.tsx` (delivered)
- `chili_app/src/utils/subgraph.ts` (delivered — the adapter, in place of a per-component `NeighborhoodAdapter.ts`)
- `chili_app/src/utils/__tests__/subgraph.test.ts` (still open — no dedicated unit test exists)
- `chili_app/src/pages/__tests__/InvestigationWorkbenchPage.test.tsx` (delivered)
- `chili_app/e2e/investigation-workbench.spec.ts` (delivered — in place of a dedicated `investigation-graph-canvas.spec.ts`)
- `chili_app/README.md` (delivered — Target Page Structure documents the graph-based workbench)

---

## Story frontend.02: Persisted evidence-pack entry point

**ID:** frontend.02
**Status:** planned
**Prerequisites:** [api.13, rag.10]
**Unblocks:** []
**Estimated size:** M

**As a** fraud analyst,
**I need** a real entry point to load and browse persisted evidence packs (by entity, alert, or pack id),
**so that** I can review previously generated reasoning without depending on the in-memory `selectedAlert` join.

### Current State
- `chili_app/src/pages/InvestigationWorkbenchPage.tsx:8,83` calls `useEvidencePack(selectedAlert?.evidence_pack_id ?? null, activeKnowledgeBaseId)` — packs only render when the selected entity happens to have a matching alert row (EVIDENCE tab, gated on `explainability`, since Sprint 2026-28 U2).
- **Corrected 2026-07-23 (reviewer-verified stale, U2 closeout, Task 10):** the AC below originally called for reusing `chili_app/src/components/investigation/EvidencePanel.tsx` — that file was an orphan (never imported outside its own tests) predating U2, and it was **deleted outright** in Sprint 2026-28 U2 Task 7 (`af14736`, D1 orphan-panel retirement) rather than wired up. The live evidence surface today is `chili_app/src/components/investigation/EvidencePackViewer.tsx` (reshaped in the same sprint, U2 Task 5, with a narrative-lead band and SHAP attribution bars) — this story's "chosen surface" should render `EvidencePackViewer`, fed by a new list-backed query, not `EvidencePanel`.
- No list view, no load-by-id input, no `/evidence-packs` route, no link from alert rows still holds — `AlertFeedPage.tsx`'s evidence expansion (U2 Task 8) still resolves the pack via the alert's own `evidence_pack_id`, not an independent lookup.
- **Superseded 2026-07-23 (alerts.36, durable alert read model; live-verified 2026-07-23, Task 6 of `feat/alerts-durable-read-model`):** the U2-era observation that the workbench EVIDENCE tab renders `EmptyState` for real entities because the alert feed's backing store was blind in a fresh deployment (the old API-owned `alert_projection` was only ever populated by test/dev-seed fixtures, per the now-closed `docs/backlog/monitoring.md` story monitoring.02) no longer applies. `GET /alerts` now reads the durable `alert_history` table directly — the same table Flow 4 writes for every real alert — so any entity with a genuine alert has a real `alert_id`/`evidence_pack_id` for `useEvidencePack(selectedAlert?.evidence_pack_id ?? null, …)` to resolve. Task 6's controller live pass confirmed this against a real browser session on the TN KB: the workbench Evidence tab rendered an AI NARRATIVE band plus 2 SHAP attribution rows for a genuine alert, with zero console errors. This story's remaining gap (no independent list/load-by-id entry point, still coupled to the currently-selected alert) is unchanged and still open.

### Acceptance Criteria
- [ ] `useEvidencePackList` (server-state hook) is added to `chili_app/src/api/evidence.ts` and consumed by a new list surface.
- [ ] Either a `/evidence-packs` route or an Investigation-side "Evidence packs" tab renders persisted packs scoped to the active KB.
- [ ] The list surface renders packs through `EvidencePackViewer.tsx` (the live, reshaped viewer — **not** `EvidencePanel.tsx`, which no longer exists).
- [ ] Alert rows in `AlertFeedPage.tsx` expose an "Open evidence pack" action that deep-links to the loaded pack.
- [ ] Vitest coverage exercises load, empty, error, and pack-not-found states.
- [ ] Playwright spec covers: load list → open pack → reasoning + items render.

### Verification
- `cd chili_app && npm run lint && npm run test:run`
- `cd chili_app && npm run test:e2e -- evidence-pack`
- Manual: seed an evidence pack via backend; confirm UI lists and renders it.

### Code touch points
- `chili_app/src/api/evidence.ts` (modify)
- `chili_app/src/components/investigation/EvidencePackViewer.tsx` (modify — consumed by the new list surface; `EvidencePanel.tsx` no longer exists to touch)
- `chili_app/src/pages/InvestigationWorkbenchPage.tsx` (modify) OR `chili_app/src/pages/EvidencePacksPage.tsx` (new)
- `chili_app/src/pages/AlertFeedPage.tsx` (modify — row action)
- `chili_app/src/app/router.tsx` (modify if new route)
- `chili_app/e2e/evidence-pack.spec.ts` (new)

---

## Story frontend.03: Mount configuration wizard shell with validation reads

**ID:** frontend.03
**Status:** planned
_Note (2026-07-12): implementation is in flight on the unmerged `feat/domain-packs-and-config-manager` branch; status flipped back to planned because the prerequisite DAG invariant (in-progress requires all prerequisites done) is CI-enforced and the listed prerequisites are not done. Restore to in-progress/done when the branch merges and the prerequisite edges are reconciled._
**Prerequisites:** [config.15, frontend.06, frontend.07]
**Progress note (2026-07-03, feat/domain-packs-and-config-manager):** a first Config Manager experience landed on `/configuration` (24eb58c): a pack switcher (`PackSwitcher`, driven by `GET /config/packs`) and an active-pack YAML editor (`ActivePackEditor`) with inline dry-run validation (`POST /config/validate` with edited content) and hot-swap apply/switch. This satisfies "route + navigation entry", "loads current configuration", and "validation errors shown inline without applying"; it is a raw-YAML editor + switcher, **not** the sectioned wizard shell — section navigation across environment/storage/graph/LLM/auth/ingestion/monitoring scopes and schema-metadata-driven forms remain open (blocked on config.08/config.15 schema slices).
**Unblocks:** [frontend.25]
**Estimated size:** L

### Narrative
As an operator,
I want a frontend configuration wizard shell that loads schemas and validates edits,
so that configuration work can begin from the UI without saving changes yet.

### Current State
The frontend has operational views, but no mounted wizard experience for configuration sections.

### Acceptance Criteria
- [ ] Wizard route and navigation entry are available to authorized users.
- [ ] Wizard loads schema metadata and current configuration from backend endpoints.
- [ ] Section navigation supports environment, storage, graph, LLM, auth, ingestion, and monitoring scopes.
- [ ] Validation errors are shown inline without applying draft values.

### Verification
- [ ] Component tests cover schema loading, section navigation, and validation error rendering.
- [ ] Browser smoke test confirms the wizard shell renders from live API data.

### Code touch points
- `frontend/src/**`
- `frontend/tests/**`
- `docs/wiki/modules/frontend.md`

---
## Story frontend.04: Migrate seeded Dashboard + RAG copy to live projections

**ID:** frontend.04
**Status:** done
**Prerequisites:** [api.28, rag.01]
**Unblocks:** [analytics.28]
**Estimated size:** M
**Done:** 2026-07-02 · docs reconcile (aa7bee0) · analyst-facing seeded/demo copy removed with regression guard

**As a** fraud analyst,
**I need** the Dashboard and RAG Chat surfaces to clearly reflect live projections rather than "seeded investigation graph" demo language,
**so that** I can trust the numbers I'm shown in real deployments.

### Current State
- Seeded/demo analyst-facing copy has been removed from Dashboard and RAG page surfaces.
- Regression coverage exists to prevent reintroducing seeded/demo analyst-facing strings.
- `chili_app/README.md` now documents the live routed surfaces and read-only configuration status.

### Acceptance Criteria
- [x] Dashboard sublabel and any "seeded" references are replaced with copy that reflects the live KB-scoped projection contract from `analytics.06`.
- [x] RAG Chat empty/intro copy reflects the live conversational endpoint contract from `rag.07`.
- [x] All hooks consume live endpoints (`useDashboardMetrics`, `useChatMessages`) with no remaining demo fallbacks.
- [x] `chili_app/README.md` Current State table strikes the seeded notes for Dashboard and RAG and links to this story id.
- [x] Vitest snapshot/text assertions are updated to the new copy.

### Verification
- `cd chili_app && npm run lint && npm run test:run`
- Manual: `make dev`, log in, confirm Dashboard + RAG Chat copy no longer mentions "seeded" or "demo".
- Grep: `grep -r "seeded\|demo" chili_app/src/pages/` returns no analyst-facing strings.

### Code touch points
- `chili_app/src/pages/DashboardPage.tsx` (modify)
- `chili_app/src/pages/RagChatPage.tsx` (modify)
- `chili_app/src/pages/__tests__/DashboardPage.test.tsx` (modify)
- `chili_app/src/pages/__tests__/RagChatPage.test.tsx` (modify)
- `chili_app/README.md` (modify)

---

## Story frontend.05: Decide and execute on `AiAssistantPanel`

**ID:** frontend.05
**Status:** planned
**Prerequisites:** [rag.01]
**Unblocks:** []
**Estimated size:** M

**As a** fraud analyst,
**I need** the right-rail AI Assistant to either talk to the real RAG endpoints or be removed,
**so that** the workspace doesn't ship dead UI that promises capability it doesn't deliver.

### Current State
- **(Corrected 2026-07-24, D1 closeout — prior text was stale.)** The panel is no
  longer a no-op: `AiAssistantPanel.tsx` parses launch context from the current
  route (`/alerts?alert=`, `/cases?case=`, entity pages, `/rag-chat` params) and
  its send button navigates to `/rag-chat` via `buildRagChatUrl` with the typed
  question, KB, and source context attached — the handoff lands in the real RAG
  chat surface. Send stays disabled until both a context and a non-empty draft
  exist.
- `AppShell.tsx:91` mounts it only while `aiPanelOpen` is toggled on (TopBar
  "AI Panel" button), not unconditionally.
- What remains of the original decision: whether an *inline* conversation
  (reply rendered in the panel via the RAG mutation, per the ACs below) is
  wanted on top of the shipped navigate-to-RAG-chat handoff, or whether the
  handoff is the recorded end state. The ACs below still describe the inline
  variant and should be re-scoped when this story is picked up.
- **PM prereq re-point (2026-06-23):** prereq `rag.07` (reranker stage) was mislabeled — wiring the assistant to the live conversational endpoint depends on **`rag.01`** (live RagService), not the optional reranker.

### Acceptance Criteria
- [ ] Decision recorded in `chili_app/README.md`: wire to RAG endpoints or delete.
- [ ] If wired: composer submits a message via the existing RAG conversation mutation, scoped to a workspace-selected KB; reply renders inline; loading + error states present.
- [ ] If wired: keyboard submit (Enter), submit-on-click, disabled while pending, and clear-on-send all covered by Vitest.
- [ ] If deleted: `AiAssistantPanel.tsx` removed, `AppShell.tsx` updated, `aiPanelOpen` + `toggleAiPanel` removed from `uiStore`, AI Panel button removed from `TopBar`, related CSS pruned.
- [ ] No dead exports remain (lint clean, no unused vars).

### Verification
- `cd chili_app && npm run lint && npm run test:run && npm run build`
- If wired: Playwright spec asserts message + reply round-trip.
- If deleted: grep `grep -r "AiAssistantPanel\|aiPanelOpen" chili_app/src/` returns no hits.

### Code touch points
- `chili_app/src/components/layout/AiAssistantPanel.tsx` (modify | delete)
- `chili_app/src/components/layout/AppShell.tsx` (modify)
- `chili_app/src/components/layout/TopBar.tsx` (modify)
- `chili_app/src/stores/uiStore.ts` (modify)
- `chili_app/README.md` (modify)

---

## Story frontend.06: Consolidate Zustand stores into one ownership model

**ID:** frontend.06
**Status:** planned
**Prerequisites:** []
**Unblocks:** [api.08, frontend.03]
**Estimated size:** M

**As a** frontend developer,
**I need** a single, explicit Zustand ownership model that doesn't double-define `selectedEntityId`, sidebar collapse, or active KB,
**so that** components don't drift between competing sources of truth and bugs caused by writing to the wrong store are eliminated.

### Current State
- `chili_app/src/stores/appStore.ts:3-20` defines `sidebarOpen`, `selectedEntityId`, `activeKnowledgeBaseId`, plus `toggleSidebar` / `selectEntity` / `setActiveKnowledgeBase`.
- `chili_app/src/stores/uiStore.ts:3-32` re-defines `sidebarCollapsed` (inverse semantic), `selectedEntityId`, `selectedRole`, `aiPanelOpen`, realtime status — with different setters.
- Investigation reads KB from the URL via `searchParams.get('kb')` (`InvestigationWorkbenchPage.tsx:42`) — neither store is used.
- `chatStore.ts` and `ingestionStudioStore.ts` exist separately and are scoped correctly.

### Acceptance Criteria
- [ ] A single decision is recorded: either `appStore` is deleted (URL is source of truth for KB + entity, `uiStore` owns chrome) or the two are merged into one store with documented semantics.
- [ ] No two stores expose overlapping keys (`sidebarOpen`/`sidebarCollapsed`, `selectedEntityId`, `activeKnowledgeBaseId`).
- [ ] All consumer sites are updated; ESLint + tsc clean.
- [ ] Store ownership table added to `chili_app/README.md` (one-row-per-store).
- [ ] Vitest covers any new store actions; existing tests updated.

### Verification
- `cd chili_app && npm run lint && npm run test:run && npm run build`
- Grep: `grep -r "useAppStore\|useUiStore" chili_app/src/` shows only the surviving store's references.

### Code touch points
- `chili_app/src/stores/appStore.ts` (modify | delete)
- `chili_app/src/stores/uiStore.ts` (modify)
- `chili_app/src/stores/__tests__/` (modify)
- All `useAppStore`/`useUiStore` callers (modify)
- `chili_app/README.md` (modify)

---

## Story frontend.07: SSE resync — Last-Event-ID + baseline refetch on long disconnect

**ID:** frontend.07
**Status:** planned
**Prerequisites:** [api.07]
**Unblocks:** [api.15, frontend.03, frontend.08, frontend.24]
**Estimated size:** L

**As a** fraud analyst,
**I need** the workspace SSE stream to resume from the last received event and reconcile a baseline snapshot after a long disconnect,
**so that** missed alerts/workflow updates don't silently drop and a sleeping tab doesn't show stale state.

### Current State
- `chili_app/src/api/realtime.ts:32-130` reconnects with exponential backoff (1s → 30s) but constructs `new EventSource(...)` with no `Last-Event-ID` parameter.
- The previous snapshot is held in a local closure (`previousSnapshot`) and discarded on remount; no baseline refetch occurs after long offline periods.
- No detection of "long disconnect" vs. transient blip.

### Acceptance Criteria
- [ ] On reconnect, the client passes the last seen event id via a query parameter or header that the backend SSE endpoint honors (contract owned by **`api.07`** — "Event-driven SSE with reconnect semantics", whose AC adds the `id:` line and honors `Last-Event-ID`; the prior `api.09`/`events.06` references were mislabeled).
- [ ] After a configurable "long disconnect" threshold (e.g. 60s), the client invalidates every workspace query key (alerts, workflows, KBs, dashboard metrics) and refetches a baseline snapshot before resuming event-driven invalidation.
- [ ] Connection state ("live" | "reconnecting" | "resyncing") is exposed on `uiStore` and surfaced via the realtime status badge in TopBar.
- [ ] Vitest covers: short blip preserves snapshot; long disconnect triggers baseline refetch; resume sends `Last-Event-ID`.
- [ ] Playwright spec simulates an offline → online toggle and asserts a refresh occurred.

### Verification
- `cd chili_app && npm run lint && npm run test:run && npm run build`
- Manual: throttle network in DevTools to offline for >60s, restore, observe baseline refetch in React Query devtools.

### Code touch points
- `chili_app/src/api/realtime.ts` (modify)
- `chili_app/src/stores/uiStore.ts` (modify)
- `chili_app/src/api/__tests__/realtime.test.ts` (new | modify)
- `chili_app/e2e/realtime-resync.spec.ts` (new)

---

## Story frontend.08: Delete `useWebSocket` or adopt it for a push channel

**ID:** frontend.08
**Status:** planned
**Prerequisites:** [frontend.07]
**Unblocks:** [api.14]
**Estimated size:** S

**As a** frontend developer,
**I need** realtime ownership to be unambiguous — exactly one transport (SSE) unless WebSocket is actually used,
**so that** dead code stops bit-rotting under tests and new contributors don't accidentally adopt the wrong hook.

### Current State
- `chili_app/src/hooks/useWebSocket.ts:61-205` ships a complete reconnect/heartbeat implementation.
- `grep -r "useWebSocket" chili_app/src/ --include="*.ts*"` returns zero non-test imports.
- `chili_app/src/types/wsEvents.ts` exists only because `useWebSocket` and `ConnectionStatus` consume it.

### Acceptance Criteria
- [ ] Decision recorded in `chili_app/README.md`: keep for a named push channel, or remove.
- [ ] If removed: `useWebSocket.ts`, its tests, `types/wsEvents.ts`, and `ConnectionStatus.tsx` (if unused per frontend.24) are deleted; no broken imports remain.
- [ ] If kept: at least one consumer page imports and uses it; rationale documented.
- [ ] Lint + tsc + test suites green.

### Verification
- `cd chili_app && npm run lint && npm run test:run && npm run build`
- Grep: confirm zero unreferenced exports remain.

### Code touch points
- `chili_app/src/hooks/useWebSocket.ts` (modify | delete)
- `chili_app/src/hooks/__tests__/useWebSocket.test.ts` (modify | delete)
- `chili_app/src/types/wsEvents.ts` (modify | delete)
- `chili_app/README.md` (modify)

---

## Story frontend.09: Page-level error boundary recovery + monitoring hook

**ID:** frontend.09
**Status:** planned
**Prerequisites:** [_observability.08]
**Unblocks:** [api.24]
**Estimated size:** M

**As a** fraud analyst,
**I need** an error boundary that lets me retry a failed page in place and reports the failure to monitoring,
**so that** a transient render error doesn't force a full nav-away and operators see what broke.

### Current State
- `chili_app/src/components/common/ErrorBoundary.tsx:13-66` wraps each route via `chili_app/src/app/router.tsx:18-20` via `withPageBoundary`.
- The default fallback renders "Something went wrong" + a "Try again" button that resets state, but `componentDidCatch` only `console.error`s — there is no monitoring hook.
- No structured event is emitted to RUM/Sentry (none configured — see frontend.17).

### Acceptance Criteria
- [ ] `ErrorBoundary` accepts an optional `onError(error, info)` callback wired by `withPageBoundary` to the RUM client introduced in `_observability.08`/frontend.17.
- [ ] The default fallback exposes "Try again", "Reload page", and "Report this error" actions; "Report" sends a structured payload to the monitoring sink.
- [ ] Boundary resets cleanly without leaking query cache state (tests cover).
- [ ] Vitest covers: thrown render error → fallback rendered → reset restores children; onError invoked exactly once.
- [ ] Storybook/visual reference (if Storybook present) or a screenshot in the PR description.

### Verification
- `cd chili_app && npm run lint && npm run test:run && npm run build`
- Manual: throw inside a page component, confirm fallback + monitoring payload.

### Code touch points
- `chili_app/src/components/common/ErrorBoundary.tsx` (modify)
- `chili_app/src/app/router.tsx` (modify)
- `chili_app/src/components/common/__tests__/ErrorBoundary.test.tsx` (modify)

---

## Story frontend.10: Accessible tablist + focus management primitives

**ID:** frontend.10
**Status:** planned
**Prerequisites:** []
**Unblocks:** [api.27, frontend.11]
**Estimated size:** M

**As a** keyboard-only user,
**I need** the shared `Tabs`, `FilterBar`, `KbTable`, and ingestion stepper to support arrow keys, Home/End, and roving tabindex,
**so that** I can navigate the workbench without a mouse and meet WCAG 2.1 AA keyboard requirements.

### Current State
- `chili_app/src/components/ui/Tabs.tsx:14-33` declares `role="tablist"` + `aria-selected` but every tab button has `tabindex=0` and there is no arrow-key handler or focus management.
- `FilterBar`, `KbTable`, and ingestion stepper share the same pattern (per auditor notes).
- No focus-trap utility exists for modals; `ConfirmDialog` relies on default tab order.

### Acceptance Criteria
- [ ] `Tabs.tsx` implements roving tabindex with Left/Right arrows, Home, End, and Enter/Space activation per WAI-ARIA APG tabs pattern.
- [ ] A reusable `useRovingTabindex` hook is added under `chili_app/src/hooks/` and consumed by `Tabs`, `FilterBar`, and the ingestion stepper.
- [ ] `KbTable` rows support arrow-up/down navigation and Enter to activate.
- [ ] A `useFocusTrap` hook is added and applied to `ConfirmDialog`.
- [ ] Vitest + Testing Library covers keyboard interactions for each.
- [ ] Documented in `chili_app/README.md` under a new Accessibility section.

### Verification
- `cd chili_app && npm run lint && npm run test:run`
- Manual: tab into each control with keyboard only, exercise arrow keys.
- axe smoke check (covered by frontend.11) shows no new violations.

### Code touch points
- `chili_app/src/components/ui/Tabs.tsx` (modify)
- `chili_app/src/components/ui/FilterBar.tsx` (modify)
- `chili_app/src/components/knowledgebase/KbTable.tsx` (modify)
- `chili_app/src/components/ingestion/IngestionStepper.tsx` (modify)
- `chili_app/src/components/common/ConfirmDialog.tsx` (modify)
- `chili_app/src/hooks/useRovingTabindex.ts` (new)
- `chili_app/src/hooks/useFocusTrap.ts` (new)
- `chili_app/src/components/ui/__tests__/Tabs.test.tsx` (modify)
- `chili_app/README.md` (modify)

---

## Story frontend.11: Automated accessibility audits in CI

**ID:** frontend.11
**Status:** planned
**Prerequisites:** [frontend.10, _cicd.05]
**Unblocks:** []
**Estimated size:** M

**As a** platform owner,
**I need** axe-core accessibility audits to run automatically against every page in CI,
**so that** WCAG AA regressions are caught at PR time, not in user reports.

### Current State
- `chili_app/package.json:18-50` lists no axe-core / jest-axe dependency.
- No axe-based Playwright check exists; Lighthouse is not part of `npm run test:e2e`.
- WCAG AA compliance is asserted only by ad-hoc aria attributes.

### Acceptance Criteria
- [ ] `@axe-core/playwright` is added as a dev dependency.
- [ ] A Playwright fixture runs axe against every routed page (logged-in admin role) and asserts zero serious/critical violations.
- [ ] A documented allowlist file captures any temporarily accepted minor violations with linked stories.
- [ ] A Lighthouse-CI job (or `@lhci/cli`) runs against `vite preview` in `_cicd.05` and enforces baseline scores: a11y ≥ 95, best-practices ≥ 90.
- [ ] The CI job fails the PR on regression; baselines committed to repo.

### Verification
- Local: `cd chili_app && npm run test:e2e -- a11y`
- CI: PR shows axe + Lighthouse steps green; intentionally inject a violation and confirm CI fails.

### Code touch points
- `chili_app/package.json` (modify)
- `chili_app/e2e/a11y.spec.ts` (new)
- `chili_app/e2e/helpers/axe.ts` (new)
- `chili_app/.lighthouserc.json` (new)
- `.github/workflows/ci.yml` (modify — owned by `_cicd.05`)

---

## Story frontend.12: i18n scaffolding for analyst-facing copy

**ID:** frontend.12
**Status:** planned
**Prerequisites:** []
**Unblocks:** []
**Estimated size:** L

**As a** non-English-speaking analyst,
**I need** all UI chrome strings to be translatable through a single i18n layer,
**so that** deploying chiliAI to non-English customers doesn't require a fork.

### Current State
- No `react-i18next` / `formatjs` / `lingui` dependency in `chili_app/package.json`.
- Every label/CTA in `chili_app/src/pages/*.tsx` is a hardcoded English literal — e.g. `KnowledgeBaseManagerPage.tsx:269` `"Guide documents and config-defined structured records…"`.
- Domain-config display labels already flow through `utils/domainDisplay.ts` (those are not in scope here).

### Acceptance Criteria
- [ ] `react-i18next` (or equivalent) is added; chosen library documented in `chili_app/README.md`.
- [ ] An `i18n/` directory holds an `en` translation catalog covering all pages and shared UI primitives.
- [ ] Hardcoded English strings in `chili_app/src/pages/*.tsx`, `chili_app/src/components/layout/*.tsx`, and shared UI primitives are replaced with `t(...)` calls.
- [ ] A lint rule (`eslint-plugin-i18next/no-literal-string` or equivalent) is added and configured to fail on raw JSX strings outside an allowlist.
- [ ] Existing Vitest tests pass with the default `en` catalog.
- [ ] A `pseudo-en` locale is added behind a query-param flag to surface untranslated strings during dev.

### Verification
- `cd chili_app && npm run lint && npm run test:run && npm run build`
- Manual: switch language via dev locale flag, confirm strings render from the catalog.

### Code touch points
- `chili_app/package.json` (modify)
- `chili_app/src/i18n/` (new)
- `chili_app/src/i18n/en/*.json` (new)
- All `chili_app/src/pages/*.tsx` (modify)
- `chili_app/src/components/layout/*.tsx` (modify)
- `chili_app/eslint.config.js` (modify)
- `chili_app/README.md` (modify)

---

## Story frontend.13: Theming surface + light-mode tokens

**ID:** frontend.13
**Status:** planned
**Prerequisites:** []
**Unblocks:** []
**Estimated size:** M

**As a** fraud analyst working in a bright office or printing reports,
**I need** a light theme alongside the existing dark theme, with a per-user toggle and `prefers-color-scheme` default,
**so that** the workbench is usable outside dark rooms and exports are print-friendly.

### Current State
- `chili_app/src/theme/tokens.ts:1-40` defines a single dark palette (`bg: '#05080f'`, `text: '#e2eaf6'`).
- `chili_app/src/theme/global.css` ships fixed dark colors.
- The only `prefers-color-scheme` reference in the repo is in `assets/vite.svg`.
- No theme toggle in `TopBar` or `Sidebar`.

### Acceptance Criteria
- [ ] `tokens.ts` is restructured to expose semantic tokens consumed via CSS variables (e.g. `--bg`, `--text`, `--surface-1`).
- [ ] `theme/global.css` defines both `:root[data-theme="dark"]` and `:root[data-theme="light"]` blocks.
- [ ] A `useTheme` hook + `ThemeProvider` adds a theme toggle persisted to `localStorage`, defaulting to `prefers-color-scheme`.
- [ ] TopBar exposes a sun/moon toggle (lucide icons) that switches `data-theme` on `document.documentElement`.
- [ ] At least two representative pages (Dashboard, Investigation Workbench) are verified in both themes via Playwright screenshots stored under `chili_app/e2e/screenshots/`.
- [ ] No hardcoded hex codes remain in components touched by this story (lint rule recommended but not required).

### Verification
- `cd chili_app && npm run lint && npm run test:run && npm run build`
- `cd chili_app && npm run test:e2e -- theme`
- Manual: toggle theme, refresh page, confirm choice persists.

### Code touch points
- `chili_app/src/theme/tokens.ts` (modify)
- `chili_app/src/theme/global.css` (modify)
- `chili_app/src/theme/ThemeProvider.tsx` (new)
- `chili_app/src/hooks/useTheme.ts` (new)
- `chili_app/src/components/layout/TopBar.tsx` (modify)
- `chili_app/src/app/providers.tsx` (modify)
- `chili_app/e2e/theme.spec.ts` (new)

---

## Story frontend.14: Route-level code splitting + bundle budgets

**ID:** frontend.14
**Status:** planned
**Prerequisites:** []
**Unblocks:** []
**Estimated size:** M

**As a** fraud analyst,
**I need** the initial bundle to load fast even when I'm only headed to one page,
**so that** I don't pay the cost of `react-force-graph-2d` and `@uiw/react-codemirror` on first paint.

### Current State
- `chili_app/src/app/router.tsx:1-16` imports every page eagerly.
- No `React.lazy`/`Suspense` is used in the app shell.
- `chili_app/README.md:68` notes the gap.
- `react-force-graph-2d` and `@uiw/react-codemirror` ship on first paint.

### Acceptance Criteria
- [ ] Every route element in `router.tsx` is converted to `React.lazy(() => import(...))`.
- [ ] A `<Suspense>` boundary in the route shell renders a skeleton/loading state during chunk load.
- [ ] `vite build` chunk output is inspected; `react-force-graph-2d` and `@uiw/react-codemirror` only appear in the chunks for Investigation Workbench and Configuration respectively.
- [ ] A bundle-size budget is added (e.g. `size-limit` or `vite-bundle-visualizer` check in CI) capping initial JS at ≤ 350 KB gzipped; CI fails on regression.
- [ ] No measurable regression in route navigation (Playwright timing assertion).

### Verification
- `cd chili_app && npm run build && npx vite-bundle-visualizer` (or equivalent).
- `cd chili_app && npm run test:e2e` — navigation flows still pass.
- Bundle size limit reported in CI artifact.

### Code touch points
- `chili_app/src/app/router.tsx` (modify)
- `chili_app/src/components/layout/AppShell.tsx` (modify — Suspense)
- `chili_app/package.json` (modify — size-limit)
- `chili_app/.size-limit.json` (new)
- `.github/workflows/ci.yml` (modify — bundle budget step)

---

## Story frontend.15: Performance-harden the graph explorer

**ID:** frontend.15
**Status:** planned
**Prerequisites:** [frontend.01, api.07, graph.05]
**Unblocks:** [ingestion.22, ingestion.29]
**Estimated size:** L

**As a** fraud analyst exploring a large Medicare provider ring,
**I need** the graph canvas to stay interactive (≥ 30 FPS) on representative subgraphs (1k+ nodes),
**so that** I can pan/zoom/click without browser lockups.

### Current State
- `chili_app/src/components/investigation/GraphCanvas.tsx:53-227` uses default `ForceGraph2D` settings: no node/link decimation, no viewport culling, no worker offload.
- `chili_app/src/pages/InvestigationWorkbenchPage.tsx:247-260` lets analysts pick depth 1-5 with no row cap.
- `docs/architecture.md:1345` flags evaluating WebGL alternatives.

### Acceptance Criteria
- [ ] `GraphCanvas` accepts a `maxNodes` prop and renders a "showing top N of M — narrow filter" banner when truncated.
- [ ] Backend neighborhood call uses the new server-side window/limit contract (owned by `api.07`/`graph.05`).
- [ ] Node and link decimation runs above a configurable threshold (e.g. simplified rendering at zoom < 0.3).
- [ ] Performance test (Playwright + tracing) on a seeded 1k-node neighborhood records < 200ms input-latency at idle.
- [ ] Depth control caps at the value where representative payload stays under the row cap; UI explains the cap.
- [ ] Decision recorded in `chili_app/README.md`: stay with `react-force-graph-2d` or evaluate Sigma.js/WebGL fork story.

### Verification
- `cd chili_app && npm run test:e2e -- graph-performance`
- Manual: load seeded large neighborhood; observe FPS counter in DevTools Performance panel.

### Code touch points
- `chili_app/src/components/investigation/GraphCanvas.tsx` (modify)
- `chili_app/src/pages/InvestigationWorkbenchPage.tsx` (modify)
- `chili_app/src/api/investigation.ts` (modify)
- `chili_app/e2e/graph-performance.spec.ts` (new)
- `chili_app/README.md` (modify)

---

## Story frontend.16: Pagination + cursor controls + infinite scroll

**ID:** frontend.16
**Status:** planned
**Prerequisites:** [api.10, api.11, api.12]
**Unblocks:** []
**Estimated size:** L

**As a** fraud analyst working through hundreds of alerts/cases,
**I need** list pages to fetch additional pages on demand instead of slicing one in-memory page,
**so that** I can browse the full inventory without manual refetches.

### Current State
- `useKnowledgeBases`, `useAlerts`, `useCases`, `useWorkflows` all return a single page-shaped payload.
- No page-component honors `page.total_items` or fetches subsequent pages.
- `chili_app/src/pages/AlertFeedPage.tsx:39-47` and `chili_app/src/pages/KnowledgeBaseManagerPage.tsx:48-58` filter and slice in-memory only.

### Acceptance Criteria
- [ ] `useAlerts`, `useCases`, `useWorkflows`, `useKnowledgeBases` are converted to `useInfiniteQuery` against cursor-shaped endpoints (cursor contract owned by `api.10`–`api.12`).
- [ ] Each list page implements an IntersectionObserver-driven sentinel that triggers `fetchNextPage`.
- [ ] A "Loading more…" skeleton + "Nothing more to load" terminator render at the list bottom.
- [ ] Page query keys are versioned to invalidate cleanly on filter change.
- [ ] Vitest covers: first page render → scroll → next page appended → no duplicates.
- [ ] Playwright spec confirms scrolling triggers a second page fetch.

### Verification
- `cd chili_app && npm run lint && npm run test:run`
- `cd chili_app && npm run test:e2e -- pagination`
- Manual: seed > 50 alerts, scroll, confirm second page appended.

### Code touch points
- `chili_app/src/api/alerts.ts` (modify)
- `chili_app/src/api/cases.ts` (modify)
- `chili_app/src/api/workflows.ts` (modify)
- `chili_app/src/api/knowledgebases.ts` (modify)
- `chili_app/src/pages/AlertFeedPage.tsx` (modify)
- `chili_app/src/pages/CaseManagementPage.tsx` (modify)
- `chili_app/src/pages/KnowledgeBaseManagerPage.tsx` (modify)
- `chili_app/src/hooks/useInfiniteScroll.ts` (new)

---

## Story frontend.17: Frontend RUM + JS-error tracking

**ID:** frontend.17
**Status:** planned
**Prerequisites:** [_observability.08, _observability.09]
**Unblocks:** []
**Estimated size:** M

**As a** platform operator,
**I need** the SPA to emit core web vitals, navigation timings, and uncaught errors to the central observability backend,
**so that** I can detect frontend regressions without waiting for user reports.

### Current State
- No Sentry/Datadog/Otel browser dependency exists in `chili_app/package.json`.
- `chili_app/src/contexts/SessionContext.tsx:24` only `console.warn`s non-401 boot errors.
- `chili_app/src/components/common/ErrorBoundary.tsx` swallows render crashes (see frontend.09).

### Acceptance Criteria
- [ ] The chosen RUM client (decision recorded in `_observability.08`) is added as a dependency.
- [ ] A bootstrap module under `chili_app/src/observability/` initializes the client with DSN/sample-rate from `import.meta.env.VITE_RUM_*`.
- [ ] `web-vitals` (LCP, INP, CLS, TTFB) are measured and reported.
- [ ] Uncaught errors and unhandled promise rejections are captured.
- [ ] `ErrorBoundary` `onError` (frontend.09) is wired to the RUM client.
- [ ] PII redaction (auth tokens, session cookie) is documented and tested.
- [ ] No RUM init in test environments (Vitest); env-gated.

### Verification
- `cd chili_app && npm run lint && npm run test:run && npm run build`
- Manual: open a page, inspect network for outbound RUM events; intentionally throw and confirm capture.

### Code touch points
- `chili_app/package.json` (modify)
- `chili_app/src/observability/rum.ts` (new)
- `chili_app/src/main.tsx` (modify)
- `chili_app/src/components/common/ErrorBoundary.tsx` (modify)
- `chili_app/src/observability/__tests__/rum.test.ts` (new)
- `chili_app/.env.example` (modify)

---

## Story frontend.18: Complete auth UI — sign-out, session expiry, role gating

**ID:** frontend.18
**Status:** planned
**Prerequisites:** [_security.05, _security.06, api.05]
**Unblocks:** []
**Estimated size:** M

**As a** fraud analyst,
**I need** a visible Sign-out control, a clear message when my session expires, and a role picker that only shows roles I'm actually assigned,
**so that** I can end my session deliberately, understand why I'm being redirected, and not be presented with privileges I don't have.

### Current State
- `useSession().signOut` is implemented in `chili_app/src/contexts/SessionContext.tsx:33-39` but no component invokes it (no Sign-out button in `Sidebar.tsx` / `TopBar.tsx`).
- `chili_app/src/lib/apiClient.ts:164-168` hard-redirects on 401 with no toast or explanation.
- `chili_app/src/components/layout/TopBar.tsx:30-45` exposes `Object.keys(domainFeatures.roles)` as a free-choice picker — any user can self-promote in the UI.

### Acceptance Criteria
- [ ] A Sign-out button (icon + label) is added to TopBar (or a user menu) and calls `signOut()`.
- [ ] On 401 redirect, a toast/banner explains "Your session expired — please sign in again" using `toastStore` (cross-edge to frontend.24).
- [ ] The role picker shows only roles included in the authenticated user's claims (`_security.05` provides claim shape; `api.05` exposes via `/auth/me`).
- [ ] If the user has exactly one role, the picker collapses to a static badge.
- [ ] Vitest covers: signOut call, expired-session toast, role-list filtering.
- [ ] Playwright spec covers: sign in → click sign out → land on `/login`; 401 mid-session → toast + redirect.

### Verification
- `cd chili_app && npm run lint && npm run test:run`
- `cd chili_app && npm run test:e2e -- auth-ui`

### Code touch points
- `chili_app/src/components/layout/TopBar.tsx` (modify)
- `chili_app/src/contexts/SessionContext.tsx` (modify)
- `chili_app/src/lib/apiClient.ts` (modify)
- `chili_app/src/contexts/sessionContextValue.ts` (modify)
- `chili_app/src/components/layout/__tests__/TopBar.test.tsx` (new | modify)
- `chili_app/e2e/auth-ui.spec.ts` (new)

---

## Story frontend.19: TopBar tenant switcher + persisted active tenant

**ID:** frontend.19
**Status:** planned
**Prerequisites:** [_multitenancy.04, _multitenancy.06, _security.07]
**Unblocks:** [_multitenancy.14]
**Estimated size:** L

**As a** multi-tenant administrator,
**I need** to switch the active tenant from the TopBar and have that selection persist across reloads,
**so that** I can scope queries, KBs, and config to the correct tenant in a multi-tenant deployment.

### Current State
- `grep -r "tenant" chili_app/src/` returns zero non-test hits despite `_multitenancy.md` being part of the endgame.
- All API calls are tenant-agnostic; query keys do not include tenant.

### Acceptance Criteria
- [ ] `useTenants` (server-state hook) fetches the user's accessible tenants from the contract defined in `_multitenancy.04`.
- [ ] A TopBar selector renders the tenant list and the active choice.
- [ ] The active tenant is persisted (URL prefix or `localStorage` — decision documented in `chili_app/README.md`) and surfaced as a header on every API call.
- [ ] Switching tenant clears tenant-scoped query keys and refetches.
- [ ] Vitest covers: tenant list render, switch resets caches, header injected on `apiRequest`.
- [ ] Playwright spec: switch tenant, confirm KB list changes.

### Verification
- `cd chili_app && npm run lint && npm run test:run`
- `cd chili_app && npm run test:e2e -- tenant-switch`

### Code touch points
- `chili_app/src/api/tenants.ts` (new)
- `chili_app/src/components/layout/TopBar.tsx` (modify)
- `chili_app/src/lib/apiClient.ts` (modify — inject `X-Tenant` header)
- `chili_app/src/contexts/TenantContext.tsx` (new)
- `chili_app/src/app/providers.tsx` (modify)
- `chili_app/e2e/tenant-switch.spec.ts` (new)
- `chili_app/README.md` (modify)

---

## Story frontend.20: Expand Playwright coverage to mutation, error, and realtime flows

**ID:** frontend.20
**Status:** planned
**Prerequisites:** [_cicd.06]
**Unblocks:** []
**Estimated size:** L
**Spec:** docs/superpowers/specs/2026-05-17-ingestion-studio-ui-ux-design.md

**As a** release manager,
**I need** Playwright coverage of mutation, error, and realtime flows — not just happy-path renders,
**so that** PRs catch regressions in upload, save, reconnect, role redirect, and 401 recovery before merge.

### Current State
- `chili_app/e2e/` ships 11 specs covering happy-path renders (login redirect, smoke, knowledge-base-list, investigation render, RAG chat, etc.).
- Missing flows per `chili_app/README.md:108-121`: ingestion-studio document upload + records submit, evidence-pack drill-down, configuration save, SSE reconnect, role-based redirect to landing, 401 logout recovery.

### Acceptance Criteria
- [ ] New specs added covering: (a) ingestion-studio document upload happy path, (b) records submit happy + validation-failure path, (c) configuration save (covered with frontend.03), (d) SSE reconnect (covered with frontend.07), (e) role-based redirect, (f) 401 logout recovery.
- [ ] Backend fixtures/seed scripts owned by `_cicd.06` make each flow deterministic.
- [ ] All new specs pass locally and in CI.
- [ ] Playwright reporter uploads traces on failure.

### Verification
- `cd chili_app && npm run test:e2e`
- CI shows green on the expanded matrix.

### Code touch points
- `chili_app/e2e/ingestion-document-upload.spec.ts` (new)
- `chili_app/e2e/ingestion-records-submit.spec.ts` (new)
- `chili_app/e2e/role-based-redirect.spec.ts` (new)
- `chili_app/e2e/auth-401-recovery.spec.ts` (new)
- `chili_app/e2e/helpers/` (modify — fixtures)

---

## Story frontend.21: Vitest coverage gate + transport/realtime coverage

**ID:** frontend.21
**Status:** planned
**Prerequisites:** [_cicd.05]
**Unblocks:** []
**Estimated size:** M

**As a** quality owner,
**I need** Vitest to enforce the 85% coverage gate required by CLAUDE.md and to actually exercise the high-risk transport + realtime code,
**so that** silent gaps in error handling, timeouts, and reconnect loops can't ship.

### Current State
- `chili_app/vitest.config.ts:1-13` has no `coverage` threshold block; CLAUDE.md requires ≥ 85%.
- `chili_app/src/lib/apiClient.ts:94-179` (timeout/abort/auth-redirect paths) and `chili_app/src/api/realtime.ts:32-130` (reconnect, snapshot diff) lack thorough tests beyond happy path.

### Acceptance Criteria
- [ ] `vitest.config.ts` adds `coverage: { provider: 'v8', thresholds: { lines: 85, functions: 85, branches: 80, statements: 85 } }`.
- [ ] `apiClient.test.ts` covers: timeout, abort signal forwarding, 401 redirect skipped on `/auth/*` paths, validation-detail flattening, JSON vs text parsing.
- [ ] `realtime.test.ts` covers: connect → workspace-update invalidates correct keys, reconnect with backoff, long-disconnect resync (paired with frontend.07), cleanup on unmount.
- [ ] `npm run test:run -- --coverage` runs in CI and fails on threshold drop.

### Verification
- `cd chili_app && npm run test:run -- --coverage`
- CI artifact shows coverage report ≥ 85%.

### Code touch points
- `chili_app/vitest.config.ts` (modify)
- `chili_app/src/lib/__tests__/apiClient.test.ts` (modify | new)
- `chili_app/src/api/__tests__/realtime.test.ts` (modify | new)
- `.github/workflows/ci.yml` (modify — coverage step, owned by `_cicd.05`)

---

## Story frontend.22: Reconcile `chili_app/README.md` with actual `AppProviders` tree

**ID:** frontend.22
**Status:** done
**Prerequisites:** []
**Unblocks:** []
**Estimated size:** S
**Done:** 2026-07-02 · docs reconcile (aa7bee0) · README matches providers.tsx

**As a** new contributor,
**I need** the frontend README to accurately describe the live provider tree,
**so that** I don't waste time hunting for a `DomainConfigProvider` that doesn't ship.

### Current State
- `chili_app/README.md` now matches the real provider tree in `src/app/providers.tsx` (`QueryClientProvider`, `SessionProvider`, optional `ReactQueryDevtools`).
- The only `DomainConfigProvider` in the repo remains the test utility `src/test-utils/MockDomainConfigProvider.tsx`; runtime domain config flows through TanStack Query hooks (`useDomainConfig`, `useDomainFeatures`).

### Acceptance Criteria
- [x] `chili_app/README.md` § "Current State" is rewritten to match `providers.tsx` exactly: lists `QueryClientProvider`, `SessionProvider`, optional `ReactQueryDevtools`.
- [x] The README documents that domain config flows through TanStack Query hooks, with a pointer to `api/config.ts`.
- [x] If a real `DomainConfigProvider` is desired (decision recorded), a follow-up story is created in this file before merge; otherwise the test-only provider is renamed `MockDomainConfigProvider` (already is) and that fact is noted in the README.

### Verification
- `diff` the README claims against `providers.tsx` — must agree.
- Manual review.

### Code touch points
- `chili_app/README.md` (modify)
- `chili_app/src/test-utils/MockDomainConfigProvider.tsx` (modify — comment header only)

---

## Story frontend.23: Adopt generated OpenAPI client for typed contracts

**ID:** frontend.23
**Status:** planned
**Prerequisites:** [api.20]
**Unblocks:** []
**Estimated size:** L

**As a** frontend developer,
**I need** the typed contracts in `chili_app/src/api/` to be generated from the backend OpenAPI spec instead of hand-maintained,
**so that** backend schema drift surfaces in CI rather than at runtime.

### Current State
- `chili_app/package.json:13` ships `codegen:api` (`openapi-typescript http://localhost:8000/openapi.json --output src/lib/api/schema.ts`).
- The output file `chili_app/src/lib/api/schema.ts` does not exist.
- Every `chili_app/src/api/*.ts` hand-types DTOs via `chili_app/src/api/contracts.ts:1-40`; drift between backend OpenAPI and frontend types is unguarded.

### Acceptance Criteria
- [ ] OpenAPI stability prereqs (`api.20`, `api.21`) are in place: versioned, exported, stable schema.
- [ ] `npm run codegen:api` generates `chili_app/src/lib/api/schema.ts` and the file is committed.
- [ ] Hand-typed DTOs in `chili_app/src/api/contracts.ts` are replaced with imports from the generated schema; thin wrapper types remain only for UI-specific shapes.
- [ ] A CI job runs `npm run codegen:api` against the backend container and fails if the committed file is out of date.
- [ ] Existing tests pass with regenerated types; no `any` introduced.

### Verification
- `cd chili_app && npm run codegen:api && git diff --exit-code -- src/lib/api/schema.ts`
- `cd chili_app && npm run lint && npm run test:run && npm run build`

### Code touch points
- `chili_app/src/lib/api/schema.ts` (new — generated)
- `chili_app/src/api/contracts.ts` (modify)
- `chili_app/src/api/*.ts` (modify — import from schema)
- `.github/workflows/ci.yml` (modify — codegen-drift step)
- `chili_app/README.md` (modify — document codegen workflow)

---

## Story frontend.24: Consolidate toast + connection surfaces and surface realtime status

**ID:** frontend.24
**Status:** planned
**Prerequisites:** [frontend.07]
**Unblocks:** []
**Estimated size:** M

**As a** fraud analyst,
**I need** every mutation to surface success/failure via a single toast surface, and the realtime connection state to be visible with a reconnect action when needed,
**so that** I'm not left guessing whether a save worked or why data stopped updating.

### Current State
- `ToastContainer` is mounted globally at `chili_app/src/main.tsx:6,18` but `toastStore` is not invoked from any mutation handler — grep shows zero non-test calls to `showToast` or `useToastStore.getState().push`.
- `chili_app/src/components/common/ConnectionStatus.tsx:17-34` ships a connection badge component that no page imports.
- `chili_app/src/components/layout/TopBar.tsx:20,46` shows realtime state only as a plain text badge ("Live updates" / "Realtime reconnecting") with no reconnect action.

### Acceptance Criteria
- [ ] A reusable `useMutationToast` wrapper (or convention) wires `showToast` into mutation `onSuccess` / `onError` for KB CRUD, alert ack, case feedback, ingestion submits, and configuration save.
- [ ] `ConnectionStatus` is rendered in TopBar (or removed if frontend.07's status surface in TopBar supersedes it — decision documented).
- [ ] When realtime is `closed` for > 30s, the TopBar shows a "Reconnect" action that forces an immediate reconnect attempt (callable via `useRealtimeWorkspaceStream` API).
- [ ] Vitest covers: each mutation pushes the expected toast variant; reconnect action triggers reconnect.
- [ ] Playwright spec covers: trigger a mutation → toast renders → dismisses; offline → "Reconnect" appears → click → online → toast clears.

### Verification
- `cd chili_app && npm run lint && npm run test:run`
- `cd chili_app && npm run test:e2e -- realtime-status`

### Code touch points
- `chili_app/src/hooks/useMutationToast.ts` (new)
- `chili_app/src/components/common/ConnectionStatus.tsx` (modify)
- `chili_app/src/components/layout/TopBar.tsx` (modify)
- `chili_app/src/api/realtime.ts` (modify — expose reconnect)
- All mutation hooks in `chili_app/src/api/*.ts` (modify)
- `chili_app/e2e/realtime-status.spec.ts` (new)

## Story frontend.25: Build structured configuration editor sections

**ID:** frontend.25
**Status:** planned
**Prerequisites:** [frontend.03, config.14]
**Progress note (2026-07-03, feat/domain-packs-and-config-manager):** only the "raw YAML view remains available" AC is effectively covered — the Config Manager (24eb58c) ships a raw YAML editor for the active pack. Typed per-section controls and a draft diff have NOT landed; drafts do not exist yet (no config.14 backend).
**Progress note (2026-07-27, UXA-404):** the Configuration page now renders `/config/domain/schema` as a browsable reference (`SchemaBrowser`), and a validation issue reveals the line it came from in the YAML buffer. Neither closes any AC here: this story wants *editable* per-section controls over a draft, and the schema browser is read-only reference beside the raw editor. Still blocked on config.14.
**Unblocks:** [frontend.26]
**Estimated size:** L

### Narrative
As an operator,
I want structured editor sections for configuration drafts,
so that common changes can be made without editing raw YAML.

### Acceptance Criteria
- [ ] Wizard renders typed controls for environment, storage, graph, LLM, auth, ingestion, and monitoring sections.
- [ ] Raw YAML or JSON view remains available for advanced inspection where appropriate.
- [ ] Draft diff is visible before save/apply.

### Verification
- [ ] Component tests cover representative field types, diff rendering, and raw editor fallback.
- [ ] Accessibility checks cover labels, errors, and keyboard navigation.

### Code touch points
- `frontend/src/**`
- `frontend/tests/**`

---

## Story frontend.26: Complete configuration wizard save/apply flow

**ID:** frontend.26
**Status:** planned
_Note (2026-07-12): implementation is in flight on the unmerged `feat/domain-packs-and-config-manager` branch; status flipped back to planned because the prerequisite DAG invariant (in-progress requires all prerequisites done) is CI-enforced and the listed prerequisites are not done. Restore to in-progress/done when the branch merges and the prerequisite edges are reconciled._
**Prerequisites:** [frontend.25, config.15]
**Progress note (2026-07-03, feat/domain-packs-and-config-manager):** the apply flow partially landed without a draft model (24eb58c): the Config Manager validates edited YAML inline (dry-run, backend field-level errors rendered), applies/switches packs via admin-gated `POST /config/apply|switch`, and surfaces success/failure via `SwapResultBanner`. **Semantics gotcha:** "Apply" re-validates and hot-swaps the *on-disk* pack file — the edited buffer is never persisted (no raw pack write endpoint yet; charted under config.07's remaining work). Draft save does not exist. Admin gating verified backend-side; e2e specs (`chili_app/e2e/config-manager.spec.ts`) require `CHILI_DEV_ANONYMOUS_ROLE=admin`. Remaining: draft save/apply lifecycle once config.14/15 land.
**Unblocks:** [_observability.11]
**Estimated size:** M

### Narrative
As an operator,
I want the configuration wizard to save and apply drafts from the UI,
so that configuration changes can be completed without leaving the app.

### Acceptance Criteria
- [ ] UI saves drafts, displays backend validation errors, and applies valid drafts.
- [ ] Admin-only actions are hidden or disabled for unauthorized users and rejected by backend tests.
- [ ] Success and failure states are clear after apply attempts.

### Verification
- [ ] Browser E2E test covers validation failure, draft save, diff review, and apply success.
- [ ] Component tests cover unauthorized and failed-save states.

### Code touch points
- `frontend/src/**`
- `frontend/tests/**`
- `tests/e2e/**`

---

## Story frontend.27: BL-050 (U2) — IntegrityAI-hierarchy workbench reshape implementation

**ID:** frontend.27
**Status:** done
**Prerequisites:** []
**Unblocks:** []
**Estimated size:** L
**Spec:** docs/superpowers/specs/2026-07-23-sprint28-u1-workbench-reshape-design.md
**Done:** 2026-07-23 · Task 11 controller live pass · full Playwright 31 passed/2 skipped + browser verification on the TN KB

**As a** fraud analyst,
**I need** the Investigation Workbench, Alert Feed, and Dashboard restyled around the IntegrityAI-inspired hierarchy (risk numerals, an AI-voice signal band, capability-gated tabs, cluster overlays, narrative-lead evidence) instead of flat card stacks,
**so that** the highest-signal facts (how bad, why, and what to do) are legible at a glance rather than buried in equally-weighted cards.

### Current State (Sprint 2026-28 U2, `feat/sprint-2026-28-u2-workbench-reshape`, 2026-07-23 — live-verified)
All nine implementation tasks of the U2 plan (`docs/superpowers/plans/2026-07-23-sprint28-u2-workbench-reshape.md`) have landed on the feature branch, frontend-only (no backend/contract changes — B1–B3's already-shipped fields are consumed as-is):
- `chili_app/src/pages/pages.css` + `chili_app/src/utils/graphStyles.ts` gained the reshape's CSS classes (`.workbench-*`, `.dossier-*`, `.triage-*`, `.signal-band*`, `.callout--*`, `.fade-up`) and `clusterColorFor`/`isPredictedRelationship`/`predictedConfidenceFor`/`PREDICTED_LINK_COLOR`/`PREDICTED_LINK_DASH`.
- `chili_app/src/components/investigation/EntityDossierHeader.tsx` + `SignalBand.tsx` (new) render the entity identity, Oxanium risk numeral, and an "AI ANALYSIS · N RISK SIGNALS" callout band; the header now carries `key={entity.id}` so the fade-up motion replays on entity change (final-review fix).
- `chili_app/src/components/investigation/AnomalyTrendPanel.tsx` (new, extracted) carries the timeseries chart + red anomaly markers.
- `chili_app/src/components/investigation/EntityPolicyPanel.tsx` + `chili_app/src/components/charts/AttributionBars.tsx` (new) surface policy items on entity/alert views and signed SHAP-style attribution bars.
- `chili_app/src/components/investigation/EvidencePackViewer.tsx` reshaped: narrative-lead band (`data-testid="evidence-narrative"`), `AttributionBars` section gated on `pack.attribution` presence.
- `chili_app/src/components/investigation/GraphCanvas.tsx` + `ClusterMembershipPanel.tsx` (new): community-colored nodes in cluster mode, membership panel with select/highlight, dormant dashed predicted-link rendering (styles only — see frontend.29, no live data exists yet).
- `chili_app/src/pages/InvestigationWorkbenchPage.tsx` restructured into a search-rail + dossier layout with a capability-gated `Tabs` strip: Signals renders only when `risk_scoring` or `timeseries` is on, Network is unconditional, Policy+Evidence render when `explainability` is on (final-review fix — the initial cut rendered Signals unconditionally, missing the plan's §Global-Constraints gate; when only one tab survives, the strip is dropped entirely and that tab's panel renders directly, per plan); the three orphan panels (`EntityDetailPanel`, `EvidencePanel`, `TimelinePanel`) were deleted (`af14736`).
- `chili_app/src/pages/AlertFeedPage.tsx` gained risk-ranked triage rows (numeral + `flagLabelFor` mono flag) and the evidence expansion now fetches a real depth-1 neighborhood + real `entityTypes` instead of an empty subgraph.
- `chili_app/src/pages/DashboardPage.tsx` gained the triage-row lead-card treatment, live `Graph clusters` panel with `clusterColorFor` swatches + workbench deep-links, and updated header copy (no more "Phase 5 data live").
- Task 10 added `chili_app/src/utils/triage.ts` (shared `triageNumeralColor`, deduplicated out of the two pages) and removed the orphaned `.investigation-layout` CSS selector. The final-review pass also removed two dead `?? []` fallbacks on `alert.tags` in `AlertFeedPage.tsx` (`tags` is contract-required — `RequireFields<Schemas['AlertListItem'], 'tags'>`).
- Task 11 (controller live pass, 2026-07-23) ran the full-stack verification and closed out the story — see Verification.

### Acceptance Criteria
- [x] Entity dossier: risk numeral + confidence, AI signal band, capability-gated Signals/Network/Policy/Evidence tabs (§4.1 of the design).
- [x] Cluster overlay + membership panel on `GraphCanvas`, gated on `gnn` (§4.1 NETWORK tab, design D4).
- [x] Evidence viewer: narrative-lead band + attribution bars, gated on field presence (design D5).
- [x] Policy items surfaced on entity (workbench POLICY tab) and alert (Alert Feed chips) views via client-side `target_kind`/`target_ref` filtering (design D7).
- [x] Alert Feed: risk-ranked triage rows with real flag labels; evidence expansion renders a real subgraph, not an empty one (design D6).
- [x] Dashboard: lead-card triage treatment, live clusters panel, updated copy (§4.2).
- [x] Housing-pack (`gnn:false`, `peer_stats:false`) capability degradation is structural (tabs/panels absent, not broken) per the code paths written for §5 — exercised live against the running housing-pack stack (see Verification).
- [x] Dormant predicted-link rendering ships (styles + helpers) without fabricating data — see frontend.29 for the backend dependency that will light it up.
- [x] Full-stack browser/e2e verification (Task 11): Playwright specs updated/extended and run against `make dev` with real CMS DE-SynPUF data; housing-pack capability-degradation walkthrough; zero console errors. **Live-verified 2026-07-23** — see Verification.

### Verification
- `cd chili_app && npm run test:run` — 477 tests / 69 files passed (2026-07-23, post-final-review-fix commit; includes the new tab-strip-collapse-to-Network unit test).
- `cd chili_app && npm run build` — `tsc -b && vite build` clean (one pre-existing >500kB chunk-size advisory, not an error; tracked by frontend.14).
- `cd chili_app && npm run lint` — clean.
- **Task 11 controller live pass (2026-07-23), against the full running stack (`make dev`):** full Playwright suite 31 passed / 2 skipped, including new tab-aware workbench assertions and triage/narrative-band evidence assertions run against the live stack (not mocked). Browser pass on the TN demo KB: dossier header, Network tab cluster overlay/membership panel, Dashboard clusters panel — all 4 `clusterColorFor` swatches match between workbench and dashboard. Housing pack verified untouched (its four routed pages render unaffected by the reshape; zero CMS strings anywhere). Zero browser console errors across all three pages.
- **Config discovery, since superseded (alerts.36, 2026-07-23):** at U2 closeout, the `medicare_fraud_cms_desynpuf` pack's analyst role deliberately excluded the Dashboard page (`enabled_pages` — supervisor role owned it); that was existing role-gating behavior, not a workbench-reshape regression. The `feat/alerts-durable-read-model` branch removed the exclusion — `roles.analyst.pages` now includes `dashboard` on the CMS, food-supply-chain, and legacy medicare packs (`backend/config/defaults/*.yaml`, alerts.36) — because the durable alert-history read model makes dashboard metrics meaningful for analysts, not just supervisors. This note is retained as history; do not re-flag the analyst-role-excludes-Dashboard behavior as a discovery going forward.

### Code touch points
- `chili_app/src/pages/InvestigationWorkbenchPage.tsx`, `AlertFeedPage.tsx`, `DashboardPage.tsx`, `pages.css` (modify)
- `chili_app/src/components/investigation/EntityDossierHeader.tsx`, `SignalBand.tsx`, `AnomalyTrendPanel.tsx`, `EntityPolicyPanel.tsx`, `ClusterMembershipPanel.tsx` (new)
- `chili_app/src/components/investigation/GraphCanvas.tsx`, `EvidencePackViewer.tsx` (modify)
- `chili_app/src/components/charts/AttributionBars.tsx` (new)
- `chili_app/src/utils/graphStyles.ts`, `subgraph.ts` (modify), `triage.ts` (new)
- `chili_app/src/components/investigation/EntityDetailPanel.tsx(+.module.css)`, `EvidencePanel.tsx(+.module.css)`, `TimelinePanel.tsx` (deleted, `af14736`)
- Full test suites under `chili_app/src/**/__tests__/`

---

## Story frontend.28: Workbench dossier phase-2 surfaces — Timeline tab, peer-comparison bars, cluster centrality ordering

**ID:** frontend.28
**Status:** planned
**Prerequisites:** []
**Unblocks:** []
**Estimated size:** L
**Spec:** docs/superpowers/specs/2026-07-23-sprint28-u1-workbench-reshape-design.md (§6)

**As a** fraud analyst using the entity dossier,
**I need** a detection-events timeline, peer-comparison bars (entity vs. p50/p90), and centrality-ordered cluster membership,
**so that** I get the mockup's remaining persuasive surfaces once their backing data exists, instead of the workbench silently lacking them forever.

### Current State
U1's design pass (§6, "Phase 2 / out of sprint") identified three dossier surfaces the IntegrityAI mockup carries that U2 (Sprint 2026-28, frontend.27) deliberately did not build, because none has a backing API today:
- **Timeline tab** — the mockup's "smoking gun" ledger (trigger event → AI detection → analyst assignment) needs a unified detection-events feed. Today, alert history, policy-item status transitions, and anomaly `detected_at` timestamps live in three separate stores with no joining endpoint; `InvestigationWorkbenchPage.tsx`'s tab set (Signals/Network/Policy/Evidence) has no Timeline entry.
- **Peer-comparison bars** (entity vs. p50/p90) — `backend/analytics/peerstats` persists per-entity z-scores as risk-factor signals (`weekly_carrier_billing`, etc.), not the underlying peer distribution (p50/p90) needed to render a comparison bar; no endpoint returns it.
- **Cluster centrality ordering** — `chili_app/src/components/investigation/ClusterMembershipPanel.tsx` (Sprint 2026-28 U2) orders clusters by `anomaly_score` then member count only, because `ClusterResult` (`chili_app/src/api/contracts.ts:239`, backed by `backend/analytics/gnn/models.py`'s `ClusterSummary`) carries no per-member `centrality_score`. The value itself is not missing platform-wide — `agent.coordinator._write_analytics_properties_to_graph` already writes `centrality_score` onto individual graph entity properties (see `docs/backlog/analytics.md` story analytics.24) — but the clusters route the membership panel reads from does not expose it per-member, and resolving it via N per-entity property fetches for every visible member is not a UI-side fix.

### Acceptance Criteria
- [ ] A backend detection-events story is chartered (new analytics/monitoring module story, not yet created) defining a unified `GET .../detection-events` shape joining alert-lifecycle, policy-item transitions, and anomaly `detected_at`; a Timeline tab is added to `InvestigationWorkbenchPage.tsx`'s capability-gated tab set once it exists.
- [ ] A backend peer-distribution story is chartered (new `analytics/peerstats` module story, not yet created) exposing p50/p90 (or full distribution) per metric per peer group; `AttributionBars`-style signed comparison bars render entity-vs-peer once the endpoint exists.
- [ ] `ClusterResult` (or a members sub-resource) exposes `centrality_score` per member; `ClusterMembershipPanel.tsx`'s ordering gains a centrality-desc option once the field lands (cross-edge: `docs/backlog/analytics.md` analytics.24 or a follow-on story on the `/analytics/gnn/clusters` route).
- [ ] None of the above is faked with client-side approximations in the interim — the dossier's Signals/Network/Policy/Evidence tabs stay exactly as Sprint 2026-28 U2 shipped them until real data exists.

### Verification
- N/A until a backend story lands; this entry exists to fence phase-2 scope so it isn't silently forgotten, per the U1 design's own §6 instruction to record it at U2 closeout.

### Code touch points
- `chili_app/src/pages/InvestigationWorkbenchPage.tsx` (modify — Timeline tab, once chartered)
- `chili_app/src/components/investigation/ClusterMembershipPanel.tsx` (modify — centrality ordering, once chartered)
- `chili_app/src/components/charts/AttributionBars.tsx` or a new peer-comparison component (modify/new, once chartered)
- New backend stories under `docs/backlog/analytics.md` (or `monitoring.md`) for the detection-events feed and peer-distribution endpoint (not yet created)

---

## Story frontend.29: Dormant predicted-link rendering — waiting on the GNN write-back transport

**ID:** frontend.29
**Status:** planned
**Prerequisites:** [analytics.24]
**Unblocks:** []
**Estimated size:** S
**Spec:** docs/superpowers/specs/2026-07-23-sprint28-u1-workbench-reshape-design.md (§7)

**As a** fraud analyst inspecting the entity network,
**I need** GNN-predicted relationships to render as dashed, confidence-labeled links on the graph canvas,
**so that** I can see the model's speculative connections distinct from confirmed ones — once the backend actually produces them.

### Current State
Sprint 2026-28 U2 (frontend.27) shipped the canvas-side support **dormant and unwired to any real data**, verified deliberately at U2's start (`docs/superpowers/plans/2026-07-23-sprint28-u2-workbench-reshape.md` Global Constraints): `chili_app/src/utils/graphStyles.ts` exports `isPredictedRelationship(rel)` (reads `metadata.predicted === true`), `predictedConfidenceFor(rel)` (reads `metadata.confidence`), `PREDICTED_LINK_COLOR`, and `PREDICTED_LINK_DASH`; `GraphCanvas.tsx` renders any relationship carrying `metadata.predicted === true` as a dashed purple link with confidence in the tooltip. **No relationship in any live payload ever carries that metadata** — `docs/backlog/analytics.md` story analytics.24 documents the exact gap: `agent.coordinator` computes `GnnAnalysisResponse.predicted_links` every pipeline run but never persists them anywhere (not onto relationship metadata, not onto a queryable route) — "`predicted_neighbor_ids` is never written back" is analytics.24's own words for this. Until analytics.24 (or an equivalent write-back story) ships, the dormant rendering path is exercised only by tests with synthetic metadata, never real data.

### Acceptance Criteria
- [ ] `docs/backlog/analytics.md` story analytics.24 (or a successor) ships the write-back: either `metadata.predicted`/`metadata.confidence` on persisted relationships (preferred — renders through the existing neighborhood fetch, no new endpoint) or an equivalent predicted-links shape on the `/analytics/gnn/clusters` route.
- [ ] Once shipped, a live-data Playwright assertion (extending `chili_app/e2e/investigation-workbench.spec.ts`) confirms a real predicted link renders dashed with a confidence tooltip against the full stack — the existing unit tests already cover the rendering logic against synthetic fixtures, so this AC is about closing the "real data" gap, not writing new component code.
- [ ] No change to `GraphCanvas.tsx`/`graphStyles.ts` is anticipated — this story is expected to be backend-only plus one e2e assertion.

### Verification
- Backend: whatever `analytics.24`'s own Verification section specifies for the write-back.
- Frontend: `cd chili_app && npm run test:e2e -- investigation-workbench` shows a real dashed predicted link once seed/demo data includes one.

### Code touch points
- `backend/agent/coordinator.py` (analytics.24's scope — write predicted-link metadata back onto relationships)
- `chili_app/e2e/investigation-workbench.spec.ts` (modify — add the live-data assertion once real predicted links exist)

---

## Story frontend.30: Give `/policy` a first-class nav placement (or record the direct-URL posture)

**ID:** frontend.30
**Status:** planned
**Prerequisites:** []
**Unblocks:** []
**Estimated size:** S

**As a** fraud analyst working the policy queue,
**I need** the Policy Intelligence page to be reachable from the sidebar (or its direct-URL-only status to be a recorded product decision),
**so that** a core demo surface isn't a page you can only reach by knowing its URL.

### Current State
Found during Sprint 2026-28 D1 (presenter-script verification, adjudicated
non-blocking): on the `medicare_fraud_cms_desynpuf` pack, `/policy` is not in
any role's `enabled_pages`, so `chili_app/src/lib/access.ts` treats it as an
unmatched route — it renders fine when visited directly (the demo script and
`make demo-cms` print the URL) but shows no sidebar nav entry and no role gates
it. The page itself (`PolicyIntelligencePage.tsx`) is fully functional against
live data (2046 items on the 1% TN subset). This is a pack-config decision, not
a code defect: adding `policy` to `enabled_pages`/role `pages` in
`backend/config/defaults/*.yaml` is all it takes to surface it.

### Acceptance Criteria
- [ ] Decision recorded: either `policy` is added to the appropriate packs' `enabled_pages` + role `pages` (analyst at minimum on the CMS pack), or this direct-URL posture is documented in `docs/demo/README.md` and the pack YAML comments as intentional.
- [ ] If surfaced: sidebar shows the Policy entry under the granted roles across the CMS packs; `chili_app/e2e/demo-walkthrough.spec.ts` navigates via the sidebar instead of a raw `page.goto`.
- [ ] Existing nav-less direct rendering keeps working either way (deep links from `make demo-cms` output must not break).

### Verification
- `make dev` + browser: sidebar shows/omits Policy per the decision; `/policy?kb=<id>` still renders standalone.
- `cd chili_app && npm run test:e2e -- demo-walkthrough` green.

### Code touch points
- `backend/config/defaults/medicare_fraud_cms_desynpuf.yaml` (modify — `enabled_pages`/roles, if surfaced)
- `chili_app/e2e/demo-walkthrough.spec.ts` (modify — sidebar navigation, if surfaced)
- `docs/demo/README.md` (modify — posture note, if not surfaced)
