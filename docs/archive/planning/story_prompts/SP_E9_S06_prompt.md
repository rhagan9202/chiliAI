# Story E9-S06: Knowledge Base Manager page — list and create

## Story
As an analyst, I want a KB Manager page to view and create knowledge bases.

## Acceptance Criteria
1. `src/pages/KnowledgeBaseManager.tsx` renders table: name, status, document count, created date.
2. "Create Knowledge Base" button opens form with name + description fields.
3. Form submission calls `POST /knowledgebases`, invalidates list query on success.
4. Status badges show KB lifecycle state.
5. Error states display toast notification.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | M    | E9-S03, E5-S11 |

## Target Files
- `chili_app/src/pages/KnowledgeBaseManager.tsx` — replace placeholder with KB list table and create form
- `chili_app/src/components/knowledgebase/KbTable.tsx` — knowledge base list table component
- `chili_app/src/components/knowledgebase/KbTable.module.css` — table styles
- `chili_app/src/components/knowledgebase/CreateKbForm.tsx` — create KB form (modal or slide-out)
- `chili_app/src/components/knowledgebase/StatusBadge.tsx` — status badge component for KB lifecycle states
- `chili_app/src/components/common/Toast.tsx` — reusable toast notification component
- `chili_app/src/hooks/useKnowledgeBases.ts` — update existing hook or ensure list query exists
- `chili_app/src/hooks/useCreateKnowledgeBase.ts` — TanStack Query mutation hook for creating KB
- `chili_app/src/types/knowledgeBase.ts` — TypeScript types for KB entities

## Reference Files to Read First
- `chili_app/src/pages/KnowledgeBaseManager.tsx` — current placeholder (from E9-S01)
- `chili_app/src/hooks/useKnowledgeBases.ts` — existing sample hook (from E9-S03)
- `chili_app/src/lib/queryClient.ts` — query client for cache invalidation (from E9-S03)
- `chili_app/src/lib/apiClient.ts` — API client (from E9-S03)
- `backend/api/routers/` — KB-related API routes for endpoint reference
- `docs/architecture.md` — §8 for KB Manager page description

## Architectural Constraints
- React 19, TypeScript strict mode (`noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`)
- Functional components with hooks only
- TanStack Query for server state, Zustand for client state, React Router v7 for routing
- No business logic in components — delegate to hooks and services
- Keep builds and lint clean: `npm run build && npm run lint`
- Use TanStack Query `useMutation` for the create operation with `onSuccess` invalidating the list query key
- Form must validate required fields (name) before submission — use native HTML validation or a lightweight approach
- Status badges should map KB lifecycle states to colors (e.g., active=green, building=yellow, error=red)
- Toast notifications should auto-dismiss after ~5 seconds
- Table should be sortable by at least the "created date" column
- Follow the query key convention from E9-S03

## What NOT To Do
- Do NOT implement document upload — that is E9-S07
- Do NOT implement KB deletion or editing — only list and create
- Do NOT install a full table library (ag-grid, tanstack-table) — a simple HTML table with sorting is sufficient
- Do NOT install a toast library — build a simple toast component or use a minimal one
- Do NOT add pagination — not needed until the list is large
- Do NOT implement the backend endpoints — those are in E5-S11
- Do NOT add KB detail/drill-down view — that is part of E9-S07

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] `npm run build` passes (TypeScript compiles)
- [x] `npm run lint` passes (ESLint clean)
- [x] Components render without errors
- [x] KB table renders with columns: name, status, doc count, created date
- [x] Create form opens, validates, and submits
- [x] List refreshes after successful creation
- [x] Status badges display correctly for all lifecycle states
- [x] Error toast appears on API failure

## Implementation Note
Completed on April 27, 2026. `KnowledgeBaseManager.tsx` renders a
`KbTable` (sortable by created date) consuming `useKnowledgeBases`,
plus a primary "Create Knowledge Base" button that opens a modal
`CreateKbForm` posting to `POST /knowledgebases` via a new
`useCreateKnowledgeBase` mutation that invalidates the list query on
success. A reusable `StatusBadge` maps the five backend lifecycle
states (active/ready/building/error/archived) to color variants in
`KbTable.module.css`. A lightweight `Toast` component plus singleton
`useToastStore` (Zustand) handles success/error notifications and
auto-dismisses after 5s; the `ToastContainer` is mounted inside
`DomainConfigProvider` in `main.tsx`. List load failures surface via a
toast and inline message. Tests (`KbTable`, `CreateKbForm`) cover row
rendering, empty state, sort toggle, name selection callback, and
mutation success path.

## Validation Note
From `chili_app/`:
- `npx tsc --noEmit` passed (0 errors)
- `npm run lint` passed (0 problems)
- `npx vitest run --pool=threads src/components/knowledgebase` passed
  (10 tests across `KbTable`, `DropZone`, `CreateKbForm`)
- `npm run build` passed.

