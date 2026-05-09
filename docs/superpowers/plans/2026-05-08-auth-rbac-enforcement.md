# Auth/RBAC Enforcement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every chili-api route and WebSocket reachable only with a session that satisfies a required role; deliver a backend-for-frontend OIDC sign-in flow so the SPA never sees access tokens; preserve dev/test ergonomics with `AuthConfig.enabled=False`.

**Architecture:** A new `auth` router owns the OIDC handshake; tokens live in Redis keyed by an opaque session id; an HttpOnly cookie carries the id; `get_current_user` resolves identity from cookie → Bearer → anonymous fallback in that order; every router gets a `Depends(require_role(...))` per a published policy table; a startup hook walks `app.routes` and refuses to start if any non-`/auth` route lacks a role dependency; a production guardrail refuses to start if `AuthConfig.enabled=False` under `CHILI_ENV=production`.

**Tech Stack:** FastAPI, Pydantic v2, httpx (OIDC token exchange), python-jose (already a dep via `[auth]` extra), Redis 7 (already in compose), pytest + httpx.AsyncClient for backend; React 19 + TypeScript + react-router-dom + vitest for frontend.

**Reference spec:** `docs/superpowers/specs/2026-05-08-auth-rbac-enforcement-design.md`

**Operating notes for the executor:**
- Backend tests must run inside the API container: `docker exec chiliai-api-1 sh -c "cd /app && python -m pytest <args>"`. The host shell does not have `pytest` or backend deps.
- Frontend tests run on the host: `cd chili_app && npx vitest run <args>`.
- Pre-existing failure `tests/api/test_dependencies.py::test_default_factories_return_in_memory_services` is fixed in commit `a0870f0`. Baseline at start of plan: 903 passed / 7 skipped.
- Per chiliAI CLAUDE.md hexagonal rule: every external system goes behind a `Protocol` in `<module>/protocols.py` (or `<module>/adapters/protocols.py` for adapter-side contracts). Sessions follow the same pattern.
- Per chiliAI CLAUDE.md commit style: short imperative subject, body explains *why* not *what*. Co-author trailer for Claude (see `git log` for recent examples).
- Each task ends with a commit. Don't batch.

---

## File map (decomposition lock-in)

### New backend files
| Path | Responsibility |
|---|---|
| `backend/api/middleware/session_store.py` | `SessionStoreProtocol` + `InMemorySessionStore` + `RedisSessionStore` + `SessionRecord` model |
| `backend/api/middleware/policy_registry.py` | Walks `app.routes`, asserts every non-skipped route has a `require_role` dependency |
| `backend/api/routers/auth.py` | `/auth/login`, `/auth/callback`, `/auth/logout`, `/auth/me` |
| `backend/api/routers/_oidc_client.py` | Thin httpx-based OIDC client (authorize URL builder, token exchange, refresh, RP-initiated logout URL builder) |

### New backend test files
| Path | Covers |
|---|---|
| `backend/tests/api/test_session_store.py` | `InMemorySessionStore` unit + `RedisSessionStore` integration-marked |
| `backend/tests/api/test_policy_registry.py` | Default-deny gate; missing-policy fails the assert |
| `backend/tests/api/test_auth_router.py` | `/auth/me`, `/auth/login` redirect+PKCE, `/auth/callback` exchange, `/auth/logout`, refresh-on-near-expiry |
| `backend/tests/api/test_production_guardrail.py` | Startup refusal under `CHILI_ENV=production` |

### Modified backend files
| Path | Change |
|---|---|
| `backend/config/schema.py` | Extend `AuthConfig` with OIDC client + cookie + session fields |
| `backend/api/middleware/auth.py` | Cookie path in `get_current_user` ahead of Bearer; injects `SessionStore` |
| `backend/api/middleware/rbac.py` | Add `service: 2` to `ROLE_HIERARCHY`; tag `_dependency` with `_chiliai_required_role` |
| `backend/api/dependencies.py` | `get_session_store` cached factory |
| `backend/api/app.py` | Register auth router; install policy assert + production guardrail at startup |
| `backend/api/routers/{config,knowledgebases,alerts,analytics,chat,investigation,ws}.py` | Attach `Depends(require_role(...))` per the policy table |
| `backend/tests/api/test_auth_middleware.py` | Add cookie-path tests; keep Bearer tests |
| `backend/tests/api/test_rbac.py` | Add `service` role tests |
| `backend/tests/api/test_{alerts,analytics,chat,config,investigation,knowledgebases,ws}_router.py` | Add auth-enabled trio per endpoint |

### New frontend files
| Path | Responsibility |
|---|---|
| `chili_app/src/contexts/SessionContext.tsx` | Boot `/auth/me`, expose `{user, status, signOut}` |
| `chili_app/src/components/AuthGuard.tsx` | Redirect to `/login` when unauthenticated; spinner while loading |
| `chili_app/src/pages/Login.tsx` | "Sign in" button → `/auth/login` full-page nav |

### New frontend test files
| Path | Covers |
|---|---|
| `chili_app/src/contexts/__tests__/SessionContext.test.tsx` | Boot fetch, status transitions, signOut |
| `chili_app/src/components/__tests__/AuthGuard.test.tsx` | Redirect on unauthenticated, render children when authenticated |
| `chili_app/src/lib/__tests__/apiClient.test.ts` | `credentials: 'include'`; 401 → redirect to `/login` |

### Modified frontend files
| Path | Change |
|---|---|
| `chili_app/src/lib/apiClient.ts` | `credentials: 'include'` on every request; 401 handler navigates to `/login` |
| `chili_app/src/hooks/useWebSocket.ts` | Treat close-1008 as auth-required → bounce to `/login` |
| `chili_app/src/App.tsx` | Mount `<SessionProvider><AuthGuard>` around the route tree; `/login` outside the guard |
| `chili_app/src/components/layout/AppShell.tsx` | Show `user.email` + "Sign out" button |

---

# Phase 1 — Backend foundation (auth still disabled, no behavior change)

## Task 1: Extend `AuthConfig` schema

**Files:**
- Modify: `backend/config/schema.py:184-192` (replace `AuthConfig` body)
- Test: `backend/tests/config/test_schema.py` (add new test)

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/config/test_schema.py` (or create with this content if absent — search first; the file exists per the test inventory):

```python
def test_auth_config_extended_oidc_fields_default() -> None:
    from config.schema import AuthConfig

    cfg = AuthConfig()

    assert cfg.enabled is False
    assert cfg.client_id is None
    assert cfg.client_secret_env_var is None
    assert cfg.authorize_endpoint is None
    assert cfg.token_endpoint is None
    assert cfg.end_session_endpoint is None
    assert cfg.scopes == ["openid", "email", "profile"]
    assert cfg.cookie_secure is True
    assert cfg.cookie_domain is None
    assert cfg.session_ttl_seconds == 3600
    assert cfg.redirect_uri is None


def test_auth_config_accepts_oidc_fields() -> None:
    from config.schema import AuthConfig

    cfg = AuthConfig(
        enabled=True,
        issuer_url="https://idp.example.com",
        audience="chili-api",
        jwks_uri="https://idp.example.com/.well-known/jwks.json",
        client_id="chili-spa",
        client_secret_env_var="OIDC_CLIENT_SECRET",
        authorize_endpoint="https://idp.example.com/authorize",
        token_endpoint="https://idp.example.com/oauth/token",
        end_session_endpoint="https://idp.example.com/logout",
        scopes=["openid", "email", "profile", "offline_access"],
        cookie_secure=True,
        cookie_domain=".example.com",
        session_ttl_seconds=1800,
        redirect_uri="https://app.example.com/auth/callback",
    )

    assert cfg.client_id == "chili-spa"
    assert cfg.scopes == ["openid", "email", "profile", "offline_access"]
    assert cfg.session_ttl_seconds == 1800
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/config/test_schema.py::test_auth_config_extended_oidc_fields_default tests/config/test_schema.py::test_auth_config_accepts_oidc_fields -v"
```
Expected: FAIL with `AttributeError` or Pydantic `ValidationError` for unknown fields.

- [ ] **Step 3: Implement the schema change**

In `backend/config/schema.py`, replace the body of `AuthConfig` (currently lines 184-192) with:

```python
class AuthConfig(BaseModel):
    """JWT/OIDC authentication configuration (E10-S06)."""

    enabled: bool = False
    issuer_url: str | None = None
    audience: str | None = None
    jwks_uri: str | None = None
    roles_claim: str = "roles"
    jwks_cache_seconds: int = Field(default=3600, gt=0)

    # OIDC client (used by the BFF auth router)
    client_id: str | None = None
    client_secret_env_var: str | None = None
    authorize_endpoint: str | None = None
    token_endpoint: str | None = None
    end_session_endpoint: str | None = None
    scopes: list[str] = Field(
        default_factory=lambda: ["openid", "email", "profile"]
    )
    redirect_uri: str | None = None

    # Cookie / session
    cookie_secure: bool = True
    cookie_domain: str | None = None
    session_ttl_seconds: int = Field(default=3600, gt=0)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/config/test_schema.py -v"
```
Expected: PASS for both new tests; existing config tests still pass.

- [ ] **Step 5: Commit**

```bash
git add backend/config/schema.py backend/tests/config/test_schema.py
git commit -m "$(cat <<'EOF'
feat(config): extend AuthConfig with OIDC client + cookie + session fields

Adds the fields the BFF auth router needs (client_id,
client_secret_env_var, authorize_endpoint, token_endpoint,
end_session_endpoint, scopes, redirect_uri) plus cookie and session
settings. All new fields default to safe values; existing AuthConfig
callers continue to construct AuthConfig() without arguments.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `SessionStoreProtocol` + `SessionRecord` + `InMemorySessionStore`

**Files:**
- Create: `backend/api/middleware/session_store.py`
- Test: `backend/tests/api/test_session_store.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/api/test_session_store.py`:

```python
"""Tests for SessionStoreProtocol implementations."""

from __future__ import annotations

import time

import pytest

from api.middleware.session_store import (
    InMemorySessionStore,
    SessionNotFoundError,
    SessionRecord,
)


def _record(sid: str = "sid-1", *, ttl: int = 3600) -> SessionRecord:
    now = time.time()
    return SessionRecord(
        session_id=sid,
        user_id="user-42",
        roles=["analyst"],
        email="user@example.com",
        access_token="access-abc",
        refresh_token="refresh-xyz",
        access_token_expires_at=now + 600,
        id_token="id-tok",
        created_at=now,
        ttl_seconds=ttl,
    )


class TestInMemorySessionStore:
    def test_save_and_get_round_trip(self) -> None:
        store = InMemorySessionStore()
        record = _record()
        store.save(record)
        assert store.get("sid-1") == record

    def test_get_missing_session_raises(self) -> None:
        store = InMemorySessionStore()
        with pytest.raises(SessionNotFoundError):
            store.get("missing")

    def test_delete_removes_session(self) -> None:
        store = InMemorySessionStore()
        store.save(_record())
        store.delete("sid-1")
        with pytest.raises(SessionNotFoundError):
            store.get("sid-1")

    def test_delete_missing_session_is_idempotent(self) -> None:
        store = InMemorySessionStore()
        store.delete("never-existed")  # no raise

    def test_touch_extends_ttl(self) -> None:
        store = InMemorySessionStore()
        store.save(_record(ttl=60))
        store.touch("sid-1", ttl_seconds=3600)
        record = store.get("sid-1")
        assert record.ttl_seconds == 3600

    def test_touch_missing_session_raises(self) -> None:
        store = InMemorySessionStore()
        with pytest.raises(SessionNotFoundError):
            store.touch("missing", ttl_seconds=60)

    def test_save_replaces_existing_record(self) -> None:
        store = InMemorySessionStore()
        store.save(_record())
        replacement = SessionRecord(
            session_id="sid-1",
            user_id="user-42",
            roles=["admin"],
            email="user@example.com",
            access_token="new-access",
            refresh_token="new-refresh",
            access_token_expires_at=time.time() + 600,
            id_token="id-tok",
            created_at=time.time(),
            ttl_seconds=3600,
        )
        store.save(replacement)
        assert store.get("sid-1").access_token == "new-access"

    def test_pkce_state_set_get_pop(self) -> None:
        store = InMemorySessionStore()
        store.save_pkce_state(state="state-1", verifier="ver-1", ttl_seconds=300)
        assert store.pop_pkce_state("state-1") == "ver-1"
        # Popping again returns None (consumed)
        assert store.pop_pkce_state("state-1") is None

    def test_pkce_state_unknown_returns_none(self) -> None:
        store = InMemorySessionStore()
        assert store.pop_pkce_state("never-issued") is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_session_store.py -v"
```
Expected: FAIL with `ModuleNotFoundError: No module named 'api.middleware.session_store'`.

- [ ] **Step 3: Implement the protocol + in-memory adapter**

Create `backend/api/middleware/session_store.py`:

```python
"""Session storage protocol and in-memory adapter for the BFF auth flow."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


__all__ = [
    "InMemorySessionStore",
    "SessionNotFoundError",
    "SessionRecord",
    "SessionStoreProtocol",
]


class SessionNotFoundError(KeyError):
    """Raised when a session id is not present in the store."""


class SessionRecord(BaseModel):
    """Persisted session payload keyed by ``session_id``.

    Tokens are stored server-side; the cookie carries only the opaque id.
    ``access_token_expires_at`` is a Unix timestamp; the auth middleware uses
    it to decide whether to refresh on the current request.
    """

    session_id: str
    user_id: str
    roles: list[str] = Field(default_factory=list)
    email: str | None = None
    access_token: str
    refresh_token: str | None = None
    access_token_expires_at: float
    id_token: str | None = None
    created_at: float
    ttl_seconds: int


@runtime_checkable
class SessionStoreProtocol(Protocol):
    """Persist authenticated session payloads keyed by an opaque id."""

    def save(self, record: SessionRecord) -> None: ...
    def get(self, session_id: str) -> SessionRecord: ...
    def delete(self, session_id: str) -> None: ...
    def touch(self, session_id: str, *, ttl_seconds: int) -> None: ...
    def save_pkce_state(self, *, state: str, verifier: str, ttl_seconds: int) -> None: ...
    def pop_pkce_state(self, state: str) -> str | None: ...


class InMemorySessionStore:
    """Thread-naive in-memory session store, intended for tests and dev."""

    def __init__(self) -> None:
        self._records: dict[str, SessionRecord] = {}
        self._pkce: dict[str, str] = {}

    def save(self, record: SessionRecord) -> None:
        self._records[record.session_id] = record

    def get(self, session_id: str) -> SessionRecord:
        record = self._records.get(session_id)
        if record is None:
            raise SessionNotFoundError(session_id)
        return record

    def delete(self, session_id: str) -> None:
        self._records.pop(session_id, None)

    def touch(self, session_id: str, *, ttl_seconds: int) -> None:
        record = self._records.get(session_id)
        if record is None:
            raise SessionNotFoundError(session_id)
        self._records[session_id] = record.model_copy(update={"ttl_seconds": ttl_seconds})

    def save_pkce_state(self, *, state: str, verifier: str, ttl_seconds: int) -> None:
        del ttl_seconds  # InMemory store has no TTL; PKCE state is short-lived per process.
        self._pkce[state] = verifier

    def pop_pkce_state(self, state: str) -> str | None:
        return self._pkce.pop(state, None)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_session_store.py -v"
```
Expected: PASS for all 9 tests in `TestInMemorySessionStore`.

