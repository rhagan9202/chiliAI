# Module: frontend (chili_app)

**Verified against codebase:** 2026-05-28 — **stale as of 2026-08-06**
**Source:** `chili_app/src/`

> The page table and `src/api/` client list below predate the SAFE-CMS surge and
> the UX audit. Missing at minimum: `/governance` (`GovernancePage.tsx`),
> `/housing`, `/scorecards/:runId`, `NotFoundPage`, and ~10 api-client modules.
> The `PolicyIntelligencePage` hook list names `usePolicyGaps`, `usePolicyGap`,
> `usePolicyGapCases` and `useCreatePolicyBrief`, all of which were removed (see
> `backend/policy/README.md`). `chili_app/src/app/router.tsx` is the ground truth.

## Purpose

React 19 SPA serving as the analyst workbench. Renders navigation and feature gates from `GET /config/features` / `GET /config/domain`. Built with Vite 8, TypeScript strict mode, React Router v8, and TanStack Query.

---

## Router (`src/app/router.tsx`)

`AppProviders` wraps the app with `QueryClientProvider` and `SessionProvider`; authenticated shell routes are wrapped in `<AuthGuard>`.

| Path | Component | Notes |
|------|-----------|-------|
| `/login` | `Login` | No auth guard |
| `/` | → `/dashboard` | Redirect |
| `/dashboard` | `DashboardPage` | |
| `/alerts` | `AlertFeedPage` | |
| `/investigation` | `InvestigationWorkbenchPage` | |
| `/investigation/:entityId` | `InvestigationWorkbenchPage` | Entity preselected |
| `/cases` | `CaseManagementPage` | |
| `/knowledge-bases` | `KnowledgeBaseLibraryPage` | Library — KB cards + create panel |
| `/knowledge-bases/:kbId` | `KnowledgeBaseWorkspacePage` → `OverviewSection` | Workspace root (index route, no path segment) |
| `/knowledge-bases/:kbId/add` | `KnowledgeBaseWorkspacePage` → `AddDataSection` | |
| `/knowledge-bases/:kbId/data` | `KnowledgeBaseWorkspacePage` → `DataSection` | Focused document in `?document=` |
| `/knowledge-bases/:kbId/runs` | `KnowledgeBaseWorkspacePage` → `RunsSection` | |
| `/knowledge-bases/:kbId/settings` | `KnowledgeBaseWorkspacePage` → `SettingsSection` | |
| `/knowledgebases` | → `/knowledge-bases` (query string preserved) | `LegacyKnowledgeBasesRedirect`; `?kb=<id>[&document=<id>[&chunk=<n>]]` resolves further, into the matching workspace address |
| `/policy` | `PolicyIntelligencePage` | |
| `/rag-chat` | `RagChatPage` | |
| `/configuration` | `ConfigurationPage` | |
| `*` (authenticated) | `PagePlaceholder` | Domain-config-registered pages without components |
| `*` (unauthenticated) | → `/` | |

---

## Pages (`src/pages/`)

Last verified: 2026-05-28, except the three rows below (Dashboard, Alert
Feed, Investigation Workbench) — **re-verified 2026-07-23** after Sprint
2026-28 U2's workbench reshape (`docs/backlog/frontend.md` story
frontend.27); the rest of this table is unchanged and carries the older
verification date.

