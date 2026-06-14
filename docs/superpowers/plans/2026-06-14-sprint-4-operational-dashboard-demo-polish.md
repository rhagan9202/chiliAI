# Sprint 4 Operational Dashboard And Demo Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the dashboard a demo-ready operational command center with clickable KPIs, queue health, analytics summaries, and a verified dashboard to ingest/run to alert to case to RAG explanation path.

**Architecture:** Reuse existing backend contracts and routes where possible. Add typed frontend analytics hooks for collection summaries, make dashboard KPIs route-aware, and keep demo polish inside existing pages rather than introducing global graph drawers, WebSocket UI, or config mutation.

**Tech Stack:** React 19, React Router, TanStack Query, Vite, Vitest, FastAPI analytics routes, pytest/pyright only if backend contracts are touched.

**Spec:** [docs/superpowers/specs/2026-06-14-demoable-workflow-increments-design.md](../specs/2026-06-14-demoable-workflow-increments-design.md)

---

## File Structure

- Modify: `chili_app/src/api/contracts.ts` — add aliases for collection analytics schemas if missing.
- Modify: `chili_app/src/api/analytics.ts` — add collection analytics API helpers/hooks.
- Create/modify: `chili_app/src/api/__tests__/analytics.test.ts`
- Modify: `chili_app/src/components/ui/KpiCard.tsx` — support optional link rendering.
- Modify: `chili_app/src/pages/DashboardPage.tsx` — clickable KPIs, queue health, analytics summaries.
- Modify: `chili_app/src/pages/pages.css` — dashboard summary layout only if needed.
- Modify: `chili_app/src/pages/__tests__/DashboardPage.test.tsx`
- Review: `backend/api/routers/analytics.py` — remove the collection analytics future-development comment only after UI consumes those routes.
- Review/modify only if needed: `backend/tests/api/test_analytics_router.py`

## Task 1: Add Typed Collection Analytics Hooks

**Files:**
- Modify: `chili_app/src/api/contracts.ts`
- Modify: `chili_app/src/api/analytics.ts`
- Create/modify: `chili_app/src/api/__tests__/analytics.test.ts`
- Review: `backend/api/routers/analytics.py`

- [ ] **Step 1: Add failing query-serialization tests**

```ts
await getRiskScores({ knowledgeBaseId: 'kb-1', entityType: 'provider', limit: 5 })
expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/analytics/risk-scores?kb_id=kb-1&entity_type=provider&limit=5'), expect.anything())

await getMetricTimeseries({
  knowledgeBaseId: 'kb-1',
  metric: 'claim_volume',
  start: '2026-05-15T00:00:00.000Z',
  end: '2026-06-14T00:00:00.000Z',
})
expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/analytics/timeseries?'), expect.anything())

await getGnnClusters('kb-1')
expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/analytics/gnn/clusters?kb_id=kb-1'), expect.anything())
```

- [ ] **Step 2: Run failing API tests**

Run:

```bash
cd chili_app
npm run test:run -- src/api/__tests__/analytics.test.ts
```

Expected: tests fail because helper functions do not exist.

- [ ] **Step 3: Add response type aliases in `contracts.ts`**

```ts
export type RiskScoreListResponse = Schemas['RiskScoreListResponse']
export type MetricTimeseriesResponse = Schemas['MetricTimeseriesResponse']
export type GnnClusterResponse = Schemas['GnnClusterResponse']
```

- [ ] **Step 4: Add helpers and query keys in `analytics.ts`**

```ts
export type RiskScoresFilters = {
  knowledgeBaseId: string
  entityType?: string
  limit?: number
}

export function getRiskScores(filters: RiskScoresFilters): Promise<RiskScoreListResponse> {
  const params = new URLSearchParams({ kb_id: filters.knowledgeBaseId })
  if (filters.entityType) params.set('entity_type', filters.entityType)
  if (filters.limit !== undefined) params.set('limit', String(filters.limit))
  return apiFetch<RiskScoreListResponse>(`/analytics/risk-scores?${params}`)
}
```

Add equivalent helpers for `getMetricTimeseries` and `getGnnClusters`, plus `useRiskScores`, `useMetricTimeseries`, and `useGnnClusters` with `enabled: Boolean(knowledgeBaseId)`.

- [ ] **Step 5: Run analytics client tests**

Run:

```bash
cd chili_app
npm run test:run -- src/api/__tests__/analytics.test.ts
```

Expected: API helper tests pass.

## Task 2: Make Dashboard KPIs Clickable Drilldowns

**Files:**
- Modify: `chili_app/src/components/ui/KpiCard.tsx`
- Modify: `chili_app/src/pages/DashboardPage.tsx`
- Modify: `chili_app/src/pages/__tests__/DashboardPage.test.tsx`