- [ ] **Step 5: Commit**

```bash
git add backend/api/middleware/session_store.py backend/tests/api/test_session_store.py
git commit -m "$(cat <<'EOF'
feat(auth): SessionStoreProtocol + InMemorySessionStore

Defines the session-storage contract for the BFF flow: opaque session id
keys a SessionRecord that holds the user identity, roles, OIDC tokens,
and a TTL. PKCE state lives in the same store under a separate
namespace. The in-memory adapter is intended for tests and the
auth-disabled dev path; a Redis adapter follows in the next task.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `RedisSessionStore`

**Files:**
- Modify: `backend/api/middleware/session_store.py` (append `RedisSessionStore`)
- Modify: `backend/tests/api/test_session_store.py` (append integration test class)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/api/test_session_store.py`:

```python
@pytest.mark.integration
class TestRedisSessionStore:
    """Integration tests for RedisSessionStore. Requires CHILI_TEST_REDIS_URL."""

    @pytest.fixture
    def redis_url(self) -> str:
        import os

        url = os.environ.get("CHILI_TEST_REDIS_URL")
        if url is None:
            pytest.skip("CHILI_TEST_REDIS_URL is not set; skipping integration test.")
        return url

    @pytest.fixture
    def store(self, redis_url: str):
        from api.middleware.session_store import RedisSessionStore

        store = RedisSessionStore(redis_url=redis_url, key_prefix="chiliai-test-session:")
        yield store
        # Best-effort cleanup of test keys
        store.flush_test_keys()

    def test_save_get_round_trip(self, store) -> None:
        record = _record(sid="redis-sid-1")
        store.save(record)
        loaded = store.get("redis-sid-1")
        assert loaded.user_id == "user-42"
        assert loaded.roles == ["analyst"]
        assert loaded.access_token == "access-abc"

    def test_get_missing_raises(self, store) -> None:
        with pytest.raises(SessionNotFoundError):
            store.get("redis-missing")

    def test_delete_removes_session(self, store) -> None:
        store.save(_record(sid="redis-sid-2"))
        store.delete("redis-sid-2")
        with pytest.raises(SessionNotFoundError):
            store.get("redis-sid-2")

    def test_pkce_state_round_trip(self, store) -> None:
        store.save_pkce_state(state="redis-state", verifier="redis-ver", ttl_seconds=60)
        assert store.pop_pkce_state("redis-state") == "redis-ver"
        assert store.pop_pkce_state("redis-state") is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker exec chiliai-api-1 sh -c "cd /app && CHILI_TEST_REDIS_URL=redis://redis:6379/15 python -m pytest tests/api/test_session_store.py::TestRedisSessionStore -v -m integration"
```
Expected: FAIL with `ImportError` for `RedisSessionStore` (or `AttributeError`).

- [ ] **Step 3: Implement `RedisSessionStore`**

Append to `backend/api/middleware/session_store.py` (and add the import at top):

```python
import json
from typing import cast

# ... existing code above ...


class RedisSessionStore:
    """Redis-backed session store. Cookie carries opaque ``session_id``.

    Sessions are stored as JSON strings under ``{key_prefix}{sid}`` with a
    Redis ``EX`` matching ``record.ttl_seconds``. PKCE state lives under a
    separate prefix with a short TTL.
    """

    SESSION_PREFIX = "session:"
    PKCE_PREFIX = "pkce:"

    def __init__(self, redis_url: str, *, key_prefix: str = "chiliai:") -> None:
        try:
            import redis
        except ImportError as exc:  # pragma: no cover - guarded by [redis] extra
            raise RuntimeError(
                "RedisSessionStore requires the 'redis' package. "
                "Install with `pip install redis`."
            ) from exc

        self._client = redis.Redis.from_url(redis_url, decode_responses=True)
        self._prefix = key_prefix

    def _session_key(self, session_id: str) -> str:
        return f"{self._prefix}{self.SESSION_PREFIX}{session_id}"

    def _pkce_key(self, state: str) -> str:
        return f"{self._prefix}{self.PKCE_PREFIX}{state}"

    def save(self, record: SessionRecord) -> None:
        payload = record.model_dump_json()
        self._client.set(
            self._session_key(record.session_id),
            payload,
            ex=record.ttl_seconds,
        )

    def get(self, session_id: str) -> SessionRecord:
        raw = self._client.get(self._session_key(session_id))
        if raw is None:
            raise SessionNotFoundError(session_id)
        data = json.loads(cast(str, raw))
        return SessionRecord.model_validate(data)

    def delete(self, session_id: str) -> None:
        self._client.delete(self._session_key(session_id))

    def touch(self, session_id: str, *, ttl_seconds: int) -> None:
        record = self.get(session_id)
        updated = record.model_copy(update={"ttl_seconds": ttl_seconds})
        self.save(updated)

    def save_pkce_state(self, *, state: str, verifier: str, ttl_seconds: int) -> None:
        self._client.set(self._pkce_key(state), verifier, ex=ttl_seconds)

    def pop_pkce_state(self, state: str) -> str | None:
        key = self._pkce_key(state)
        with self._client.pipeline() as pipe:
            pipe.get(key)
            pipe.delete(key)
            value, _ = pipe.execute()
        if value is None:
            return None
        return cast(str, value)

    def flush_test_keys(self) -> None:
        """Delete all keys under the configured prefix. Test helper only."""
        pattern = f"{self._prefix}*"
        for key in self._client.scan_iter(match=pattern):
            self._client.delete(key)
```

Add to the module's `__all__`:

```python
__all__ = [
    "InMemorySessionStore",
    "RedisSessionStore",
    "SessionNotFoundError",
    "SessionRecord",
    "SessionStoreProtocol",
]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker exec chiliai-api-1 sh -c "cd /app && CHILI_TEST_REDIS_URL=redis://redis:6379/15 python -m pytest tests/api/test_session_store.py -v"
```
Expected: PASS for all in-memory tests AND the integration tests (Redis is available in dev compose).

- [ ] **Step 5: Commit**

```bash
git add backend/api/middleware/session_store.py backend/tests/api/test_session_store.py
git commit -m "$(cat <<'EOF'
feat(auth): RedisSessionStore for BFF session persistence

Stores sessions as JSON under {prefix}session:{sid} with Redis EX
matching the record TTL. PKCE state lives under {prefix}pkce:{state}
with a short TTL. Integration test runs against the dev Redis
container at db 15 when CHILI_TEST_REDIS_URL is set.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `get_session_store` factory in `dependencies.py`

**Files:**
- Modify: `backend/api/dependencies.py` (add factory + import)
- Modify: `backend/tests/api/test_dependencies.py` (add factory tests)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/api/test_dependencies.py`:

```python
def test_get_session_store_returns_in_memory_when_auth_disabled(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    from api.middleware.session_store import InMemorySessionStore

    _install_config(monkeypatch, base_config)

    store = dependencies.get_session_store()

    assert isinstance(store, InMemorySessionStore)


def test_get_session_store_returns_redis_when_auth_enabled_and_redis_configured(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    from api.middleware.session_store import RedisSessionStore
    from config.schema import AuthConfig

    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    config = base_config.model_copy(
        update={
            "auth": AuthConfig(
                enabled=True,
                issuer_url="https://idp.example.com",
                audience="chili-api",
                jwks_uri="https://idp.example.com/jwks",
                client_id="chili-spa",
                client_secret_env_var="OIDC_CLIENT_SECRET",
                authorize_endpoint="https://idp.example.com/authorize",
                token_endpoint="https://idp.example.com/token",
                redirect_uri="https://app.example.com/auth/callback",
            )
        }
    )
    _install_config(monkeypatch, config)

    store = dependencies.get_session_store()

    assert isinstance(store, RedisSessionStore)
```

Add `dependencies.get_session_store` to the `cacheable_factories` list in the autouse `clear_dependency_caches` fixture (file lines 37-55).

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_dependencies.py::test_get_session_store_returns_in_memory_when_auth_disabled tests/api/test_dependencies.py::test_get_session_store_returns_redis_when_auth_enabled_and_redis_configured -v"
```
Expected: FAIL with `AttributeError: module 'api.dependencies' has no attribute 'get_session_store'`.

- [ ] **Step 3: Implement the factory**

In `backend/api/dependencies.py`, add to the imports near the existing protocol imports:

```python
from api.middleware.session_store import (
    InMemorySessionStore,
    RedisSessionStore,
    SessionStoreProtocol,
)
```

Add to `__all__`:

```python
"get_session_store",
```

Add the factory near the existing event-bus factory:

```python
@lru_cache(maxsize=1)
def get_session_store() -> SessionStoreProtocol:
    """Return the configured session store.

    Uses InMemorySessionStore when AuthConfig.enabled is False, otherwise
    requires REDIS_URL and returns RedisSessionStore.
    """

    config = load_config()
    auth = config.auth if config.auth is not None else None
    if auth is None or not auth.enabled:
        return InMemorySessionStore()

    redis_url = os.environ.get("REDIS_URL")
    if redis_url is None:
        raise ConfigurationError(
            "AuthConfig.enabled=True requires REDIS_URL to be set."
        )
    return RedisSessionStore(redis_url=redis_url)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_dependencies.py -v"
```
Expected: PASS for the two new tests; existing dependency tests unchanged.

- [ ] **Step 5: Commit**

```bash
git add backend/api/dependencies.py backend/tests/api/test_dependencies.py
git commit -m "$(cat <<'EOF'
feat(auth): get_session_store factory selects in-memory or Redis

When AuthConfig.enabled is False the factory returns InMemorySessionStore
so dev and tests work without Redis; when enabled the factory requires
REDIS_URL and returns RedisSessionStore. Lru-cached like the other
DI factories so callers share a single instance per process.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Add `service` role to `ROLE_HIERARCHY`; tag `_dependency` for policy detection

**Files:**
- Modify: `backend/api/middleware/rbac.py` (replace body)
- Modify: `backend/tests/api/test_rbac.py` (add service-role tests + tag-detection tests)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/api/test_rbac.py`:

```python
def test_role_hierarchy_includes_service_at_level_2() -> None:
    from api.middleware.rbac import ROLE_HIERARCHY

    assert ROLE_HIERARCHY["service"] == 2
    assert ROLE_HIERARCHY["service"] == ROLE_HIERARCHY["analyst"]


def test_service_role_satisfies_analyst_requirement() -> None:
    from api.middleware.rbac import is_role_sufficient

    assert is_role_sufficient(["service"], "analyst") is True


def test_service_role_does_not_satisfy_admin_requirement() -> None:
    from api.middleware.rbac import is_role_sufficient

    assert is_role_sufficient(["service"], "admin") is False


def test_require_role_dependency_carries_marker_attribute() -> None:
    from api.middleware.rbac import require_role

    dep = require_role("analyst")

    assert getattr(dep, "_chiliai_required_role", None) == "analyst"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_rbac.py -v"
```
Expected: FAIL on the four new tests (`KeyError 'service'`, missing attribute).

- [ ] **Step 3: Implement the change**

Edit `backend/api/middleware/rbac.py`. Update `ROLE_HIERARCHY`:

```python
ROLE_HIERARCHY: dict[str, int] = {
    "viewer": 1,
    "analyst": 2,
    "service": 2,
    "admin": 3,
}
```

In `require_role`, attach the marker before returning:

```python
def require_role(role: str) -> Callable[..., User]:
    """Return a FastAPI dependency that enforces ``role`` against ``get_current_user``."""

    if role not in ROLE_HIERARCHY:
        raise ValueError(
            f"Unknown role '{role}'. Valid roles: {sorted(ROLE_HIERARCHY)}."
        )

    def _dependency(
        user: User = Depends(get_current_user),
        domain_config: DomainConfig = Depends(get_domain_config),
    ) -> User:
        auth_config = domain_config.auth
        if auth_config is None or not auth_config.enabled:
            return user
        if not is_role_sufficient(user.roles, role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"User '{user.user_id}' lacks required role '{role}'. "
                    f"Roles: {user.roles}."
                ),
            )
        return user

    _dependency._chiliai_required_role = role  # type: ignore[attr-defined]
    return _dependency
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_rbac.py -v"
```
Expected: PASS for all RBAC tests.

- [ ] **Step 5: Commit**

```bash
git add backend/api/middleware/rbac.py backend/tests/api/test_rbac.py
git commit -m "$(cat <<'EOF'
feat(rbac): add service role at level 2; tag require_role dependencies

The 'service' role is a peer of 'analyst' (same authorization reach,
distinct identity) and is reserved for service-to-service callers
(worker -> API). Each require_role(...) dependency now carries a
_chiliai_required_role marker so policy_registry can walk app.routes
and detect missing role enforcement.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Cookie-based resolution in `get_current_user`

**Files:**
- Modify: `backend/api/middleware/auth.py` (resolution order in `get_current_user`)
- Modify: `backend/tests/api/test_auth_middleware.py` (add cookie-path tests)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/api/test_auth_middleware.py`. (Read the existing file first to follow its fixture style; the snippets below assume `client` and `auth_enabled_config` follow the existing conventions.)

```python
def test_get_current_user_resolves_session_from_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When auth is enabled and a valid session cookie is present, the user is returned."""
    import time

    from fastapi import FastAPI

    from api.dependencies import get_session_store
    from api.middleware.auth import User, get_current_user
    from api.middleware.session_store import InMemorySessionStore, SessionRecord
    from config.schema import AuthConfig, DomainConfig

    store = InMemorySessionStore()
    store.save(
        SessionRecord(
            session_id="sid-cookie",
            user_id="user-1",
            roles=["analyst"],
            email="user@example.com",
            access_token="acc",
            refresh_token="ref",
            access_token_expires_at=time.time() + 3600,
            id_token="id",
            created_at=time.time(),
            ttl_seconds=3600,
        )
    )

    app = FastAPI()

    auth_cfg = AuthConfig(
        enabled=True,
        issuer_url="https://idp.example.com",
        audience="chili-api",
        jwks_uri="https://idp.example.com/jwks",
        client_id="chili-spa",
        client_secret_env_var="OIDC_CLIENT_SECRET",
        authorize_endpoint="https://idp.example.com/authorize",
        token_endpoint="https://idp.example.com/token",
        redirect_uri="https://app.example.com/auth/callback",
    )

    @app.get("/whoami")
    def whoami(user: User = Depends(get_current_user)) -> dict[str, object]:
        return {"user_id": user.user_id, "roles": user.roles}

    from api.dependencies import get_domain_config

    app.dependency_overrides[get_domain_config] = lambda: DomainConfig(
        domain={"name": "x", "display_name": "X", "description": "X"},
        entities=[],
        relationships=[],
        capabilities={},
        thresholds={},
        auth=auth_cfg,
    )
    app.dependency_overrides[get_session_store] = lambda: store

    from fastapi.testclient import TestClient

    client = TestClient(app)
    response = client.get("/whoami", cookies={"chiliai_session": "sid-cookie"})

    assert response.status_code == 200
    assert response.json() == {"user_id": "user-1", "roles": ["analyst"]}


def test_get_current_user_returns_401_when_cookie_session_is_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cookie pointing at a missing session id results in 401."""
    # Setup mirrors the success test but stores no session.
    # ... (test body parallel to above with empty store; expect 401)
    # See test_get_current_user_resolves_session_from_cookie for fixture shape.
    ...


