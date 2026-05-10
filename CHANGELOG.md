# Changelog

## Unreleased

### Post-merge stabilization (`fix/post-merge-stabilization`)

- Collapsed the duplicated frontend app trees: `main.tsx` no longer mounts an
  outer `BrowserRouter` or `QueryClientProvider`. The Phase 5 `RouterProvider`
  in `App.tsx` is the single router; `AppProviders` owns the QueryClient and
  the `SessionProvider`.
- Restored the `/login` route. The router now wraps the authenticated shell in
  `<AuthGuard>` + `<DomainConfigProvider>`. Unauthenticated requests redirect
  to `/login` instead of 404'ing.
- Deleted the legacy page tree (`Dashboard.tsx`, `InvestigationWorkbench.tsx`,
  `RagChat.tsx`, `KnowledgeBaseManager.tsx`, `ConfigEditor.tsx`,
  `AlertFeed.tsx`, `NotFound.tsx`) and their stale tests; the Phase 5 `*Page`
  components are the live versions.
- Split `SessionContext` so the hook (`useSession`) is in
  `contexts/sessionContextValue.ts` and the component
  (`SessionProvider`) is in `contexts/SessionContext.tsx`. Fixes the
  React Fast Refresh ESLint error.

- Added `Depends(require_role(...))` to every Phase 5+ router so
  `policy_registry.assert_complete` succeeds under
  `CHILI_ENV=production` + `auth.enabled=True`. Reads = viewer, writes =
  analyst.
- Removed the duplicate `POST /chat/conversations/{id}/messages` registration:
  `chat.py` was dropped, `rag.py` is now the single chat router and supports
  streaming via `?stream=true` (SSE). The non-streaming branch returns the
  full `ChatConversationResponse`.
- Reconciled the alerts contract. `alerts.py` now returns
  `api.contracts.AlertListResponse` (`{items, page}`) instead of
  `monitoring.service_models.AlertListResponse` (`{items, total}`) and is
  wired through `ApiState` so the seeded data the rest of Phase 5 uses is
  visible to the frontend.
- Added the missing path-parameter analytics endpoints (`/analytics/overview`,
  `/analytics/risk-scores/{entity_id}`, `/analytics/timeseries/{entity_id}`).
- Replaced the process-level `@lru_cache` singleton on `get_api_state` with
  per-app `app.state.api_state`. `get_domain_config` is still process-cached
  but the cache is cleared at the top of `create_app()` so each TestClient
  gets fresh config.
- Added `GraphService.get_neighbors(kb_id, entity_id)` so the existing
  `tests/graph/test_service_reads.py` and `ApiState.get_graph_entity_detail`
  no longer hit `AttributeError`.

- Frontend `api/client.ts` now delegates to `lib/apiClient.apiRequest`, so
  every Phase 5 query sends the `chiliai_session` cookie (`credentials:
  'include'`) and redirects to `/login` on 401.
- Frontend `EventSource` for `/events/stream` now passes
  `withCredentials: true` so the server-side `require_role("viewer")` guard
  on the SSE endpoint can identify the user.
- Sidebar nav iterates `domainConfig.ui.navigation.pages` directly with a
  per-id icon map and a generic icon fallback for unknown ids. The router has
  a catch-all inside the AppShell that renders `PagePlaceholder` for any
  configured page id without a built component, so a new domain pack can ship
  pages without an immediate frontend change.

- Removed `.vscode/settings.json` from tracking (it leaked an internal GHE
  hostname). Added `.vscode/` to `.gitignore`.

- Fixed `make dev` failing during the chili_app image build. The inherited
  `package-lock.json` (carried in from the merge in `32c01ef`) marks the
  optional platform-specific `@esbuild/*` binaries as `"extraneous"` instead
  of `"optional"`, so `npm ci` tries to install the aix-ppc64 binary on
  linux/x64 and exits with `EBADPLATFORM`. The bug pre-dates this branch —
  `origin/main` does not build either. Switched the Dockerfile build stage
  to `npm install --no-audit --no-fund` so dev builds work; restoring
  `npm ci` belongs in a follow-up that regenerates the lockfile (likely
  alongside a vitest 2 → 3 bump so vite 8 and vitest no longer fight over
  esbuild's major version).

## Initial scaffold