| File | Route | Primary API calls | Stores used |
|------|-------|-------------------|-------------|
| `DashboardPage.tsx` | `/dashboard` | `useAnalyticsOverview`, `useAlerts`, `useGnnClusters`, `useMetricTimeseries`, `useRiskScores`, `useKnowledgeBases`, `useWorkflows` | none (local `useState` for the active tab only) |
| `AlertFeedPage.tsx` | `/alerts` | `useAlerts`, `useAcknowledgeAlert`, `useCases`, `usePromoteAlertToCase`, `useEvidencePack`, `useInvestigationNeighborhood` (real depth-1 subgraph for the evidence expansion, since U2), `usePolicyItems` (policy chips, since U2) | none |
| `InvestigationWorkbenchPage.tsx` | `/investigation`, `/investigation/:entityId` | `useInvestigationEntitySearch`, `useInvestigationEntity`, `useInvestigationNeighborhood`, `useRiskScore`, `useTimeseries`, `useGnnClusters` (cluster overlay/membership), `usePolicyItems` (via `EntityPolicyPanel`, POLICY tab) | none — KB id and entity id are URL-driven (`?kb=`, `:entityId`), not store-backed, despite the "Drift note" below predating this |
| `CaseManagementPage.tsx` | `/cases` | `useCases`, `useCase`, `useCreateCase`, `useUpdateCase`, `useCaseFeedback` | `uiStore` |
| `KnowledgeBaseLibraryPage.tsx` | `/knowledge-bases` | `useKnowledgeBases`, `useDomainConfig` | none — no "selected" KB here; opening one is navigation into its workspace |
| `KnowledgeBaseWorkspacePage.tsx` + `features/kb/{overview,add-data,data,runs,settings}/*.tsx` | `/knowledge-bases/:kbId[/add\|/data\|/runs\|/settings]` | `useKnowledgeBase`, `useKnowledgeBaseDocuments`, `uploadDocuments`, `useIngestionDraftStore`, `useActiveKnowledgeBase` | `ingestionDraftStore` (Add data staging, keyed by `kbId`) — the knowledge base itself comes from the route path (`useActiveKnowledgeBase`'s top-ranked precedence level, above `?kb=`), not a deep-link fallback; a `?kb=[&document=]` address on the pre-split path redirects here rather than being read directly |
| `PolicyIntelligencePage.tsx` | `/policy` | `usePolicyGaps`, `usePolicyGap`, `usePolicyGapCases`, `useCreatePolicyBrief` | — |
| `RagChatPage.tsx` | `/rag-chat` | `createConversation`, `sendMessage`, `streamMessage` | `chatStore`, `appStore` |
| `ConfigurationPage.tsx` | `/configuration` | `useDomainConfig`, `getDomainConfigSchema` | — |
| `Login.tsx` | `/login` | `/auth/login` redirect | — |
| `PagePlaceholder.tsx` | `*` (authenticated) | None | — |

Since U2 (Sprint 2026-28), the Investigation Workbench renders a
capability-gated `Tabs` strip (Signals / Network / Policy / Evidence):
Signals is present only when `risk_scoring` or `timeseries` is on, Network
is always present, and Policy + Evidence are present only when
`explainability` is on — instead of a flat vertical card stack. When only
one tab survives the gating, the strip is dropped entirely and that tab's
panel renders directly (final-review fix, 2026-07-23; regression-covered by
a unit test asserting no `tablist`/`tab` renders and the Network panel
content renders on its own). The three previously-orphaned components
`EntityDetailPanel.tsx`, `EvidencePanel.tsx`, and `TimelinePanel.tsx` were
deleted outright (`af14736`) rather than wired up — there is no Timeline
tab (needs a detection-events API; tracked as `docs/backlog/frontend.md`
story frontend.28).

---

## API Client (`src/api/`)

Last verified: 2026-05-28.

Base utilities in `src/lib/apiClient.ts`. `src/api/client.ts` re-exports `apiFetch`, `apiPost`, `apiPatch`, `apiDelete`, `apiUpload` wrappers. API contract types are generated from backend OpenAPI into `src/lib/api/schema.ts`; `src/api/contracts.ts` aliases and tightens those generated schemas for frontend use.

| File | Backend resource | Key functions / hooks |
|------|-----------------|-----------------------|
| `client.ts` | Base fetch wrappers | `apiFetch`, `apiPost`, `apiPatch`, `apiDelete`, `apiUpload` |
| `contracts.ts` | Shared TS types | Frontend aliases over generated `src/lib/api/schema.ts` OpenAPI schemas |
| `knowledgebases.ts` | `/knowledgebases` | `useKnowledgeBases`, `useKnowledgeBase`, `useKnowledgeBaseDocuments`, `createKnowledgeBase`, `deleteKnowledgeBase`, `uploadDocuments` |
| `alerts.ts` | `/alerts` | `useAlerts`, `useAlert`, `useAcknowledgeAlert`, `getAlerts`, `getAlert`, `acknowledgeAlert` |
| `cases.ts` | `/cases` | `useCases`, `useCase`, `useCreateCase`, `useUpdateCase`, `useCaseFeedback` |
| `evidence.ts` | `/evidence-packs` | `useEvidencePack`, `getEvidencePack` |
| `graph.ts` | `/graph/entities` | `useGraphEntity`, `getGraphEntity` |
| `rag.ts` | `/chat` | `useConversation`, `createConversation`, `sendMessage`, `streamMessage` (SSE) |
| `records.ts` | `/records` | `uploadRecordFile`, `pushRecords` |
| `workflows.ts` | `/workflows` | `useWorkflows`, `getWorkflows` |
| `analytics.ts` | `/analytics` | `useAnalyticsOverview`, `useRiskScore`, `useTimeseries`, `getAnalyticsOverview`, `getRiskScore`, `getTimeseries` |
| `config.ts` | `/config/domain`, `/config/features` | `useDomainConfig`, `useDomainFeatures`, `getDomainConfig`, `getDomainFeatures`, `getDomainConfigSchema` |
| `investigation.ts` | `/investigation` | `useInvestigationEntitySearch`, `useInvestigationEntity`, `useInvestigationNeighborhood`, `searchInvestigationEntities`, `getInvestigationEntity`, `getInvestigationNeighborhood` |
| `policy.ts` | `/policy` | `usePolicyGaps`, `usePolicyGap`, `usePolicyGapCases`, `useCreatePolicyBrief` |
| `realtime.ts` | SSE `/events/stream` | `useRealtimeWorkspaceStream` (SSE stream consumer) |

All data-fetching hooks use `@tanstack/react-query`. Query keys follow `[resource, scope, ...params]` pattern. Mutation hooks use `useMutation` with `queryClient.invalidateQueries` on success.

---

## Stores (`src/stores/`)

Last verified: 2026-05-28. All stores use Zustand v4.

### `appStore.ts` — `useAppStore`

```typescript
interface AppState {
  sidebarOpen: boolean
  selectedEntityId: string | null
  activeKnowledgeBaseId: string | null
  toggleSidebar: () => void
  selectEntity: (id: string | null) => void
  setActiveKnowledgeBase: (id: string | null) => void
}
```

### `chatStore.ts` — `useChatStore`

```typescript
interface ChatMessage {
  id: string; role: ChatRole; content: string
  citations: string[]; pending: boolean; createdAt: number
}
interface ChatConversation { id: string; messages: ChatMessage[] }
interface ChatState {
  conversations: Record<string, ChatConversation>
  activeConversationId: string | null
  setActiveConversation(conversationId: string): void
  appendMessage(conversationId: string, message: ChatMessage): void
  appendAssistantToken(conversationId: string, messageId: string, token: string): void
  finalizeAssistantMessage(conversationId: string, messageId: string, citations: string[]): void
  failAssistantMessage(conversationId: string, messageId: string, errorText: string): void
  resetConversation(conversationId: string): void
}
```

### `ingestionDraftStore.ts` — `useIngestionDraftStore`

Staging work per knowledge base, keyed by id — no page-chrome state lives
here. The six-step ingestion wizard stepper (and the `currentStep` /
`IngestionStepId` state that drove it, and the store itself — formerly
`ingestionStudioStore.ts`) was deleted in the phase-2 IA split: stage position
is the URL, not store state. `KnowledgeBaseManagerPage.tsx` is gone; the five
stages are now routed sections (`overview`, `add`, `data`, `runs`, `settings`)
under `/knowledge-bases/:kbId/...`, rendered by `KnowledgeBaseWorkspacePage.tsx`
and the components in `features/kb/`. Backend submission errors are read directly off the mutation that
produced them (`uploadMutation.error`, `uploadRecordFileMutation.error`,
`pushRecordsMutation.error`) rather than stored, so they clear on retry
without anyone remembering to clear them; document/row validation
(`validateDocumentFiles`, `validateRecordRows`) is a memoized derivation of
the staged content, not stored state either.

```typescript
type IngestionDraft = {
  sourceType: IngestionSourceType | null
  selectedFeedName: string | null
  pendingFiles: File[]
  pendingRecordFile: File | null
  parsedRows: Record<string, unknown>[]
  parseIssues: ValidationIssue[]      // issues produced by the parse itself
}

type IngestionDraftState = {
  draftsByKb: Record<string, IngestionDraft>
  // Actions: updateDraft(kbId, patch), clearDraft(kbId), reset()
}
```

### `uiStore.ts` — `useUiStore`

```typescript
type UiState = {
  accessNotice: string | null
  aiPanelOpen: boolean              // default: true
  lastRealtimeEventAt: string | null
  realtimeConnected: boolean
  selectedRole: string | null
  selectedEntityId: string | null
  sidebarCollapsed: boolean
  setAccessNotice(message: string | null): void
  setLastRealtimeEventAt(timestamp: string | null): void
  setRealtimeConnected(connected: boolean): void
  setSelectedRole(role: string | null): void
  toggleAiPanel(): void
  toggleSidebar(): void
  setSelectedEntityId(entityId: string | null): void
}
```

**Drift note:** Both `appStore` and `uiStore` track `selectedEntityId`. They are distinct — `appStore.selectedEntityId` is set by the investigation workbench, `uiStore.selectedEntityId` is the UI-layer selection state. Callers should verify which store they need; this duplication may cause stale-state bugs.

---

## Shared Components (`src/components/`)

Last verified: 2026-05-20 (file list only — props not exhaustively verified).

### Layout
| Component | File | Purpose |
|-----------|------|---------|
| `AppShell` | `layout/AppShell.tsx` | Root layout: sidebar + topbar + outlet |
| `Sidebar` | `layout/Sidebar.tsx` | Navigation driven by `DomainConfig.ui.navigation.pages` |
| `TopBar` | `layout/TopBar.tsx` | Header with user role indicator and AI panel toggle |
| `AiAssistantPanel` | `layout/AiAssistantPanel.tsx` | Slide-out AI assistant panel; `uiStore.aiPanelOpen` controls visibility |

### Auth
| Component | File | Purpose |
|-----------|------|---------|
| `AuthGuard` | `components/AuthGuard.tsx` | Redirects to `/login` if no session; reads from `SessionContext` |

### Common UI
`ErrorBoundary`, `LoadingSpinner`, `Skeleton`, `Toast`, `ConfirmDialog`, `ConnectionStatus` — all in `components/common/`.

Toast state: `components/common/toastStore.ts` (internal Zustand store, not exported to pages).

### Domain-adaptive UI
| Component | File | Purpose |
|-----------|------|---------|
| `RiskBadge` | `ui/RiskBadge.tsx` | Severity/risk color chip |
| `ConfidenceBar` | `ui/ConfidenceBar.tsx` | Horizontal progress bar for confidence scores |
| `FilterBar` | `ui/FilterBar.tsx` | Generic filter row component |

### Investigation dossier components (added/changed Sprint 2026-28 U2, `investigation/`)
This list is not exhaustive of the whole `components/investigation/` and
`components/charts/` directories (e.g. the pre-existing `GraphCanvas.tsx`
and `EvidencePackViewer.tsx` are not re-listed here) — it covers what U2
added or removed, since that is what this reconciliation pass verified.

| Component | File | Purpose |
|-----------|------|---------|
| `EntityDossierHeader` | `investigation/EntityDossierHeader.tsx` | Entity identity (via `domainDisplay.ts`) + Oxanium risk numeral + confidence bar; availability-aware |
| `SignalBand` | `investigation/SignalBand.tsx` | "AI ANALYSIS · N RISK SIGNALS" callout listing risk factors with signed contribution bars |
| `AnomalyTrendPanel` | `investigation/AnomalyTrendPanel.tsx` | Timeseries chart + red anomaly markers (extracted from the page's former inline `ChartFrameInvestigation`) |
| `EntityPolicyPanel` | `investigation/EntityPolicyPanel.tsx` | Policy items filtered by `target_kind`/`target_ref`, critical-item callout |
| `ClusterMembershipPanel` | `investigation/ClusterMembershipPanel.tsx` | GNN cluster list beside `GraphCanvas`; select/highlight interplay |
| `AttributionBars` | `charts/AttributionBars.tsx` | Signed horizontal SHAP-style feature-attribution bars; consumed only by `EvidencePackViewer` (the dossier's risk-factor band is `SignalBand`, not `AttributionBars`) |
| ~~`EntityDetailPanel`~~ | ~~`investigation/EntityDetailPanel.tsx`~~ | **Deleted** (`af14736`) — was an orphan, never routed; superseded by `EntityDossierHeader` |
| ~~`EvidencePanel`~~ | ~~`investigation/EvidencePanel.tsx`~~ | **Deleted** (`af14736`) — was an orphan, never routed; superseded by the live `EvidencePackViewer` |
| ~~`TimelinePanel`~~ | ~~`investigation/TimelinePanel.tsx`~~ | **Deleted** (`af14736`) — was an orphan, never routed; no replacement yet (needs a detection-events API, `docs/backlog/frontend.md` frontend.28) |

---

## TypeScript Types (`src/types/`)

| File | Purpose |
|------|---------|
| `api.ts` | Frontend mirrors of backend API response types (KnowledgeBase, Alert, Entity, etc.) |
| `domainConfig.ts` | TypeScript mirror of `backend/config/schema.py::DomainConfig` |
| `config.ts` | Frontend app config types |
| `dashboard.ts` | Dashboard widget data types |
| `wsEvents.ts` | WebSocket event payload types |

---

## Contexts (`src/contexts/`)

`SessionProvider` — calls `GET /auth/me` on mount, exposes session status/user/sign-out through `useSession`. Domain config and feature data are fetched through TanStack Query hooks in `src/api/config.ts`, not a dedicated context provider.

---

## AuthGuard (`src/components/AuthGuard.tsx`)

Redirects to `/login` if `useSession()` reports `unauthenticated`; shows a loading status while the session probe is in flight.

---

## Test Locations

- Unit tests: `src/**/__tests__/` (Vitest)
- E2e tests: `chili_app/e2e/` (Playwright, 23 spec files as of 2026-07-24 — added `demo-walkthrough.spec.ts`, the D1 scripted-demo reference+live-mode walkthrough)

Commands:
```bash
npm run test:run    # Vitest single run
npm run test:e2e    # Playwright (starts Vite automatically)
```

---

## Key Frontend ↔ Backend Contract Points

| Frontend | Backend |
|----------|---------|
| `types/domainConfig.ts` | `config/schema.py::DomainConfig` |
| `types/api.ts` | `shared/types.py`, `api/contracts.py` |
| `api/rag.ts` SSE parsing | `api/routers/rag.py::_sse_event()` format |
| `api/config.ts` | `GET /config/domain`, `GET /config/features`, `GET /config/domain/schema` |
| Cookie `chiliai_session` | `api/middleware/auth.py::SESSION_COOKIE_NAME` |

---

## Frontend ↔ Backend Type Drift

**Verified against codebase:** 2026-05-28
**Sources:** `chili_app/src/lib/api/schema.ts`, `chili_app/src/api/contracts.ts`, `backend/api/contracts.py`

The previous hand-written drift table is obsolete. Frontend route-facing types now come from generated OpenAPI schemas in `src/lib/api/schema.ts`, with `src/api/contracts.ts` providing aliases such as `AlertListItem`, `EvidencePackResponse`, `KnowledgeBaseDocumentResponse`, `RiskScoreResponse`, and `TimeseriesResponse`.

Remaining caveat: `src/types/api.ts` still contains legacy/internal graph and KB mirrors used by some older components. New API clients should prefer `src/api/contracts.ts`; any use of `src/types/api.ts` should be checked against generated OpenAPI before expanding it.
