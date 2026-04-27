# Story E9-S04: Zustand client state setup

## Story
As a frontend developer, I want Zustand configured for client-side state (sidebar, selected entity, active filters).

## Acceptance Criteria
1. `zustand` installed.
2. `useAppStore` manages: `sidebarOpen`, `selectedEntityId`, `activeKnowledgeBaseId`.
3. Actions: `toggleSidebar()`, `selectEntity(id)`, `setActiveKnowledgeBase(id)`.
4. Unit test verifies store actions and state transitions.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | S    | None         |

## Target Files
- `chili_app/package.json` — add `zustand` dependency
- `chili_app/src/stores/appStore.ts` — `useAppStore` Zustand store with state and actions
- `chili_app/src/stores/__tests__/appStore.test.ts` — unit tests for store actions and state transitions

## Reference Files to Read First
- `chili_app/package.json` — current dependencies
- `chili_app/src/components/layout/Sidebar.tsx` — sidebar component that will consume `sidebarOpen` (from E9-S01)
- `docs/architecture.md` — §8 for frontend state management approach

## Architectural Constraints
- React 19, TypeScript strict mode (`noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`)
- Functional components with hooks only
- TanStack Query for server state, Zustand for client state, React Router v7 for routing
- No business logic in components — delegate to hooks and services
- Keep builds and lint clean: `npm run build && npm run lint`
- Zustand store must be fully typed — define an interface for state and actions
- `selectedEntityId` and `activeKnowledgeBaseId` are `string | null`
- `sidebarOpen` defaults to `true`
- Use Zustand's vanilla store pattern (no middleware needed for this scope)
- Store should be a single slice for now — do NOT over-engineer with slice patterns unless needed
- Tests should use `vitest` (Vite's test runner) or the project's established test framework
- Tests must verify: initial state, each action mutates state correctly, toggling sidebar toggles boolean

## What NOT To Do
- Do NOT add persistence middleware (localStorage) — not needed yet
- Do NOT add devtools middleware unless it is zero-config
- Do NOT create multiple stores or slices — one `useAppStore` is sufficient for current needs
- Do NOT add filter state, investigation state, or chat state — those will come in their respective stories
- Do NOT wire the store into components in this story — only define and test the store
- Do NOT add computed/derived state helpers — keep it simple

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] `npm run build` passes (TypeScript compiles)
- [x] `npm run lint` passes (ESLint clean)
- [x] Components render without errors
- [x] Unit tests pass for all store actions
- [x] Store types are fully defined (no `any`)
- [x] `zustand` appears in `package.json` dependencies

## Implementation Note
Completed on April 27, 2026. `src/stores/appStore.ts` defines an
`AppState` interface (state + actions, no `any`) and exports
`useAppStore = create<AppState>(…)`. Initial state matches the prompt:
`sidebarOpen: true`, `selectedEntityId: null`,
`activeKnowledgeBaseId: null`. Actions are `toggleSidebar`,
`selectEntity(id: string | null)`,
`setActiveKnowledgeBase(id: string | null)` — signatures accept null so
that the matching cleared-state cases in higher stories don't require
extra plumbing. The `AppShell` already consumes the store
(`sidebarOpen`/`toggleSidebar`) so the sidebar collapse from E9-S01 is
wired without additional changes. Vitest is the test runner of choice
(installed at the wave level for downstream stories); the suite at
`src/stores/__tests__/appStore.test.ts` resets state in `beforeEach` and
verifies (1) initial state, (2) toggle round-trip, (3) `selectEntity`
set/clear, (4) `setActiveKnowledgeBase` set/clear.

## Validation Note
From `chili_app/`: `npx tsc --noEmit` clean; `npm run lint` clean;
`npm run test:run` reports `Test Files 1 passed (1) | Tests 4 passed
(4)` with the appStore suite. `npm run build` passes (vite ~180 ms,
263 kB JS gzip 83 kB). Coverage gate is provided by
`@vitest/coverage-v8` for downstream stories.
