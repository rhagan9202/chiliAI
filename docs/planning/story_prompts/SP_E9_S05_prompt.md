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
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] `npm run build` passes (TypeScript compiles)
- [ ] `npm run lint` passes (ESLint clean)
- [ ] Components render without errors
- [ ] KPI cards render with loading skeletons
- [ ] Recent activity timeline renders last 10 events
- [ ] Dashboard is the default route (`/`)
- [ ] Responsive layout works across breakpoints
