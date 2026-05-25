# UI/UX ↔ Backend Integration Evaluation

> Date: May 8, 2026  
> Scope: Evaluate how the merged upstream prototype UI/UX assets can be brought into the chiliAI React frontend while preserving the new backend architecture boundaries.

> Superseded implementation snapshot: this planning document predates the routed `chili_app/` workbench, expanded API routers, auth/session flow, active KB contract, and RAG message streaming shape. Use it as historical planning context only; verify current behavior against code/tests before implementing from it.

## Executive conclusion

The upstream UI under `code-starters/ui/` is best treated as a high-fidelity prototype and visual/product reference, not as production application code. The current chiliAI frontend (`chili_app/`) should be rebuilt around the prototype’s UI/UX patterns using React 19 + TypeScript, typed API contracts, React Router, TanStack Query, and config-driven rendering.

The backend should not bend around the prototype’s hardcoded provider-specific data. Instead, the API layer should expose frontend-oriented read models that aggregate existing backend service boundaries: graph, risk, monitoring alerts, evidence packs, RAG, workflows, and domain config.

## Current surfaces

### Current chiliAI frontend

- `chili_app/src/App.tsx` is still the Vite starter template.
- `chili_app/package.json` has only React/React DOM runtime dependencies.
- No router, API client, data-fetching layer, state store, real app shell, pages, or domain-aware UI exists yet.

### Upstream prototype UI

- `code-starters/ui/integrity-ai.jsx` is a monolithic React demo with reusable visual ideas but hardcoded data and local state.
- It contains useful component candidates:
  - `RiskBadge`
  - `ConfBar`
  - `Chip`
  - `KPICard`
  - `Dashboard`
  - `AnomalyFeed`
  - `ProviderDive`
  - `PolicyIntel`
  - `CaseMgmt`
  - `AIPanel`
- `code-starters/ui/package.json` depends on `recharts` and `lucide-react`; these are suitable to add to `chili_app` when rebuilding.
- `core/ui/design_system.md`, `core/ui/navigation_flow.md`, and `core/ui/screens_spec.md` are the strongest reusable upstream assets because they describe the intended workflow, not just demo code.

### Current backend/API

- `backend/api/app.py` currently registers only config and knowledge-base routers.
- `backend/api/routers/config.py` exposes `GET /config/domain`.
- `backend/api/routers/knowledgebases.py` exposes document upload only.
- Existing backend modules already define a strong internal architecture: service protocols, adapters, domain config, events, graph, vectorstore, RAG, LLM, analytics, monitoring, and shared types.
- The missing piece is a thin frontend-facing API contract layer that composes existing services into UI read models.

## Boundary assessment

### Boundary to preserve

The frontend should communicate only through FastAPI routes and WebSocket/SSE channels. It should not encode backend module internals or infer cross-module contracts from UI code.

Backend cross-module interaction should remain limited to:

1. API gateway orchestration for frontend-initiated requests.
2. Agent/workflow coordinator for multi-step asynchronous pipelines.
3. Shared types/utilities for stable contracts.

### Integration anti-patterns to avoid

- Do not copy `integrity-ai.jsx` wholesale into `chili_app/src/App.tsx`.
- Do not preserve the prototype’s hardcoded mock arrays as application state.
- Do not create Medicare-only frontend domain models that bypass `DomainConfig`.
- Do not let UI pages call backend service modules directly or mirror internal service models one-to-one.
- Do not place backend aggregation logic in React components.

## Recommended target frontend architecture

```text
chili_app/src/
  api/
    client.ts
    contracts.ts
    alerts.ts
    cases.ts
    config.ts
    evidence.ts
    graph.ts
    knowledgeBases.ts
    rag.ts
    workflows.ts
  app/
    App.tsx
    router.tsx
    providers.tsx
  components/
    charts/
    evidence/
    feedback/
    graph/
    layout/
    policy/
    ui/
  features/
    alerts/
    cases/
    config/
    dashboard/
    investigation/
    knowledgeBase/
    policy/
    ragChat/
  hooks/
  pages/
    DashboardPage.tsx
    AlertFeedPage.tsx
    InvestigationWorkbenchPage.tsx
    CaseManagementPage.tsx
    KnowledgeBaseManagerPage.tsx
    PolicyIntelligencePage.tsx
    RagChatPage.tsx
    ConfigurationPage.tsx
  stores/
    uiStore.ts
  theme/
    tokens.ts
    global.css
  types/
```

