# Auth/RBAC Enforcement — Design Spec

- **Date**: 2026-05-08
- **Status**: Draft, awaiting user review
- **Scope**: Backend route enforcement + frontend sign-in flow (BFF). Per-KB / multi-tenant authorization is out of scope and will land in a separate spec.

## 1. Problem and goal

Today the API has scaffolded JWT/OIDC middleware (`api/middleware/auth.py`) and an RBAC role hierarchy (`api/middleware/rbac.py`), but no router actually enforces them. With `AuthConfig.enabled=False` (the current default) every endpoint admits an anonymous viewer; flipping the flag to `True` produces a system in which routes still admit any authenticated user because no `Depends(require_role(...))` is attached.

The frontend has no concept of a logged-in user: `chili_app` has no login page, `apiClient.ts` does not send credentials, and the WebSocket upgrades anonymously.

The goal of this spec is to close that gap end-to-end:

1. Every route in the FastAPI gateway requires an explicit role policy.
2. The browser obtains a session via a backend-for-frontend (BFF) OIDC handshake; tokens never reach JavaScript.
3. The system fails closed in production: misconfiguration refuses to start, and routes without an explicit policy refuse to register.
4. Local dev and the existing test suite continue to work without an identity provider.

## 2. Architectural choices (decided)

| Choice | Decision | Rationale |
|---|---|---|
| Identity provider | **Provider-agnostic OIDC** | Backend already validates against any OIDC JWKS; frontend uses generic OIDC config. Fits chiliAI's domain-reconfigurable ethos. |
| Browser auth pattern | **Backend-for-frontend (BFF)** | HttpOnly session cookie; tokens never reach JS; immune to XSS token theft; simplifies WebSocket auth. |
| Session storage | **Redis-backed** | Redis 7 is already in compose; opaque session id in cookie; server-side revocation is trivial. |
| Role model | **Existing 3-tier hierarchy** (`viewer < analyst < admin`) plus a `service` peer for service-to-service callers | Already implemented; avoids scope creep into per-resource permissions (deferred). |
| Per-KB authorization | **Out of scope** | Tracked separately as the "tenant isolation" Tier-2 item. |

## 3. Architecture

```
Browser (chili_app SPA)
   │  HttpOnly Secure SameSite=Lax cookie  "chiliai_session=<opaque-sid>"
   ▼
chili-api (FastAPI)
   │
   ├─ NEW api/routers/auth.py
   │     /auth/login     → 302 to IdP authorize_endpoint (PKCE-S256)
   │     /auth/callback  → exchange code, mint session in Redis, Set-Cookie, 302 to "/"
   │     /auth/logout    → delete session, clear cookie, optional 302 to IdP end_session
   │     /auth/me        → current User (or 401)
   │
   ├─ NEW api/middleware/session_store.py  (SessionStoreProtocol + Redis + InMemory)
   │     {sid → {user_id, roles, email, access_token, refresh_token, exp}}
   │
   ├─ MODIFIED api/middleware/auth.get_current_user
   │     Resolution order:
   │       1. AuthConfig.enabled=False         → anonymous viewer (unchanged)
   │       2. Cookie chiliai_session present   → SessionStore.get(sid) → User
   │       3. Authorization: Bearer present    → existing JWT/JWKS path (service-to-service)
   │       4. nothing                          → 401
   │
   ├─ UNCHANGED api/middleware/rbac.require_role
   │
   └─ Every router gets Depends(require_role(...)) per the policy table.
         Default-deny enforced by a startup hook + unit test that walks routes.
```

**WebSocket auth:** browser sends the same `chiliai_session` cookie on the upgrade request (same-origin). The `/ws` route adds `Depends(require_role("viewer"))` which reads the cookie via the existing dependency.

## 4. Policy table

