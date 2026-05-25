## File: docs/backlog/_security.md

**Scope:** Production hardening of authentication, authorization, secret/credential management, transport security, audit logging, and log hygiene on top of the in-place auth/RBAC middleware shipped 2026-05-08 (`backend/api/middleware/auth.py`, `rbac.py`, `policy_registry.py`, `session_store.py`, `backend/api/routers/auth.py`).

### Epics
1. Ship reference production IdP profiles and JWKS-rotation hardening — `AuthConfig` in `backend/config/schema.py:261` defines OIDC fields generically, but there are no per-IdP (Auth0, Okta, Cognito, Keycloak, Google) recipes, no JWKS-rotation/kid-rollover test, and no signed `id_token` validation in `_user_from_session` (`backend/api/middleware/auth.py:110`).
2. Add resource-level authorization for knowledge bases and documents — `require_role` in `backend/api/middleware/rbac.py:53` enforces role tier only; no story of "this user owns/can access KB X" exists (KB models in `backend/knowledgebases/` carry no `owner_id`/ACL field), so any authenticated viewer can read any KB.
3. Enforce tenant isolation across every persistence boundary — `User` in `backend/api/middleware/auth.py:52` has no tenant claim, KB IDs are global, and the §12.3 "scoped at adapter layer" promise is not honored anywhere; cross-file edges below to `_multitenancy.md`.
4. Integrate a production secret manager with rotation — secrets today are read straight from env vars via the `*_env_var` pattern (`backend/config/schema.py:121,137,147,261-273`); no Vault/AWS Secrets Manager/External Secrets adapter, no rotation hooks, and JWT/cookie secrets cannot be rotated without restarts.
5. Establish TLS termination posture and service-to-service mTLS — checklist §A02 says "TLS terminates at ingress" but no manifest enforces it; `backend/events/runtime.py:51` notes TLS for Redis is unimplemented, and Postgres/Neo4j/Qdrant adapter configs accept no `sslmode`/CA bundle.
6. Add a durable audit log for analyst and admin actions — §14.2 lists audit log as a Medium-priority future capability; no `AuditLog` model, no router emits audit events, the only "audit" references are vector-index artifacts and route-policy startup checks.
7. Wire structured PII/secret redaction into the logging pipeline — `backend/shared/logging.py` configures structlog but has no redaction processor; checklist A05 claims "PII-stripping processors" but the processor list contains only `merge_contextvars`/`add_log_level`/timestamper, so request bodies, tokens, and emails are not scrubbed.
8. Provide admin-side session revocation and refresh-token rotation policy — `SessionStoreProtocol.delete` (`backend/api/middleware/session_store.py:48`) supports per-sid delete but there is no `/auth/sessions` admin endpoint, no "revoke all sessions for user", and refresh tokens are stored verbatim in Redis with no rotation-on-use audit.
9. Add CSRF protection for cookie-authenticated unsafe methods — tracked finding in `docs/security_checklist.md:156-168`: cookie-bearing requests use `SameSite=Lax` only, with no synchronizer-token or double-submit middleware on `POST/PUT/DELETE`.
10. Add API rate limiting and brute-force/abuse protection — §12.4 lists rate limiting as deferred; no middleware exists today, exposing `/auth/login`, `/chat`, `/records/*/push`, and the OIDC callback to enumeration/abuse.
11. Audit and tighten the existing 3-tier RBAC policy table — verify each router's `require_role(...)` matches the policy table in `docs/superpowers/specs/2026-05-08-auth-rbac-enforcement-design.md` §4 (e.g., `records.py` uses `analyst` only — no `admin` for destructive paths; no role guard exists for evidence/case mutations beyond `viewer`/`analyst`).
12. Operationalize the security checklist quarterly review and dependency-scan gating — `docs/security_checklist.md` declares a quarterly cadence and pip-audit/npm-audit gates but the first review is scheduled 2026-07-26 with no Findings entries, and CI failure thresholds for HIGH/CRITICAL audits are not codified in a workflow file under this concern's ownership.

### Provisional cross-file edges
- Epic 3 (tenant isolation enforcement) → `_multitenancy.md` epics covering tenant-scoped KB IDs, tenant-claim resolution from JWT, and adapter-layer tenant scoping on `graph`/`vectorstore`/`storage`/`database`/`events` modules.
- Epic 2 (resource-level authz) → `_multitenancy.md` epic on per-resource ACL surfaces (owner_id/acl on `KnowledgeBase`, document-level grants).
- Epic 6 (audit log) → `_observability.md` epics for structured-log sinks, correlation-ID propagation, and metrics on audit-event volume; `database.md` epic for an `audit_log` Postgres table and Alembic migration.
- Epic 4 (secret manager) → `_infra.md` epic for Kubernetes External Secrets / Vault Agent injector wiring; `_cicd.md` epic for CI secret-provider auth.
- Epic 5 (TLS/mTLS) → `_infra.md` epic for ingress/cert-manager + per-service TLS chart values; `database.md` epic for Postgres TLS sslmode; `events.md` epic for Redis TLS.
- Epic 10 (rate limiting) → `_observability.md` epic for rate-limit metrics; `api.md` epic for the rate-limit middleware itself.
- Epic 12 (checklist + dep audits) → `_cicd.md` epic for `pip-audit`/`npm audit` CI gating thresholds.

### Open questions
- Do we adopt a managed IdP (Auth0/Okta/Cognito) as the reference profile or stay provider-agnostic with documented recipes for the four major IdPs? Affects scope of Epic 1.
- Is tenant identity drawn from a JWT claim (`tenant_id`/`org_id`) or derived from KB ownership? Affects shape of Epics 2 and 3 and the cross-file edges to `_multitenancy.md`.
- Should audit-log storage be a dedicated `audit_log` Postgres table (Plan-C style) or an append-only outbox replayed to a SIEM, or both? Affects Epic 6 and its `database.md` edge.
- Per the 2026-05-08 spec §10, refresh-token encryption at rest in Redis was deferred — include it in Epic 8 or punt to a follow-up? 
- CSRF (Epic 9) only matters once cookie auth is enabled in production; do we ship it now or gate on the production cookie-deployment topology decision called out in `docs/security_checklist.md:166-168`?
