# BL-022 — OIDC hardening remainder (design)

> Status: approved by product owner 2026-07-15 (one scope ruling recorded below).
> Sprint: 2026-27 **stretch** (pulled after the 14 SP core completed day 1). Module story: `_security.01` remainder — `docs/backlog/_security.md`. Requirement: REQ-AUTH-001.

## Problem

4 of 7 `_security.01` acceptance items shipped previously (JWKS TTL cache, full aud/iss/exp+signature validation, validated id_token decode in the callback, production auth guardrail). Three remain:

1. **No kid-aware rotation**: `decode_token` (`api/middleware/auth.py:150-221`) hands the whole cached JWKS to `jwt.decode`; when an IdP rotates signing keys inside the 1-hour TTL, every token signed by the new key 401s until the TTL expires. Nothing inspects the token header's `kid`.
2. **No nonce**: the OIDC flow round-trips PKCE `state`+verifier only (`api/routers/auth.py:72-118`); the id_token's `nonce` claim is neither requested nor validated, leaving the code-injection/replay hole nonce exists to close.
3. **No IdP configuration templates** in the repo.

## Product-owner ruling (2026-07-15)

**Test-double verification only.** Rotation and nonce are proven via injected JWKS fetchers and scripted token/claims doubles in the test suite; no live IdP is stood up. Consequence, stated plainly: the Keycloak/Okta templates ship **desk-checked, not live-verified** — the template doc says so, and proving them against a live IdP is the story's recorded residual follow-up.

## Design

### 1. Kid-aware JWKS rotation

- `JwksCache` gains:
  - `invalidate_uri(uri: str) -> None` (today only global `invalidate()` exists).
  - A **forced-refresh throttle**: `force_refresh(uri) -> dict[str, object]` refetches immediately only if the last *forced* refresh for that URI is older than `min_forced_refresh_seconds` (default **30**, monotonic clock — same `_clock` injection as the TTL); inside the window it returns the cached document unchanged. This caps IdP JWKS-endpoint load under a flood of bogus-`kid` tokens: at most one forced fetch per URI per 30s, everything else 401s against cache.
- `decode_token` kid-resolution step, before `jwt.decode`:
  1. `jwt.get_unverified_header(token)` → `kid` (jose; header parse failure ⇒ 401 as today's JWTError path).
  2. No `kid` in the header ⇒ keep today's behavior exactly (whole-JWKS decode attempt).
  3. `kid` present and found among the cached JWKS `keys[*].kid` ⇒ proceed.
  4. `kid` present and NOT found ⇒ `force_refresh(jwks_uri)` (throttled) and re-check; still missing ⇒ 401 (`"Token signing key is unknown."`). Found ⇒ proceed with the refreshed document.
- Rotation tests (injected fetcher, no network): old-key token validates → fetcher output rotated to a new key → new-key token triggers exactly ONE forced refetch (fetch-count asserted) and validates → old-key token now 401s → within the throttle window another unknown-`kid` token does NOT refetch (count still 1) and 401s → after advancing the injected clock past the throttle, refetch happens again.

### 2. Nonce in the OIDC flow

- `/auth/login` generates `nonce = generate_id()` alongside `state`, includes `nonce=` in the authorize URL (`_oidc_client.build_authorize_url` gains the parameter), and stores it with the PKCE record.
- Session-store surface: `save_pkce_state(*, state, verifier, ttl_seconds, nonce)` and `pop_pkce_state(state) -> PkceState | None` where `PkceState` carries `verifier: str` and `nonce: str` (today `pop` returns the bare verifier string) — protocol + BOTH session-store adapters + all call sites. A small typed model beats a tuple; existing persisted bare-string states (if any survive a deploy) fail closed as unknown state — acceptable, the PKCE TTL is short.
- Callback validation, after `decode_token` succeeds: **when the decoded token is the id_token**, require `claims.get("nonce") == stored nonce`; mismatch or absence ⇒ 400 (`"id_token nonce mismatch."`), no session minted. **When the flow fell back to decoding the access_token** (no id_token in the response), the nonce check is skipped — nonce is an id_token claim by OIDC spec; this limitation is documented in the template doc and the code comment rather than silently ignored.
- Tests: nonce round-trips into the authorize URL; callback happy path (claims nonce matches); mismatch ⇒ 400 + no session cookie; absent nonce claim on an id_token ⇒ 400; access-token fallback path skips the check; both session-store adapters round-trip `PkceState`.

### 3. IdP configuration templates

- One doc: `docs/auth/idp-templates.md` (new directory) with, per IdP:
  - **Keycloak**: worked `AuthConfig` YAML (issuer `https://<host>/realms/<realm>`, `jwks_uri` under `/protocol/openid-connect/certs`, audience/client id, `roles_claim` for realm roles), IdP-side steps (public client + PKCE S256, redirect URI `<api>/auth/callback`, realm-role mapping), key-rotation posture note (chiliAI recovers via kid-refetch).
  - **Okta**: worked `AuthConfig` YAML (org authorization server issuer, `/v1/keys` jwks, audience), IdP-side steps (OIDC web/PKCE app, groups claim → `roles_claim`).
  - A "what chiliAI validates" table: signature (RS256), `iss`, `aud`, `exp`, id_token `nonce`, kid-triggered JWKS refetch (30s throttle), and what it does NOT yet do (refresh-token rotation, back-channel logout — out of scope).
  - The explicit **desk-checked disclaimer** per the ruling.

### 4. Testing & gates

- All verification is test-double based (ruling): injected `JwksFetcher`, scripted claims/token doubles following the existing auth test patterns (`tests/api/test_auth.py` module conventions).
- No API contract changes: `state`/`nonce` travel via redirect URLs and IdP round-trips, not our request/response models — no OpenAPI regen expected (CI contract job will prove it).
- pyright --strict clean (auth middleware/router are include-scoped — verify; if not, standalone-clean per this sprint's convention); coverage ≥ 85% on touched packages; ruff clean.

### 5. Scope guards (explicitly out)

Refresh-token rotation, back-channel/logout tokens, multi-IdP support, live-IdP verification (residual follow-up), any frontend changes. `_security.01` flips `done` with the desk-checked-templates deviation noted inline; BL-022 closes in the sprint file as the delivered stretch.

## Code touch points

`backend/api/middleware/auth.py` (JwksCache + decode_token), `backend/api/routers/auth.py` (login/callback), `backend/api/routers/_oidc_client.py` (authorize URL), session-store protocol + adapters (locate: `save_pkce_state` home — read before planning), `backend/tests/api/test_auth.py` (+ session-store tests), `docs/auth/idp-templates.md` (new), `docs/backlog/_security.md`, planning backlog + sprint file.
