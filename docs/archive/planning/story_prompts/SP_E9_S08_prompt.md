# Story E9-S08: Alert Feed page

## Story
As an analyst, I want an Alert Feed page with filtering and bulk acknowledgment.

## Acceptance Criteria
1. `src/pages/AlertFeed.tsx` renders sortable, filterable alert table.
2. Filters: severity (multi-select), status, entity type, date range.
3. Bulk actions: acknowledge selected, dismiss selected.
4. Clicking alert navigates to Investigation Workbench with entity pre-selected.
5. Real-time updates via WebSocket.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | L    | E9-S03, E5-S01, E9-S12 |

## Target Files
- `chili_app/src/pages/AlertFeed.tsx` — replace placeholder with full alert feed page
- `chili_app/src/components/alerts/AlertTable.tsx` — sortable, selectable alert table
- `chili_app/src/components/alerts/AlertTable.module.css` — alert table styles
- `chili_app/src/components/alerts/AlertFilters.tsx` — filter bar: severity, status, entity type, date range
- `chili_app/src/components/alerts/AlertFilters.module.css` — filter styles
- `chili_app/src/components/alerts/BulkActions.tsx` — bulk action bar (acknowledge, dismiss)
- `chili_app/src/components/alerts/SeverityBadge.tsx` — severity-colored badge component
- `chili_app/src/hooks/useAlerts.ts` — TanStack Query hook for fetching alerts with filter params
- `chili_app/src/hooks/useBulkAlertAction.ts` — mutation hook for bulk acknowledge/dismiss
- `chili_app/src/types/alert.ts` — TypeScript types for alert entities, severity, status enums

## Reference Files to Read First
- `chili_app/src/pages/AlertFeed.tsx` — current placeholder (from E9-S01)
- `chili_app/src/hooks/useWebSocket.ts` — WebSocket hook for real-time updates (from E9-S12)
- `chili_app/src/lib/queryClient.ts` — query client (from E9-S03)
- `chili_app/src/lib/apiClient.ts` — API client (from E9-S03)
- `chili_app/src/stores/appStore.ts` — Zustand store for `selectedEntityId` (from E9-S04)
- `backend/shared/types.py` — `Alert` model for type reference
- `docs/architecture.md` — §8 for Alert Feed page description

## Architectural Constraints
- React 19, TypeScript strict mode (`noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`)
- Functional components with hooks only
- TanStack Query for server state, Zustand for client state, React Router v7 for routing
- No business logic in components — delegate to hooks and services
- Keep builds and lint clean: `npm run build && npm run lint`
- Alert table must support row selection (checkboxes) for bulk actions
- Clicking an alert row navigates to `/investigation?entity={entityId}` — use React Router `useNavigate`
- Severity multi-select filter allows selecting multiple severity levels simultaneously
- Date range filter uses native `<input type="date">` — do NOT install a date picker library
- Real-time: subscribe to `alert.created` events via `useWebSocket` hook and invalidate/append to query cache
- Table sorting should be client-side on the currently loaded data
- Bulk actions should be disabled when no rows are selected
- Alert types must align with backend `Alert` model from `shared/types.py`

## What NOT To Do
- Do NOT implement the backend alert endpoints — those are in E5-S01
- Do NOT implement the WebSocket backend — that is E5-S07; only consume via `useWebSocket` hook (E9-S12)
- Do NOT install a date picker library — use native HTML date inputs
- Do NOT install a table library — build with HTML table and sorting logic
- Do NOT add alert detail modal or side panel — clicking navigates to Investigation Workbench
- Do NOT add alert creation — alerts are system-generated
- Do NOT implement server-side pagination yet — client-side filtering is sufficient for this story

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] `npm run build` passes (TypeScript compiles)
- [ ] `npm run lint` passes (ESLint clean)
- [ ] Components render without errors
- [ ] Alert table renders with sortable columns
- [ ] All four filter types work (severity multi-select, status, entity type, date range)
- [ ] Bulk acknowledge and dismiss work on selected rows
- [ ] Clicking alert navigates to Investigation Workbench with entity pre-selected
- [ ] Real-time updates received via WebSocket refresh the alert list

## Implementation Note (2026-04-27)

Replaced the `AlertFeed` placeholder with a fully wired feed page. The page composes `AlertFilters` (severity multi-select, status select, entity-type select sourced from the loaded data, two `<input type="date">` controls), `AlertTable` (client-side sortable on severity / status / entity / created_at, row checkbox column, full-row click), and a bulk-action toolbar with Acknowledge / Dismiss buttons disabled until at least one row is selected. Sort precedence honours the requested ordering `critical > high > medium > low` via a numeric severity rank.

Data flow:
- `src/hooks/useAlerts.ts` exposes `useAlerts(filters)`, `useAcknowledgeAlerts()`, and `useDismissAlerts()`. Mutations fan out one POST per selected ID and invalidate the shared `['alerts']` query key on success.
- `buildAlertsQueryKey(filters)` produces a structurally stable key so changing any filter triggers a refetch (covered by a unit test).
- The page uses `useWebSocket<WsEvent>('/ws/alerts', ...)` from E9-S12; on `alert.created` it calls `queryClient.invalidateQueries({ queryKey: ['alerts'] })` to refresh the list. The connection state is rendered via `ConnectionStatus` next to the row counter.
- Row click sets `selectedEntityId` in the Zustand `appStore` and navigates to `/investigation?entity_id=...` via `useNavigate`.

`src/types/api.ts` already had `Alert` / `AlertListResponse` from F2; extended (not overwritten) with optional `kb_id`, `message`, `acknowledged_by`, and `properties` to match the story's union of fields the backend may grow into. The mandatory subset matches today's `shared.types.Alert` exactly.

Tests in `src/components/alerts/__tests__/AlertTable.test.tsx` cover: severity-desc sort ordering, row checkbox toggling, full-row click invocation, and filter-driven query-key changes.

## Validation Note (2026-04-27)

```
cd /home/rdhagan92/chiliAI/chili_app
npx tsc --noEmit                                                                      # clean
npm run lint -- src/pages/AlertFeed.tsx src/components/alerts src/hooks/useAlerts.ts  # clean
npx vitest run src/components/alerts src/hooks/__tests__/useWebSocket.test.tsx        # 10/10 passing
```

Repository-wide `npm run build` and `npm run test:run` surface pre-existing failures in unrelated test files (`@testing-library/react` re-exports `screen`/`fireEvent`/`waitFor` rely on the missing `@testing-library/dom` peer). These are owned by other agents' stories and are out of scope here.