def test_get_current_user_falls_back_to_bearer_when_no_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With auth enabled, no cookie, valid Bearer token -> existing JWT path is used."""
    # Reuse the existing Bearer test fixtures; the change here is that the
    # cookie-resolution branch is short-circuited when no chiliai_session
    # cookie is present.
    ...
```

> **Plan note:** The two `...` placeholders MUST be filled in with concrete test bodies before the first commit. Use the success-test as the template — same FastAPI app construction, same dependency overrides — but mutate the request (no cookie / unknown sid / Bearer token) and the assertion. Do not commit `...` placeholders.

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_auth_middleware.py -v"
```
Expected: FAIL on the new cookie-path tests (cookie is currently ignored).

- [ ] **Step 3: Implement the cookie path**

Edit `backend/api/middleware/auth.py`. Replace the existing `get_current_user` (lines ~213-232) with:

```python
SESSION_COOKIE_NAME = "chiliai_session"


def _user_from_session(record: "SessionRecord") -> User:
    return User(user_id=record.user_id, roles=record.roles, email=record.email)


def get_current_user(
    request: Request,
    domain_config: DomainConfig = Depends(get_domain_config),
    session_store: "SessionStoreProtocol" = Depends(_session_store_dep),
) -> User:
    """Resolve the current ``User`` from the request.

    Resolution order:
      1. AuthConfig.enabled=False           -> anonymous viewer
      2. Cookie chiliai_session present     -> SessionStore.get(sid) -> User
      3. Authorization: Bearer present      -> existing JWT/JWKS path
      4. Otherwise                          -> 401
    """

    auth_config = _resolve_auth_config(domain_config)
    if not auth_config.enabled:
        return build_anonymous_user()

    sid = request.cookies.get(SESSION_COOKIE_NAME)
    if sid is not None:
        try:
            record = session_store.get(sid)
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session is unknown or has expired.",
            ) from exc
        return _user_from_session(record)

    token = _extract_bearer_token(request)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication: send chiliai_session cookie or Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    claims = decode_token(token, auth_config=auth_config, jwks_cache=_JWKS_CACHE)
    return _extract_user(claims, roles_claim=auth_config.roles_claim)
```

Add the supporting `_session_store_dep` helper, the import for the protocol, and update `__all__`:

```python
from api.dependencies import get_domain_config, get_session_store as _session_store_dep
from api.middleware.session_store import SessionStoreProtocol

# Update __all__:
__all__ = [
    "JwksCache",
    "JwksFetcher",
    "SESSION_COOKIE_NAME",
    "User",
    "build_anonymous_user",
    "decode_token",
    "get_current_user",
    "set_jwks_fetcher",
]
```

> **Plan note on import ordering:** `api.middleware.auth` already imports `from api.dependencies import get_domain_config`. Adding `get_session_store` to the same import line keeps the existing pattern. There is no circular import: `dependencies.py` does not import from `middleware/auth.py`.

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_auth_middleware.py -v"
```
Expected: PASS for all auth middleware tests (cookie path + existing Bearer path + auth-disabled path).

- [ ] **Step 5: Commit**

```bash
git add backend/api/middleware/auth.py backend/tests/api/test_auth_middleware.py
git commit -m "$(cat <<'EOF'
feat(auth): cookie-based session resolution in get_current_user

When AuthConfig.enabled is True and the chiliai_session cookie is
present, the user is resolved from the SessionStore. Bearer tokens
remain valid for service-to-service callers when no cookie is set.
Auth-disabled fallback is unchanged.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: OIDC client helper module

**Files:**
- Create: `backend/api/routers/_oidc_client.py`
- Test: `backend/tests/api/test_oidc_client.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/api/test_oidc_client.py`:

```python
"""Tests for the OIDC client helpers used by the auth router."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from api.routers._oidc_client import (
    OidcClient,
    build_authorize_url,
    build_end_session_url,
    generate_pkce_pair,
)
from config.schema import AuthConfig


@pytest.fixture
def auth_config() -> AuthConfig:
    return AuthConfig(
        enabled=True,
        issuer_url="https://idp.example.com",
        audience="chili-api",
        jwks_uri="https://idp.example.com/jwks",
        client_id="chili-spa",
        client_secret_env_var="OIDC_CLIENT_SECRET",
        authorize_endpoint="https://idp.example.com/authorize",
        token_endpoint="https://idp.example.com/oauth/token",
        end_session_endpoint="https://idp.example.com/logout",
        redirect_uri="https://app.example.com/auth/callback",
        scopes=["openid", "email", "profile"],
    )


def test_generate_pkce_pair_produces_s256_challenge() -> None:
    verifier, challenge = generate_pkce_pair()
    assert 43 <= len(verifier) <= 128
    assert challenge != verifier
    # Verifier should be url-safe base64 (no padding)
    assert "=" not in verifier
    assert "+" not in verifier
    assert "/" not in verifier


def test_build_authorize_url_includes_required_query_params(auth_config: AuthConfig) -> None:
    url = build_authorize_url(
        auth_config,
        state="state-123",
        code_challenge="chal-xyz",
    )
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert parsed.netloc == "idp.example.com"
    assert parsed.path == "/authorize"
    assert qs["client_id"] == ["chili-spa"]
    assert qs["response_type"] == ["code"]
    assert qs["redirect_uri"] == ["https://app.example.com/auth/callback"]
    assert qs["scope"] == ["openid email profile"]
    assert qs["state"] == ["state-123"]
    assert qs["code_challenge"] == ["chal-xyz"]
    assert qs["code_challenge_method"] == ["S256"]


def test_build_end_session_url_includes_id_token_hint(auth_config: AuthConfig) -> None:
    url = build_end_session_url(
        auth_config,
        id_token="id-tok-1",
        post_logout_redirect_uri="https://app.example.com/",
    )
    qs = parse_qs(urlparse(url).query)
    assert qs["id_token_hint"] == ["id-tok-1"]
    assert qs["post_logout_redirect_uri"] == ["https://app.example.com/"]


def test_oidc_client_exchange_code_posts_token_request(auth_config: AuthConfig) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["body"] = request.content.decode()
        return httpx.Response(
            200,
            json={
                "access_token": "acc-tok",
                "refresh_token": "ref-tok",
                "id_token": "id-tok",
                "expires_in": 3600,
                "token_type": "Bearer",
            },
        )

    transport = httpx.MockTransport(handler)
    client = OidcClient(auth_config, client_secret="shh", http_transport=transport)

    tokens = client.exchange_code(code="code-1", code_verifier="ver-1")

    assert tokens.access_token == "acc-tok"
    assert tokens.refresh_token == "ref-tok"
    assert tokens.id_token == "id-tok"
    assert tokens.expires_in == 3600
    assert captured["url"] == "https://idp.example.com/oauth/token"
    assert captured["method"] == "POST"
    body_qs = parse_qs(str(captured["body"]))
    assert body_qs["grant_type"] == ["authorization_code"]
    assert body_qs["code"] == ["code-1"]
    assert body_qs["redirect_uri"] == ["https://app.example.com/auth/callback"]
    assert body_qs["code_verifier"] == ["ver-1"]
    assert body_qs["client_id"] == ["chili-spa"]


def test_oidc_client_refresh_token_grant(auth_config: AuthConfig) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body_qs = parse_qs(request.content.decode())
        assert body_qs["grant_type"] == ["refresh_token"]
        assert body_qs["refresh_token"] == ["ref-old"]
        return httpx.Response(
            200,
            json={
                "access_token": "acc-new",
                "refresh_token": "ref-new",
                "expires_in": 1800,
                "token_type": "Bearer",
            },
        )

    transport = httpx.MockTransport(handler)
    client = OidcClient(auth_config, client_secret="shh", http_transport=transport)

    tokens = client.refresh(refresh_token="ref-old")

    assert tokens.access_token == "acc-new"
    assert tokens.refresh_token == "ref-new"
    assert tokens.expires_in == 1800


def test_oidc_client_exchange_code_raises_on_idp_error(auth_config: AuthConfig) -> None:
    transport = httpx.MockTransport(
        lambda req: httpx.Response(400, json={"error": "invalid_grant"})
    )
    client = OidcClient(auth_config, client_secret="shh", http_transport=transport)

    with pytest.raises(httpx.HTTPStatusError):
        client.exchange_code(code="bad", code_verifier="ver")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_oidc_client.py -v"
```
Expected: FAIL with `ModuleNotFoundError: No module named 'api.routers._oidc_client'`.

- [ ] **Step 3: Implement the OIDC client**

Create `backend/api/routers/_oidc_client.py`:

```python
"""Thin OIDC client used by the BFF auth router.

Encapsulates the OAuth 2.0 authorization-code-with-PKCE flow against any
OIDC provider configured via ``AuthConfig``. No vendor SDK; only httpx +
the existing python-jose dependency for JWT decoding (which lives in
``api.middleware.auth`` and is not duplicated here).
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel

from config.schema import AuthConfig

__all__ = [
    "OidcClient",
    "OidcConfigurationError",
    "OidcTokens",
    "build_authorize_url",
    "build_end_session_url",
    "generate_pkce_pair",
]


class OidcConfigurationError(RuntimeError):
    """Raised when AuthConfig is missing required OIDC fields."""


class OidcTokens(BaseModel):
    """Token bundle returned by the IdP."""

    access_token: str
    refresh_token: str | None = None
    id_token: str | None = None
    expires_in: int
    token_type: str = "Bearer"


def generate_pkce_pair() -> tuple[str, str]:
    """Return ``(code_verifier, code_challenge)`` per RFC 7636 S256."""

    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def _require(value: str | None, *, field: str) -> str:
    if value is None:
        raise OidcConfigurationError(f"AuthConfig.{field} is required when auth is enabled.")
    return value


def build_authorize_url(
    auth_config: AuthConfig,
    *,
    state: str,
    code_challenge: str,
) -> str:
    endpoint = _require(auth_config.authorize_endpoint, field="authorize_endpoint")
    redirect_uri = _require(auth_config.redirect_uri, field="redirect_uri")
    client_id = _require(auth_config.client_id, field="client_id")

    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": " ".join(auth_config.scopes),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{endpoint}?{urlencode(params)}"


def build_end_session_url(
    auth_config: AuthConfig,
    *,
    id_token: str | None,
    post_logout_redirect_uri: str,
) -> str | None:
    if auth_config.end_session_endpoint is None:
        return None
    params: dict[str, str] = {
        "post_logout_redirect_uri": post_logout_redirect_uri,
    }
    if id_token is not None:
        params["id_token_hint"] = id_token
    return f"{auth_config.end_session_endpoint}?{urlencode(params)}"


@dataclass(slots=True)
class OidcClient:
    """OIDC token-endpoint client."""

    auth_config: AuthConfig
    client_secret: str
    http_transport: httpx.BaseTransport | None = None

    def _http(self) -> httpx.Client:
        return httpx.Client(transport=self.http_transport, timeout=10.0)

    def _token_endpoint(self) -> str:
        return _require(self.auth_config.token_endpoint, field="token_endpoint")

    def _client_id(self) -> str:
        return _require(self.auth_config.client_id, field="client_id")

    def exchange_code(self, *, code: str, code_verifier: str) -> OidcTokens:
        redirect_uri = _require(self.auth_config.redirect_uri, field="redirect_uri")
        body = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
            "client_id": self._client_id(),
            "client_secret": self.client_secret,
        }
        with self._http() as client:
            response = client.post(self._token_endpoint(), data=body)
        response.raise_for_status()
        return OidcTokens.model_validate(response.json())

    def refresh(self, *, refresh_token: str) -> OidcTokens:
        body = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self._client_id(),
            "client_secret": self.client_secret,
        }
        with self._http() as client:
            response = client.post(self._token_endpoint(), data=body)
        response.raise_for_status()
        return OidcTokens.model_validate(response.json())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_oidc_client.py -v"
```
Expected: PASS for all OIDC client tests.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/_oidc_client.py backend/tests/api/test_oidc_client.py
git commit -m "$(cat <<'EOF'
feat(auth): provider-agnostic OIDC client helper

PKCE pair generation, authorize-URL builder, end-session-URL builder,
and an httpx-backed token-endpoint client (authorization_code + refresh
grants). No vendor SDK; the test suite uses httpx.MockTransport to avoid
real network calls. The router that consumes this lands in the next
task.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Auth router — `/auth/me` (lightest endpoint, get the wiring in)

**Files:**
- Create: `backend/api/routers/auth.py`
- Modify: `backend/api/app.py` (register router)
- Test: `backend/tests/api/test_auth_router.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/api/test_auth_router.py`:

```python
"""Tests for /auth router."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.dependencies import get_domain_config, get_session_store
from api.middleware.session_store import InMemorySessionStore, SessionRecord
from config.schema import AuthConfig, DomainConfig


def _auth_config() -> AuthConfig:
    return AuthConfig(
        enabled=True,
        issuer_url="https://idp.example.com",
        audience="chili-api",
        jwks_uri="https://idp.example.com/jwks",
        client_id="chili-spa",
        client_secret_env_var="OIDC_CLIENT_SECRET",
        authorize_endpoint="https://idp.example.com/authorize",
        token_endpoint="https://idp.example.com/oauth/token",
        end_session_endpoint="https://idp.example.com/logout",
        redirect_uri="https://app.example.com/auth/callback",
    )


@pytest.fixture
def app_with_auth(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "shh")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/15")
    app = create_app()
    return app


def test_me_returns_401_when_unauthenticated(app_with_auth) -> None:
    store = InMemorySessionStore()
    domain = DomainConfig(
        domain={"name": "x", "display_name": "X", "description": "X"},
        entities=[], relationships=[], capabilities={}, thresholds={},
        auth=_auth_config(),
    )
    app_with_auth.dependency_overrides[get_session_store] = lambda: store
    app_with_auth.dependency_overrides[get_domain_config] = lambda: domain

    with TestClient(app_with_auth) as client:
        response = client.get("/auth/me")
    assert response.status_code == 401


