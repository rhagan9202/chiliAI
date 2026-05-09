# UI/UX ↔ Backend Integration Evaluation

> Date: May 8, 2026  
> Scope: Evaluate how the merged upstream prototype UI/UX assets can be brought into the chiliAI React frontend while preserving the new backend architecture boundaries.

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