## Prototype asset mapping

| Prototype asset | Recommended production destination | Reuse approach |
|---|---|---|
| Color tokens in `C` | `chili_app/src/theme/tokens.ts` | Directly port, type as `const` |
| Global CSS/font imports | `chili_app/src/theme/global.css` | Port and normalize for app-wide use |
| `KPICard`, `RiskBadge`, `ConfBar`, `Chip` | `components/ui/` | Rebuild in TypeScript with typed props |
| `Dashboard` | `pages/DashboardPage.tsx` + `features/dashboard/` | Rebuild from layout and chart patterns |
| `AnomalyFeed` | `pages/AlertFeedPage.tsx` + `features/alerts/` | Rebuild with paginated API data |
| `ProviderDive` | `pages/InvestigationWorkbenchPage.tsx` | Rename to generic entity investigation, not provider-only |
| Network SVG | `components/graph/` | Keep as first-pass component, later replace with graph library if needed |
| `PolicyIntel` | `pages/PolicyIntelligencePage.tsx` | Rebuild as evidence/policy intelligence view |
| `CaseMgmt` | `pages/CaseManagementPage.tsx` | Rebuild around server-backed case lifecycle |
| `AIPanel` | `components/layout/AiAssistantPanel.tsx` or `features/rag/` | Rebuild around RAG/chat API |
| Mock data arrays | `mocks/` only for Storybook/dev fixtures | Use only to define contract examples |

## Backend API contracts required by the rebuilt UI

### Configuration

- `GET /config/domain`
- `GET /config/features`
- `GET /config/domain/schema`

Purpose: domain labels, enabled capabilities, entity display names, field labels, UI feature gates, role/page visibility.

### Knowledge bases

- `GET /knowledgebases`
- `POST /knowledgebases`
- `GET /knowledgebases/{knowledge_base_id}`
- `DELETE /knowledgebases/{knowledge_base_id}`
- `POST /knowledgebases/{knowledge_base_id}/documents`
- `GET /knowledgebases/{knowledge_base_id}/documents`
- `GET /knowledgebases/{knowledge_base_id}/documents/{document_id}/status`
- `DELETE /knowledgebases/{knowledge_base_id}/documents/{document_id}`

Purpose: the Knowledge Base Manager page and ingestion status.

### Alert feed / triage queue

- `GET /alerts`
- `GET /alerts/{alert_id}`
- `POST /alerts/{alert_id}/acknowledge`
- `POST /alerts/{alert_id}/resolve`
- `POST /alerts/{alert_id}/dismiss`

Frontend read model should include:

- alert ID
- knowledge base ID
- entity ID/type
- display name
- severity
- risk score
- confidence
- reason codes
- evidence completeness
- status
- assignment/case linkage
- timestamps

### Investigation workbench

- `GET /graph/entities`
- `GET /graph/entities/{entity_id}`
- `GET /graph/entities/{entity_id}/relationships`
- `GET /graph/entities/{entity_id}/neighborhood`
- `GET /evidence-packs/{evidence_pack_id}`
- `GET /analytics/risk-scores/{entity_id}`
- `GET /analytics/timeseries/{entity_id}`

Purpose: generic entity investigation. It should not be provider-only, even when the Medicare domain displays providers.

### Case management / feedback

- `GET /cases`
- `POST /cases`
- `GET /cases/{case_id}`
- `PATCH /cases/{case_id}`
- `POST /cases/{case_id}/feedback`

Feedback model should align with `core/ui/screens_spec.md`:

- label: suspicious / not_suspicious / insufficient_evidence
- reason tags
- explanation usefulness rating
- evidence adequacy rating
- missing evidence list
- notes

### RAG / AI assistant

- `POST /chat/conversations`
- `GET /chat/conversations/{conversation_id}`
- `POST /chat/conversations/{conversation_id}/messages`
- optional stream: `GET /chat/conversations/{conversation_id}/stream`

Purpose: convert `AIPanel` into a backend-backed RAG assistant with citations and context.

### Workflow / realtime

- `POST /workflows`
- `GET /workflows/{workflow_id}`
- `GET /workflows`
- `DELETE /workflows/{workflow_id}`
- `WS /ws` or SSE endpoint for alerts/workflow updates

Purpose: pipeline status, alert updates, and ingestion progress.

