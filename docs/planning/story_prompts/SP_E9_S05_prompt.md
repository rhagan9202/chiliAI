# Story E9-S05: Dashboard page

## Story
As an analyst, I want a Dashboard page displaying key metrics.

## Acceptance Criteria
1. `src/pages/Dashboard.tsx` renders KPI cards: total entities, total relationships, open alerts, active KBs.
2. Recent-activity timeline shows last 10 events.
3. Data fetched via TanStack Query hooks.
4. Cards show loading skeletons while fetching.
5. Default route (`/`).

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | M    | E9-S03, E5-S09 |

## Target Files
- `chili_app/src/pages/Dashboard.tsx` — replace placeholder with full dashboard page
- `chili_app/src/components/dashboard/KpiCard.tsx` — reusable KPI card component (title, value, icon, loading state)
- `chili_app/src/components/dashboard/KpiCard.module.css` — KPI card styles
- `chili_app/src/components/dashboard/RecentActivity.tsx` — recent activity timeline component
- `chili_app/src/components/dashboard/RecentActivity.module.css` — timeline styles
- `chili_app/src/components/common/Skeleton.tsx` — reusable loading skeleton component
- `chili_app/src/hooks/useDashboardMetrics.ts` — TanStack Query hook for fetching dashboard KPI data
- `chili_app/src/hooks/useRecentActivity.ts` — TanStack Query hook for fetching recent activity events
- `chili_app/src/types/dashboard.ts` — TypeScript types for dashboard metrics and activity events

## Reference Files to Read First
- `chili_app/src/pages/Dashboard.tsx` — current placeholder (from E9-S01)
- `chili_app/src/lib/queryClient.ts` — TanStack Query setup (from E9-S03)
- `chili_app/src/lib/apiClient.ts` — API client (from E9-S03)
- `chili_app/src/hooks/useKnowledgeBases.ts` — sample hook pattern (from E9-S03)
- `chili_app/src/contexts/DomainConfigContext.tsx` — domain config for dynamic labels (from E9-S02)
- `docs/architecture.md` — §8 for dashboard description

## Architectural Constraints
- React 19, TypeScript strict mode (`noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`)
- Functional components with hooks only
- TanStack Query for server state, Zustand for client state, React Router v7 for routing
- No business logic in components — delegate to hooks and services
- Keep builds and lint clean: `npm run build && npm run lint`
- KPI cards must show loading skeletons (not spinners) while data is fetching
- Use domain config context for dynamic labels where applicable (e.g., entity type names)
- Dashboard hooks should follow the query key convention established in E9-S03
- Activity timeline items should display: event type, description, timestamp, and entity link
- Cards should be laid out in a responsive grid (2 columns on tablet, 4 on desktop, 1 on mobile)
- All data types must be explicitly defined — no inline object shapes

## What NOT To Do
- Do NOT implement the backend dashboard endpoints — those are in E5
- Do NOT add charts, graphs, or complex visualizations — this is KPI cards and a timeline only
- Do NOT add real-time updates — that depends on E9-S12 (WebSocket)
- Do NOT add click-through navigation from dashboard cards to detail pages yet
- Do NOT hard-code metric values — always fetch via hooks (show skeletons while loading)
- Do NOT use a charting library (recharts, chart.js, etc.) — not needed for this story

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] `npm run build` passes (TypeScript compiles)
- [x] `npm run lint` passes (ESLint clean)
- [x] Components render without errors
- [x] KPI cards render with loading skeletons
- [x] Recent activity timeline renders last 10 events
- [x] Dashboard is the default route (`/`)
- [x] Responsive layout works across breakpoints

## Implementation Note
Completed on April 27, 2026. `Dashboard.tsx` now renders four KPI cards
(Total Entities, Total Relationships, Open Alerts, Active Knowledge Bases)
in a responsive 1/2/4-column CSS grid plus a "Recent Activity" timeline
of the last 10 events. KPI values are fetched by `useDashboardMetrics`
which aggregates `GET /knowledgebases` (entity/relationship/active counts)
with `GET /alerts?status=open` (open count) since no dedicated dashboard
summary endpoint exists yet. `useRecentActivity` merges KB-created and
alert-opened events sorted by timestamp. Loading is shown via a new
`Skeleton` component (not spinners) and errors render inline. Dynamic
domain label uses `useDomainConfig()`. New `src/types/api.ts` and
`src/types/dashboard.ts` define the API and view-model shapes. Tests
under `components/dashboard/__tests__` and `hooks/__tests__` cover loaded,
loading, error, and aggregation paths.

## Validation Note
From `chili_app/`:
- `npx tsc --noEmit` passed (0 errors)
- `npm run lint` passed (0 problems)
- `npx vitest run --pool=threads` passed (52 of 53 — the single failure is
  pre-existing in `pages/__tests__/InvestigationWorkbench.test.tsx`, owned
  by the Investigation agent and unrelated to this story)
- `npm run build` (`tsc -b && vite build`) passed and produced bundles.