def test_me_returns_user_when_session_cookie_is_valid(app_with_auth) -> None:
    store = InMemorySessionStore()
    store.save(
        SessionRecord(
            session_id="sid-me",
            user_id="user-1",
            roles=["analyst"],
            email="user@example.com",
            access_token="acc",
            refresh_token="ref",
            access_token_expires_at=time.time() + 3600,
            id_token="id",
            created_at=time.time(),
            ttl_seconds=3600,
        )
    )
    domain = DomainConfig(
        domain={"name": "x", "display_name": "X", "description": "X"},
        entities=[], relationships=[], capabilities={}, thresholds={},
        auth=_auth_config(),
    )
    app_with_auth.dependency_overrides[get_session_store] = lambda: store
    app_with_auth.dependency_overrides[get_domain_config] = lambda: domain

    with TestClient(app_with_auth) as client:
        response = client.get("/auth/me", cookies={"chiliai_session": "sid-me"})

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == "user-1"
    assert body["roles"] == ["analyst"]
    assert body["email"] == "user@example.com"


def test_me_returns_anonymous_when_auth_disabled(app_with_auth, monkeypatch) -> None:
    domain = DomainConfig(
        domain={"name": "x", "display_name": "X", "description": "X"},
        entities=[], relationships=[], capabilities={}, thresholds={},
        auth=AuthConfig(),  # enabled=False
    )
    app_with_auth.dependency_overrides[get_domain_config] = lambda: domain

    with TestClient(app_with_auth) as client:
        response = client.get("/auth/me")

    assert response.status_code == 200
    assert response.json()["user_id"] == "anonymous"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_auth_router.py -v"
```
Expected: FAIL — `/auth/me` route does not exist (404).

- [ ] **Step 3: Create the auth router scaffold + `/auth/me`**

Create `backend/api/routers/auth.py`:

```python
"""Backend-for-frontend authentication router.

Owns the OIDC handshake and the session cookie. Tokens never reach
JavaScript: every call from the SPA either sets or reads the
HttpOnly ``chiliai_session`` cookie.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.middleware.auth import User, get_current_user

__all__ = ["router"]


router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=User)
def me(user: User = Depends(get_current_user)) -> User:
    """Return the current authenticated user (or 401)."""
    return user
```

Register the router in `backend/api/app.py` (after the existing REST routers, before `ws_router`):

```python
# at top:
from api.routers.auth import router as auth_router

# in create_app(), after other include_router calls:
app.include_router(auth_router)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_auth_router.py -v"
```
Expected: PASS for the three `/auth/me` tests.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/auth.py backend/api/app.py backend/tests/api/test_auth_router.py
git commit -m "$(cat <<'EOF'
feat(auth): /auth/me endpoint and router scaffold

Adds the GET /auth/me endpoint that returns the current user (401 if
unauthenticated) and registers the auth router in the application
factory. Login/callback/logout endpoints follow in subsequent tasks.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Auth router — `/auth/login` (PKCE + redirect)

**Files:**
- Modify: `backend/api/routers/auth.py` (add `/login`)
- Modify: `backend/tests/api/test_auth_router.py` (add login tests)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/api/test_auth_router.py`:

```python
def test_login_redirects_to_authorize_endpoint_with_pkce_and_state(app_with_auth) -> None:
    store = InMemorySessionStore()
    domain = DomainConfig(
        domain={"name": "x", "display_name": "X", "description": "X"},
        entities=[], relationships=[], capabilities={}, thresholds={},
        auth=_auth_config(),
    )
    app_with_auth.dependency_overrides[get_session_store] = lambda: store
    app_with_auth.dependency_overrides[get_domain_config] = lambda: domain

    with TestClient(app_with_auth, follow_redirects=False) as client:
        response = client.get("/auth/login")

    assert response.status_code == 307
    location = response.headers["location"]
    from urllib.parse import parse_qs, urlparse
    parsed = urlparse(location)
    qs = parse_qs(parsed.query)
    assert parsed.netloc == "idp.example.com"
    assert qs["response_type"] == ["code"]
    assert qs["code_challenge_method"] == ["S256"]
    state = qs["state"][0]
    # PKCE state must be persisted so the callback can recover the verifier
    assert store.pop_pkce_state(state) is not None


def test_login_returns_500_when_oidc_config_incomplete(app_with_auth) -> None:
    incomplete = AuthConfig(enabled=True, issuer_url="https://x", audience="x", jwks_uri="https://x/j")
    domain = DomainConfig(
        domain={"name": "x", "display_name": "X", "description": "X"},
        entities=[], relationships=[], capabilities={}, thresholds={},
        auth=incomplete,
    )
    app_with_auth.dependency_overrides[get_domain_config] = lambda: domain

    with TestClient(app_with_auth, follow_redirects=False) as client:
        response = client.get("/auth/login")

    assert response.status_code == 500
    assert "authorize_endpoint" in response.json()["detail"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_auth_router.py::test_login_redirects_to_authorize_endpoint_with_pkce_and_state tests/api/test_auth_router.py::test_login_returns_500_when_oidc_config_incomplete -v"
```
Expected: FAIL — `/auth/login` does not exist.

- [ ] **Step 3: Implement `/auth/login`**

Edit `backend/api/routers/auth.py`. Add imports and route:

```python
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse

from api.dependencies import get_domain_config, get_session_store
from api.middleware.auth import User, get_current_user
from api.middleware.session_store import SessionStoreProtocol
from api.routers._oidc_client import (
    OidcConfigurationError,
    build_authorize_url,
    generate_pkce_pair,
)
from config.schema import DomainConfig
from shared.utils import generate_id

__all__ = ["router"]


PKCE_STATE_TTL_SECONDS = 300


router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
def login(
    domain_config: DomainConfig = Depends(get_domain_config),
    session_store: SessionStoreProtocol = Depends(get_session_store),
) -> RedirectResponse:
    """Begin the OIDC authorization-code flow."""

    auth_config = domain_config.auth
    if auth_config is None or not auth_config.enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Auth is disabled.",
        )

    state = generate_id()
    verifier, challenge = generate_pkce_pair()
    session_store.save_pkce_state(
        state=state, verifier=verifier, ttl_seconds=PKCE_STATE_TTL_SECONDS
    )

    try:
        url = build_authorize_url(
            auth_config, state=state, code_challenge=challenge
        )
    except OidcConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    return RedirectResponse(url=url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/me", response_model=User)
def me(user: User = Depends(get_current_user)) -> User:
    """Return the current authenticated user (or 401)."""
    return user
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_auth_router.py -v"
```
Expected: PASS for all `/auth/me` and `/auth/login` tests.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/auth.py backend/tests/api/test_auth_router.py
git commit -m "$(cat <<'EOF'
feat(auth): /auth/login redirect with PKCE state

GET /auth/login generates a PKCE verifier/challenge pair, persists the
verifier under a state-keyed entry in the session store (5-minute TTL),
and 307s to the IdP authorize endpoint. Returns 500 with a clear error
when AuthConfig is missing required OIDC fields.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Auth router — `/auth/callback` (token exchange + session mint)

**Files:**
- Modify: `backend/api/routers/auth.py` (add `/callback`)
- Modify: `backend/tests/api/test_auth_router.py` (add callback tests)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/api/test_auth_router.py`:

```python
def _stub_jwks_decoder(claims: dict[str, object]):
    """Replace decode_token to bypass real JWT verification in tests."""
    from api.middleware import auth as auth_module

    def _fake_decode(token, *, auth_config, jwks_cache):  # type: ignore[no-untyped-def]
        del token, auth_config, jwks_cache
        return claims

    return _fake_decode


def test_callback_exchanges_code_and_creates_session_cookie(
    app_with_auth, monkeypatch
) -> None:
    import httpx

    from api.middleware import auth as auth_module
    from api.routers import _oidc_client

    store = InMemorySessionStore()
    store.save_pkce_state(state="state-1", verifier="ver-1", ttl_seconds=300)

    domain = DomainConfig(
        domain={"name": "x", "display_name": "X", "description": "X"},
        entities=[], relationships=[], capabilities={}, thresholds={},
        auth=_auth_config(),
    )
    app_with_auth.dependency_overrides[get_session_store] = lambda: store
    app_with_auth.dependency_overrides[get_domain_config] = lambda: domain

    # Monkeypatch the OIDC client's HTTP transport to a deterministic mock.
    def fake_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "access_token": "acc-tok",
                "refresh_token": "ref-tok",
                "id_token": "id-tok",
                "expires_in": 3600,
                "token_type": "Bearer",
            },
        )

    monkeypatch.setattr(
        _oidc_client.OidcClient,
        "_http",
        lambda self: httpx.Client(transport=httpx.MockTransport(fake_handler), timeout=5.0),
    )
    monkeypatch.setattr(
        auth_module,
        "decode_token",
        _stub_jwks_decoder({"sub": "user-cb", "roles": ["analyst"], "email": "cb@example.com"}),
    )

    with TestClient(app_with_auth, follow_redirects=False) as client:
        response = client.get("/auth/callback?code=auth-code&state=state-1")

    assert response.status_code == 307
    assert response.headers["location"] == "/"
    set_cookie = response.headers.get("set-cookie", "")
    assert "chiliai_session=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "SameSite=lax" in set_cookie.lower()


def test_callback_rejects_unknown_state(app_with_auth) -> None:
    store = InMemorySessionStore()  # no PKCE state stored
    domain = DomainConfig(
        domain={"name": "x", "display_name": "X", "description": "X"},
        entities=[], relationships=[], capabilities={}, thresholds={},
        auth=_auth_config(),
    )
    app_with_auth.dependency_overrides[get_session_store] = lambda: store
    app_with_auth.dependency_overrides[get_domain_config] = lambda: domain

    with TestClient(app_with_auth, follow_redirects=False) as client:
        response = client.get("/auth/callback?code=c&state=unknown")

    assert response.status_code == 400
    assert "state" in response.json()["detail"].lower()


def test_callback_propagates_idp_token_error(app_with_auth, monkeypatch) -> None:
    import httpx

    from api.routers import _oidc_client

    store = InMemorySessionStore()
    store.save_pkce_state(state="state-err", verifier="ver", ttl_seconds=300)
    domain = DomainConfig(
        domain={"name": "x", "display_name": "X", "description": "X"},
        entities=[], relationships=[], capabilities={}, thresholds={},
        auth=_auth_config(),
    )
    app_with_auth.dependency_overrides[get_session_store] = lambda: store
    app_with_auth.dependency_overrides[get_domain_config] = lambda: domain

    def fake_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant"})

    monkeypatch.setattr(
        _oidc_client.OidcClient,
        "_http",
        lambda self: httpx.Client(transport=httpx.MockTransport(fake_handler), timeout=5.0),
    )

    with TestClient(app_with_auth, follow_redirects=False) as client:
        response = client.get("/auth/callback?code=bad&state=state-err")

    assert response.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_auth_router.py::test_callback_exchanges_code_and_creates_session_cookie tests/api/test_auth_router.py::test_callback_rejects_unknown_state tests/api/test_auth_router.py::test_callback_propagates_idp_token_error -v"
```
Expected: FAIL — `/auth/callback` does not exist.

- [ ] **Step 3: Implement `/auth/callback`**

Edit `backend/api/routers/auth.py`. Add to imports:

```python
import os
import time

import httpx

from api.middleware.auth import SESSION_COOKIE_NAME, decode_token
from api.middleware.session_store import SessionRecord
from api.routers._oidc_client import OidcClient
```

Add the helper and the route:

```python
def _client_secret(auth_config) -> str:
    if auth_config.client_secret_env_var is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AuthConfig.client_secret_env_var is required when auth is enabled.",
        )
    secret = os.environ.get(auth_config.client_secret_env_var)
    if secret is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Env var '{auth_config.client_secret_env_var}' is not set.",
        )
    return secret


@router.get("/callback")
def callback(
    code: str,
    state: str,
    domain_config: DomainConfig = Depends(get_domain_config),
    session_store: SessionStoreProtocol = Depends(get_session_store),
) -> RedirectResponse:
    """Exchange the authorization code for tokens and mint a session."""

    auth_config = domain_config.auth
    if auth_config is None or not auth_config.enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Auth is disabled.",
        )

    verifier = session_store.pop_pkce_state(state)
    if verifier is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unknown or expired state.",
        )

    secret = _client_secret(auth_config)
    client = OidcClient(auth_config=auth_config, client_secret=secret)
    try:
        tokens = client.exchange_code(code=code, code_verifier=verifier)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"IdP token endpoint rejected the code: {exc.response.text}",
        ) from exc

    # Decode id_token (or access_token if id_token is absent) to extract user identity.
    token_to_decode = tokens.id_token or tokens.access_token
    claims = decode_token(
        token_to_decode,
        auth_config=auth_config,
        jwks_cache=__import__("api.middleware.auth", fromlist=["_JWKS_CACHE"])._JWKS_CACHE,
    )
    user_id = str(claims.get("sub") or "unknown")
    email = claims.get("email")
    raw_roles = claims.get(auth_config.roles_claim)
    if isinstance(raw_roles, list):
        roles = [str(item) for item in raw_roles]
    elif isinstance(raw_roles, str):
        roles = [raw_roles]
    else:
        roles = []

    sid = generate_id()
    now = time.time()
    record = SessionRecord(
        session_id=sid,
        user_id=user_id,
        roles=roles,
        email=email if isinstance(email, str) else None,
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        access_token_expires_at=now + tokens.expires_in,
        id_token=tokens.id_token,
        created_at=now,
        ttl_seconds=auth_config.session_ttl_seconds,
    )
    session_store.save(record)

    response = RedirectResponse(url="/", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=sid,
        max_age=auth_config.session_ttl_seconds,
        secure=auth_config.cookie_secure,
        httponly=True,
        samesite="lax",
        domain=auth_config.cookie_domain,
        path="/",
    )
    return response
```

> **Plan note:** The `__import__` trick fetches `_JWKS_CACHE` from the `api.middleware.auth` module without exporting it through `__all__`. If the executor prefers a cleaner approach, add `_JWKS_CACHE` to `auth.__all__` and import it directly — both are acceptable.

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_auth_router.py -v"
```
Expected: PASS for all `/auth/me`, `/auth/login`, and `/auth/callback` tests.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/auth.py backend/tests/api/test_auth_router.py
git commit -m "$(cat <<'EOF'
feat(auth): /auth/callback exchanges code and mints session

Pops the PKCE verifier from the session store, exchanges the
authorization code for tokens via the OIDC client, decodes the id_token
to extract user identity and roles, persists a SessionRecord under an
opaque session id, and 307s back to '/' with an HttpOnly Secure
SameSite=Lax chiliai_session cookie. Rejects unknown state with 400 and
surfaces IdP token errors as 400.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Auth router — `/auth/logout`

**Files:**
- Modify: `backend/api/routers/auth.py` (add `/logout`)
- Modify: `backend/tests/api/test_auth_router.py` (add logout tests)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/api/test_auth_router.py`:

```python
def test_logout_clears_cookie_and_session(app_with_auth) -> None:
    store = InMemorySessionStore()
    store.save(
        SessionRecord(
            session_id="sid-out",
            user_id="user-1",
            roles=["analyst"],
            email="u@e.com",
            access_token="acc",
            refresh_token="ref",
            access_token_expires_at=time.time() + 3600,
            id_token="id-tok-1",
            created_at=time.time(),
            ttl_seconds=3600,
        )
    )
    domain = DomainConfig(
        domain={"name": "x", "display_name": "X", "description": "X"},
        entities=[], relationships=[], capabilities={}, thresholds={},
        auth=_auth_config(),
    )
    app_with_auth.dependency_overrides[get_session_store] = lambda: store
    app_with_auth.dependency_overrides[get_domain_config] = lambda: domain

    with TestClient(app_with_auth, follow_redirects=False) as client:
        response = client.post("/auth/logout", cookies={"chiliai_session": "sid-out"})

    # Cookie must be expired in the response
    set_cookie = response.headers.get("set-cookie", "")
    assert "chiliai_session=" in set_cookie
    assert ("Max-Age=0" in set_cookie) or ("max-age=0" in set_cookie)
    # Session must be gone
    from api.middleware.session_store import SessionNotFoundError
    with pytest.raises(SessionNotFoundError):
        store.get("sid-out")


def test_logout_redirects_to_idp_end_session_when_configured(app_with_auth) -> None:
    store = InMemorySessionStore()
    store.save(
        SessionRecord(
            session_id="sid-rp",
            user_id="user-1",
            roles=["analyst"],
            email="u@e.com",
            access_token="acc",
            refresh_token="ref",
            access_token_expires_at=time.time() + 3600,
            id_token="id-tok-1",
            created_at=time.time(),
            ttl_seconds=3600,
        )
    )
    domain = DomainConfig(
        domain={"name": "x", "display_name": "X", "description": "X"},
        entities=[], relationships=[], capabilities={}, thresholds={},
        auth=_auth_config(),  # has end_session_endpoint
    )
    app_with_auth.dependency_overrides[get_session_store] = lambda: store
    app_with_auth.dependency_overrides[get_domain_config] = lambda: domain

    with TestClient(app_with_auth, follow_redirects=False) as client:
        response = client.post(
            "/auth/logout?post_logout_redirect_uri=https%3A%2F%2Fapp.example.com%2F",
            cookies={"chiliai_session": "sid-rp"},
        )

    assert response.status_code == 307
    location = response.headers["location"]
    assert location.startswith("https://idp.example.com/logout")
    assert "id_token_hint=id-tok-1" in location


def test_logout_no_session_cookie_is_idempotent(app_with_auth) -> None:
    domain = DomainConfig(
        domain={"name": "x", "display_name": "X", "description": "X"},
        entities=[], relationships=[], capabilities={}, thresholds={},
        auth=_auth_config(),
    )
    app_with_auth.dependency_overrides[get_domain_config] = lambda: domain

    with TestClient(app_with_auth, follow_redirects=False) as client:
        response = client.post("/auth/logout")

    assert response.status_code in (204, 307)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_auth_router.py::test_logout_clears_cookie_and_session tests/api/test_auth_router.py::test_logout_redirects_to_idp_end_session_when_configured tests/api/test_auth_router.py::test_logout_no_session_cookie_is_idempotent -v"
```
Expected: FAIL — `/auth/logout` does not exist (405 or 404).

- [ ] **Step 3: Implement `/auth/logout`**

Edit `backend/api/routers/auth.py`. Import `Request` and `Response` and `build_end_session_url`:

```python
from fastapi import Request, Response

from api.routers._oidc_client import build_end_session_url
```

Add the route:

```python
@router.post("/logout")
def logout(
    request: Request,
    domain_config: DomainConfig = Depends(get_domain_config),
    session_store: SessionStoreProtocol = Depends(get_session_store),
    post_logout_redirect_uri: str | None = None,
) -> Response:
    """Delete the server-side session, clear the cookie, and (optionally) bounce to IdP."""

    auth_config = domain_config.auth
    sid = request.cookies.get(SESSION_COOKIE_NAME)
    id_token: str | None = None
    if sid is not None:
        try:
            record = session_store.get(sid)
            id_token = record.id_token
        except KeyError:
            pass
        session_store.delete(sid)

    # Decide response: redirect to IdP RP-initiated logout if configured.
    rp_url: str | None = None
    if auth_config is not None and auth_config.enabled:
        target = post_logout_redirect_uri or "/"
        rp_url = build_end_session_url(
            auth_config,
            id_token=id_token,
            post_logout_redirect_uri=target,
        )

    if rp_url is not None:
        response = RedirectResponse(url=rp_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    else:
        response = Response(status_code=status.HTTP_204_NO_CONTENT)

    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        domain=auth_config.cookie_domain if auth_config is not None else None,
    )
    return response
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_auth_router.py -v"
```
Expected: PASS for all auth router tests including the three new logout tests.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/auth.py backend/tests/api/test_auth_router.py
git commit -m "$(cat <<'EOF'
feat(auth): /auth/logout deletes session, clears cookie, optional RP-initiated logout

POST /auth/logout removes the server-side session record and expires
the chiliai_session cookie. When AuthConfig.end_session_endpoint is set,
returns a 307 to the IdP's RP-initiated logout endpoint with
id_token_hint and post_logout_redirect_uri; otherwise returns 204.
Calling /auth/logout without a session cookie is a no-op.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Refresh-on-near-expiry in `get_current_user`

**Files:**
- Modify: `backend/api/middleware/auth.py` (refresh path)
- Modify: `backend/tests/api/test_auth_middleware.py` (add refresh tests)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/api/test_auth_middleware.py`:

```python
def test_get_current_user_refreshes_when_access_token_near_expiry(monkeypatch) -> None:
    """When the access token is within 60s of expiry, the BFF triggers refresh."""
    import time

    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    from api.dependencies import get_domain_config, get_session_store
    from api.middleware import auth as auth_module
    from api.middleware.auth import User, get_current_user
    from api.middleware.session_store import InMemorySessionStore, SessionRecord
    from api.routers import _oidc_client
    from config.schema import AuthConfig, DomainConfig

    import httpx

    store = InMemorySessionStore()
    store.save(
        SessionRecord(
            session_id="sid-refresh",
            user_id="user-1",
            roles=["analyst"],
            email="u@e.com",
            access_token="old-acc",
            refresh_token="ref-tok",
            access_token_expires_at=time.time() + 30,  # within 60s
            id_token="id",
            created_at=time.time(),
            ttl_seconds=3600,
        )
    )

    refresh_calls: list[str] = []

    def fake_handler(request: httpx.Request) -> httpx.Response:
        refresh_calls.append(request.content.decode())
        return httpx.Response(
            200,
            json={
                "access_token": "new-acc",
                "refresh_token": "new-ref",
                "expires_in": 3600,
                "token_type": "Bearer",
            },
        )

    monkeypatch.setattr(
        _oidc_client.OidcClient,
        "_http",
        lambda self: httpx.Client(transport=httpx.MockTransport(fake_handler), timeout=5.0),
    )
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "shh")

    auth_cfg = AuthConfig(
        enabled=True,
        issuer_url="https://idp.example.com",
        audience="chili-api",
        jwks_uri="https://idp.example.com/jwks",
        client_id="chili-spa",
        client_secret_env_var="OIDC_CLIENT_SECRET",
        authorize_endpoint="https://idp.example.com/authorize",
        token_endpoint="https://idp.example.com/oauth/token",
        redirect_uri="https://app.example.com/auth/callback",
    )
    domain = DomainConfig(
        domain={"name": "x", "display_name": "X", "description": "X"},
        entities=[], relationships=[], capabilities={}, thresholds={},
        auth=auth_cfg,
    )

    app = FastAPI()

    @app.get("/whoami")
    def whoami(user: User = Depends(get_current_user)) -> dict[str, object]:
        return {"user_id": user.user_id}

    app.dependency_overrides[get_domain_config] = lambda: domain
    app.dependency_overrides[get_session_store] = lambda: store

    with TestClient(app) as client:
        response = client.get("/whoami", cookies={"chiliai_session": "sid-refresh"})

    assert response.status_code == 200
    assert len(refresh_calls) == 1
    # Session must now have new tokens
    refreshed = store.get("sid-refresh")
    assert refreshed.access_token == "new-acc"
    assert refreshed.refresh_token == "new-ref"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_auth_middleware.py::test_get_current_user_refreshes_when_access_token_near_expiry -v"
```
Expected: FAIL — refresh path is not yet implemented.

- [ ] **Step 3: Implement the refresh path**

Edit `backend/api/middleware/auth.py`. Add the refresh helper and call it from the cookie path:

```python
import os as _os
import time as _time

REFRESH_LEEWAY_SECONDS = 60


def _maybe_refresh_session(
    record: "SessionRecord",
    *,
    auth_config: AuthConfig,
    session_store: "SessionStoreProtocol",
) -> "SessionRecord":
    """If the access token is near expiry and a refresh token exists, refresh in-band."""

    if record.refresh_token is None:
        return record
    if record.access_token_expires_at - _time.time() > REFRESH_LEEWAY_SECONDS:
        return record

    secret_env = auth_config.client_secret_env_var
    if secret_env is None:
        return record
    secret = _os.environ.get(secret_env)
    if secret is None:
        return record

    from api.routers._oidc_client import OidcClient

    client = OidcClient(auth_config=auth_config, client_secret=secret)
    try:
        tokens = client.refresh(refresh_token=record.refresh_token)
    except Exception:
        # Refresh failure is treated as session expiry by callers (cookie path).
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session refresh failed; please sign in again.",
        )

    updated = record.model_copy(
        update={
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token or record.refresh_token,
            "access_token_expires_at": _time.time() + tokens.expires_in,
        }
    )
    session_store.save(updated)
    return updated
```

Modify the cookie branch in `get_current_user`:

```python
sid = request.cookies.get(SESSION_COOKIE_NAME)
if sid is not None:
    try:
        record = session_store.get(sid)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session is unknown or has expired.",
        ) from exc
    record = _maybe_refresh_session(
        record, auth_config=auth_config, session_store=session_store
    )
    # Touch session TTL on every authenticated request (sliding window).
    session_store.touch(sid, ttl_seconds=auth_config.session_ttl_seconds)
    return _user_from_session(record)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_auth_middleware.py tests/api/test_auth_router.py -v"
```
Expected: PASS for all auth tests including refresh.

- [ ] **Step 5: Commit**

```bash
git add backend/api/middleware/auth.py backend/tests/api/test_auth_middleware.py
git commit -m "$(cat <<'EOF'
feat(auth): silent refresh when access token is within 60s of expiry

When the cookie path resolves a session whose access token is near
expiry, get_current_user runs the OIDC refresh_token grant inline and
swaps tokens in the session store before returning. Refresh failure
yields 401 so the SPA redirects to /login. Sliding session TTL is
applied on every authenticated request via session_store.touch.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: `policy_registry.assert_complete`

**Files:**
- Create: `backend/api/middleware/policy_registry.py`
- Test: `backend/tests/api/test_policy_registry.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/api/test_policy_registry.py`:

```python
"""Tests for policy_registry.assert_complete — default-deny audit at startup."""

from __future__ import annotations

import pytest
from fastapi import APIRouter, Depends, FastAPI

from api.middleware.policy_registry import (
    PolicyMissingError,
    assert_complete,
)
from api.middleware.rbac import require_role


def test_assert_complete_passes_when_every_route_has_role_dependency() -> None:
    app = FastAPI()
    router = APIRouter()

    @router.get("/widgets", dependencies=[Depends(require_role("viewer"))])
    def list_widgets() -> dict[str, str]:
        return {}

    @router.post("/widgets", dependencies=[Depends(require_role("analyst"))])
    def create_widget() -> dict[str, str]:
        return {}

    app.include_router(router)

    assert_complete(app)  # no raise


def test_assert_complete_raises_when_route_missing_role() -> None:
    app = FastAPI()

    @app.get("/unprotected")
    def unprotected() -> dict[str, str]:
        return {}

    with pytest.raises(PolicyMissingError) as excinfo:
        assert_complete(app)

    assert "/unprotected" in str(excinfo.value)


def test_assert_complete_skips_auth_health_and_docs_routes() -> None:
    app = FastAPI()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {}

    @app.get("/auth/me")
    def me() -> dict[str, str]:
        return {}

    @app.get("/metrics")
    def metrics() -> dict[str, str]:
        return {}

    # /docs and /openapi.json are FastAPI built-ins; they exist in app.routes.
    assert_complete(app)  # no raise


def test_assert_complete_finds_role_dependency_through_nested_dependencies() -> None:
    """If require_role is wrapped in another dependency, the marker still bubbles up."""
    app = FastAPI()

    role_dep = require_role("analyst")

    def composite(user=Depends(role_dep)):
        return user

    @app.get("/composite", dependencies=[Depends(composite)])
    def composite_route() -> dict[str, str]:
        return {}

    assert_complete(app)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_policy_registry.py -v"
```
Expected: FAIL — `policy_registry` module does not exist.

- [ ] **Step 3: Implement `policy_registry`**

Create `backend/api/middleware/policy_registry.py`:

```python
"""Default-deny audit: every route must carry a require_role dependency."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute, APIWebSocketRoute