| Router | Endpoint(s) | Min role | Notes |
|---|---|---|---|
| `config` | `GET /config/domain` | viewer | All authenticated users need it for dynamic UI |
| `config` | `PUT /config/domain` (future) | admin | Config writes are governance |
| `knowledgebases` | `GET /knowledgebases`, `GET /knowledgebases/{id}` | viewer | Read browsing |
| `knowledgebases` | `POST /knowledgebases`, document upload, document delete | analyst | Analysts own their cases |
| `knowledgebases` | `DELETE /knowledgebases/{id}` | admin | Destructive |
| `alerts` | `GET /alerts`, `GET /alerts/{id}` | viewer | Dashboard reads |
| `alerts` | `POST /alerts/{id}/ack`, suppression rule changes | analyst | Mutates alert state |
| `analytics` | `POST /analytics/risk`, `/timeseries`, `/gnn`, `/explain` | viewer | Compute-bearing reads; investigation team needs broad access |
| `chat` | `POST /chat` (and SSE stream) | viewer | RAG chat is an exploration tool |
| `investigation` | entity / neighborhood / search reads | viewer | Workbench browsing |
| `ws` | `/ws` upgrade | viewer | Browser sends session cookie on upgrade |
| `auth` | `/auth/login`, `/auth/callback`, `/auth/logout`, `/auth/me` | (unauth-OK) | Sign-in surface itself |

## 5. Backend changes

### 5.1 New files

- `backend/api/routers/auth.py` — the four auth endpoints. Uses `httpx.AsyncClient` for token exchange. PKCE: generate `code_verifier` + `code_challenge` per login; stash verifier in Redis under a short-TTL key (5 min) keyed by the `state` param.
- `backend/api/middleware/session_store.py` — `SessionStoreProtocol` plus `RedisSessionStore` (production) and `InMemorySessionStore` (tests). Per chiliAI's hexagonal architecture rule.
- `backend/api/middleware/policy_registry.py` — registry that records which routes carry `require_role`. Exposes `assert_complete(app)` that walks `app.routes`, skipping `/auth/*`, `/health`, `/metrics`, `/docs`, `/openapi.json`, `/redoc`, raises if any other route has no policy.

### 5.2 Modified files

- `backend/api/middleware/auth.py` — add cookie-based resolution in `get_current_user` ahead of the existing Bearer path. Bearer kept for service-to-service callers.
- `backend/api/dependencies.py` — `get_session_store` cached factory that selects Redis vs in-memory by `AuthConfig` and the surrounding `events.uri` Redis URL.
- `backend/api/app.py` — register `auth` router; install `policy_registry.assert_complete()` as a startup hook; reject startup when `CHILI_ENV=production` and `AuthConfig.enabled=False` (or required OIDC fields are missing).
- `backend/config/schema.py` — extend `AuthConfig`:
  - existing: `enabled`, `issuer_url`, `audience`, `jwks_uri`, `roles_claim`, `jwks_cache_seconds`
  - added: `client_id`, `client_secret_env_var`, `authorize_endpoint`, `token_endpoint`, `end_session_endpoint`, `scopes` (list, default `["openid","email","profile"]`), `cookie_secure` (bool, default `True`), `cookie_domain` (str \| None), `session_ttl_seconds` (int, default `3600`), `redirect_uri` (str — public URL of `/auth/callback`, registered with the IdP)

  Note on `cookie_secure`: defaults to `True`. Local dev keeps `AuthConfig.enabled=False`, so no cookie is set and the flag is moot. Enabling auth against an IdP in dev requires HTTPS (typical for IdP redirect URIs anyway).
- All seven existing routers — add `Depends(require_role(...))` per the policy table.

### 5.3 Refresh strategy (sliding session)

- Session TTL = `session_ttl_seconds` (default 1 h). Each authenticated request pushes the TTL forward via Redis `EXPIRE`.
- When access token has < 60 s remaining, BFF runs the OIDC `refresh_token` grant in the same request, swaps tokens in Redis, returns the response normally. User never sees a 401 unless the IdP refresh fails.
- Refresh-token rotation: store whatever the IdP returns; if it issues a new refresh token, replace.

### 5.4 Logout

- `/auth/logout` deletes the Redis session, clears the cookie (`Max-Age=0`), and — if `AuthConfig.end_session_endpoint` is set — returns a 302 to the IdP's RP-initiated logout endpoint with `id_token_hint=<stored id_token>` and `post_logout_redirect_uri=<spa-origin>`. Defaults to local-only.

### 5.5 Service-to-service (worker → API)