## Domain configuration additions

Current `backend/config/defaults/medicare_fraud.yaml` defines entities, relationships, capabilities, ingestion, and alert thresholds. To drive the rebuilt UI, add a separate UI/config section rather than hardcoding page rules in React.

Recommended schema direction:

```yaml
ui:
  default_entity_type: provider
  navigation:
    pages:
      - id: dashboard
        label: Dashboard
        capability: risk_scoring
      - id: alert_feed
        label: Alert Feed
        capability: monitoring
      - id: investigation
        label: Investigation Workbench
        capability: gnn
      - id: rag_chat
        label: RAG Chat
        capability: rag_chat
  roles:
    analyst:
      landing_page: alert_feed
      pages: [alert_feed, investigation, rag_chat]
      permissions: [alerts:read, cases:write, feedback:write]
    supervisor:
      landing_page: dashboard
      pages: [dashboard, alert_feed, investigation, cases, policy]
      permissions: [alerts:read, cases:assign, feedback:read]
  display_fields:
    provider:
      title: npi
      subtitle: specialty
      chips: [state]
```

## Recommended implementation phases

### Phase 0 — Keep the merge stable

- Leave `code-starters/ui/` intact as a prototype reference.
- Do not wire it directly into production routes.
- Keep `chili_app/` as the production frontend root.

### Phase 1 — Frontend foundation

- Add `react-router-dom`, `@tanstack/react-query`, `zustand`, `lucide-react`, and `recharts` to `chili_app`.
- Extract design tokens and global CSS from the prototype.
- Replace Vite starter `App.tsx` with an application shell and placeholder routes.
- Add typed `src/api/contracts.ts` matching the planned backend read models.

### Phase 2 — Backend read model contracts

- Add `backend/api/contracts.py` for frontend-facing Pydantic read models.
- Implement read-only routers first with deterministic in-memory/mock adapters where services are incomplete.
- Start with `GET /config/domain`, `GET /alerts`, `GET /graph/entities/{id}`, and `GET /evidence-packs/{id}` because these unlock the highest-value prototype screens.

### Phase 3 — Rebuild prototype screens as typed pages

- Rebuild dashboard, alert feed, investigation workbench, case management, policy intelligence, and AI panel as separate TSX pages/components.
- Use prototype visuals and `core/ui` workflow docs as design references.
- Replace mock data with TanStack Query hooks.

### Phase 4 — Close the workflow loop

- Add case feedback mutations.
- Add workflow status and realtime alert/workflow updates.
- Add role/permission gating from domain config/auth context.

### Phase 5 — Backend production completion

- Replace read-model mocks with graph/risk/monitoring/evidence/RAG services.
- Persist cases and feedback.
- Add tests per backend package and frontend component/hook tests.

## Priority build order

1. App shell + design tokens.
2. Domain config client and provider.
3. Alert feed API + page.
4. Investigation entity detail + evidence bundle page.
5. Case feedback flow.
6. RAG AI assistant panel.
7. Dashboard and policy intelligence views.
8. Realtime updates.
9. Role-based access and admin/configuration surfaces.

## Key risks

| Risk | Impact | Mitigation |
|---|---|---|
| Copying monolithic prototype into `chili_app` | Creates untyped, hardcoded UI debt | Rebuild component-by-component in TypeScript |
| Medicare-specific UI | Breaks domain reconfigurability | Drive labels/entities/pages from `DomainConfig` |
| API contract churn | Frontend/backend mismatch | Define `backend/api/contracts.py` and frontend `api/contracts.ts` together |
| Incomplete backend services | UI blocked | Use thin API read models backed by deterministic scaffolds, then swap service adapters |
| Data volume | Slow feed/graph pages | Require pagination/filter params and later virtualization |
| Evidence overclaiming | Governance risk | Preserve triage-support language from `core/ui/screens_spec.md` |

## Recommended decision

Proceed with a UI/UX rebuild in `chili_app`, using `code-starters/ui/integrity-ai.jsx` and `core/ui/*.md` as source references. Do not migrate the prototype as-is. The first implementation story should establish the frontend shell, design tokens, routing, and typed API contracts; the second should add backend read-model contracts for alert feed and investigation detail.

## Component-by-component rebuild plan

### Planning baseline

