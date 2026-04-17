# Story E9-S10: Investigation Workbench — graph visualization

## Story
As an analyst, I want an Investigation Workbench with interactive graph visualization.

## Acceptance Criteria
1. `src/pages/InvestigationWorkbench.tsx` renders force-directed graph (WebGL: react-force-graph, sigma.js, or cytoscape.js).
2. Nodes color-coded by entity type, sized by risk score.
3. Edges display relationship type on hover.
4. Click node → updates `selectedEntityId` in Zustand store.
5. Zoom, pan, drag supported.
6. Graph data from `GET /investigation/subgraph/{entity_id}`.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | L    | E9-S04, E5-S03 |

## Target Files
- `chili_app/package.json` — add graph visualization library (e.g., `react-force-graph-2d` or `sigma` + `@react-sigma/core` or `cytoscape` + `react-cytoscapejs`)
- `chili_app/src/pages/InvestigationWorkbench.tsx` — replace placeholder with graph visualization page
- `chili_app/src/components/investigation/GraphCanvas.tsx` — graph rendering component wrapping chosen library
- `chili_app/src/components/investigation/GraphCanvas.module.css` — graph container styles
- `chili_app/src/components/investigation/GraphControls.tsx` — zoom/pan/reset controls overlay
- `chili_app/src/components/investigation/NodeTooltip.tsx` — tooltip for node hover details
- `chili_app/src/components/investigation/EdgeTooltip.tsx` — tooltip for edge hover (relationship type)
- `chili_app/src/hooks/useSubgraph.ts` — TanStack Query hook for fetching subgraph data
- `chili_app/src/types/graph.ts` — TypeScript types for graph nodes, edges, subgraph response
- `chili_app/src/utils/graphStyles.ts` — entity type → color mapping and risk score → node size mapping

## Reference Files to Read First
- `chili_app/src/pages/InvestigationWorkbench.tsx` — current placeholder (from E9-S01)
- `chili_app/src/stores/appStore.ts` — Zustand store with `selectedEntityId` (from E9-S04)
- `chili_app/src/lib/queryClient.ts` — query client (from E9-S03)
- `chili_app/src/lib/apiClient.ts` — API client (from E9-S03)
- `chili_app/src/contexts/DomainConfigContext.tsx` — domain config for entity type labels/colors (from E9-S02)
- `backend/shared/types.py` — `Entity`, `Relationship` models for type reference
- `backend/graph/models.py` — graph domain models
- `docs/architecture.md` — §8 for Investigation Workbench description

## Architectural Constraints
- React 19, TypeScript strict mode (`noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`)
- Functional components with hooks only
- TanStack Query for server state, Zustand for client state, React Router v7 for routing
- No business logic in components — delegate to hooks and services
- Keep builds and lint clean: `npm run build && npm run lint`
- Graph library recommendation: `react-force-graph-2d` (lightweight, WebGL-backed) — but `sigma.js` or `cytoscape.js` are acceptable alternatives
- Node color mapping must use domain config entity types if available, with sensible fallback colors
- Node sizing should scale proportionally to risk score (min/max bounds to prevent tiny/huge nodes)
- Clicking a node must update `selectedEntityId` in Zustand store via `selectEntity(id)` action
- Graph canvas should fill available space in the workbench layout
- Support URL query parameter `?entity={id}` to auto-focus a node on mount (from Alert Feed navigation)
- Edge labels should appear on hover only — not always visible (to reduce visual clutter)
- Zoom, pan, drag must work with mouse and trackpad

## What NOT To Do
- Do NOT implement the backend subgraph endpoint — that is E5-S03
- Do NOT implement entity detail or evidence panels — that is E9-S11
- Do NOT add graph editing (add/remove nodes) — this is read-only visualization
- Do NOT add graph layout algorithm selection — use force-directed as default
- Do NOT add search within the graph — out of scope
- Do NOT add graph export (PNG, SVG) — out of scope
- Do NOT SSR the graph component — it is inherently client-side

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] `npm run build` passes (TypeScript compiles)
- [ ] `npm run lint` passes (ESLint clean)
- [ ] Components render without errors
- [ ] Graph renders nodes color-coded by entity type
- [ ] Node sizes reflect risk scores
- [ ] Edge relationship type displays on hover
- [ ] Clicking node updates `selectedEntityId` in Zustand
- [ ] Zoom, pan, drag all functional
- [ ] URL query parameter `?entity={id}` auto-focuses node