- Worker uses `Authorization: Bearer <client-credentials JWT>` against the IdP's client-credentials grant.
- The Bearer path in `get_current_user` validates that JWT directly via JWKS (existing code). Roles claim extracted as today; the configured client should emit `service` in its roles.
- `ROLE_HIERARCHY` is extended with `service: 2` (peer of `analyst`, between `viewer` and `admin`). This gives services analyst-equivalent reach but a distinct identity for audit logs.

## 6. Frontend changes

### 6.1 New files

- `chili_app/src/pages/Login.tsx` — minimal page with "Sign in" button that navigates (full-page) to `/auth/login`. Copy uses `domainConfig.auth.display_name` if present.
- `chili_app/src/contexts/SessionContext.tsx` — fetches `/auth/me` once at boot. Exposes `{ user, status: 'loading' | 'authenticated' | 'unauthenticated', signOut }`. `signOut()` POSTs `/auth/logout`, then `window.location='/'`.
- `chili_app/src/components/AuthGuard.tsx` — wraps the existing route tree; while `status==='loading'` shows a spinner; on `'unauthenticated'` redirects to `/login`.

### 6.2 Modified files

- `chili_app/src/lib/apiClient.ts` — every fetch gets `credentials: 'include'`. Centralize 401 handling: any 401 triggers `window.location.assign('/login')` (the BFF refresh handles silent renewal, so a 401 means the session is genuinely gone).
- `chili_app/src/hooks/useWebSocket.ts` — no token query string needed; cookie rides the upgrade. Reconnect on close-1008 (policy violation) bounces the page to `/login`.
- `chili_app/src/App.tsx` — mount `<SessionProvider><AuthGuard>{routes}</AuthGuard></SessionProvider>`; `/login` route is outside the guard.
- `chili_app/src/components/AppShell.tsx` — show `user.email` and a "Sign out" button in the header.

**No token storage in JS, no refresh logic in JS, no `Authorization` header set anywhere.** That is the BFF's job.

## 7. Dev / test / production posture

### 7.1 Dev (default)

`AuthConfig.enabled=False` → `get_current_user` returns anonymous viewer; SPA's `/auth/me` returns the same anonymous viewer; `AuthGuard` admits the user; no IdP needed for `make dev`. Existing behavior preserved.

### 7.2 Test

- Unit tests use `InMemorySessionStore` and inject sessions directly.
- Integration tests for routers use an `auth_enabled` fixture that flips `AuthConfig`, stamps a session in the in-memory store, and exercises the cookie path.
- The existing `set_jwks_fetcher` test hook stays for the Bearer path.

### 7.3 Production guardrails

`api/app.create_app` raises `RuntimeError` at startup when:

- `os.environ.get("CHILI_ENV") == "production"` AND
- (`AuthConfig.enabled is False` OR any of `issuer_url`, `audience`, `jwks_uri`, `client_id`, `client_secret_env_var`, `authorize_endpoint`, `token_endpoint`, `redirect_uri` is missing).

Backed by a unit test.

### 7.4 Default-deny audit

`policy_registry.assert_complete()` runs at startup whenever `AuthConfig.enabled=True`. It walks `app.routes`, skipping `/auth/*`, `/health`, `/metrics`, `/docs`, `/openapi.json`, `/redoc`. Any other route without an attached `require_role` raises `RuntimeError`. Backed by a unit test that registers a no-policy route and expects the failure.

## 8. Testing plan

### 8.1 New backend test files

- `tests/api/test_auth_router.py` — login redirect with PKCE state, callback exchange, refresh on near-expiry, logout (local + RP-initiated), `/auth/me` (anonymous + authenticated).
- `tests/api/test_session_store.py` — `InMemorySessionStore` unit; `RedisSessionStore` marked `@pytest.mark.integration`.
- `tests/api/test_policy_registry.py` — default-deny gate; no-policy route fails the assert.
- `tests/api/test_production_guardrail.py` — startup refusal under `CHILI_ENV=production` with various AuthConfig states.

### 8.2 Extended backend test files

For every existing router test, add a "auth-enabled / wrong role / right role" trio per endpoint:

