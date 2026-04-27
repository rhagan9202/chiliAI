# chiliAI Codebase, Workflow, UX, and Performance Audit — 2026-04-27

## Executive summary

chiliAI is substantially beyond the “early-stage scaffold” language still present in several documentation files. The backend now includes a broad FastAPI gateway, event-driven worker, in-memory and production-facing adapters, analytics services, RAG/LLM/embedding/vector/graph boundaries, authentication/RBAC scaffolding, monitoring services, and a large test suite. The frontend now includes a routed analyst workbench with Dashboard, Knowledge Base Manager, Alert Feed, Investigation Workbench, RAG Chat, and Configuration Editor views.

The system is currently usable as a local development prototype and the Docker development stack is healthy. The most important audit finding is not architectural absence; it is readiness mismatch: documentation, static type/lint quality gates, production adapter selection, workflow state synchronization, and some UX affordances lag behind the implementation.

### Overall status

| Area | Audit result | Severity |
| --- | --- | --- |
| Dev stack health | All Compose services running; API, worker, Redis, Neo4j, Qdrant, MinIO healthy | Good |
| Frontend quality gates | ESLint, production build, and tests pass | Good |
| Backend tests | 848 passed, 3 skipped; total coverage 96% | Good with caveats |
| Backend lint | Passed after quality-gate cleanup | Good |
| Backend type check | Passed after quality-gate cleanup for the currently included modules | Good |
| Documentation accuracy | Multiple docs stale versus actual implementation | High |
| Primary UX flow | Navigable, but several features are placeholders or disconnected | Medium/High |
| Runtime UX reliability | Alert WebSocket dev URL issue fixed; live status reached `Live` in browser smoke test | Good |
| Frontend performance | Production build succeeds but main bundle warns at 751.17 kB minified / 239.46 kB gzip | Medium |
| Security posture | Auth/RBAC exists in code/tests, but local/dev defaults remain unauthenticated; production hardening incomplete | Medium/High |

## Audit scope and method

This audit covered:

- Repository architecture and documentation alignment.
- Backend package/module implementation status.
- Frontend routes, pages, state/query hooks, components, and tests.
- Docker Compose local workflow and live service health.
- Live user workflow walkthrough through the browser at `http://localhost:5173`.
- API smoke checks against `http://localhost:8000`.
- Frontend lint/build/test validation.
- Backend lint/type/test validation.
- User-perspective UX and performance assessment.

This audit did not perform a security penetration test, load test, external adapter integration test against real Neo4j/Qdrant/MinIO persistence, or cloud/Kubernetes deployment validation.

## Validation results

### Docker/Compose status

The development stack was running and healthy:

| Service | Status observed |
| --- | --- |
| `api` | Up, healthy, `:8000` |
| `app` | Up, `:5173` |
| `worker` | Up, healthy, worker health on `:8001` internally |
| `redis` | Up, healthy |
| `neo4j` | Up, healthy |
| `qdrant` | Up, healthy |
| `minio` | Up, healthy |

API smoke checks:

- `GET /health` returned `{"status":"ok"}`.
- `GET /config/domain` returned the Medicare Fraud Detection domain config.
- `GET /knowledgebases` initially returned an empty list.

### Frontend validation

Commands run from `chili_app/`:

| Check | Result |
| --- | --- |
| `npm run lint` | Passed |
| `npm run build` | Passed |
| `npm run test:run` | Passed: 15 files / 53 tests |

Production build output highlights:

| Asset | Size | Gzip |
| --- | ---: | ---: |
| `dist/assets/index-*.js` | 751.17 kB | 239.46 kB |
| `dist/assets/GraphCanvas-*.js` | 191.17 kB | 62.07 kB |
| `dist/assets/index-*.css` | 20.00 kB | 4.57 kB |

Vite emitted a chunk-size warning for chunks larger than 500 kB.

### Backend validation

Commands run from `backend/` using `.venv/bin/python`.

| Check | Result |
| --- | --- |
| `ruff check .` | Passed after cleanup |
| `pyright` | Passed after cleanup for the currently included modules |
| `pytest --cov` | Passed: 848 passed, 3 skipped, 2 warnings, total coverage 96% |