- [ ] **Step 1: Add failing KPI link tests**

Render `DashboardPage` inside `MemoryRouter` and assert accessible links:

```ts
expect(screen.getByRole('link', { name: /active alerts/i })).toHaveAttribute('href', '/alerts')
expect(screen.getByRole('link', { name: /open cases/i })).toHaveAttribute('href', '/cases')
expect(screen.getByRole('link', { name: /workflow runs/i })).toHaveAttribute('href', '/knowledge-bases')
expect(screen.getByRole('link', { name: /high-risk entities/i })).toHaveAttribute('href', '/investigation')
```

- [ ] **Step 2: Run failing dashboard tests**

Run:

```bash
cd chili_app
npm run test:run -- src/pages/__tests__/DashboardPage.test.tsx
```

Expected: tests fail because KPI cards are not links.

- [ ] **Step 3: Extend `KpiCard` with optional navigation props**

```tsx
type KpiCardProps = {
  label: string
  sublabel: string
  value: string
  color: string
  icon: ComponentType<{ size?: number }>
  to?: string
  ariaLabel?: string
}
```

Render a `Link` when `to` is present and keep the existing card markup when absent.

- [ ] **Step 4: Wire dashboard KPI routes**

Use:

- Active alerts -> `/alerts`
- High-risk entities -> `/investigation`
- Entities monitored -> `/investigation`
- Workflow runs -> `/knowledge-bases`
- Open cases should be surfaced as either an existing KPI or a queue-health link to `/cases`.

- [ ] **Step 5: Run dashboard tests**

Run:

```bash
cd chili_app
npm run test:run -- src/pages/__tests__/DashboardPage.test.tsx
```

Expected: KPI link tests pass.

## Task 3: Add Queue Health And Analytics Summary Panels

**Files:**
- Modify: `chili_app/src/pages/DashboardPage.tsx`
- Modify: `chili_app/src/pages/pages.css`
- Modify: `chili_app/src/pages/__tests__/DashboardPage.test.tsx`

- [ ] **Step 1: Add failing dashboard tab/content tests**

```ts
await userEvent.click(screen.getByRole('tab', { name: /queue health/i }))
expect(screen.getByText(/running workflows/i)).toBeInTheDocument()
expect(screen.getByText(/failed workflows/i)).toBeInTheDocument()

await userEvent.click(screen.getByRole('tab', { name: /policy signals/i }))
expect(screen.getByText(/top risk entities/i)).toBeInTheDocument()
expect(screen.getByText(/graph clusters/i)).toBeInTheDocument()
```

- [ ] **Step 2: Run failing dashboard tests**

Run:

```bash
cd chili_app
npm run test:run -- src/pages/__tests__/DashboardPage.test.tsx
```

Expected: tests fail until tab content is implemented.

- [ ] **Step 3: Choose an active KB for dashboard analytics**

Import `useKnowledgeBases` and choose:

```tsx
const activeKnowledgeBase =
  knowledgeBases.find((kb) => kb.status === 'ready') ?? knowledgeBases[0] ?? null
```

- [ ] **Step 4: Query bounded analytics summaries**

Use safe limits:

```tsx
const riskScoresQuery = useRiskScores(
  activeKnowledgeBase ? { knowledgeBaseId: activeKnowledgeBase.id, limit: 5 } : null,
)
const gnnClustersQuery = useGnnClusters(activeKnowledgeBase?.id ?? null)
const metricTimeseriesQuery = useMetricTimeseries(
  activeKnowledgeBase
    ? { knowledgeBaseId: activeKnowledgeBase.id, metric: 'claim_volume', start, end }
    : null,
)
```

If hook signatures require options instead of nullable filters, keep `enabled: Boolean(activeKnowledgeBase)`.

- [ ] **Step 5: Render `Queue Health` tab**

Show:

- Active alerts count.
- Open cases count.
- Workflow counts by `queued`, `running`, `failed`, and `completed`.
- Direct links to `/alerts`, `/cases`, and `/knowledge-bases`.

- [ ] **Step 6: Render `Policy Signals` tab**

Show:

- Top risk entities with score and entity ID/label.
- GNN clusters with entity count and anomaly score.
- Metric trend using existing `TrendBars` when timeseries data exists.
- Empty state when no KB exists.

- [ ] **Step 7: Run dashboard tests**

Run:

```bash
cd chili_app
npm run test:run -- src/pages/__tests__/DashboardPage.test.tsx
```

Expected: dashboard tab tests pass.

## Task 4: Preserve Backend Analytics Contract

**Files:**
- Review: `backend/api/routers/analytics.py`
- Review/modify: `backend/tests/api/test_analytics_router.py`

