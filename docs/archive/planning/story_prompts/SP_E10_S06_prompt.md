# Story E10-S06: Auth middleware — JWT/OIDC authentication

## Story
As a platform operator, I want a FastAPI middleware that validates JWT tokens from an OIDC provider, so that API endpoints are protected and user identity is available to all handlers.

## Acceptance Criteria
1. `api/middleware/auth.py` implements a FastAPI dependency `get_current_user()` that extracts and validates a JWT from the `Authorization: Bearer <token>` header.
2. Token validation includes: signature verification (RS256), expiration check, audience claim, issuer claim.
3. Configuration via `AuthConfig` in domain config: `enabled: bool`, `issuer_url: str`, `audience: str`, `jwks_uri: str`.
4. When `enabled: False`, the middleware returns a default anonymous user — no enforcement.
5. Tests verify: valid token → user identity, expired token → 401, invalid signature → 401, missing header → 401, auth disabled → anonymous.
6. No hardcoded secrets — JWKS fetched from provider.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P0       | L    | E1-S06       |

## Target Files
- `backend/api/middleware/__init__.py` — middleware package init
- `backend/api/middleware/auth.py` — JWT validation dependency and JWKS caching
- `backend/config/schema.py` — add `AuthConfig` section
- `backend/tests/api/test_auth.py` — auth middleware tests

## Reference Files to Read First
- `backend/api/app.py` — FastAPI app factory, middleware registration
- `backend/api/dependencies.py` — existing dependency injection patterns
- `backend/config/schema.py` — existing config schema structure
- `backend/shared/types.py` — shared domain types (for user identity type)

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- Use `PyJWT` with `cryptography` backend (or `python-jose`) for JWT decoding
- JWKS must be fetched from the provider URL and cached (1-hour TTL, configurable)
- The `/health` endpoint must be exempt from authentication
- `AuthConfig` must follow the existing config schema pattern (Pydantic model in `config/schema.py`)
- The `get_current_user()` dependency must return a typed user object, not a raw dict

## What NOT To Do
- Do NOT hardcode any secrets, signing keys, or provider URLs
- Do NOT store JWTs or user sessions server-side — this is stateless token validation
- Do NOT add a user database or registration flow — identity comes from the external OIDC provider
- Do NOT make real HTTP calls to OIDC providers in tests — mock JWKS responses
- Do NOT skip the `enabled: False` bypass path — it is essential for development and testing
- Do NOT add auth to the `/health` endpoint

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=api tests/api/test_auth.py` >= 85% coverage for auth module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