Ruff cleanup completed:

- Removed unused imports in `api/dependencies.py`, `api/middleware/metrics.py`, and affected tests.
- Removed stale `__all__` entries for undefined `get_auth_config` and `get_validation_config`.

Pyright cleanup completed:

- Annotated Pydantic list default factories for strict inference.
- Wrapped NetworkX, statsmodels, and sklearn access behind typed dynamic-call boundaries.
- Preserved missing-optional-dependency behavior in tests.

Coverage caveat: total coverage is excellent at 96%, but some individual files are under the stated 85% per-package/per-affected-area expectation, including examples such as `vectorstore/service.py` at 76%, `graph/adapters/neo4j_adapter.py` at 79%, `events/codec.py` at 83%, `llm/service.py` at 84%, and `vectorstore/adapters/qdrant_adapter.py` at 84%.

## Architecture and codebase audit

### Architecture alignment

The implementation largely follows the intended monorepo split:

- `backend/` contains Python 3.12 FastAPI/worker modules.
- `chili_app/` contains React 19 + TypeScript + Vite frontend.
- `docs/` contains architecture/planning docs.
- `infra/` contains deployment scaffolding.

The backend has the intended module shape: `api`, `agent`, `analytics`, `config`, `embeddings`, `events`, `graph`, `ingestion`, `llm`, `monitoring`, `rag`, `shared`, `storage`, and `vectorstore` are present.

The architectural dependency rule is mostly honored at the service/protocol level. Examples of healthy patterns:

- External systems are abstracted behind protocols/adapters.
- In-memory adapters are broadly available for local tests and development.
- API routers use dependency wiring from `api/dependencies.py`.
- The worker coordinator composes pipeline dependencies centrally.

### Architecture risks

1. **Worker coordinator is a large composition hotspot**
   - `backend/agent/coordinator.py` imports and wires many modules directly.
   - This is acceptable as a composition root, but the file is large and can become difficult to reason about.
   - Recommendation: gradually split dependency construction, event handlers, and stage orchestration into smaller composition helpers while preserving `agent/` as the workflow boundary.

2. **Production adapter selection is incomplete**
   - Config and optional dependencies define production-capable integrations, and production-facing adapters exist for several systems.
   - Dependency wiring still defaults primarily to in-memory/local backends or raises unsupported-backend errors for several configured alternatives.
   - Recommendation: add explicit adapter factory coverage for Neo4j, Qdrant, S3/MinIO, OpenAI/Anthropic, and sentence-transformers in `api/dependencies.py` and worker construction, with integration tests gated by extras.

3. **Strict type-check coverage is narrow**
   - `tool.pyright.include` only covers selected modules/tests.
   - The currently included Pyright scope is clean after this cleanup.
   - Recommendation: broaden include scope package-by-package.

4. **Quality gate configuration and expectations diverge**
   - Documentation says all backend code must pass strict Pyright and maintain coverage ≥85% per package.
   - Current Pyright scope now passes, but coverage is reported globally rather than enforcing per-file/package thresholds.
   - Recommendation: align CI/tooling with the stated gate, or revise the stated gate to an incremental migration plan.

## Backend audit

### Strengths

- Broad module coverage exists beyond scaffolding.
- Tests are extensive: 851 collected tests with 848 passing and 3 skipped.
- Domain configuration is validated with Pydantic and served through `GET /config/domain`.
- Generic `shared.types.Entity` / `Relationship` model preserves domain reconfigurability.
- API router registration is tested against OpenAPI paths.
- Auth and RBAC middleware have tests even though production authentication is not fully enabled by default.
- Event bus abstraction includes in-memory and Redis Streams implementations.
- Worker health endpoint exists and the container healthcheck is now correctly overridden to `:8001`.
- Ingestion supports multiple parser formats and has a tested workflow path.
- Analytics modules contain deterministic heuristic implementations suitable for scaffold/prototype behavior.

### Backend concerns

#### High priority