- Production frontend root remains `chili_app/`.
- Prototype source remains read-only reference material under `code-starters/ui/` and `core/ui/`.
- The Vite starter UI should be deleted rather than incrementally styled.
- All production UI must be TypeScript, strict-mode clean, and domain-config driven.
- The initial Medicare FFS screen labels may be used as default fixture content, but component and API names must remain generic: entity, alert, evidence pack, case, indicator, policy citation, workflow.

### Source-of-truth inputs

| Input | Role in rebuild |
|---|---|
| `docs/architecture.md` §8–§9 | Target frontend architecture and domain configuration rules. |
| `docs/planning/ui_ux_backend_integration_evaluation_2026-05-08.md` | Integration decision record and phased migration path. |
| `core/ui/design_system.md` | Visual tokens, typography, spacing, semantic color rules. |
| `core/ui/component_library.md` | Reusable component anatomy and props. |
| `core/ui/navigation_flow.md` | Workflow routes, role landing pages, deep-link behavior. |
| `core/ui/screens_spec.md` | Governance-safe screen requirements, triage-support language, feedback validation. |
| `core/ui/data_model.md` | Prototype data shape reference; use only to inform read-model contracts. |
| `code-starters/ui/integrity-ai.jsx` | Visual and interaction prototype; rebuild, do not copy wholesale. |

### Target implementation structure

```text
chili_app/src/
  api/
    client.ts
    contracts.ts
    config.ts
    alerts.ts
    cases.ts
    evidence.ts
    graph.ts
    knowledgeBases.ts
    rag.ts
    workflows.ts
  app/
    App.tsx
    providers.tsx
    router.tsx
  components/
    charts/
    evidence/
    feedback/
    graph/
    layout/
    policy/
    ui/
  features/
    alerts/
    cases/
    config/
    dashboard/
    investigation/
    knowledgeBase/
    policy/
    ragChat/
  hooks/
  pages/
  stores/
  theme/
    tokens.ts
    global.css
  types/
```

### Foundation workstream

1. Add runtime dependencies:
   - `react-router-dom`
   - `@tanstack/react-query`
   - `zustand`
   - `lucide-react`
   - `recharts`
2. Replace starter global styles with the dark intelligence design system:
   - `theme/tokens.ts` exports typed color, typography, spacing, radius, shadow, and z-index tokens.
   - `theme/global.css` imports Oxanium, IBM Plex Sans, and IBM Plex Mono and sets root layout styles.
3. Replace starter `App.tsx` with an app shell:
   - left sidebar
   - top bar
   - role/program/domain selector placeholder
   - main route outlet
   - persistent AI assistant panel placeholder
4. Add app providers:
   - React Query client
   - domain config bootstrap query
   - UI state store for sidebar collapse, active program accent, AI panel open state, selected entity, and route filters.
5. Add route skeletons:
   - `/dashboard`
   - `/alerts`
   - `/investigation/:entityId?`
   - `/cases`
   - `/knowledge-bases`
   - `/policy`
   - `/rag-chat`
   - `/configuration`

### UI primitive rebuild order

| Order | Prototype/component source | Production component | Notes |
|---:|---|---|---|
| 1 | `C` color object | `theme/tokens.ts` | Directly port colors, but expose semantic aliases so program accent can switch by config. |
| 2 | Prototype CSS block | `theme/global.css` | Normalize body/root/layout styles; remove Vite starter CSS. |
| 3 | `Chip` | `components/ui/Chip.tsx` | Generic semantic badge with typed variants and optional color override. |
| 4 | `RiskBadge` | `components/ui/RiskBadge.tsx` | Thresholds should eventually come from `DomainConfig.alerts.thresholds`; default to prototype thresholds until backend exposes severity tiers. |
| 5 | `ConfBar` | `components/ui/ConfidenceBar.tsx` | Keep cyan as default confidence color; do not use green for confidence. |
| 6 | `KPICard` | `components/ui/KpiCard.tsx` | Accept Lucide icon component, formatted value, label, sublabel, trend. |
| 7 | Row/card shells | `components/ui/Card.tsx`, `components/ui/SectionHeader.tsx`, `components/ui/EmptyState.tsx`, `components/ui/LoadingState.tsx`, `components/ui/ErrorState.tsx` | Required before page rebuilds so pages stay composition-only. |
| 8 | Tab and filter controls | `components/ui/Tabs.tsx`, `components/ui/FilterBar.tsx` | Shared by alerts, investigation, cases, policy. |
| 9 | Feedback controls | `components/feedback/FeedbackPanel.tsx` | Must enforce `screens_spec.md` validation fields. |
| 10 | Chart wrappers | `components/charts/*` | Wrap Recharts with theme-consistent tooltip, grid, axes, responsive container. |