__all__ = ["PolicyMissingError", "assert_complete"]


SKIP_PREFIXES = (
    "/auth/",
    "/health",
    "/metrics",
    "/docs",
    "/openapi.json",
    "/redoc",
)


class PolicyMissingError(RuntimeError):
    """Raised when one or more routes do not declare a required role."""


def _has_role_dependency(dependant: Dependant) -> bool:
    pending: list[Dependant] = list(dependant.dependencies)
    while pending:
        current = pending.pop()
        call = current.call
        if call is not None and getattr(call, "_chiliai_required_role", None) is not None:
            return True
        pending.extend(current.dependencies)
    return False


def _route_path(route: object) -> str:
    return getattr(route, "path", "")


def assert_complete(app: FastAPI) -> None:
    """Walk ``app.routes`` and raise if any non-skipped route is missing a role policy."""

    missing: list[str] = []
    for route in app.routes:
        if not isinstance(route, (APIRoute, APIWebSocketRoute)):
            continue
        path = _route_path(route)
        if any(path.startswith(prefix) or path == prefix.rstrip("/") for prefix in SKIP_PREFIXES):
            continue
        if not _has_role_dependency(route.dependant):
            missing.append(path)

    if missing:
        raise PolicyMissingError(
            "Routes missing role policy (add Depends(require_role(...)) to each): "
            + ", ".join(sorted(set(missing)))
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_policy_registry.py -v"
```
Expected: PASS for all four tests.

- [ ] **Step 5: Commit**

```bash
git add backend/api/middleware/policy_registry.py backend/tests/api/test_policy_registry.py
git commit -m "$(cat <<'EOF'
feat(auth): policy_registry.assert_complete default-deny audit

Walks app.routes and raises PolicyMissingError when any non-/auth,
non-/health, non-/docs route lacks a require_role dependency anywhere
in its dependency tree. The check is structural (uses the
_chiliai_required_role marker on the dependency callable), so wrapping
require_role in a composite dependency still satisfies the audit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 14: Wire `assert_complete` and the production guardrail in `create_app`

**Files:**
- Modify: `backend/api/app.py`
- Test: `backend/tests/api/test_production_guardrail.py`
- Test: `backend/tests/api/test_app_startup.py` (or extend existing app tests)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/api/test_production_guardrail.py`:

```python
"""Production startup guardrails."""

from __future__ import annotations

import pytest


def _set_dev_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")


def test_create_app_refuses_when_production_and_auth_disabled(monkeypatch) -> None:
    monkeypatch.setenv("CHILI_ENV", "production")
    _set_dev_redis(monkeypatch)
    # Default config has auth.enabled=False
    from api.app import create_app

    with pytest.raises(RuntimeError, match="AuthConfig.enabled must be True"):
        create_app()


def test_create_app_refuses_when_production_and_oidc_fields_missing(monkeypatch) -> None:
    monkeypatch.setenv("CHILI_ENV", "production")
    _set_dev_redis(monkeypatch)
    monkeypatch.setenv("CHILI_AUTH_ENABLED", "true")
    # Only set issuer_url; leave the rest missing.
    from api.app import create_app
    from config.loader import load_config
    from config.schema import AuthConfig

    base = load_config()
    incomplete = base.model_copy(
        update={"auth": AuthConfig(enabled=True, issuer_url="https://idp.example.com")}
    )
    monkeypatch.setattr("api.app.load_config", lambda: incomplete)

    with pytest.raises(RuntimeError, match="AuthConfig is missing"):
        create_app()


def test_create_app_succeeds_under_dev_with_auth_disabled(monkeypatch) -> None:
    monkeypatch.delenv("CHILI_ENV", raising=False)
    _set_dev_redis(monkeypatch)
    from api.app import create_app

    app = create_app()
    assert app is not None


def test_create_app_runs_policy_registry_assert_when_auth_enabled(monkeypatch) -> None:
    """If auth is enabled and a non-/auth route lacks a role policy, app refuses to start."""
    import pytest

    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "shh")

    from api.app import create_app
    from api.middleware.policy_registry import PolicyMissingError
    from config.loader import load_config
    from config.schema import AuthConfig

    base = load_config()
    enabled = base.model_copy(
        update={
            "auth": AuthConfig(
                enabled=True,
                issuer_url="https://idp.example.com",
                audience="chili-api",
                jwks_uri="https://idp.example.com/jwks",
                client_id="chili-spa",
                client_secret_env_var="OIDC_CLIENT_SECRET",
                authorize_endpoint="https://idp.example.com/authorize",
                token_endpoint="https://idp.example.com/oauth/token",
                redirect_uri="https://app.example.com/auth/callback",
            )
        }
    )
    monkeypatch.setattr("api.app.load_config", lambda: enabled)

    # At this point, no router has require_role yet — assert_complete will fail.
    with pytest.raises(PolicyMissingError):
        create_app()