1. **Documentation says modules are mostly unimplemented**
   - `backend/README.md` and `docs/architecture.md` understate current functionality.
   - This can mislead contributors and agents into duplicating work or avoiding existing code paths.

2. **Live KB summary did not reflect uploaded documents**
   - Fixed in cleanup: the in-memory KB repository now synchronizes `document_count` when documents are added or deleted.
   - Live smoke test confirmed `GET /knowledgebases/{id}` returned `document_count: 1` after upload.

#### Medium priority

1. **Several service methods are synchronous**
   - Many service methods publish events and perform storage operations synchronously.
   - This is fine for tests/prototype but may block API workers for larger files or slower external stores.

2. **In-memory state limits end-to-end persistence expectations**
   - Current local workflow can create and list entities in process memory, but persistence semantics across container restarts are limited unless production adapters are selected and wired.

3. **Event stream production hardening remains TODO**
   - Redis Streams adapter notes missing retry/backoff and stream trimming.
   - Without `MAXLEN`/trimming, streams can grow unbounded.

4. **Observability is present but incomplete**
   - Metrics middleware and tracing helpers exist.
   - Full OpenTelemetry exporter setup, dashboarding, and frontend observability remain future work.

## Frontend audit

### Strengths

- App has a real route structure in `src/App.tsx`:
  - Dashboard
  - Knowledge Bases
  - KB detail
  - Alerts
  - Investigation
  - RAG Chat
  - Configuration
- React Query is used for server state.
- Zustand is used for UI/chat state.
- Error boundaries and toast notifications exist.
- Domain config is fetched at startup and controls domain labels.
- Graph canvas is lazily imported, which is good because graph visualization is heavy.
- Major UI components have unit tests.
- Empty states exist across primary screens.
- File upload UI includes file type/size guidance.
- Config editor clearly disables Save and explains the backend endpoint is pending.

### Frontend concerns

#### High priority

1. **Investigation Workbench lacks an entity discovery path**
   - Without an alert link or known URL parameter, the user cannot search/select an entity from the workbench.
   - Empty state instructs the user to add `?kb_id=<id>` and optionally `entity_id=<id>` manually.
   - Recommendation: add KB selector and entity search directly in the workbench.

2. **Chat returns stubbed answer**
   - RAG Chat successfully submits and renders an answer, but live response was `Stubbed answer.`
   - This is acceptable for a scaffold but should be clearly labeled as placeholder until the RAG pipeline is fully wired to real retrieval/generation.

#### Medium priority

1. **React Query Devtools are visible in dev UI**
   - Expected for dev, but they add visual noise during user demos.
   - Recommendation: keep devtools, but consider an env flag to disable for demo/audit mode.

2. **Several inline styles remain in page components**
   - Inline styles appear in `Dashboard`, `InvestigationWorkbench`, `RagChat`, and `ConfigEditor`.
   - This slows design-system consistency and responsive iteration.
   - Recommendation: migrate common layout patterns to reusable CSS modules or layout primitives.

3. **Configuration Editor shows JSON with YAML highlighting**
   - The page explains this clearly, but the label “YamlEditor” and YAML highlighting can still confuse users.
   - Recommendation: label it “Domain configuration JSON view” until YAML serialization/edit/save are supported.

4. **Alert filters are partially client-side**
   - Backend accepts one severity; frontend multi-select sends first severity then narrows client-side.
   - This may surprise users once pagination is introduced.
   - Recommendation: add multi-severity server filtering or visibly state that filters are local for current page.

## User workflow walkthrough

### 1. Dashboard

Observed flow:

- Page loaded successfully after domain config fetch.
- Dashboard displayed Medicare Fraud Detection overview.
- KPI cards showed zeros.
- Recent Activity showed an empty state.

UX assessment:

- Clear and fast for an empty system.
- Good use of domain display name.
- Empty state is understandable but could include a primary action: “Create a knowledge base.”

### 2. Create knowledge base

Observed flow:

- Navigated to Knowledge Bases.
- Empty state prompted creating a KB.
- Created `Audit Walkthrough KB` through the modal.
- Toast confirmed creation.
- App navigated to KB detail page.

