# Module: frontend (chili_app)

**Verified against codebase:** 2026-05-20
**Source:** `chili_app/src/`

## Purpose

React 19 SPA serving as the analyst workbench. Renders dynamically based on `DomainConfig` fetched from `GET /config/domain` at startup. Built with Vite 8, TypeScript strict mode, React Router v6.

---

## Router (`src/app/router.tsx`)

All authenticated routes are wrapped in `<AuthGuard>` and `<DomainConfigProvider>`.

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
| `/policy` | `PolicyIntelligencePage` | |
| `/rag-chat` | `RagChatPage` | |
| `/configuration` | `ConfigurationPage` | |
| `*` (authenticated) | `PagePlaceholder` | Domain-config-registered pages without components |
| `*` (unauthenticated) | → `/` | |

---

## Pages (`src/pages/`)

Last verified: 2026-05-20.

| File | Route | Primary API calls | Stores used |
|------|-------|-------------------|-------------|
| `DashboardPage.tsx` | `/dashboard` | `useAnalyticsOverview`, `useAlerts`, `useRecentActivity` | `uiStore`, `appStore` |
| `AlertFeedPage.tsx` | `/alerts` | `useAlerts`, `useAlert`, `useAcknowledgeAlert` | `uiStore` |
| `InvestigationWorkbenchPage.tsx` | `/investigation`, `/investigation/:entityId` | `useInvestigationEntitySearch`, `useInvestigationEntity`, `useInvestigationNeighborhood` | `appStore` (selectedEntityId, activeKnowledgeBaseId) |
| `CaseManagementPage.tsx` | `/cases` | `useCases`, `useCase`, `useCreateCase`, `useUpdateCase`, `useCaseFeedback` | `uiStore` |
| `KnowledgeBaseManagerPage.tsx` | `/knowledge-bases` | `useKnowledgeBases`, `useKnowledgeBaseDocuments`, `uploadDocuments`, `useIngestionStudioStore` | `ingestionStudioStore` |
| `PolicyIntelligencePage.tsx` | `/policy` | `usePolicyGaps`, `usePolicyGap`, `usePolicyGapCases`, `useCreatePolicyBrief` | — |
| `RagChatPage.tsx` | `/rag-chat` | `createConversation`, `sendMessage`, `streamMessage` | `chatStore`, `appStore` |
| `ConfigurationPage.tsx` | `/configuration` | `useDomainConfig`, `getDomainConfigSchema` | — |
| `Login.tsx` | `/login` | `/auth/login` redirect | — |
| `PagePlaceholder.tsx` | `*` (authenticated) | None | — |

---

## API Client (`src/api/`)

Last verified: 2026-05-20.

Base utilities in `src/lib/apiClient.ts`. `src/api/client.ts` re-exports `apiFetch`, `apiPost`, `apiPatch`, `apiDelete`, `apiUpload` wrappers.

| File | Backend resource | Key functions / hooks |
|------|-----------------|-----------------------|
| `client.ts` | Base fetch wrappers | `apiFetch`, `apiPost`, `apiPatch`, `apiDelete`, `apiUpload` |
| `contracts.ts` | Shared TS types | All `*Response`, `*Request` type aliases — single source of truth for frontend API shapes |
| `knowledgebases.ts` | `/knowledgebases` | `useKnowledgeBases`, `useKnowledgeBase`, `useKnowledgeBaseDocuments`, `createKnowledgeBase`, `deleteKnowledgeBase`, `uploadDocuments` |
| `alerts.ts` | `/alerts` | `useAlerts`, `useAlert`, `useAcknowledgeAlert`, `getAlerts`, `getAlert`, `acknowledgeAlert` |
| `cases.ts` | `/cases` | `useCases`, `useCase`, `useCreateCase`, `useUpdateCase`, `useCaseFeedback` |
| `evidence.ts` | `/evidence-packs` | `useEvidencePack`, `getEvidencePack` |
| `graph.ts` | `/graph/entities` | `useGraphEntity`, `getGraphEntity` |
| `rag.ts` | `/chat` | `useConversation`, `createConversation`, `sendMessage`, `streamMessage` (SSE) |
| `records.ts` | `/records` | `uploadRecordFile`, `pushRecords` |
| `workflows.ts` | `/workflows` | `useWorkflows`, `getWorkflows` |
| `analytics.ts` | `/analytics` | `useAnalyticsOverview`, `useRiskScore`, `useEntityTimeseries`, `useRiskScores`, `useTimeseries`, `useGnnClusters` |
| `config.ts` | `/config/domain`, `/config/features` | `useDomainConfig`, `useDomainFeatures`, `getDomainConfig`, `getDomainFeatures`, `getDomainConfigSchema` |
| `investigation.ts` | `/investigation` | `useInvestigationEntitySearch`, `useInvestigationEntity`, `useInvestigationNeighborhood`, `searchInvestigationEntities`, `getInvestigationEntity`, `getInvestigationNeighborhood` |
| `policy.ts` | `/policy` | `usePolicyGaps`, `usePolicyGap`, `usePolicyGapCases`, `useCreatePolicyBrief` |
| `realtime.ts` | SSE `/events/workspace` | `useRealtimeSnapshot` (SSE stream consumer) |

All data-fetching hooks use `@tanstack/react-query`. Query keys follow `[resource, scope, ...params]` pattern. Mutation hooks use `useMutation` with `queryClient.invalidateQueries` on success.

---

## Stores (`src/stores/`)