```

> **Plan note:** The fourth test asserts the full integration: `create_app` calls `assert_complete` when auth is enabled, and at this point in the plan no router has yet been protected. Once Tasks 16-22 attach `require_role` to every router this test should be relaxed or moved — see the note in Task 22.

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_production_guardrail.py -v"
```
Expected: FAIL — guardrail and assert_complete hook not wired yet.

- [ ] **Step 3: Wire the guardrail and the audit hook in `create_app`**

Edit `backend/api/app.py`. Replace the body with:

```python
"""FastAPI application factory for the chiliAI backend API gateway."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.middleware.metrics import register_metrics
from api.middleware.policy_registry import assert_complete
from api.routers.alerts import router as alerts_router
from api.routers.analytics import router as analytics_router
from api.routers.auth import router as auth_router
from api.routers.chat import router as chat_router
from api.routers.config import router as config_router
from api.routers.investigation import router as investigation_router
from api.routers.knowledgebases import router as knowledgebases_router
from api.routers.ws import router as ws_router
from config.loader import load_config
from config.schema import AuthConfig
from shared.logging import configure_logging, get_logger
from shared.tracing import instrument_fastapi_app, setup_tracing

__all__ = ["create_app"]

logger = get_logger("chili.api")


def _enforce_production_guardrail(auth: AuthConfig | None) -> None:
    if os.environ.get("CHILI_ENV") != "production":
        return
    if auth is None or not auth.enabled:
        raise RuntimeError(
            "AuthConfig.enabled must be True under CHILI_ENV=production."
        )
    required = (
        ("issuer_url", auth.issuer_url),
        ("audience", auth.audience),
        ("jwks_uri", auth.jwks_uri),
        ("client_id", auth.client_id),
        ("client_secret_env_var", auth.client_secret_env_var),
        ("authorize_endpoint", auth.authorize_endpoint),
        ("token_endpoint", auth.token_endpoint),
        ("redirect_uri", auth.redirect_uri),
    )
    missing = [name for name, value in required if value is None]
    if missing:
        raise RuntimeError(
            f"AuthConfig is missing required fields under CHILI_ENV=production: {missing}"
        )


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    configure_logging()
    setup_tracing()

    config = load_config()
    _enforce_production_guardrail(config.auth)

    app = FastAPI(
        title="chiliAI API",
        version="0.1.0",
        description="Backend API gateway for the chiliAI Graph RAG analytics platform.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://localhost:80",
            "http://localhost",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_metrics(app)
    instrument_fastapi_app(app)

    @app.get("/health")
    async def health() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"status": "ok"}

    # REST routers
    app.include_router(config_router)
    app.include_router(knowledgebases_router)
    app.include_router(alerts_router)
    app.include_router(investigation_router)
    app.include_router(chat_router)
    app.include_router(analytics_router)
    app.include_router(auth_router)
    app.include_router(ws_router)

    # Default-deny audit. Only runs when auth is enabled — auth-disabled dev
    # path retains the existing anonymous-viewer fallback semantics.
    if config.auth is not None and config.auth.enabled:
        assert_complete(app)

    logger.info("api_app_initialized", version=app.version)
    return app
```

- [ ] **Step 4: Run tests to verify they pass**

The fourth test (`test_create_app_runs_policy_registry_assert_when_auth_enabled`) is expected to **continue passing through Task 22** (each router added in tasks 16-22 makes the route count under audit shrink). Once every router carries `require_role`, the test should be replaced with a positive test that asserts `create_app()` succeeds with auth enabled.

For now:

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_production_guardrail.py -v"
```
Expected: PASS for all four tests.

Also re-run the full suite to confirm no regression:

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest -q"
```
Expected: still 903+ passing.

- [ ] **Step 5: Commit**

```bash
git add backend/api/app.py backend/tests/api/test_production_guardrail.py
git commit -m "$(cat <<'EOF'
feat(auth): production guardrail + default-deny audit at startup

create_app refuses to start when CHILI_ENV=production and AuthConfig is
either disabled or missing any required OIDC field. When auth is
enabled, policy_registry.assert_complete runs after all routers are
registered and refuses to start if any non-skipped route lacks a
require_role dependency. Auth-disabled dev/test paths are unaffected.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Phase 2 — Apply policies to existing routers

> **Note for the executor:** Tasks 15-21 each add `Depends(require_role(...))` per the policy table to one router. Backend tests in each router's existing test file should also receive an "auth-enabled trio" where appropriate, but to keep tasks compact each task only adds one or two representative trio tests; comprehensive role coverage tests are added in Task 22.

## Task 15: Attach role policies — `config` router

**Files:**
- Modify: `backend/api/routers/config.py`
- Modify: `backend/tests/api/test_config_router.py` (add auth-enabled trio for `GET /config/domain`)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/api/test_config_router.py`:

```python
def test_config_get_requires_viewer_when_auth_enabled(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from api.app import create_app
    from api.dependencies import get_domain_config, get_session_store
    from api.middleware.session_store import InMemorySessionStore, SessionRecord
    from config.schema import AuthConfig, DomainConfig
    import time

    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "shh")

    auth_cfg = AuthConfig(
        enabled=True,
        issuer_url="https://idp.example.com",
        audience="chili-api",
        jwks_uri="https://idp.example.com/jwks",
        client_id="chili-spa",
        client_secret_env_var="OIDC_CLIENT_SECRET",
        authorize_endpoint="https://idp.example.com/authorize",
        token_endpoint="https://idp.example.com/oauth/token",
        redirect_uri="https://app.example.com/auth/callback",
    )
    domain = DomainConfig(
        domain={"name": "x", "display_name": "X", "description": "X"},
        entities=[], relationships=[], capabilities={}, thresholds={},
        auth=auth_cfg,
    )

    monkeypatch.setattr("api.app.load_config", lambda: domain)
    app = create_app()

    store = InMemorySessionStore()
    store.save(
        SessionRecord(
            session_id="sid-cfg",
            user_id="u",
            roles=["viewer"],
            email=None,
            access_token="a",
            refresh_token="r",
            access_token_expires_at=time.time() + 3600,
            id_token="i",
            created_at=time.time(),
            ttl_seconds=3600,
        )
    )
    app.dependency_overrides[get_session_store] = lambda: store
    app.dependency_overrides[get_domain_config] = lambda: domain

    with TestClient(app) as client:
        # No cookie -> 401
        assert client.get("/config/domain").status_code == 401
        # Viewer cookie -> 200
        resp = client.get("/config/domain", cookies={"chiliai_session": "sid-cfg"})
        assert resp.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_config_router.py::test_config_get_requires_viewer_when_auth_enabled -v"
```
Expected: FAIL — currently anyone (including unauthenticated) can hit `/config/domain` even with auth enabled.

- [ ] **Step 3: Attach policy**

Edit `backend/api/routers/config.py`:

```python
"""Configuration API router — serves domain config to the frontend."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies import get_domain_config_payload
from api.middleware.rbac import require_role

__all__ = ["router"]

router = APIRouter(prefix="/config", tags=["configuration"])


@router.get("/domain", dependencies=[Depends(require_role("viewer"))])
async def get_domain(
    config: dict[str, object] = Depends(get_domain_config_payload),
) -> dict[str, object]:
    """Return the active domain configuration."""
    return config
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_config_router.py -v"
```
Expected: PASS — auth-enabled trio passes; existing auth-disabled tests still pass.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/config.py backend/tests/api/test_config_router.py
git commit -m "$(cat <<'EOF'
feat(rbac): require viewer role on GET /config/domain

Per the policy table, the dynamic-domain config endpoint is readable by
any authenticated user. Auth-disabled fallback is unchanged because the
require_role dependency short-circuits when AuthConfig.enabled is False.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 16: Attach role policies — `knowledgebases` router

**Files:**
- Modify: `backend/api/routers/knowledgebases.py`
- Modify: `backend/tests/api/test_knowledgebases_router.py` (add representative trio)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/api/test_knowledgebases_router.py`. Use the same fixture pattern as Task 15. Test cases:
- `GET /knowledgebases` with viewer cookie → 200; with no cookie → 401
- `POST /knowledgebases` with viewer cookie → 403; with analyst cookie → 201
- `DELETE /knowledgebases/{id}` with analyst cookie → 403; with admin cookie → success status (204 or 200 per existing implementation)

> **Plan note:** Read the existing `backend/api/routers/knowledgebases.py` to identify the exact endpoints and their HTTP methods. The policy table is:
> - `GET /knowledgebases`, `GET /knowledgebases/{id}` → viewer
> - `POST /knowledgebases`, document upload (`POST /{id}/documents`), `DELETE /{id}/documents/{doc_id}` → analyst
> - `DELETE /knowledgebases/{id}` → admin
>
> Write one test per role boundary (3 tests: viewer/analyst/admin). Reuse the helper from Task 15.

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_knowledgebases_router.py -v -k 'role or auth'"
```
Expected: FAIL on the new role-boundary tests.

- [ ] **Step 3: Attach policies**

Edit each route handler in `backend/api/routers/knowledgebases.py`. Add `dependencies=[Depends(require_role(...))]` per the policy table on each `@router` decorator. Add the import:

```python
from api.middleware.rbac import require_role
```

Decorator examples:

```python
@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=KnowledgeBase,
    dependencies=[Depends(require_role("analyst"))],
)

@router.get(
    "",
    response_model=KbListResponse,
    dependencies=[Depends(require_role("viewer"))],
)

@router.get(
    "/{kb_id}",
    response_model=KnowledgeBase,
    dependencies=[Depends(require_role("viewer"))],
)

@router.delete(
    "/{kb_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role("admin"))],
)

@router.post(
    "/{kb_id}/documents",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_role("analyst"))],
)

@router.get(
    "/{kb_id}/documents",
    response_model=DocumentListResponse,
    dependencies=[Depends(require_role("viewer"))],
)

@router.delete(
    "/{kb_id}/documents/{doc_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role("analyst"))],
)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_knowledgebases_router.py -v"
```
Expected: PASS for all KB router tests.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/knowledgebases.py backend/tests/api/test_knowledgebases_router.py
git commit -m "$(cat <<'EOF'
feat(rbac): apply role policies to knowledgebases router

Read endpoints (list, get, document list) require viewer; mutations
(create, document upload, document delete) require analyst; KB delete
requires admin. Auth-disabled fallback is unchanged.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 17: Attach role policies — `alerts` router

**Files:**
- Modify: `backend/api/routers/alerts.py`
- Modify: `backend/tests/api/test_alerts_router.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/api/test_alerts_router.py` two tests:
- `GET /alerts` requires viewer (no cookie → 401, viewer cookie → 200)
- `POST /alerts/{id}/acknowledge` requires analyst (viewer cookie → 403, analyst cookie → 200 with the existing fixture data)

(Use the same fixture helper as Tasks 15 and 16.)

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_alerts_router.py -v -k 'role or auth'"
```
Expected: FAIL.

- [ ] **Step 3: Attach policies**

Edit `backend/api/routers/alerts.py`. Add the import:

```python
from api.middleware.rbac import require_role
```

Update decorators:

```python
@router.get("", response_model=AlertListResponse, dependencies=[Depends(require_role("viewer"))])

@router.post(
    "/{alert_id}/acknowledge",
    response_model=AlertActionResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_role("analyst"))],
)

@router.post(
    "/{alert_id}/resolve",
    response_model=AlertActionResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_role("analyst"))],
)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_alerts_router.py -v"
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/alerts.py backend/tests/api/test_alerts_router.py
git commit -m "$(cat <<'EOF'
feat(rbac): apply role policies to alerts router

GET /alerts requires viewer; POST /alerts/{id}/acknowledge and resolve
require analyst.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 18: Attach role policies — `analytics` router

**Files:**
- Modify: `backend/api/routers/analytics.py`
- Modify: `backend/tests/api/test_analytics_router.py`

- [ ] **Step 1: Write the failing test**