UX assessment:

- This is the strongest workflow in the app.
- Create button disabled until name is entered, which is good.
- Toast feedback is immediate and clear.

### 3. Upload document

Observed flow:

- KB detail page showed upload drop zone and documents table.
- Browser file chooser could not access the WSL file path in this audit environment, so the document was uploaded through the API.
- After reload, the UI listed `audit_walkthrough_provider.json` with status `pending`.
- Header still showed `0 document(s)`.

UX assessment:

- Upload UI is clear.
- The count mismatch is the main issue.
- Document status remained `pending`; there was no visible pipeline progress/status transition from pending to parsed/chunked/ready.

### 4. Alert Feed

Observed flow:

- Alert Feed displayed filters, bulk actions, and an empty state.
- WebSocket connection status showed connecting.
- Original audit observed a dev WebSocket origin mismatch. Cleanup now derives the WebSocket URL from the API origin and the Alert Feed reached `Live` in a browser smoke test.

UX assessment:

- Static alert-list UX is well structured.
- Real-time status reached `Live` after the WebSocket URL fix; keep regression coverage as deployment modes expand.
- Empty state could suggest how alerts are generated or link to monitoring setup.

### 5. Investigation Workbench

Observed flow:

- Without URL params, page showed no KB selected and asked the user to add query params manually.
- With `?kb_id=<id>`, page loaded but no graph data existed.
- Evidence panel notes that the evidence endpoint is not implemented.

UX assessment:

- Layout communicates the target product well.
- Current entry workflow is too technical for an analyst.
- Needs first-class KB/entity selection and search.

### 6. RAG Chat

Observed flow:

- Chat page loaded available KBs.
- Sending a question worked.
- Response rendered as `Stubbed answer.`

UX assessment:

- Chat affordance is intuitive.
- Disabled send behavior works until input is present.
- Needs visible “prototype/stubbed” indication or real RAG wiring to avoid confusing users.

### 7. Configuration Editor

Observed flow:

- Page loaded active Medicare Fraud Detection config.
- Save is disabled with a tooltip/title reason.
- Reset to defaults is available.
- Editor displays pretty-printed JSON with YAML syntax highlighting.

UX assessment:

- Honest about save not being implemented.
- Good for inspection.
- Potentially confusing because it is called YAML while rendering JSON.

## UX performance audit

### Browser runtime observations

Measured in the running Vite development server, not production nginx.

| Metric | Observed value |
| --- | ---: |
| DOMContentLoaded | ~80 ms |
| Load event | ~81 ms |
| Total resource entries during session | 98 |
| Script resource entries | 92 |
| CSS/link resource entries | 14 |
| API-like resource entries during session | 18 |

Interpretation:

- Dev-server navigation was fast on this machine.
- The many script resources are expected in Vite dev mode and should not be interpreted as production request count.
- Production build size is the more meaningful performance signal for deployment.

### Production bundle observations

- Main JS chunk: 751.17 kB minified / 239.46 kB gzip.
- Graph chunk: 191.17 kB minified / 62.07 kB gzip.
- Vite warned that some chunks exceed 500 kB.

Recommendations:

1. Keep `GraphCanvas` lazy loaded; this is already done and should remain.
2. Add route-level lazy loading for pages, especially `ConfigEditor` with CodeMirror and `RagChat`/alert components.
3. Consider manual chunking for heavy libraries:
   - React/vendor core
   - CodeMirror
   - graph visualization
   - TanStack Query/devtools
4. Ensure React Query Devtools are excluded from production, which they currently are via `import.meta.env.DEV` conditional rendering.
5. Add Lighthouse/Web Vitals checks once the app is served through production nginx, not only Vite dev server.

## Security and compliance audit

### Strengths

- Backend includes auth middleware and RBAC tests.
- API inputs are Pydantic/FastAPI validated.
- Upload validation tests exist for file size and query length boundaries.
- External integrations are intended to be environment/config driven.
- Secrets are not required for the current in-memory/local default path.

### Risks

1. **Authentication remains effectively optional/deferred in local flows**
   - This is fine for dev but must be gated before any shared environment.