Last verified: 2026-05-20. All stores use Zustand v4.

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
  aiPanelOpen: boolean              // default: true
  lastRealtimeEventAt: string | null
  realtimeConnected: boolean
  selectedRole: string | null
  selectedEntityId: string | null
  sidebarCollapsed: boolean
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

`DomainConfigProvider` — fetches `GET /config/domain` on mount, provides `DomainConfig` to all child components. Navigation and feature flags are driven from this context.

---

## AuthGuard (`src/components/AuthGuard.tsx`)

Redirects to `/login` if no session. Reads auth state from `appStore`.

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
| `contexts/DomainConfigContext` | `GET /config/domain` + `GET /config/features` |
| Cookie `chiliai_session` | `api/middleware/auth.py::SESSION_COOKIE_NAME` |

---

## Frontend ↔ Backend Type Drift

**Verified against codebase:** 2026-05-20
**Sources:** `chili_app/src/types/api.ts` vs `backend/shared/types.py` + `backend/api/contracts.py`

| Frontend type | Field | Backend counterpart | Drift description | Wire impact |
|--------------|-------|---------------------|-------------------|-------------|
| `Alert` (`types/api.ts`) | `updated_at?: string \| null` | `shared/types.py::Alert.updated_at: datetime \| None` | Present in both; frontend uses `string` not `Date`. Consistent with ISO serialization. | No issue |
| `Alert` (`types/api.ts`) | `acknowledged: boolean` | `shared/types.py::Alert.acknowledged: bool` | Matches. Backend comment marks this field deprecated in favor of `status`. | Frontend may surface stale behavior if it relies on `acknowledged` instead of `status`. |
| `Alert` (`types/api.ts`) | `kb_id?: string \| null` | `shared/types.py::Alert` — no `kb_id` field | **Drift.** Frontend defines `kb_id` as optional field; backend `Alert` has no such field. | Safe: optional client-side extension, will never be populated from API responses unless a future backend adds it. Comment in frontend marks it "E9-S08 Alert Feed". |
| `Alert` (`types/api.ts`) | `message?: string \| null` | `shared/types.py::Alert` — no `message` field | **Drift.** Frontend adds `message`; backend uses `title` + `reasoning`. | Safe: optional, never populated by current API. |
| `Alert` (`types/api.ts`) | `acknowledged_by?: string \| null` | `shared/types.py::Alert` — no `acknowledged_by` field | **Drift.** Frontend adds `acknowledged_by`; backend has `resolved_by` only. | Safe: optional, never populated. |
| `Alert` (`types/api.ts`) | `properties?: Record<string, unknown> \| null` | `shared/types.py::Alert` — no `properties` field | **Drift.** Frontend adds generic `properties` bag; backend has none. | Safe: optional, never populated. |
| `Alert` (`types/api.ts`) | `severity: AlertSeverity \| string` | `shared/types.py::Alert.severity: str` | Frontend widens to `AlertSeverity \| string` union. Backend is bare `str` (no enum validation). Loose on both sides. | No 422 risk. |
| `AlertListResponse` (`types/api.ts`) | `{ items: Alert[], total: number }` | `api/contracts.py::AlertListResponse` → `{ items: list[AlertListItem], page: PageInfo }` | **Shape mismatch.** Frontend expects flat `total: number`; backend returns `page: PageInfo {page, page_size, total_items}`. Frontend `Alert` maps to backend `AlertListItem` (which adds `entity_label`, `confidence`, `tags`). | **Drift.** Frontend `Alert` is missing `entity_label: string`, `confidence: float`, `tags: list[str]` that backend `AlertListItem` carries. These fields will be `undefined` in the frontend. |
| `DocumentSummary` (`types/api.ts`) | no `knowledge_base_id` field | `api/contracts.py::DocumentSummary.knowledge_base_id: str` | Frontend `DocumentSummary` omits `knowledge_base_id`. | Safe if the field is not needed client-side, but callers relying on it will get `undefined`. |
| `KnowledgeBaseListResponse` (`types/api.ts`) | `{ items: KnowledgeBase[], total: number }` | `api/contracts.py::KbListResponse` → `{ items: list[KnowledgeBase], total: int }` | Matches structurally. | No issue |
| `EvidencePack` (`types/api.ts`) | `subgraph_nodes: string[]`, `subgraph_edges: string[]` | `shared/types.py::EvidencePack.subgraph_nodes`, `subgraph_edges` | Matches. | No issue |
| `EvidencePack` (`types/api.ts`) | `source_documents: string[]` | `shared/types.py::EvidencePack.source_documents: list[str]` | Matches. | No issue |
| `EvidencePack` (`types/api.ts`) | No `items` or `policy_citations` fields | `api/contracts.py::EvidencePackResponse` has `items: list[EvidenceItemResponse]`, `policy_citations`, `subgraph_node_ids`, `subgraph_edge_ids` | **Drift.** Frontend `EvidencePack` mirrors `shared/types.py::EvidencePack` (the internal model), not `api/contracts.py::EvidencePackResponse` (the API shape). The `/evidence-packs/{id}` route returns `EvidencePackResponse` which uses `subgraph_node_ids`/`subgraph_edge_ids` (not `subgraph_nodes`/`subgraph_edges`). | **Wire mismatch.** Frontend will fail to read `subgraph_node_ids` and will see `undefined` for `items` and `policy_citations`. |
| `Entity` / `Relationship` (`types/api.ts`) | Matches `shared/types.py::Entity`, `Relationship` | — | Structurally correct. | No issue |