- `tests/api/test_alerts_router.py`
- `tests/api/test_analytics_router.py`
- `tests/api/test_chat_router.py`
- `tests/api/test_config_router.py`
- `tests/api/test_investigation_router.py`
- `tests/api/test_knowledgebases_router.py`
- `tests/api/test_ws_router.py` (cookie sent on upgrade; 1008 close on insufficient role)

### 8.3 Frontend test files

- `chili_app/src/__tests__/SessionContext.test.tsx` — boot-time `/auth/me` flow; loading → authenticated/unauthenticated transitions.
- `chili_app/src/components/__tests__/AuthGuard.test.tsx` — redirect on unauthenticated; render children when authenticated.
- `chili_app/src/lib/__tests__/apiClient.test.ts` — verifies `credentials: 'include'` on every request; 401 triggers `window.location.assign('/login')` (mocked).

### 8.4 Coverage expectations

- New backend modules ≥85% (project rule).
- Existing router modules: no coverage regression.
- Frontend: keep existing 55+ vitest tests passing; ~10 new tests across the three suites above.

## 9. Migration sequence

Stacked PRs (or single PR — author's call). The auth-disabled path keeps every step shippable independently.

1. **Land cookie resolution + session store + auth router.** `AuthConfig.enabled` still defaults to `False`. No behavior change.
2. **Land `policy_registry` + `require_role` decorators on every router.** Auth still disabled — anonymous viewer satisfies viewer policies; tests pass.
3. **Land frontend `SessionContext` + `AuthGuard` + `apiClient` cookie include.** Auth still disabled — guard admits anonymous viewer.
4. **Flip `AuthConfig.enabled=True` in a staging environment** with any OIDC IdP (Keycloak, Auth0, Okta, Cognito, Google Workspace — all work the same way through the configured endpoints). Verify the cookie flow end-to-end.
5. **Promote to production.** The production guardrail prevents the flag from reverting silently.

## 10. Open questions deferred to implementation

- Cookie domain attribute when SPA and API are deployed under different sub-domains. Decide based on the production deployment topology; default `cookie_domain=None` (host-only cookie) is correct for the typical same-origin case.
- Whether to honor `prompt=none` silent-renewal as an additional pre-expiry safety net (likely not needed once the BFF refresh path is in).
- Audit logging hooks (login success/failure, logout, refresh). Belongs to the future observability spec; this design simply emits structured events at those points so the observability spec can route them.

## 11. Out of scope

- Per-KB / per-resource authorization (tenant isolation). Tracked separately.
- User and role management UI (creating users, assigning roles). Owned by the IdP.
- Audit log persistence / SIEM forwarding. Belongs to the observability spec.
- MFA, passkeys, IdP-specific features. Owned by the IdP.

## 12. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| OIDC misconfiguration silently produces 500s | MEDIUM | HIGH | `/auth/callback` handler returns explicit 4xx for missing code, bad state, IdP error; structured log on every failure path. |
| Cookie not sent cross-origin in production | MEDIUM | HIGH | Document that SPA and API must share a registrable domain, or set `cookie_domain` explicitly. Production guardrail can enforce this once we know the topology. |
| WebSocket auth quietly bypassed | LOW | HIGH | Explicit test for `Depends(require_role("viewer"))` on `/ws`; integration test that an unauthenticated upgrade is closed with code 1008. |
| Service-to-service `service` role leaks human privileges | LOW | MEDIUM | `service` role is its own bucket with analyst-equivalent reach but distinct identity; admin actions still require explicit `admin` role. |
| Refresh-token theft from Redis | LOW | HIGH | Redis access already restricted to API + worker. Document that refresh tokens are stored at-rest in Redis; future work could encrypt the value with a server-side key. |
| Default-deny audit creates friction adding new routes | LOW | LOW | The error message names the offending route and points to the policy table; documented in `backend/README.md`. |

## 13. Success criteria

- Every API route is reachable only with a session that has the policy-table role, and unreachable without one.
- A misconfigured production deployment refuses to start.
- A new route added without a `require_role` dependency fails CI.
- The SPA renders a functional login page, redirects unauthenticated users, and shows the signed-in user's email.
- WebSocket upgrades fail closed when the cookie is missing or the role is insufficient.
- Local dev (`make dev`) and the test suite continue to pass without any IdP configuration.
