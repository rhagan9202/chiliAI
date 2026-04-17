# Story E9-S11: Investigation Workbench — entity detail and evidence panels

## Story
As an analyst, I want side panels showing entity details and evidence packs when selecting a graph node.

## Acceptance Criteria
1. Selecting node opens Entity Detail panel: type, properties, risk score, community ID, timestamps.
2. Evidence Panel lists related evidence packs with reasoning summaries and confidence scores.
3. Each evidence item expandable.
4. Timeline view for entity-related events.
5. Panels collapsible, don't obscure graph.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | L    | E9-S10, E5-S03 |

## Target Files
- `chili_app/src/pages/InvestigationWorkbench.tsx` — integrate side panels alongside graph canvas
- `chili_app/src/components/investigation/EntityDetailPanel.tsx` — entity detail side panel
- `chili_app/src/components/investigation/EntityDetailPanel.module.css` — detail panel styles
- `chili_app/src/components/investigation/EvidencePanel.tsx` — evidence packs panel
- `chili_app/src/components/investigation/EvidencePanel.module.css` — evidence panel styles
- `chili_app/src/components/investigation/EvidenceItem.tsx` — expandable evidence item component
- `chili_app/src/components/investigation/EntityTimeline.tsx` — timeline view for entity events
- `chili_app/src/components/investigation/EntityTimeline.module.css` — timeline styles
- `chili_app/src/components/investigation/PanelContainer.tsx` — collapsible panel wrapper
- `chili_app/src/hooks/useEntityDetail.ts` — TanStack Query hook for entity detail data
- `chili_app/src/hooks/useEntityEvidence.ts` — TanStack Query hook for entity evidence packs
- `chili_app/src/hooks/useEntityTimeline.ts` — TanStack Query hook for entity timeline events
- `chili_app/src/types/entity.ts` — TypeScript types for entity detail, evidence, timeline
- `chili_app/src/types/evidence.ts` — TypeScript types for evidence packs and items

## Reference Files to Read First
- `chili_app/src/pages/InvestigationWorkbench.tsx` — graph workbench (from E9-S10)
- `chili_app/src/components/investigation/GraphCanvas.tsx` — graph canvas layout (from E9-S10)
- `chili_app/src/stores/appStore.ts` — Zustand store with `selectedEntityId` (from E9-S04)
- `chili_app/src/lib/queryClient.ts` — query client (from E9-S03)
- `chili_app/src/lib/apiClient.ts` — API client (from E9-S03)
- `backend/shared/types.py` — `Entity`, `EvidencePack` models for type reference
- `docs/architecture.md` — §8 for Investigation Workbench description

## Architectural Constraints
- React 19, TypeScript strict mode (`noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`)
- Functional components with hooks only
- TanStack Query for server state, Zustand for client state, React Router v7 for routing
- No business logic in components — delegate to hooks and services
- Keep builds and lint clean: `npm run build && npm run lint`
- Panels must read `selectedEntityId` from Zustand store and fetch data reactively
- Panel queries should be enabled only when `selectedEntityId` is non-null (`enabled: !!entityId`)
- Panels must be collapsible — use a toggle button or collapse icon
- Panel layout: graph takes remaining space, detail panel on right side, panels stack vertically or tab
- Panels must NOT overlay the graph — use a resizable split layout or fixed-width side area
- Evidence items must be expandable/collapsible (accordion pattern) — show summary by default, expand for full reasoning
- Timeline should display events chronologically (newest first or oldest first with toggle)
- Confidence scores should display as percentage or fraction with visual indicator (color/bar)
- When no entity is selected, panels should show a "Select a node" placeholder message

## What NOT To Do
- Do NOT implement backend entity/evidence endpoints — those are in E5-S03
- Do NOT add entity editing — this is read-only viewing
- Do NOT add evidence creation or annotation
- Do NOT add a mapping from evidence to graph (clicking evidence highlights graph edges) — future enhancement
- Do NOT install a rich text renderer for evidence — plain text with basic formatting is sufficient
- Do NOT add print or export functionality for panels
- Do NOT add drag-to-resize panels — fixed width or simple collapse is sufficient

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] `npm run build` passes (TypeScript compiles)
- [ ] `npm run lint` passes (ESLint clean)
- [ ] Components render without errors
- [ ] Entity Detail panel shows: type, properties, risk score, community ID, timestamps
- [ ] Evidence Panel shows evidence packs with reasoning and confidence scores
- [ ] Evidence items are expandable/collapsible
- [ ] Timeline displays entity-related events chronologically
- [ ] Panels are collapsible and don't obscure graph
- [ ] "Select a node" placeholder shown when no entity selected
