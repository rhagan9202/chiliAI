# Module: frontend (chili_app)

**Verified against codebase:** 2026-05-28
**Source:** `chili_app/src/`

## Purpose

React 19 SPA serving as the analyst workbench. Renders navigation and feature gates from `GET /config/features` / `GET /config/domain`. Built with Vite 8, TypeScript strict mode, React Router v7, and TanStack Query.

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
| `/knowledge-bases` | `KnowledgeBaseManagerPage` | |
| `/knowledgebases` | → `/knowledge-bases` | Back-compat redirect |
| `/policy` | `PolicyIntelligencePage` | |
| `/rag-chat` | `RagChatPage` | |
| `/configuration` | `ConfigurationPage` | |
| `*` (authenticated) | `PagePlaceholder` | Domain-config-registered pages without components |
| `*` (unauthenticated) | → `/` | |

---

## Pages (`src/pages/`)

Last verified: 2026-05-28.

| File | Route | Primary API calls | Stores used |
|------|-------|-------------------|-------------|
| `DashboardPage.tsx` | `/dashboard` | `useAnalyticsOverview`, `useAlerts`, `useRecentActivity`, `useRealtimeWorkspaceStream` | `uiStore`, `appStore` |
| `AlertFeedPage.tsx` | `/alerts` | `useAlerts`, `useAlert`, `useAcknowledgeAlert` | `uiStore` |
| `InvestigationWorkbenchPage.tsx` | `/investigation`, `/investigation/:entityId` | `useInvestigationEntitySearch`, `useInvestigationEntity`, `useInvestigationNeighborhood`, `useRiskScore`, `useTimeseries` | `appStore` (selectedEntityId, activeKnowledgeBaseId), `uiStore` |
| `CaseManagementPage.tsx` | `/cases` | `useCases`, `useCase`, `useCreateCase`, `useUpdateCase`, `useCaseFeedback` | `uiStore` |
| `KnowledgeBaseManagerPage.tsx` | `/knowledge-bases` | `useKnowledgeBases`, `useKnowledgeBaseDocuments`, `uploadDocuments`, `useIngestionStudioStore` | `ingestionStudioStore` |
| `PolicyIntelligencePage.tsx` | `/policy` | `usePolicyGaps`, `usePolicyGap`, `usePolicyGapCases`, `useCreatePolicyBrief` | — |
| `RagChatPage.tsx` | `/rag-chat` | `createConversation`, `sendMessage`, `streamMessage` | `chatStore`, `appStore` |
| `ConfigurationPage.tsx` | `/configuration` | `useDomainConfig`, `getDomainConfigSchema` | — |
| `Login.tsx` | `/login` | `/auth/login` redirect | — |
| `PagePlaceholder.tsx` | `*` (authenticated) | None | — |

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

### `ingestionStudioStore.ts` — `useIngestionStudioStore`

```typescript
type IngestionStudioState = {
  currentStep: IngestionStepId       // 'knowledge-base' | ... (from lib/ingestion/types.ts)
  sourceType: IngestionSourceType | null
  selectedFeedName: string | null
  pendingFiles: File[]
  pendingRecordFile: File | null
  parsedRows: Record<string, unknown>[]
  validationIssues: ValidationIssue[]
  receipts: IngestionReceiptEntry[]
  activeTimelineEntryId: string | null
  // Actions: setCurrentStep, setSourceType, setSelectedFeedName, setPendingFiles,
  //          setPendingRecordFile, setParsedRows, setValidationIssues, addValidationIssues,
  //          addReceipt, setActiveTimelineEntryId, reset
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
- E2e tests: `chili_app/e2e/` (Playwright, 17 tests)

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