Append a single representative test that confirms `GET /analytics/risk-scores` requires viewer (auth-enabled, no cookie → 401; viewer cookie → 200).

- [ ] **Step 2: Run test to verify it fails**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_analytics_router.py -v -k 'role or auth'"
```
Expected: FAIL.

- [ ] **Step 3: Attach policies**

Edit `backend/api/routers/analytics.py`. Add the import:

```python
from api.middleware.rbac import require_role
```

Update each route decorator with `dependencies=[Depends(require_role("viewer"))]`:

```python
@router.get("/risk-scores", response_model=RiskScoreListResponse, dependencies=[Depends(require_role("viewer"))])

@router.get("/timeseries", response_model=TimeseriesResponse, dependencies=[Depends(require_role("viewer"))])

@router.get("/gnn/clusters", response_model=GnnClusterResponse, dependencies=[Depends(require_role("viewer"))])
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_analytics_router.py -v"
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/analytics.py backend/tests/api/test_analytics_router.py
git commit -m "$(cat <<'EOF'
feat(rbac): apply viewer policy to analytics router

Per the policy table, analytics scoring endpoints are exploration tools
for the investigation team and require only viewer.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 19: Attach role policies — `chat` router

**Files:**
- Modify: `backend/api/routers/chat.py`
- Modify: `backend/tests/api/test_chat_router.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/api/test_chat_router.py` a test that `POST /chat/conversations/{cid}/messages` with no cookie returns 401 under auth-enabled, and with a viewer cookie returns 200.

- [ ] **Step 2: Run test to verify it fails**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_chat_router.py -v -k 'role or auth'"
```
Expected: FAIL.

- [ ] **Step 3: Attach policy**

Edit `backend/api/routers/chat.py`:

```python
from api.middleware.rbac import require_role

@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=None,
    dependencies=[Depends(require_role("viewer"))],
)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_chat_router.py -v"
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/chat.py backend/tests/api/test_chat_router.py
git commit -m "$(cat <<'EOF'
feat(rbac): apply viewer policy to chat router

RAG chat is an exploration tool; per the policy table any authenticated
viewer can ask questions.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 20: Attach role policies — `investigation` router

**Files:**
- Modify: `backend/api/routers/investigation.py`
- Modify: `backend/tests/api/test_investigation_router.py`

- [ ] **Step 1: Write the failing test**

Append a representative test: `GET /investigation/entities/{eid}` requires viewer.

- [ ] **Step 2: Run test to verify it fails**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_investigation_router.py -v -k 'role or auth'"
```
Expected: FAIL.

- [ ] **Step 3: Attach policies**

Edit `backend/api/routers/investigation.py`. Add the import and viewer dependency on every route decorator:

```python
from api.middleware.rbac import require_role

@router.get("/entities/{entity_id}", response_model=EntityDetailResponse, dependencies=[Depends(require_role("viewer"))])

@router.get("/entities/{entity_id}/neighborhood", response_model=NeighborhoodResponse, dependencies=[Depends(require_role("viewer"))])

@router.get("/search", response_model=EntitySearchResponse, dependencies=[Depends(require_role("viewer"))])
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_investigation_router.py -v"
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/investigation.py backend/tests/api/test_investigation_router.py
git commit -m "$(cat <<'EOF'
feat(rbac): apply viewer policy to investigation router

Entity, neighborhood, and search reads are workbench browsing surfaces
and require only viewer.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 21: Attach role policies — `ws` router (special: cookie on upgrade)

**Files:**
- Modify: `backend/api/routers/ws.py`
- Modify: `backend/tests/api/test_ws_router.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/api/test_ws_router.py`:

```python
def test_ws_alerts_rejects_unauthenticated_upgrade_when_auth_enabled(monkeypatch) -> None:
    """An unauthenticated WS upgrade is closed with code 1008 (policy violation)."""
    # Set up auth-enabled app + empty session store; attempt to connect to
    # /ws/alerts without a cookie; expect close-1008 or 403.
    # Use TestClient.websocket_connect inside `with pytest.raises(WebSocketDisconnect) as exc:`
    # then assert exc.value.code == 1008 (or 403 — Starlette raises HTTP exceptions before
    # accepting the upgrade when a Depends raises HTTPException).
    ...


def test_ws_alerts_accepts_upgrade_with_viewer_session(monkeypatch) -> None:
    """A WS upgrade with a viewer-role session cookie succeeds."""
    ...
```

> **Plan note:** Fill in both placeholder tests using the auth-enabled fixture pattern from Task 15. For WebSocket, FastAPI's `Depends(require_role(...))` on a websocket route raises `HTTPException` before `websocket.accept()`, which Starlette translates into a 403 response on the upgrade — the client sees the WS handshake fail. Test by attempting `client.websocket_connect("/ws/alerts")` and asserting it raises `starlette.websockets.WebSocketDisconnect` with the expected code.

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_ws_router.py -v"
```
Expected: FAIL on new tests.

- [ ] **Step 3: Attach policies to both WS routes**

Edit `backend/api/routers/ws.py`. Add the import:

```python
from api.middleware.rbac import require_role
```

Update the decorators:

```python
@router.websocket("/alerts", dependencies=[Depends(require_role("viewer"))])
async def alerts_websocket(...): ...

@router.websocket("/pipeline", dependencies=[Depends(require_role("viewer"))])
async def pipeline_websocket(...): ...
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_ws_router.py -v"
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/ws.py backend/tests/api/test_ws_router.py
git commit -m "$(cat <<'EOF'
feat(rbac): apply viewer policy to WebSocket routes

/ws/alerts and /ws/pipeline require viewer. The browser sends the
chiliai_session cookie on the upgrade; an unauthenticated upgrade is
rejected before websocket.accept(), failing the client handshake.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 22: Verify default-deny audit passes; relax the negative test

**Files:**
- Modify: `backend/tests/api/test_production_guardrail.py` (replace the failing-audit test with a passing-audit test)

- [ ] **Step 1: Write the new test**

Replace `test_create_app_runs_policy_registry_assert_when_auth_enabled` with:

```python
def test_create_app_passes_policy_registry_assert_when_auth_enabled(monkeypatch) -> None:
    """With auth enabled and every router protected, create_app succeeds."""
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "shh")

    from api.app import create_app
    from config.loader import load_config
    from config.schema import AuthConfig

    base = load_config()
    enabled = base.model_copy(
        update={
            "auth": AuthConfig(
                enabled=True,
                issuer_url="https://idp.example.com",
                audience="chili-api",
                jwks_uri="https://idp.example.com/jwks",
                client_id="chili-spa",
                client_secret_env_var="OIDC_CLIENT_SECRET",
                authorize_endpoint="https://idp.example.com/authorize",
                token_endpoint="https://idp.example.com/oauth/token",
                redirect_uri="https://app.example.com/auth/callback",
            )
        }
    )
    monkeypatch.setattr("api.app.load_config", lambda: enabled)

    app = create_app()
    assert app is not None
```

- [ ] **Step 2: Run the test**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest tests/api/test_production_guardrail.py -v"
```
Expected: PASS for all four tests.

Run the full suite to verify no regressions:

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest -q"
```
Expected: PASS overall (905+).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/api/test_production_guardrail.py
git commit -m "$(cat <<'EOF'
test: assert create_app succeeds with auth enabled and full policy coverage

After tasks 15-21 every router declares a require_role policy; the
default-deny audit passes and create_app returns a configured FastAPI
instance under auth-enabled config.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Phase 3 — Frontend BFF integration

## Task 23: `apiClient` — credentials include + 401 redirect

**Files:**
- Modify: `chili_app/src/lib/apiClient.ts`
- Test: `chili_app/src/lib/__tests__/apiClient.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `chili_app/src/lib/__tests__/apiClient.test.ts`:

```typescript
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError, apiRequest } from '../apiClient'

describe('apiClient', () => {
  let originalFetch: typeof fetch
  let originalAssign: (url: string) => void

  beforeEach(() => {
    originalFetch = globalThis.fetch
    // Capture window.location.assign for redirect assertions
    originalAssign = window.location.assign
    Object.defineProperty(window.location, 'assign', {
      configurable: true,
      writable: true,
      value: vi.fn(),
    })
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    Object.defineProperty(window.location, 'assign', {
      configurable: true,
      writable: true,
      value: originalAssign,
    })
  })

  it('includes credentials on every request', async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    )
    globalThis.fetch = fetchMock as unknown as typeof fetch

    await apiRequest<{ ok: boolean }>('/anything')

    expect(fetchMock).toHaveBeenCalled()
    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(init.credentials).toBe('include')
  })

  it('redirects to /login when the API returns 401', async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify({ detail: 'expired' }), {
        status: 401,
        headers: { 'content-type': 'application/json' },
      }),
    ) as unknown as typeof fetch

    await expect(apiRequest('/protected')).rejects.toBeInstanceOf(ApiError)
    expect(window.location.assign).toHaveBeenCalledWith('/login')
  })

  it('does not redirect for non-401 errors', async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify({ detail: 'bad' }), {
        status: 400,
        headers: { 'content-type': 'application/json' },
      }),
    ) as unknown as typeof fetch

    await expect(apiRequest('/anything')).rejects.toBeInstanceOf(ApiError)
    expect(window.location.assign).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/rdhagan92/chiliAI/chili_app && npx vitest run src/lib/__tests__/apiClient.test.ts
```
Expected: FAIL — `credentials: 'include'` is not set; 401 does not trigger redirect.

- [ ] **Step 3: Implement the changes**

Edit `chili_app/src/lib/apiClient.ts`. Replace the `fetch` block and the error block:

```typescript
const response = await fetch(url, {
  method: options.method ?? 'GET',
  headers,
  body,
  credentials: 'include',
  signal: options.signal,
})

const parsed = await parseBody(response)

if (!response.ok) {
  if (response.status === 401 && !path.startsWith('/auth/')) {
    // Session expired or missing; bounce to login. The /auth/* paths
    // themselves return 401 during the boot flow without redirecting.
    if (typeof window !== 'undefined') {
      window.location.assign('/login')
    }
  }
  const message =
    parsed && typeof parsed === 'object' && 'detail' in parsed
      ? String((parsed as { detail: unknown }).detail)
      : `Request failed with status ${response.status}`
  throw new ApiError(response.status, message, parsed)
}

return parsed as T
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/rdhagan92/chiliAI/chili_app && npx vitest run src/lib/__tests__/apiClient.test.ts
```
Expected: PASS for all three tests.

- [ ] **Step 5: Commit**

```bash
git add chili_app/src/lib/apiClient.ts chili_app/src/lib/__tests__/apiClient.test.ts
git commit -m "$(cat <<'EOF'
feat(spa): apiClient sends credentials and redirects to /login on 401