### Feature/page rebuild order

#### 1. Dashboard page

- Rebuild prototype `Dashboard` as `pages/DashboardPage.tsx` plus `features/dashboard/` widgets.
- Initial widgets:
  - program summary KPI row
  - alert volume trend chart
  - recovery/risk category chart
  - queue health summary
  - recent high-priority alerts
- Data source progression:
  1. local typed fixture matching `api/contracts.ts`
  2. `GET /dashboard/summary` read model when backend router exists
  3. realtime refresh through workflow/alert events

#### 2. Alert feed page

- Rebuild prototype `AnomalyFeed` as a generic triage queue: `pages/AlertFeedPage.tsx` and `features/alerts/`.
- Rename concepts:
  - anomaly row → alert row
  - provider-only fields → entity display fields
  - NPI route → entity route
- Required components:
  - `AlertFilters`
  - `AlertRow`
  - `AlertDetailDrawer`
  - `AlertReasonCodes`
  - assignment/status controls
- Backend contract priority:
  - `GET /alerts`
  - `GET /alerts/{alert_id}`
  - `POST /alerts/{alert_id}/acknowledge`
  - `POST /alerts/{alert_id}/resolve`
  - `POST /alerts/{alert_id}/dismiss`

#### 3. Investigation workbench

- Rebuild prototype `ProviderDive` as `pages/InvestigationWorkbenchPage.tsx`.
- Generic route: `/investigation/:entityId`.
- Initial tabs/panels:
  - Overview
  - Evidence
  - Network
  - Timeline
  - Policy Analysis
  - Feedback / Evidence Log
- Required components:
  - `EntityHeader`
  - `EvidenceSummaryPanel`
  - `SignalEvidencePanel`
  - `PolicyCitationCard`
  - `PolicyDeterminationCard`
  - `NetworkSliceCanvas`
  - `TimelineChart`
  - `SourceRecordList`
- Backend contract priority:
  - `GET /graph/entities/{entity_id}`
  - `GET /graph/entities/{entity_id}/neighborhood`
  - `GET /evidence-packs/{evidence_pack_id}`
  - `GET /analytics/risk-scores/{entity_id}`
  - `GET /analytics/timeseries/{entity_id}`

#### 4. Case management page

- Rebuild prototype `CaseMgmt` as `pages/CaseManagementPage.tsx`.
- Keep governance wording: suspicious / not suspicious / insufficient evidence; never “fraud confirmed.”
- Required components:
  - `CaseTable`
  - `CaseDetailDrawer`
  - `CaseStatusControl`
  - `AssignmentControl`
  - `FeedbackPanel`
  - `EvidenceCompletenessBadge`
- Backend contract priority:
  - `GET /cases`
  - `POST /cases`
  - `GET /cases/{case_id}`
  - `PATCH /cases/{case_id}`
  - `POST /cases/{case_id}/feedback`

#### 5. Policy intelligence page

- Rebuild prototype `PolicyIntel` as `pages/PolicyIntelligencePage.tsx`.
- Keep PKG green exclusively for policy knowledge graph / AI intelligence affordances.
- Required components:
  - `PolicyGapCard`
  - `PolicyCitationCard`
  - `PolicyBriefBuilder`
  - `PolicyTrendChart`
  - `AffectedCasesList`
- Backend contract priority:
  - `GET /policy/gaps`
  - `GET /policy/gaps/{gap_id}`
  - `GET /policy/gaps/{gap_id}/cases`
  - `POST /policy/briefs`

#### 6. Knowledge base manager

- Build from chiliAI architecture rather than prototype.
- Required components:
  - `KnowledgeBaseList`
  - `DocumentUploadDropzone`
  - `DocumentInventoryTable`
  - `IngestionStatusTimeline`
  - `RebuildIndexControl`
- Backend contract priority:
  - existing `POST /knowledgebases/{knowledge_base_id}/documents`
  - add list/create/delete KB and document status endpoints.

#### 7. RAG chat / AI assistant

- Rebuild prototype `AIPanel` as both:
  - persistent `components/layout/AiAssistantPanel.tsx`
  - full `pages/RagChatPage.tsx`
