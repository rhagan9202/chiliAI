# BL-022 OIDC Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Kid-aware JWKS rotation with a throttled forced refresh, OIDC nonce round-trip validation, and desk-checked Keycloak/Okta templates — per `docs/superpowers/specs/2026-07-15-bl022-oidc-hardening-design.md` (the `_security.01` remainder).

**Architecture:** `JwksCache` gains per-URI invalidation and a 30s-throttled `force_refresh`; `decode_token` resolves the token header's `kid` against the cached key set and forces one refetch on a miss. The login flow generates a nonce stored with the PKCE record (`PkceState` model through the session-store protocol and both adapters) and validates it against id_token claims in the callback. All verification is test-double based (product-owner ruling — no live IdP).

**Tech Stack:** Python 3.12, python-jose (existing `[auth]` extra), FastAPI, pytest with injected fetchers/clocks.

## Global Constraints

- Product-owner ruling: **test-double verification only**; templates ship desk-checked with an explicit disclaimer; live-IdP proof is the recorded residual follow-up.
- Throttle: `min_forced_refresh_seconds` default **30**, per-URI, monotonic clock (the cache's existing `_clock` injection). Inside the window an unknown `kid` does NOT refetch — it 401s against the cached document.
- Kid matrix (spec §1): no-kid-header ⇒ today's behavior; known kid ⇒ proceed; unknown ⇒ one throttled force_refresh then re-check; still unknown ⇒ 401 `"Token signing key is unknown."`.
- Nonce: validated ONLY when the id_token was decoded; access-token fallback skips it (documented, not silent). Mismatch/absent ⇒ 400 `"id_token nonce mismatch."`, no session minted.
- `pop_pkce_state` returns `PkceState | None` (model: `verifier: str`, `nonce: str`); legacy bare-string records fail closed as unknown state.
- `api*` is fully pyright-include-scoped — everything touched must be strict-clean under bare `pyright`. No API contract changes expected (CI contract job proves it — do NOT regen unless it fails, and if it fails, investigate: this story must not change wire models).
- Gates from `/home/rdhagan92/chiliAI/backend`: `.venv/bin/pytest tests/api -q`, full `DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest --cov -m "not integration" -q`, `.venv/bin/pyright` (0 errors), `.venv/bin/ruff check --no-cache .`.
- All commits end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: `JwksCache.invalidate_uri` + throttled `force_refresh`

**Files:**
- Modify: `backend/api/middleware/auth.py:74-101` (the `JwksCache` dataclass)
- Test: `backend/tests/api/test_auth_middleware.py`

**Interfaces:**
- Produces: `JwksCache.invalidate_uri(uri: str) -> None`; `JwksCache.force_refresh(uri: str) -> dict[str, object]` — refetches immediately only when the last forced refresh for that URI is ≥ `min_forced_refresh_seconds` (new field, default 30) ago; inside the window returns the current cached document (fetching normally if nothing is cached). Task 2 calls `force_refresh` on kid miss.

- [ ] **Step 1: Write the failing tests** — append to `backend/tests/api/test_auth_middleware.py` (READ the module first; reuse its fetcher-stub style — the assertions below are normative):

```python
def test_invalidate_uri_clears_single_entry() -> None:
    calls: list[str] = []

    def fetcher(uri: str) -> dict[str, object]:
        calls.append(uri)
        return {"keys": [{"kid": f"key-{len(calls)}"}]}

    cache = JwksCache(fetcher=fetcher, ttl_seconds=3600)
    cache.get("https://idp/a")
    cache.get("https://idp/b")
    cache.invalidate_uri("https://idp/a")
    cache.get("https://idp/a")  # refetches
    cache.get("https://idp/b")  # still cached
    assert calls == ["https://idp/a", "https://idp/b", "https://idp/a"]


def test_force_refresh_is_throttled_per_uri() -> None:
    calls: list[str] = []
    now = {"t": 1000.0}

    def fetcher(uri: str) -> dict[str, object]:
        calls.append(uri)
        return {"keys": [{"kid": f"key-{len(calls)}"}]}

    cache = JwksCache(fetcher=fetcher, ttl_seconds=3600, _clock=lambda: now["t"])
    first = cache.force_refresh("https://idp/jwks")
    assert calls == ["https://idp/jwks"]
    # Inside the 30s window: no refetch, cached doc returned.
    now["t"] += 10
    second = cache.force_refresh("https://idp/jwks")
    assert calls == ["https://idp/jwks"]
    assert second == first
    # Past the window: refetches.
    now["t"] += 30
    third = cache.force_refresh("https://idp/jwks")
    assert calls == ["https://idp/jwks", "https://idp/jwks"]
    assert third != first
```

(If the dataclass's private `_clock` field cannot be passed positionally/by-name from tests without pyright complaint, add a small factory or set it post-construction the way existing tests manipulate the cache — read them; never suppress.)

- [ ] **Step 2: Run to verify failure**

Run: `cd /home/rdhagan92/chiliAI/backend && .venv/bin/pytest tests/api/test_auth_middleware.py -q -k "invalidate_uri or force_refresh"`
Expected: FAIL (`AttributeError`).

- [ ] **Step 3: Implement** — extend `JwksCache` in `backend/api/middleware/auth.py`:

```python
@dataclass(slots=True)
class JwksCache:
    """TTL cache for JWKS documents keyed by URI.

    ``force_refresh`` supports kid-aware rotation (BL-022): an unknown ``kid``
    may force one refetch per URI per ``min_forced_refresh_seconds`` so a
    flood of bogus-kid tokens cannot hammer the IdP's JWKS endpoint.
    """

    fetcher: JwksFetcher = _default_jwks_fetcher
    ttl_seconds: int = 3600
    min_forced_refresh_seconds: int = 30
    _entries: dict[str, _CachedJwks] = field(
        default_factory=lambda: cast(dict[str, _CachedJwks], {})
    )
    _forced_at: dict[str, float] = field(
        default_factory=lambda: cast(dict[str, float], {})
    )
    _clock: Callable[[], float] = field(default=time.monotonic)

    def get(self, uri: str) -> dict[str, object]:
        cached = self._entries.get(uri)
        now = self._clock()
        if cached is not None and (now - cached.fetched_at) < self.ttl_seconds:
            return cached.document
        document = self.fetcher(uri)
        self._entries[uri] = _CachedJwks(document=document, fetched_at=now)
        return document

    def force_refresh(self, uri: str) -> dict[str, object]:
        """Refetch ``uri`` now, at most once per ``min_forced_refresh_seconds``."""

        now = self._clock()
        last_forced = self._forced_at.get(uri)
        if (
            last_forced is not None
            and (now - last_forced) < self.min_forced_refresh_seconds
        ):
            return self.get(uri)
        self._forced_at[uri] = now
        document = self.fetcher(uri)
        self._entries[uri] = _CachedJwks(document=document, fetched_at=now)
        return document

    def invalidate_uri(self, uri: str) -> None:
        self._entries.pop(uri, None)

    def invalidate(self) -> None:
        self._entries.clear()
        self._forced_at.clear()
```

- [ ] **Step 4: Run tests + gates**

Run: `cd /home/rdhagan92/chiliAI/backend && .venv/bin/pytest tests/api/test_auth_middleware.py -q && .venv/bin/pyright && .venv/bin/ruff check --no-cache .`
Expected: PASS / 0 errors / clean.

- [ ] **Step 5: Commit**

```bash
cd /home/rdhagan92/chiliAI
git add backend/api/middleware/auth.py backend/tests/api/test_auth_middleware.py
git commit -m "feat(auth): JwksCache per-URI invalidation + throttled force_refresh (BL-022)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Kid-aware resolution in `decode_token`

**Files:**
- Modify: `backend/api/middleware/auth.py:150-221` (`decode_token`)
- Test: `backend/tests/api/test_auth_middleware.py`

**Interfaces:**
- Consumes: Task 1's `force_refresh`.
- Produces: `decode_token` kid matrix per Global Constraints. Signature unchanged.

- [ ] **Step 1: Write the failing tests.** These need real RSA-signed tokens; READ the module's existing `decode_token` tests first — they already mint RS256 tokens with jose (key fixtures). Reuse those helpers to build TWO keypairs with distinct `kid`s and write the rotation matrix (assertions normative; adapt helper names):

```python
def test_unknown_kid_forces_one_refetch_and_validates() -> None:
    # fetcher serves JWKS_OLD first, then JWKS_NEW (with the new kid)
    # 1. token signed by OLD key, kid=old -> validates, fetch_count == 1
    # 2. rotate: fetcher now returns JWKS_NEW only
    # 3. token signed by NEW key, kid=new -> decode_token succeeds, fetch_count == 2 (exactly one forced refetch)
    # 4. token signed by OLD key -> 401, fetch_count == 2 (old kid known-missing, but... see matrix: unknown kid inside throttle -> no refetch)


def test_unknown_kid_still_missing_after_refetch_is_401() -> None:
    # fetcher always returns a JWKS without the token's kid
    # decode_token -> HTTPException 401 "Token signing key is unknown."
    # fetch_count == 2 (initial get + one forced refresh)


def test_unknown_kid_inside_throttle_window_does_not_refetch() -> None:
    # injected clock; first unknown kid consumes the forced refresh (fetch_count 2)
    # second unknown-kid token within 30s -> 401 with fetch_count still 2
    # advance clock past 30s -> third unknown-kid token -> fetch_count 3


def test_token_without_kid_header_keeps_legacy_path() -> None:
    # token minted without a kid header, key present in JWKS -> validates, no forced refresh
```

Write these as complete tests using the module's real key/token helpers — every comment line above must become an assertion.

- [ ] **Step 2: Run to verify failure**

Run: `cd /home/rdhagan92/chiliAI/backend && .venv/bin/pytest tests/api/test_auth_middleware.py -q -k kid`
Expected: FAIL (no kid handling — unknown-kid currently 401s WITHOUT refetch, so the refetch-count assertions fail).

- [ ] **Step 3: Implement.** In `decode_token`, after the JWKS fetch (`jwks = jwks_cache.get(...)`) and before `jwt.decode`, insert:

```python
    token_kid = _token_kid(token)
    if token_kid is not None and not _jwks_has_kid(jwks, token_kid):
        try:
            jwks = jwks_cache.force_refresh(auth_config.jwks_uri)
        except Exception as exc:  # noqa: BLE001 - refetch failures map to 401
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unable to refresh JWKS for token validation.",
            ) from exc
        if not _jwks_has_kid(jwks, token_kid):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token signing key is unknown.",
            )