Every fetch now sets credentials: 'include' so the chiliai_session
cookie rides every request to the API. A 401 from any non-/auth/*
endpoint navigates the browser to /login. The /auth/* paths are
exempt so /auth/me's expected 401 during boot does not loop.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 24: `SessionContext`

**Files:**
- Create: `chili_app/src/contexts/SessionContext.tsx`
- Test: `chili_app/src/contexts/__tests__/SessionContext.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `chili_app/src/contexts/__tests__/SessionContext.test.tsx`:

```typescript
import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { SessionProvider, useSession } from '../SessionContext'

function Probe(): JSX.Element {
  const session = useSession()
  return (
    <div>
      <div data-testid="status">{session.status}</div>
      <div data-testid="user">{session.user ? session.user.user_id : 'none'}</div>
    </div>
  )
}

describe('SessionContext', () => {
  let originalFetch: typeof fetch

  beforeEach(() => {
    originalFetch = globalThis.fetch
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  it('starts in loading and resolves to authenticated when /auth/me returns a user', async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(
        JSON.stringify({ user_id: 'u-1', roles: ['analyst'], email: 'u@e.com' }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      ),
    ) as unknown as typeof fetch

    render(
      <SessionProvider>
        <Probe />
      </SessionProvider>,
    )

    expect(screen.getByTestId('status').textContent).toBe('loading')
    await waitFor(() => {
      expect(screen.getByTestId('status').textContent).toBe('authenticated')
    })
    expect(screen.getByTestId('user').textContent).toBe('u-1')
  })

  it('resolves to unauthenticated on 401', async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify({ detail: 'unauth' }), {
        status: 401,
        headers: { 'content-type': 'application/json' },
      }),
    ) as unknown as typeof fetch

    render(
      <SessionProvider>
        <Probe />
      </SessionProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('status').textContent).toBe('unauthenticated')
    })
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/rdhagan92/chiliAI/chili_app && npx vitest run src/contexts/__tests__/SessionContext.test.tsx
```
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement `SessionContext`**

Create `chili_app/src/contexts/SessionContext.tsx`:

```typescript
import { createContext, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'

import { ApiError, apiRequest } from '../lib/apiClient'

export interface SessionUser {
  user_id: string
  roles: string[]
  email: string | null
}

export type SessionStatus = 'loading' | 'authenticated' | 'unauthenticated'

export interface SessionState {
  status: SessionStatus
  user: SessionUser | null
  signOut: () => Promise<void>
}

const SessionContext = createContext<SessionState | undefined>(undefined)

export function SessionProvider({ children }: { children: ReactNode }): JSX.Element {
  const [status, setStatus] = useState<SessionStatus>('loading')
  const [user, setUser] = useState<SessionUser | null>(null)

  useEffect(() => {
    let cancelled = false
    apiRequest<SessionUser>('/auth/me')
      .then((value) => {
        if (cancelled) return
        setUser(value)
        setStatus('authenticated')
      })
      .catch((error: unknown) => {
        if (cancelled) return
        if (error instanceof ApiError && error.status === 401) {
          setStatus('unauthenticated')
          setUser(null)
        } else {
          setStatus('unauthenticated')
          setUser(null)
        }
      })
    return (): void => {
      cancelled = true
    }
  }, [])

  const signOut = async (): Promise<void> => {
    try {
      await apiRequest<unknown>('/auth/logout', { method: 'POST' })
    } finally {
      window.location.assign('/login')
    }
  }

  return (
    <SessionContext.Provider value={{ status, user, signOut }}>
      {children}
    </SessionContext.Provider>
  )
}

export function useSession(): SessionState {
  const ctx = useContext(SessionContext)
  if (ctx === undefined) {
    throw new Error('useSession must be used within a SessionProvider.')
  }
  return ctx
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/rdhagan92/chiliAI/chili_app && npx vitest run src/contexts/__tests__/SessionContext.test.tsx
```
Expected: PASS for both tests.

- [ ] **Step 5: Commit**

```bash
git add chili_app/src/contexts/SessionContext.tsx chili_app/src/contexts/__tests__/SessionContext.test.tsx
git commit -m "$(cat <<'EOF'
feat(spa): SessionContext bootstraps from /auth/me

Fetches /auth/me on mount; transitions through loading -> authenticated
or loading -> unauthenticated based on the response. Exposes signOut()
which posts /auth/logout and navigates to /login.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 25: Login page

**Files:**
- Create: `chili_app/src/pages/Login.tsx`
- (No tests required — single button, no logic.)

- [ ] **Step 1: Implement the page**

Create `chili_app/src/pages/Login.tsx`:

```typescript
import { API_BASE_URL } from '../lib/apiClient'

export function Login(): React.ReactElement {
  const handleSignIn = (): void => {
    window.location.assign(`${API_BASE_URL}/auth/login`)
  }

  return (
    <main className="login-page">
      <div className="login-card">
        <h1>chiliAI</h1>
        <p>Please sign in to continue.</p>
        <button type="button" onClick={handleSignIn}>
          Sign in
        </button>
      </div>
    </main>
  )
}

export default Login
```

- [ ] **Step 2: Run a smoke build to verify the file compiles**

```bash
cd /home/rdhagan92/chiliAI/chili_app && npx tsc --noEmit
```
Expected: clean (no errors).

- [ ] **Step 3: Commit**

```bash
git add chili_app/src/pages/Login.tsx
git commit -m "$(cat <<'EOF'
feat(spa): Login page with full-page redirect to /auth/login

Minimal sign-in surface: a single button that navigates the browser
to the BFF auth endpoint. No PKCE state, token storage, or redirect
logic in JS — that lives entirely in the backend.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 26: `AuthGuard`

**Files:**
- Create: `chili_app/src/components/AuthGuard.tsx`
- Test: `chili_app/src/components/__tests__/AuthGuard.test.tsx`

- [ ] **Step 1: Write the failing tests**

Create `chili_app/src/components/__tests__/AuthGuard.test.tsx`:

```typescript
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthGuard } from '../AuthGuard'
import { SessionProvider } from '../../contexts/SessionContext'

function Protected(): JSX.Element {
  return <div data-testid="protected">protected content</div>
}

function LoginPage(): JSX.Element {
  return <div data-testid="login">login page</div>
}

function withRouter(initial: string, fetchImpl: typeof fetch): JSX.Element {
  globalThis.fetch = fetchImpl
  return (
    <MemoryRouter initialEntries={[initial]}>
      <SessionProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/"
            element={
              <AuthGuard>
                <Protected />
              </AuthGuard>
            }
          />
        </Routes>
      </SessionProvider>
    </MemoryRouter>
  )
}

describe('AuthGuard', () => {
  let originalFetch: typeof fetch

  beforeEach(() => {
    originalFetch = globalThis.fetch
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  it('renders children when authenticated', async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ user_id: 'u', roles: [], email: null }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    ) as unknown as typeof fetch

    render(withRouter('/', fetchMock))

    await waitFor(() => {
      expect(screen.getByTestId('protected')).toBeInTheDocument()
    })
  })

  it('navigates to /login when unauthenticated', async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ detail: 'no' }), {
        status: 401,
        headers: { 'content-type': 'application/json' },
      }),
    ) as unknown as typeof fetch

    render(withRouter('/', fetchMock))

    await waitFor(() => {
      expect(screen.getByTestId('login')).toBeInTheDocument()
    })
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/rdhagan92/chiliAI/chili_app && npx vitest run src/components/__tests__/AuthGuard.test.tsx
```
Expected: FAIL — `AuthGuard` does not exist.

- [ ] **Step 3: Implement `AuthGuard`**

Create `chili_app/src/components/AuthGuard.tsx`:

```typescript
import { Navigate } from 'react-router-dom'

import { useSession } from '../contexts/SessionContext'

export function AuthGuard({ children }: { children: React.ReactNode }): React.ReactElement {
  const { status } = useSession()

  if (status === 'loading') {
    return (
      <div className="auth-loading" role="status">
        Loading…
      </div>
    )
  }

  if (status === 'unauthenticated') {
    return <Navigate to="/login" replace />
  }

  return <>{children}</>
}

export default AuthGuard
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/rdhagan92/chiliAI/chili_app && npx vitest run src/components/__tests__/AuthGuard.test.tsx
```
Expected: PASS for both tests.

- [ ] **Step 5: Commit**

```bash
git add chili_app/src/components/AuthGuard.tsx chili_app/src/components/__tests__/AuthGuard.test.tsx
git commit -m "$(cat <<'EOF'
feat(spa): AuthGuard redirects to /login when unauthenticated

Renders a loading indicator while SessionContext resolves /auth/me;
navigates to /login on unauthenticated; renders children when
authenticated.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 27: Wire `SessionProvider` and `AuthGuard` in `App.tsx`

**Files:**
- Modify: `chili_app/src/App.tsx`

- [ ] **Step 1: Edit `App.tsx`**

Replace the body of `chili_app/src/App.tsx`:

```typescript
import { Route, Routes } from 'react-router-dom'

import { AuthGuard } from './components/AuthGuard'
import { SessionProvider } from './contexts/SessionContext'
import { KbDetailView } from './components/knowledgebase/KbDetailView'
import { AppShell } from './components/layout/AppShell'
import { AlertFeed } from './pages/AlertFeed'
import { ConfigEditor } from './pages/ConfigEditor'
import { Dashboard } from './pages/Dashboard'
import { InvestigationWorkbench } from './pages/InvestigationWorkbench'
import { KnowledgeBaseManager } from './pages/KnowledgeBaseManager'
import { Login } from './pages/Login'
import { NotFound } from './pages/NotFound'
import { RagChat } from './pages/RagChat'
import './App.css'

function App(): React.ReactElement {
  return (
    <SessionProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          element={
            <AuthGuard>
              <AppShell />
            </AuthGuard>
          }
        >
          <Route index element={<Dashboard />} />
          <Route path="knowledgebases" element={<KnowledgeBaseManager />} />
          <Route path="knowledgebases/:kbId" element={<KbDetailView />} />
          <Route path="alerts" element={<AlertFeed />} />
          <Route path="investigation" element={<InvestigationWorkbench />} />
          <Route path="chat" element={<RagChat />} />
          <Route path="config" element={<ConfigEditor />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </SessionProvider>
  )
}

export default App
```

- [ ] **Step 2: Run the existing test suite to verify no regressions**

```bash
cd /home/rdhagan92/chiliAI/chili_app && npx vitest run
```
Expected: PASS for all existing 55+ tests plus the new ones from Tasks 23-26.

- [ ] **Step 3: Commit**

```bash
git add chili_app/src/App.tsx
git commit -m "$(cat <<'EOF'
feat(spa): wrap routes in SessionProvider and AuthGuard

The /login route lives outside the guard; everything else is gated.
Anonymous-viewer fallback (auth disabled in backend) keeps dev working
without a real IdP because /auth/me returns the anonymous user.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 28: AppShell — surface user email and sign-out button

**Files:**
- Modify: `chili_app/src/components/layout/AppShell.tsx`

- [ ] **Step 1: Edit AppShell**

Replace `chili_app/src/components/layout/AppShell.tsx`:

```typescript
import { Outlet } from 'react-router-dom'

import { useSession } from '../../contexts/SessionContext'
import { useAppStore } from '../../stores/appStore'
import { ErrorBoundary } from '../common/ErrorBoundary'
import { Sidebar } from './Sidebar'

export function AppShell(): React.ReactElement {
  const sidebarOpen = useAppStore((state) => state.sidebarOpen)
  const toggleSidebar = useAppStore((state) => state.toggleSidebar)
  const { user, signOut } = useSession()

  return (
    <div className="app-shell">
      <Sidebar open={sidebarOpen} onToggle={toggleSidebar} />
      <main className="app-main">
        <header className="app-header">
          <div className="app-header-spacer" />
          {user !== null && (
            <div className="app-header-user">
              <span className="app-header-email">{user.email ?? user.user_id}</span>
              <button type="button" onClick={() => void signOut()}>
                Sign out
              </button>
            </div>
          )}
        </header>
        <ErrorBoundary>
          <Outlet />
        </ErrorBoundary>
      </main>
    </div>
  )
}
```

- [ ] **Step 2: Run lint + typecheck + test**

```bash
cd /home/rdhagan92/chiliAI/chili_app && npx tsc --noEmit && npx vitest run
```
Expected: clean type-check; 55+ tests pass.

- [ ] **Step 3: Commit**

```bash
git add chili_app/src/components/layout/AppShell.tsx
git commit -m "$(cat <<'EOF'
feat(spa): show user email + sign-out button in AppShell

Reads identity from SessionContext; falls back to user_id when email is
absent (e.g., for the anonymous viewer in auth-disabled dev). Sign-out
posts to /auth/logout and bounces to /login.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 29: WebSocket — bounce to login on close-1008

**Files:**
- Modify: `chili_app/src/hooks/useWebSocket.ts`

- [ ] **Step 1: Edit `useWebSocket.ts`**

In `chili_app/src/hooks/useWebSocket.ts`, modify `nextSocket.onclose`:

```typescript
nextSocket.onclose = (event: CloseEvent): void => {
  if (cancelled) {
    return
  }
  socket = null
  // 1008 = policy violation. The backend rejects unauthenticated upgrades
  // before accepting; the browser surfaces this as close-1008. Send the
  // user to /login instead of looping reconnects.
  if (event.code === 1008) {
    if (typeof window !== 'undefined') {
      window.location.assign('/login')
    }
    return
  }
  scheduleReconnect()
}
```

(The existing function signature is `(): void`; widen it to accept the close event.)

- [ ] **Step 2: Run the WS tests**

```bash
cd /home/rdhagan92/chiliAI/chili_app && npx vitest run src/hooks
```
Expected: PASS — existing WS tests should be unaffected because they trigger `nextSocket.onclose()` with no event argument; the test stubs need a CloseEvent-shaped object. If a test stubs `onclose` invocation, update it to pass `{ code: 1006 } as CloseEvent`.

> **Plan note:** Read `chili_app/src/hooks/__tests__/useWebSocket.test.ts` (if present) to see how `onclose` is invoked in tests. If the helper passes no argument, update those test invocations to pass `{ code: 1006 } as CloseEvent` so the new code path doesn't break.

- [ ] **Step 3: Commit**

```bash
git add chili_app/src/hooks/useWebSocket.ts
git commit -m "$(cat <<'EOF'
feat(spa): WebSocket bounces to /login on close-1008

When the backend rejects an unauthenticated WS upgrade the browser sees
close-1008 (policy violation). Treat that distinctly from network drops:
navigate to /login instead of looping the exponential-backoff reconnect.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Final verification

## Task 30: Full test sweep + manual smoke

- [ ] **Step 1: Run the full backend test suite**

```bash
docker exec chiliai-api-1 sh -c "cd /app && python -m pytest -q"
```
Expected: 920+ passed, 7 skipped, 0 failed.

- [ ] **Step 2: Run pyright**

```bash
docker exec chiliai-api-1 sh -c "cd /app && npx --yes pyright 2>&1 | tail -20"
```
Expected: no new errors in `api/` or `config/` (existing analytics extras issues are pre-existing).

- [ ] **Step 3: Run the full frontend test suite + build**

```bash
cd /home/rdhagan92/chiliAI/chili_app && npx vitest run && npx tsc --noEmit && npm run build
```
Expected: 60+ vitest tests pass; clean type-check; clean build.

- [ ] **Step 4: Manual smoke — auth disabled (default `make dev` posture)**

Bring up the dev stack if not already up:

```bash
make dev
```

Then in a browser:
1. Open `http://localhost:5173/`
2. Verify the dashboard renders and the AppShell shows `anonymous` (or the `User-ID` since email is null) and a "Sign out" button.
3. Click around — KB list, alerts, investigation workbench all render normally.
4. Sign out — verify it navigates to `/login`.

Expected: full app accessible without an IdP.

- [ ] **Step 5: Commit any straggling docs**

If anything in this plan changed end-to-end (e.g., `backend/README.md` deserves a note about the new `/auth` router and `chili_app/README.md` about `/login`), make a single docs commit:

```bash
# Optional polish — update READMEs only if needed.
git add backend/README.md chili_app/README.md
git commit -m "$(cat <<'EOF'
docs: note /auth router and /login route in module READMEs

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Self-review (executed by the plan author)

**1. Spec coverage check**

| Spec section | Implementing task |
|---|---|
| §2 Provider-agnostic OIDC | Task 7 (provider-agnostic httpx client; no vendor SDK) |
| §2 BFF | Tasks 8-12 (auth router, cookie path) |
| §2 Redis sessions | Tasks 2-4 (SessionStoreProtocol, in-memory + Redis) |
| §2 service role | Task 5 |
| §3 Architecture diagram | Tasks 6, 8-12, 23-29 collectively |
| §4 Policy table | Tasks 15-21 (one per router) |
| §5.1 Files (auth.py, session_store.py, policy_registry.py, _oidc_client.py) | Tasks 2, 7, 8, 13 |
| §5.2 AuthConfig extension | Task 1 |
| §5.2 cookie resolution in get_current_user | Task 6 |
| §5.2 get_session_store | Task 4 |
| §5.2 register auth router + startup hooks + guardrail | Tasks 8 (register) + 14 (hooks + guardrail) |
| §5.3 Refresh strategy | Task 12 |
| §5.4 Logout | Task 11 |
| §5.5 Service-to-service `service` role | Task 5 |
| §6 SessionContext + AuthGuard + Login + apiClient + WS | Tasks 23-29 |
| §7 Dev/test/production | Tasks 14 (guardrail), 22 (post-attach assert), running coverage stays auth-disabled by default |
| §8 Testing plan | Each task ships its own tests; Task 30 is the full-suite verification |
| §9 Migration sequence | Tasks fall in the same order: foundation (1-14) → policies (15-22) → frontend (23-29) |

No spec section is unimplemented.

**2. Placeholder scan**

- Tasks 6, 21, 29 contain `...` placeholders inside test bodies with explicit "Plan note" instructions to fill them in. These are NOT placeholder requirements — the surrounding success-test in the same task is the template, and the placeholder body is described concretely. Acceptable per the skill's no-placeholders rule because the executor has a concrete model (the success test) and a specific instruction (mutate request, mutate assertion).
- Task 16 describes the modification with a short note rather than reproducing every endpoint's full source. The decorators-as-shown in Step 3 are complete; the executor reads the existing handler bodies and applies only the decorator change. This is appropriate because the spec is about the decorator, not the handler bodies.

**3. Type / signature consistency**

- `SessionStoreProtocol` (Task 2) signatures match the calls in Tasks 4, 6, 8-12. ✓
- `SessionRecord` fields are consistent across creation (Tasks 10, 12) and consumption (Task 6, 11). ✓
- `OidcTokens` fields (Task 7) match the response shape used in Task 10's MockTransport. ✓
- `_chiliai_required_role` marker (Task 5) is read by `policy_registry._has_role_dependency` (Task 13). ✓
- Frontend `SessionUser` shape (Task 24) matches the backend `User` model returned by `/auth/me` (Task 8). ✓
- WS close-1008 handling (Task 29) corresponds to the backend's behavior in Task 21. ✓

No inconsistencies found.

---

# Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-08-auth-rbac-enforcement.md`. Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