2. **Default MinIO credentials in Compose**
   - `minioadmin`/`minioadmin` are acceptable for local development only.
   - Ensure production Compose/Kubernetes uses secrets.

3. **CORS is permissive for local origins**
   - `allow_methods=["*"]`, `allow_headers=["*"]`, and local origins are fine for dev.
   - Production should be locked to deployed frontend origins.

4. **Redis stream growth TODO**
   - Redis Streams adapter does not yet trim streams.
   - Long-running environments risk unbounded growth.

5. **Audit logging is not yet implemented**
   - Analyst actions like alert acknowledgments, config edits, graph queries, and chat prompts should eventually be audit logged.

## Documentation drift

### Stale or inaccurate statements

- `README.md` says both frontend and backend are early-stage scaffolds.
- `docs/architecture.md` §8 says frontend language is TypeScript 6, but `chili_app/package.json` now uses TypeScript `~5.9.3` for OpenAPI tool compatibility.
- `docs/architecture.md` §14.3 says backend is a minimal `main.py` scaffold with no dependencies and frontend is a Vite placeholder.
- `backend/README.md` says most analytics/pipeline modules are not implemented, but many modules and tests exist.
- `chili_app/README.md` says `src/App.tsx` is default template placeholder, but it is now a routed application shell.

### Recommendation

Update docs in this order:

1. `README.md`: current-state summary and verified quick start.
2. `backend/README.md`: actual implemented modules, validation status, adapter support matrix.
3. `chili_app/README.md`: actual routes, UX status, test commands, known placeholders.
4. `docs/architecture.md`: separate target architecture from implementation status; update TS version to 5.9.x unless/until `openapi-typescript` supports TS 6.
5. Add a status matrix for each module: `prototype`, `in-memory only`, `production adapter present`, `wired in DI`, `tested`, `type-checked`.

## Prioritized action plan

### P0 — unblock stated quality gates

1. Decide whether per-file/package coverage is enforced; if yes, configure coverage thresholds and raise low files above 85%.
2. Continue broadening Pyright strict scope package-by-package.
3. Keep documentation synchronized as implementation changes.

### P1 — fix live workflow trust issues

1. Add visible pipeline status/progress after upload.
2. Add Workbench KB selector and entity search.
3. Label stubbed RAG behavior clearly or wire chat to real RAG retrieval/generation.

### P2 — harden architecture for production adapters

1. Complete adapter factories for Neo4j, Qdrant, S3/MinIO, OpenAI/Anthropic, and sentence-transformers.
2. Add integration test profiles for optional adapters.
3. Add Redis stream trimming/retry/backoff policy.
4. Add persistence strategy documentation for local vs production state.

### P3 — improve frontend performance and polish

1. Route-level code splitting.
2. Manual chunks for CodeMirror and graph visualization.
3. Replace inline page styles with shared layout primitives.
4. Add accessible empty-state CTAs.
5. Add production Lighthouse/Web Vitals audit.

## Recommended next engineering tasks

1. **Coverage policy PR**
   - Decide whether per-file/package coverage is enforced.
   - Add coverage configuration for the chosen policy.
   - Raise remaining low-coverage files or mark integration-only gaps explicitly.

2. **Pyright expansion PR**
   - Broaden `tool.pyright.include` package-by-package.
   - Keep each newly included package strict-clean before expanding further.

3. **Docs freshness PR**
   - Continue replacing stale current-state language with implemented/prototype/target matrices.
   - Add known limitations and verified command outputs.

4. **Analyst workflow UX PR**
   - Dashboard CTA to create KB.
   - Workbench KB selector/entity search.
   - Alert empty-state guidance.
   - Placeholder banners for unimplemented evidence/RAG save endpoints.

## Final assessment

chiliAI has a solid modular foundation and much stronger test coverage than the current docs imply. The repo is in a healthy prototype phase, not a blank scaffold. The next milestone should be stabilizing developer trust and user trust: make the documented quality gates pass, fix the live workflow inconsistencies, and update the docs so contributors understand what exists and what remains target architecture.
