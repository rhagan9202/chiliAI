# Auth Flow: Login → Session → RBAC

**Verified against codebase:** 2026-05-20
**Sources:** `api/routers/auth.py`, `api/middleware/auth.py`, `api/middleware/rbac.py`, `api/middleware/session_store.py`

Auth shipped 2026-05-08. When `AuthConfig.enabled=False` (local/dev), the entire flow is bypassed.

---

## Configuration

Auth is enabled by setting `auth.enabled: true` in the domain YAML config and providing all required `AuthConfig` fields. Required under `CHILI_ENV=staging` or `production` (enforced by `create_app()`).

---

## OIDC Authorization Code Flow (PKCE)

```
1. Frontend: navigates to GET /auth/login
   ├── Generates state (UUID) + PKCE pair (verifier + S256 challenge)
   ├── Stores state + verifier in SessionStore with 300s TTL
   └── Redirects to AuthConfig.authorize_endpoint?
         response_type=code&client_id=...&redirect_uri=...&scope=openid email profile
         &state=<state>&code_challenge=<challenge>&code_challenge_method=S256

2. OIDC provider authenticates user → redirects to GET /auth/callback?code=...&state=...

3. /auth/callback handler:
   ├── Validates state matches stored PKCE session
   ├── Exchanges code for tokens via POST to AuthConfig.token_endpoint
   │     (includes code_verifier from PKCE session)
   │     Headers: client_id + client_secret (from AuthConfig.client_secret_env_var)
   ├── Extracts user_id, email, roles from ID token claims
   │     (roles extracted from AuthConfig.roles_claim, default = "roles")
   ├── Creates SessionRecord {user_id, email, roles}
   ├── Stores session in SessionStoreProtocol with TTL = AuthConfig.session_ttl_seconds
   └── Sets HttpOnly cookie: chiliai_session=<session_id>
         Secure=AuthConfig.cookie_secure (True in prod)
         Domain=AuthConfig.cookie_domain
         SameSite=Lax

4. Subsequent API calls:
   └── auth.py middleware reads chiliai_session cookie
         → SessionStoreProtocol.get(session_id) → SessionRecord
         → User {user_id, roles, email}
         (Alternative: Authorization: Bearer <jwt> → JWKS validation)
```

---

## Bearer Token Path

For machine-to-machine service accounts:
```
Request: Authorization: Bearer <jwt>
  └── auth.py decodes JWT against JWKS (fetched from AuthConfig.jwks_uri, cached jwks_cache_seconds)
        Validates: audience, issuer, expiry
        Extracts roles from AuthConfig.roles_claim
        Returns User {user_id, roles, email}
```

---

## Anonymous (Auth Disabled) Path

```
AuthConfig.enabled = False
  └── get_current_user() returns:
        User(user_id="anonymous", roles=["_authdisabled"])
        Role "_authdisabled" bypasses all require_role() checks
```

---

## Logout

```
POST /auth/logout
  ├── Reads session from cookie
  ├── Calls SessionStoreProtocol.delete(session_id)
  ├── Optionally redirects to AuthConfig.end_session_endpoint (OIDC RP-initiated logout)
  └── Clears chiliai_session cookie (Max-Age=0)
```

---

## GET /auth/me

```
GET /auth/me
  └── Calls get_current_user() → returns User {user_id, roles, email}
      Returns 401 if no valid session or token
```

---

## RBAC Enforcement

Every route is decorated with `require_role(role)`:
```python
ROLE_HIERARCHY = {"viewer": 1, "analyst": 2, "service": 2, "admin": 3}

require_role("viewer") → passes if user has viewer, analyst, service, or admin
require_role("analyst") → passes if user has analyst, service, or admin
require_role("admin") → passes if user has admin only
```

When auth is disabled, `require_role` short-circuits and returns the user unconditionally.

Policy registry (`middleware/policy_registry.py`): `assert_complete(app)` called at startup verifies every route has a `require_role` annotation — implements default-deny audit.

---

## Session Store

`SessionStoreProtocol` has two adapters and the selection is **wired** (since 2026-07-15, BL-022): `get_session_store()` in `backend/api/dependencies.py` returns `InMemorySessionStore` when `AuthConfig.enabled` is false, and `RedisSessionStore` otherwise — raising `ConfigurationError` if `REDIS_URL` is unset rather than silently falling back to an in-process store that would break multi-replica deployments.

> This section previously read "not yet wired", which stayed wrong for three weeks and invites a duplicate implementation of something that already exists.

```python
class SessionRecord:
    session_id: str
    user_id: str
    email: str | None
    roles: list[str]
    created_at: datetime
    expires_at: datetime
```

---

## Relevant Source Files

- `backend/api/routers/auth.py` — login, callback, logout, me endpoints
- `backend/api/routers/_oidc_client.py` — PKCE generation, authorize URL builder, token exchange
- `backend/api/middleware/auth.py` — `get_current_user`, JWKS cache, `decode_token`
- `backend/api/middleware/rbac.py` — `require_role`, `ROLE_HIERARCHY`
- `backend/api/middleware/session_store.py` — `SessionStoreProtocol`, `SessionRecord`