```

with module-level helpers (place near `decode_token`; `jose` is imported lazily inside functions in this module — follow that pattern):

```python
def _token_kid(token: str) -> str | None:
    """Return the token header's ``kid``, or None (malformed headers -> None,
    letting jwt.decode produce the canonical 401)."""

    try:
        from jose import jwt
    except ImportError:  # pragma: no cover - guarded by [auth] extra
        return None
    try:
        header = cast(dict[str, object], jwt.get_unverified_header(token))
    except Exception:  # noqa: BLE001 - malformed header falls through to decode
        return None
    kid = header.get("kid")
    return kid if isinstance(kid, str) else None


def _jwks_has_kid(jwks: dict[str, object], kid: str) -> bool:
    keys = jwks.get("keys")
    if not isinstance(keys, list):
        return False
    for key in cast(list[object], keys):
        if isinstance(key, dict) and cast(dict[str, object], key).get("kid") == kid:
            return True
    return False
```

- [ ] **Step 4: Run tests + gates**

Run: `cd /home/rdhagan92/chiliAI/backend && .venv/bin/pytest tests/api -q && .venv/bin/pyright && .venv/bin/ruff check --no-cache .`
Expected: PASS / 0 / clean.

- [ ] **Step 5: Commit**

```bash
cd /home/rdhagan92/chiliAI
git add backend/api/middleware/auth.py backend/tests/api/test_auth_middleware.py
git commit -m "feat(auth): kid-aware JWKS resolution with throttled refetch in decode_token (BL-022)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Nonce through the OIDC flow