- Required capabilities:
  - conversation list
  - message stream area
  - citation chips
  - context/entity attachment
  - “triage support, not final decision” helper text
- Backend contract priority:
  - `POST /chat/conversations`
  - `GET /chat/conversations/{conversation_id}`
  - `POST /chat/conversations/{conversation_id}/messages`
  - optional streaming endpoint.

#### 8. Configuration page

- Build after domain-config shape is extended with UI navigation and display metadata.
- Required components:
  - `DomainSummaryCard`
  - `EntityTypeTable`
  - `RelationshipTypeTable`
  - `CapabilityMatrix`
  - `UiNavigationPreview`
  - future schema-driven editor.
- Backend contract priority:
  - existing `GET /config/domain`
  - add `GET /config/features`
  - add `GET /config/domain/schema`

### Backend/API planning required before production wiring

1. Add a frontend-facing `backend/api/contracts.py` module for Pydantic read models. These models should not expose internal service models directly.
2. Add routers in priority order:
   1. `alerts.py`
   2. `graph.py`
   3. `evidence.py`
   4. `cases.py`
   5. `rag.py`
   6. `workflows.py`
   7. `analytics.py`
   8. policy/intelligence router when the policy service exists.
3. Use deterministic in-memory read-model scaffolds where service modules are incomplete; this unblocks typed frontend integration without violating backend module boundaries.
4. Keep routers as thin orchestration only. Aggregation belongs in API read-model services/adapters, not React components and not cross-module imports.
5. Extend `DomainConfig` with a typed `ui` section:

```yaml
ui:
  default_entity_type: provider
  navigation:
    pages:
      - id: dashboard
        label: Dashboard
        route: /dashboard
        capability: risk_scoring
      - id: alerts
        label: Alert Feed
        route: /alerts
        capability: monitoring
      - id: investigation
        label: Investigation Workbench
        route: /investigation
        capability: gnn
      - id: cases
        label: Case Management
        route: /cases
      - id: policy
        label: Policy Intelligence
        route: /policy
        capability: rag_chat
      - id: rag_chat
        label: RAG Chat
        route: /rag-chat
        capability: rag_chat
  display_fields:
    provider:
      title: npi
      subtitle: specialty
      chips: [state]
```

### API contract sequencing

| Sprint | Frontend deliverable | Backend deliverable | Exit criterion |
|---|---|---|---|
| 1 | App shell, tokens, primitive components, route skeletons | no new backend required beyond `GET /config/domain` | Frontend build/lint passes and shell renders from domain config. |
| 2 | Alert feed page with fixtures and React Query hooks | `GET /alerts` read model scaffold | Alerts render through API hook, not inline arrays. |
| 3 | Investigation workbench with entity/evidence fixtures | `GET /graph/entities/{id}` and `GET /evidence-packs/{id}` scaffolds | Selecting alert opens entity workbench with evidence. |
| 4 | Case management and feedback | `GET /cases`, `PATCH /cases/{id}`, `POST /cases/{id}/feedback` | Feedback submits through typed mutation and validates required fields. |
| 5 | RAG panel and chat page | chat conversation endpoints | User can ask a context-aware question and see citations. |
| 6 | Knowledge base manager | KB list/status endpoints | Upload and ingestion status are visible in UI. |
| 7 | Dashboard and policy intelligence backed by read models | dashboard/policy summary endpoints | Leadership/supervisor views render from backend read models. |
| 8 | Realtime updates and role gating | WebSocket/SSE and config-driven page visibility | Alerts/workflows update without refresh; nav is role/capability filtered. |

### Acceptance criteria

- `npm run build` and `npm run lint` pass in `chili_app/` after each frontend slice.
- All React components use typed props; no implicit `any` and no hardcoded Medicare-only types in reusable components.
- Page labels, entity labels, capability visibility, and default entity display fields are read from backend domain config where available.
- No prototype mock arrays are imported into production code. Fixtures, if needed, live in a clearly isolated dev/test fixture module and match `api/contracts.ts`.
- UI copy preserves triage-support framing and avoids automated enforcement language.
- Backend routers introduced for UI integration include pytest coverage for response contracts and validation behavior.
- Frontend pages use TanStack Query hooks and API modules, never direct `fetch` calls inside page components.
- Component styling uses shared tokens; no new hardcoded hex values outside `theme/tokens.ts`.
