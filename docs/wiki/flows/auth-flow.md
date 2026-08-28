# Auth Flow: Login → Session → RBAC

**Verified against codebase:** 2026-08-28
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
   ├── Sets HttpOnly cookie: chiliai_login_state=<state>
   │     Secure=AuthConfig.cookie_secure (True in prod)
   │     Domain=AuthConfig.cookie_domain
   │     SameSite=Lax, Max-Age=600s
   │     (binds this authorization request to the browser that started it --
   │      see "Login CSRF / session fixation" below)
   └── Redirects to AuthConfig.authorize_endpoint?
         response_type=code&client_id=...&redirect_uri=...&scope=openid email profile
         &state=<state>&code_challenge=<challenge>&code_challenge_method=S256

2. OIDC provider authenticates user → redirects to GET /auth/callback?code=...&state=...

3. /auth/callback handler:
   ├── Requires cookie chiliai_login_state to be present and equal (constant-time
   │     compare) to the `state` query param -- rejects 400 otherwise, before ever
   │     looking up the PKCE state. Cleared on every exit path (success and failure
   │     alike); never trusts a request with no cookie.
   ├── Validates state matches stored PKCE session
   ├── Exchanges code for tokens via POST to AuthConfig.token_endpoint
   │     (includes code_verifier from PKCE session)
   │     Headers: client_id + client_secret (from AuthConfig.client_secret_env_var)
   ├── Extracts user_id, email, roles, knowledge_base_ids from ID token claims
   │     (roles from AuthConfig.roles_claim, default = "roles";
   │      knowledge_base_ids from AuthConfig.knowledge_base_ids_claim)
   ├── Creates SessionRecord {user_id, email, roles, knowledge_base_ids}
   ├── Stores session in SessionStoreProtocol with TTL = AuthConfig.session_ttl_seconds
   └── Sets HttpOnly cookie: chiliai_session=<session_id>
         Secure=AuthConfig.cookie_secure (True in prod)
         Domain=AuthConfig.cookie_domain
         SameSite=Lax
       (and clears chiliai_login_state, its job now done)

4. Subsequent API calls:
   └── auth.py middleware reads chiliai_session cookie
         → SessionStoreProtocol.get(session_id) → SessionRecord
         → User {user_id, roles, email, knowledge_base_ids}
         (Alternative: Authorization: Bearer <jwt> → JWKS validation)
```

### Login CSRF / session fixation

`state` alone only proves the caller knows a value chiliAI handed to *someone*
via `/auth/login` -- on its own it says nothing about *who*. Before the
`chiliai_login_state` cookie was introduced, `/auth/callback` accepted any
`state` present in the process-wide PKCE store with no reference to the
requesting browser: an attacker could start a login, capture their own
`code`+`state` (the id_token nonce validates fine either way, since it's read
from the same server-side record), and induce a victim's browser to hit
`/auth/callback` with those values -- logging the victim into the
**attacker's** account. The `chiliai_login_state` cookie set by `/auth/login`
is the only signal that ties an authorization request to the browser that
actually started it, so `/auth/callback` requires it (constant-time compared
against `state`) before doing anything else, and fails closed -- a missing
cookie is rejected, never treated as a legacy/compatible client.

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
    knowledge_base_ids: list[str] | None
    created_at: datetime
    expires_at: datetime
```

`knowledge_base_ids` carries the per-KB entitlement claim and must be persisted
on the session, because the cookie path rebuilds the principal from the
`SessionRecord` alone and never re-reads the `id_token`. `None` means the IdP
issued no claim (unrestricted); an empty list is a real restriction. Omitting it
here silently disables every per-KB gate on the only path the SPA uses — it did,
until 2026-08-26 — while the bearer path stayed correctly enforced.

### Deploy requirement: flush existing sessions

**Sessions created before the per-KB entitlement fix are not restricted by it.**
The fix changed what `/auth/callback` *writes*; it did not change what already
sits in Redis. A stored `SessionRecord` written by the old code has no
`knowledge_base_ids` field, so it deserializes to `None` — which this design
reads as "the IdP issued no claim", i.e. **unrestricted** — and that session
stays fully unrestricted for its entire remaining TTL
(`AuthConfig.session_ttl_seconds`), on every KB in the deployment, until the
user re-logs in.

Deploying the fix is therefore not sufficient on its own. As part of the
rollout, delete the existing session keys from the Redis session store (or let
`session_ttl_seconds` elapse before considering the control enforced, if a
forced re-login is unacceptable). Verify afterwards by logging in and confirming
`GET /auth/me` returns the expected `knowledge_base_ids`.

---

## Relevant Source Files

- `backend/api/routers/auth.py` — login, callback, logout, me endpoints
- `backend/api/routers/_oidc_client.py` — PKCE generation, authorize URL builder, token exchange
- `backend/api/middleware/auth.py` — `get_current_user`, JWKS cache, `decode_token`
- `backend/api/middleware/rbac.py` — `require_role`, `ROLE_HIERARCHY`
- `backend/api/middleware/session_store.py` — `SessionStoreProtocol`, `SessionRecord`