**Files:**
- Modify: `backend/api/middleware/session_store.py` (protocol + `InMemorySessionStore` + `RedisSessionStore`)
- Modify: `backend/api/routers/_oidc_client.py:61-81` (`build_authorize_url`)
- Modify: `backend/api/routers/auth.py` (login ~lines 58-93, callback ~lines 96-175)
- Test: `backend/tests/api/test_auth_router.py` (+ session-store tests — find where `save_pkce_state` is currently tested and extend there)

**Interfaces:**
- Consumes: nothing new from Tasks 1-2 (independent).
- Produces:

```python
class PkceState(BaseModel):
    verifier: str
    nonce: str

# protocol:
def save_pkce_state(self, *, state: str, verifier: str, ttl_seconds: int, nonce: str) -> None: ...
def pop_pkce_state(self, state: str) -> PkceState | None: ...

# build_authorize_url gains keyword-only: nonce: str  (adds "nonce": nonce to params)
```

Redis storage format: JSON `{"verifier": ..., "nonce": ...}` via `PkceState.model_dump_json()`; `pop` parses with `PkceState.model_validate_json` and returns `None` on ANY parse failure (legacy bare-string records fail closed as unknown state — spec §2).

- [ ] **Step 1: Write the failing tests.** Session-store level (both adapters — mirror where existing PKCE tests live; Redis tests use whatever fake/real client pattern the module's existing Redis tests use):

```python
def test_pkce_state_roundtrips_nonce() -> None:
    store = InMemorySessionStore()
    store.save_pkce_state(state="s1", verifier="v1", ttl_seconds=60, nonce="n1")
    popped = store.pop_pkce_state("s1")
    assert popped is not None
    assert popped.verifier == "v1"
    assert popped.nonce == "n1"
    assert store.pop_pkce_state("s1") is None  # pop is one-shot


def test_legacy_bare_string_pkce_record_fails_closed() -> None:
    # Redis adapter only: seed the raw key with a legacy bare-verifier string,
    # pop_pkce_state must return None (fail closed), not crash.
```

Router level — extend `test_auth_router.py`'s existing login/callback tests (READ them; they monkeypatch `_auth_module.decode_token` and the OIDC client):

```python
def test_login_includes_nonce_in_authorize_url(...) -> None:
    # GET /auth/login -> 307; parse Location query: "nonce" param present, non-empty,
    # and distinct from "state".


def test_callback_rejects_nonce_mismatch(...) -> None:
    # save_pkce_state with nonce="expected"; decode_token double returns claims
    # with nonce="wrong" (id_token present in the token response double)
    # -> 400, detail contains "nonce", and NO session cookie set.


def test_callback_rejects_missing_nonce_claim(...) -> None:
    # claims WITHOUT a nonce key, id_token present -> 400.


def test_callback_accepts_matching_nonce(...) -> None:
    # claims nonce == stored nonce -> 307 redirect, session cookie set.


def test_callback_access_token_fallback_skips_nonce(...) -> None:
    # token response double with id_token=None; claims without nonce -> succeeds
    # (nonce is an id_token claim; fallback path documented as skipping it).
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /home/rdhagan92/chiliAI/backend && .venv/bin/pytest tests/api/test_auth_router.py tests/api/test_auth_middleware.py -q -k "nonce or pkce"`
Expected: FAIL (`nonce` kwarg unexpected / PkceState missing).

- [ ] **Step 3: Implement.**

`session_store.py`: add `PkceState(BaseModel)` (fields above) next to `SessionRecord`; update the protocol; `InMemorySessionStore._pkce: dict[str, PkceState]`; `RedisSessionStore.save_pkce_state` stores `PkceState(verifier=verifier, nonce=nonce).model_dump_json()`, `pop_pkce_state` does GET+DEL as today then:

```python
        if raw is None:
            return None
        try:
            return PkceState.model_validate_json(raw)
        except ValidationError:
            return None  # legacy bare-string record: fail closed (BL-022)
```

`_oidc_client.py`: `build_authorize_url(auth_config, *, state, code_challenge, nonce)` adds `"nonce": nonce` to `params`.

`auth.py` login: `nonce = generate_id()`; pass `nonce=nonce` to `build_authorize_url` and `save_pkce_state(state=state, verifier=verifier, ttl_seconds=PKCE_STATE_TTL_SECONDS, nonce=nonce)`.

`auth.py` callback: `pkce = session_store.pop_pkce_state(state)`; `if pkce is None: ...400 unknown state (unchanged text)`; `verifier = pkce.verifier`. After `claims = _auth_module.decode_token(...)` insert:

```python
    # Nonce binds the id_token to this login attempt (BL-022). It is an
    # id_token claim by OIDC spec, so the access-token fallback path skips it —
    # see docs/auth/idp-templates.md.
    if tokens.id_token is not None:
        if claims.get("nonce") != pkce.nonce:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="id_token nonce mismatch.",
            )
```

- [ ] **Step 4: Run tests + gates**

Run: `cd /home/rdhagan92/chiliAI/backend && .venv/bin/pytest tests/api -q && .venv/bin/pyright && .venv/bin/ruff check --no-cache .`
Expected: PASS / 0 / clean. Fix any other `save_pkce_state`/`pop_pkce_state` callers/tests the signature change surfaces (grep first; adapt them to the new shape, do not weaken).

- [ ] **Step 5: Commit**

```bash
cd /home/rdhagan92/chiliAI
git add backend/api/middleware/session_store.py backend/api/routers/_oidc_client.py backend/api/routers/auth.py backend/tests/api
git commit -m "feat(auth): OIDC nonce round-trip via PkceState with id_token validation (BL-022)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: IdP templates + story closeout

**Files:**
- Create: `docs/auth/idp-templates.md` (new directory)
- Modify: `backend/README.md` (auth section pointer), `docs/architecture.md` (auth hardening note if it describes token validation), `docs/backlog/_security.md` (_security.01 → done), `docs/project/planning/backlog.md` (BL-022 row + detail), `docs/project/planning/sprints/2026-27.md` (stretch progress entry)

- [ ] **Step 1: Write `docs/auth/idp-templates.md`** with all spec §3 content:
  - Header disclaimer, verbatim intent: these templates are **desk-checked against IdP documentation, not verified against a live IdP** (product-owner ruling 2026-07-15); live-IdP verification is the recorded follow-up.
  - **Keycloak** section: worked `auth:` YAML for `DomainConfig` (READ `backend/config/schema.py`'s `AuthConfig` fields first and use the REAL field names — issuer_url, jwks_uri, authorize/token/end_session endpoints, client_id, audience, redirect_uri, scopes, roles_claim, cookie flags, session_ttl_seconds) with `https://<host>/realms/<realm>`-shaped URLs; IdP-side steps: public client, PKCE S256 required, redirect URI `<api-base>/auth/callback`, realm-role claim mapping to `roles_claim`, note on realm key rotation (chiliAI recovers via kid-triggered refetch, ≤30s throttle).
  - **Okta** section: worked YAML (org authorization server issuer `https://<org>.okta.com/oauth2/default`, `/v1/keys` JWKS), app setup steps (OIDC Web App w/ PKCE, groups claim → `roles_claim`).
  - "What chiliAI validates" table: RS256 signature, `iss`, `aud`, `exp`, id_token `nonce` (id_token flows only), kid-triggered JWKS refetch (30s per-URI throttle). "Not yet": refresh-token rotation, back-channel logout (out of scope, `_security.md` backlog).

- [ ] **Step 2: Story + backlog closeout.** `docs/backlog/_security.md` `_security.01` → `done`, Done line `**Done:** 2026-07-15 · BL-022 (Sprint 2026-27 stretch) · feat/sprint-2026-27-oidc-hardening`, ALL AC boxes checked, with two inline deviations: templates desk-checked only (PO ruling), and nonce validated on id_token flows only (OIDC-spec scoping). Planning backlog: BL-022 → done (test-double verification per ruling — there is NO deferred live pass to run; say so plainly rather than "pending"). Sprint file: stretch delivered entry + move the "live-IdP template verification" item into the fix-later/follow-up list. Run `backend/.venv/bin/python scripts/backlog_consistency.py` (+ include rollup rewrites) then `--check` exit 0.

- [ ] **Step 3: Full gates**

Run: `cd /home/rdhagan92/chiliAI/backend && DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest --cov -m "not integration" -q && .venv/bin/pyright && .venv/bin/ruff check --no-cache .`
Expected: full pass, `api` package ≥ 85%, 0 errors, clean.

- [ ] **Step 4: Commit**

```bash
cd /home/rdhagan92/chiliAI
git add docs/ backend/README.md
git commit -m "docs(auth): Keycloak/Okta IdP templates (desk-checked); _security.01 closeout (BL-022)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Self-review notes (already applied)

- Spec coverage: §1→Tasks 1-2, §2→Task 3, §3→Task 4, §4 (test-double gates) →every task, §5 scope guards→Task 4 Step 2 wording. No live-verification step exists by ruling — the plan says so explicitly in Task 4 Step 2 to prevent a stale "pending controller pass" note.
- Type consistency: `force_refresh`/`invalidate_uri`/`min_forced_refresh_seconds` (T1) consumed by T2; `PkceState`/`save_pkce_state(..., nonce)`/`pop_pkce_state -> PkceState | None`/`build_authorize_url(..., nonce)` are all defined in T3's Produces block and used verbatim in its Step 3.
- Task 2 Step 1 tests are deliberately specified as a matrix over the module's REAL key-minting helpers (they exist — the module already mints RS256 tokens); every comment line is mandatory as an assertion.
- Kid-matrix nuance encoded: an old-kid token AFTER rotation is 401 (key genuinely gone) and, inside the throttle window, must not trigger another fetch.
