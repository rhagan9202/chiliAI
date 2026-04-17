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
- `chili_app/src/App.tsx` — current Vite placeholder to replace
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
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] `npm run build` passes (TypeScript compiles)
- [ ] `npm run lint` passes (ESLint clean)
- [ ] Components render without errors
- [ ] All six routes navigable in browser
- [ ] 404 route works for unknown paths
- [ ] Sidebar highlights active route
- [ ] Sidebar collapses on mobile viewport
