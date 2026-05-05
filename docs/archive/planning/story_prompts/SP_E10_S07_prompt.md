# Story E10-S07: RBAC authorization — role-based access control

## Story
As a platform operator, I want role-based access control (admin, analyst, viewer) enforced on API endpoints, so that users can only perform actions appropriate to their role.

## Acceptance Criteria
1. User roles are extracted from the JWT `roles` claim (configurable claim name).
2. A `require_role(role: str)` FastAPI dependency is available for router-level protection.
3. Role hierarchy: admin > analyst > viewer (admin inherits all lower permissions).
4. Default role assignments: config endpoints → admin, write operations → analyst, read operations → viewer.
5. Tests verify: admin can access all, analyst cannot access config, viewer cannot write, unrecognized role → 403.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | M    | E10-S06      |

## Target Files
- `backend/api/middleware/auth.py` — extend with role extraction from JWT claims
- `backend/api/middleware/rbac.py` — `require_role()` dependency and role hierarchy logic
- `backend/tests/api/test_rbac.py` — RBAC authorization tests

## Reference Files to Read First
- `backend/api/middleware/auth.py` — auth middleware from E10-S06 (JWT validation, user model)
- `backend/api/routers/` — existing router definitions to understand endpoint groupings
- `backend/api/dependencies.py` — existing dependency injection patterns

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- Role hierarchy must be explicit and configurable, not hardcoded in conditionals
- `require_role()` must compose with `get_current_user()` — it depends on the user being authenticated first
- Role claim name must be configurable in `AuthConfig` (default: `roles`)
- When auth is disabled (`enabled: False`), RBAC is also bypassed — anonymous user gets admin-equivalent access

## What NOT To Do
- Do NOT implement fine-grained permission systems (ABAC, resource-level ACLs) — stick to role-based
- Do NOT add role management endpoints — roles come from the OIDC provider
- Do NOT store roles in a local database
- Do NOT create a separate role hierarchy per endpoint — use one global hierarchy
- Do NOT break existing endpoint functionality — RBAC is additive authorization on top of authentication
- Do NOT apply RBAC to the `/health` or `/metrics` endpoints

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=api tests/api/test_rbac.py` >= 85% coverage for RBAC module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
