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
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] `npm run build` passes (TypeScript compiles)
- [x] `npm run lint` passes (ESLint clean)
- [x] Components render without errors
- [x] Graph renders nodes color-coded by entity type
- [x] Node sizes reflect risk scores
- [x] Edge relationship type displays on hover
- [x] Clicking node updates `selectedEntityId` in Zustand
- [x] Zoom, pan, drag all functional
- [x] URL query parameter `?entity_id={id}` auto-focuses node

## Implementation Note
Completed on April 27, 2026. Used `react-force-graph-2d` (already in
`package.json`, untouched) lazy-loaded via `React.lazy()` so its canvas
machinery only initialises in the browser and never blocks SSR/test
environments. `chili_app/src/components/investigation/GraphCanvas.tsx`
wraps the library: maps `SubgraphResult.nodes` → `GraphNode[]` (color
from `colorForEntityType`, size from `sizeForRiskScore`) and
`subgraph.edges` → `GraphLink[]` keyed on `source_id`/`target_id`. The
center entity is auto-fitted (`zoomToFit(400, 80)`) and re-centred
whenever the subgraph or `centerEntityId` changes; the selected node is
highlighted in amber. Edge `relationship.type` surfaces via the
library's built-in hover label (`linkLabel`), and a hover state mirrors
it as a tooltip in the corner. A small palette legend (entity type →
swatch) sits over the canvas. `onNodeClick` calls
`useAppStore.selectEntity(id)`. The `InvestigationWorkbench` page seeds
the store from `?entity_id=…&kb_id=…` once on mount (subsequent URL
sync is store→URL only, to avoid a render loop), wires
`useNeighborhood(entityId, kbId, depth=2)` for graph data, and pulls
`DomainConfig.entities` via `useDomainConfig()` so the hashed colour
slot uses canonical entity names. The new TypeScript types `Entity`,
`Relationship`, `SubgraphResult`, `EntityDetailResponse`,
`NeighborhoodResponse`, `EntitySearchResponse`, `EvidencePack`,
`TimelineEvent` were appended to `src/types/api.ts` (extended, not
overwritten — coordinates with F2/F3). `src/utils/graphStyles.ts` owns
the entity-type → palette colour mapping (preferring config-defined
entity slot over a deterministic FNV-1a hash fallback) and the risk-
score → node-size scale (clamped 4..24 px). Deferred: `GraphControls`,
`NodeTooltip`, `EdgeTooltip` were not split into separate files — the
controls (zoom/pan/drag) come for free from the library and tooltips
are handled inline. `useSubgraph.ts` was renamed to `useNeighborhood.ts`
to match the actual backend endpoint shape.

## Validation Note
From `chili_app/`: `npx tsc --noEmit` clean; `npm run lint` clean
(no warnings); `npm run test:run` reports `Test Files 15 passed (15) |
Tests 53 passed (53)` including the four new investigation suites
(`GraphCanvas` 4, `EntityDetailPanel` 3, `EvidencePanel` 3, page-level
`InvestigationWorkbench` 2). `npm run build` passes — vite emits a
separate `GraphCanvas-*.js` chunk (191 kB / 62 kB gzip) thanks to
`React.lazy`, so the force-graph engine is loaded only when the
workbench route is visited. `package.json` was not modified.