- [ ] **Step 1: Confirm existing endpoints satisfy UI**

Confirm these routes exist and remain viewer-protected:

- `GET /analytics/overview`
- `GET /analytics/risk-scores`
- `GET /analytics/timeseries`
- `GET /analytics/gnn/clusters`

- [ ] **Step 2: Remove stale future-development comment only after UI consumes these routes**

If Sprint 4 uses collection analytics, update the collection analytics future-development comment in `backend/api/routers/analytics.py`.

- [ ] **Step 3: Add backend tests only if a missing contract is found**

If query or response shape needs backend adjustment, add focused tests to `backend/tests/api/test_analytics_router.py`.

- [ ] **Step 4: Run backend checks if backend changed**

Run:

```bash
uv run --project backend pytest backend/tests/api/test_analytics_router.py -q
uv run --project backend pyright
```

Expected: backend analytics tests and typecheck pass if backend files changed.

## Task 5: Tighten The Cross-Screen Demo Path

**Files:**
- Modify tests as needed:
  - `chili_app/src/pages/__tests__/KnowledgeBaseManagerPage.test.tsx`
  - `chili_app/src/pages/__tests__/AlertFeedPage.test.tsx`
  - `chili_app/src/pages/__tests__/CaseManagementPage.test.tsx`
  - `chili_app/src/pages/__tests__/RagChatPage.test.tsx`
- Modify pages only if tests expose a broken route or missing CTA.

- [ ] **Step 1: Add a dashboard-to-workflow test checklist**

In page tests or a small integration-style Vitest, verify:

- Dashboard workflow KPI opens `/knowledge-bases`.
- Dashboard active alerts KPI opens `/alerts`.
- Dashboard cases link opens `/cases`.
- Dashboard investigation link opens `/investigation`.

- [ ] **Step 2: Verify existing sprint handoffs remain intact**

Run focused tests from sprints 1-3 that cover:

- KB -> Investigation.
- Alert -> Case.
- Alert/Case/Entity -> RAG.

- [ ] **Step 3: Run focused page tests**

Run:

```bash
cd chili_app
npm run test:run -- src/pages/__tests__/KnowledgeBaseManagerPage.test.tsx src/pages/__tests__/AlertFeedPage.test.tsx src/pages/__tests__/CaseManagementPage.test.tsx src/pages/__tests__/RagChatPage.test.tsx src/pages/__tests__/DashboardPage.test.tsx
```

Expected: cross-screen page tests pass.

## Task 6: Final Verification

**Files:**
- All touched files.

- [ ] **Step 1: Run frontend focused tests**

Run:

```bash
cd chili_app
npm run test:run -- src/api/__tests__/analytics.test.ts src/pages/__tests__/DashboardPage.test.tsx
npm run test:run -- src/pages/__tests__/KnowledgeBaseManagerPage.test.tsx src/pages/__tests__/AlertFeedPage.test.tsx src/pages/__tests__/CaseManagementPage.test.tsx src/pages/__tests__/RagChatPage.test.tsx
```

Expected: focused frontend tests pass.

- [ ] **Step 2: Run frontend build and lint**

Run:

```bash
cd chili_app
npm run build
npm run lint
```

Expected: build and lint pass.

- [ ] **Step 3: Run backend checks if backend changed**

Run:

```bash
uv run --project backend pytest backend/tests/api/test_analytics_router.py -q
uv run --project backend pyright
```

Expected: backend checks pass if backend files changed.

- [ ] **Step 4: Check whitespace**

Run:

```bash
git diff --check
```

Expected: no whitespace errors.

## Acceptance Checks

- [ ] Dashboard KPIs are keyboard-accessible links to alerts, cases, KB ingestion/workflows, and investigation.
- [ ] Dashboard shows active alerts, open cases, running/queued workflows, and failed workflows before drilldown.
- [ ] Dashboard shows analyst-useful analytics summaries: top risk scores, clusters, and trend data when available.
- [ ] No config mutation, WebSocket UI, or global graph entity drawer work is introduced.
- [ ] Demo path works from dashboard -> KB ingest/run -> alert feed -> case promotion/review -> RAG explanation with citations.
- [ ] Frontend build and focused tests pass.

## Demo Script

1. Open `/dashboard`.
2. Point out active alerts, open cases, workflow status, and top risk/policy signals.
3. Click `Workflow runs` to open `/knowledge-bases`.
4. Submit or select an ingestion run and follow Sprint 1 handoff to Investigation.
5. Return to Dashboard and click `Active alerts`.
6. Promote an alert to a case and save feedback.
7. Return to Dashboard and click `Open cases`.
8. Open the case and launch contextual RAG.
9. Show the cited answer and navigate back to evidence or investigation.
