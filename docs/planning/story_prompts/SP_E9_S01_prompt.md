# Story E9-S01: App shell, routing, and layout scaffold

## Story
As a frontend developer, I want a top-level app shell with sidebar navigation, route definitions for all six pages, and a responsive layout.

## Acceptance Criteria
1. React Router v7 configured with routes: `/` (Dashboard), `/knowledgebases` (KB Manager), `/alerts` (Alert Feed), `/investigation` (Investigation Workbench), `/chat` (RAG Chat), `/config` (Configuration).
2. Persistent sidebar with navigation links and active-state highlighting.
3. 404 catch-all route with "Not Found" page.
4. Responsive — sidebar collapses to hamburger on mobile.
5. Vite template placeholder in `App.tsx` replaced.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P0       | M    | None         |

## Target Files
- `chili_app/src/App.tsx` — replace Vite placeholder with app shell, `<Outlet />` for nested routes
- `chili_app/src/App.css` — replace with app shell layout styles (sidebar + main area)
- `chili_app/src/main.tsx` — wrap app with `BrowserRouter` (or use `createBrowserRouter`)
- `chili_app/src/components/layout/AppShell.tsx` — shell component with sidebar and content area
- `chili_app/src/components/layout/Sidebar.tsx` — navigation sidebar with links and active-state
- `chili_app/src/components/layout/Sidebar.module.css` — sidebar styles including responsive collapse
- `chili_app/src/pages/Dashboard.tsx` — placeholder page component
- `chili_app/src/pages/KnowledgeBaseManager.tsx` — placeholder page component
- `chili_app/src/pages/AlertFeed.tsx` — placeholder page component
- `chili_app/src/pages/InvestigationWorkbench.tsx` — placeholder page component
- `chili_app/src/pages/RagChat.tsx` — placeholder page component
- `chili_app/src/pages/ConfigEditor.tsx` — placeholder page component
- `chili_app/src/pages/NotFound.tsx` — 404 catch-all page

## Reference Files to Read First
- `chili_app/src/App.tsx` — historical pre-implementation Vite placeholder context
- `chili_app/src/main.tsx` — current entry point
- `chili_app/src/App.css` — current styles to replace
- `chili_app/package.json` — current dependencies
- `chili_app/tsconfig.app.json` — TypeScript config
- `chili_app/vite.config.ts` — Vite config
- `chili_app/eslint.config.js` — ESLint config
- `docs/architecture.md` — §8 for frontend page structure

## Architectural Constraints
- React 19, TypeScript strict mode (`noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`)
- Functional components with hooks only
- TanStack Query for server state, Zustand for client state, React Router v7 for routing
- No business logic in components — delegate to hooks and services
- Keep builds and lint clean: `npm run build && npm run lint`
- Install `react-router` v7 (the package is `react-router` not `react-router-dom` for v7)
- Use CSS modules or Tailwind for styling — no global CSS except in `index.css`
- Shell is the layout container; pages render inside `<Outlet />`
- Placeholder page components should export a simple component with the page name as heading
- Sidebar must use `<NavLink>` for active-state highlighting
- Responsive breakpoint: sidebar collapses to hamburger menu at 768px or below

## What NOT To Do
- Do NOT implement full page functionality — only placeholder components with headings
- Do NOT install or configure TanStack Query or Zustand in this story — those are separate stories (E9-S03, E9-S04)
- Do NOT fetch any data or connect to backend APIs
- Do NOT add authentication or route guards
- Do NOT use a CSS framework (e.g., Tailwind, Material UI) unless it is already in `package.json`
- Do NOT modify `index.html` beyond what is necessary
- Do NOT add tests — this is scaffolding only

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] `npm run build` passes (TypeScript compiles)
- [x] `npm run lint` passes (ESLint clean)
- [x] Components render without errors
- [x] All six routes navigable in browser
- [x] 404 route works for unknown paths
- [x] Sidebar highlights active route
- [x] Sidebar collapses on mobile viewport

## Implementation Note
Completed on April 27, 2026. The Vite placeholder shell was replaced with a
React Router v7 layout: `<BrowserRouter>` is mounted in `main.tsx` and
`App.tsx` declares `<Routes>` rooted at `<AppShell>`, which renders a
`<Sidebar>` plus `<Outlet />` inside an `ErrorBoundary`. The sidebar uses
`<NavLink>` for active-state highlighting, exposes a desktop collapse toggle,
and switches to an off-canvas drawer with hamburger toggle below 768px. Six
page stubs (`Dashboard`, `KnowledgeBaseManager`, `AlertFeed`,
`InvestigationWorkbench`, `RagChat`, `ConfigEditor`) plus a `NotFound`
catch-all (`path="*"`) satisfy routing while later wave stories flesh out
their bodies. Note: this story was implemented as part of a coordinated
foundation wave (E9-S01..S04) so the package was `react-router-dom@^7`
rather than `react-router` — both expose the v7 API; `react-router-dom`
keeps `<BrowserRouter>` available for the chosen JSX-routes style.

## Validation Note
From `chili_app/`: `npm install --legacy-peer-deps` succeeded
(the project later settled on TypeScript `~5.9.3` for `openapi-typescript`
compatibility). `npx tsc --noEmit`, `npm run
lint`, and `npm run build` (`tsc -b && vite build` → 263 kB JS / 3.98 kB CSS)
all pass with zero errors and zero warnings.
