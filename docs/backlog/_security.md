# _security backlog

> **Scope:** IdP profiles, secret management, TLS, RBAC hardening, audit log, sensitive-data redaction, session management.
> **Story format and rules:** see [design spec §5](../superpowers/specs/2026-05-24-complete-backlog-design.md#5-story-format).

## Story _security.01: Ship reference production IdP profiles and JWKS-rotation hardening

**ID:** _security.01
**Status:** planned
**Prerequisites:** []
**Unblocks:** [llm.04, rag.09, vectorstore.10]
**Estimated size:** L
**Spec:** docs/superpowers/specs/2026-05-08-auth-rbac-enforcement-design.md

**As a** platform operator deploying chiliAI against a production identity provider,
**I need** a documented, tested integration recipe per major OIDC IdP plus signed-token validation that tolerates JWKS key rotation,
**so that** I can stand up auth in staging/production without bespoke debugging and survive an IdP `kid` rollover without an outage.

### Current State
- `AuthConfig` (`backend/config/schema.py:261-285`) defines OIDC fields generically (`issuer_url`, `audience`, `jwks_uri`, `client_id`, `client_secret_env_var`, `authorize_endpoint`, `token_endpoint`, `end_session_endpoint`, `redirect_uri`, `scopes`) but ships no per-IdP recipe or template config.
- `decode_token` (`backend/api/middleware/auth.py:136-206`) hard-codes `algorithms=["RS256"]` and validates `audience` + `issuer` only; there is no `kid`-based key selection test, no key-rollover fixture in `tests/api/`, and no negative test asserting that a token signed by a rotated-out key is rejected.
- `JwksCache` (`backend/api/middleware/auth.py:80-101`) caches the entire JWKS document with a single TTL and exposes only `invalidate()`; there is no "miss-on-unknown-kid → force refetch" path, so a fresh key rolled in mid-window cannot validate until TTL expires.
- The `/auth/callback` flow (`backend/api/routers/auth.py:128-144`) decodes the `id_token` for identity but never verifies it as an `id_token` (no `nonce`, no `azp`/`at_hash` checks); the design spec §3 calls this out as "signed `id_token` validation" still owed.
- No reference YAML exists under `backend/config/defaults/` for Auth0, Okta, Cognito, Keycloak, or Google Workspace; ops has no copy-paste starting point.

### Acceptance Criteria
- [ ] Per-IdP reference configs land under `backend/config/defaults/auth/` (one YAML per IdP: `auth0.yaml`, `okta.yaml`, `cognito.yaml`, `keycloak.yaml`, `google.yaml`) with comments naming required env vars and IdP-side setup steps.
- [ ] `docs/auth_idp_recipes.md` is created describing redirect-URI registration, scopes, roles-claim mapping, and end-session URL handling for each of the five IdPs above.
- [ ] `JwksCache.get` accepts an optional `kid` argument and refetches the JWKS document once per cache window when the requested `kid` is absent from the cached document; a hard-error backoff prevents refetch storms.
- [ ] `decode_token` selects the JWK by `kid` from the decoded JOSE header rather than handing the full JWKS to `jwt.decode` blindly.
- [ ] `/auth/callback` validates the `id_token` (not just decodes): asserts `aud == client_id`, `iss == issuer_url`, `exp > now`, and (when a `nonce` was issued during `/auth/login`) `nonce` round-trips.
- [ ] A `nonce` is generated alongside the PKCE pair in `/auth/login`, stored next to the verifier via `save_pkce_state`, and verified in `/auth/callback`.
- [ ] New unit tests cover key-rotation: a token signed by a key not in the initial JWKS triggers exactly one refetch, validates successfully on the refreshed document, and the refetch is recorded as a metric.
- [ ] New unit tests assert rejection of unsigned/`alg:none` tokens, mismatched `kid`, expired tokens, and tokens with wrong `aud`/`iss`.
- [ ] Coverage on `backend/api/middleware/auth.py` and `backend/api/routers/auth.py` stays ≥ 85% with the new tests.

### Verification
- `cd backend && pytest tests/api/test_auth_middleware.py tests/api/test_auth_router.py tests/api/test_jwks_rotation.py --cov=api.middleware.auth --cov=api.routers.auth --cov-fail-under=85`
- `cd backend && pyright api/middleware/auth.py api/routers/auth.py config/schema.py`
- Manual: stand up Keycloak locally per `docs/auth_idp_recipes.md`, run the BFF flow end-to-end, force a key rotation in Keycloak, observe that subsequent logins succeed without restarting the API.

### Code touch points
- `backend/api/middleware/auth.py` (modify)
- `backend/api/routers/auth.py` (modify)
- `backend/api/middleware/session_store.py` (modify — persist `nonce` next to PKCE verifier)
- `backend/config/defaults/auth/auth0.yaml` (new)
- `backend/config/defaults/auth/okta.yaml` (new)
- `backend/config/defaults/auth/cognito.yaml` (new)
- `backend/config/defaults/auth/keycloak.yaml` (new)
- `backend/config/defaults/auth/google.yaml` (new)
- `docs/auth_idp_recipes.md` (new)
- `tests/api/test_jwks_rotation.py` (new)
- `tests/api/test_auth_middleware.py` (modify)
- `tests/api/test_auth_router.py` (modify)

---

## Story _security.02: Add resource-level authorization for knowledge bases and documents

**ID:** _security.02
**Status:** planned
**Prerequisites:** [_security.03, knowledgebases.01, database.01]
**Unblocks:** [graph.12, knowledgebases.07, llm.14, storage.03]
**Estimated size:** L
**Spec:** docs/superpowers/specs/2026-05-08-auth-rbac-enforcement-design.md

**As an** analyst working on a sensitive investigation,
**I need** per-KB and per-document ACL enforcement on top of the role tier,
**so that** a fellow viewer in my organization cannot read a KB I have not granted them access to.

### Current State
- `require_role` (`backend/api/middleware/rbac.py:53-79`) enforces role tier only; there is no resource axis in the dependency.
- KB list/get/delete endpoints (`backend/api/routers/knowledgebases.py:100-172, 265-366`) gate purely on tier (`viewer`/`analyst`/`admin`) and return any KB the repository yields without an owner/ACL check.
- KB models in `backend/knowledgebases/` carry no `owner_id` or ACL field — once the repository surfaces a row, any authenticated user with the right tier sees it.
- The 2026-05-08 design spec §2 explicitly defers per-KB authorization to a "tenant isolation" Tier-2 item, and `docs/architecture.md:1289-1294` (§12.3) promises adapter-layer scoping that does not exist.
- `User` (`backend/api/middleware/auth.py:52-57`) has no concept of group/team membership, so any ACL must be expressed as either `user_id` grants or, later, group grants once group membership is sourced from the IdP.

### Acceptance Criteria
- [ ] A `KnowledgeBaseAccess` Pydantic model is added to `backend/knowledgebases/models.py` carrying `owner_id: str`, `acl: list[KnowledgeBaseGrant]` (where `KnowledgeBaseGrant` = `{principal_id, principal_type: "user"|"group", role: "viewer"|"analyst"|"admin"}`), and `created_at`/`updated_at`.
- [ ] The KB repository protocol exposes `list_for_user(user_id, roles, tenant_id)` and `assert_user_can_access(kb_id, user_id, roles, tenant_id, required_role)`; both in-memory and Postgres adapters implement them.
- [ ] A new dependency `require_kb_access(required_role)` in `backend/api/middleware/rbac.py` reads `kb_id` from the path and calls `assert_user_can_access`; failure raises 403 (or 404 to avoid existence disclosure for users without `viewer` on the KB).
- [ ] Every `/knowledgebases/{kb_id}/...` route swaps `require_role(...)` for `require_kb_access(...)`; `GET /knowledgebases` returns only KBs the user can see via `list_for_user`.
- [ ] An admin endpoint `POST /knowledgebases/{kb_id}/grants` + `DELETE /knowledgebases/{kb_id}/grants/{principal_id}` lets owners manage ACL entries; both require `admin` on the KB.
- [ ] An Alembic migration adds `owner_id` and `acl` columns (jsonb for ACL) to the KB table created by `database.01`; existing rows backfill `owner_id` from a configurable bootstrap admin.
- [ ] Negative tests in `tests/api/test_knowledgebases_router.py` assert: viewer-tier user without a grant gets 404 on `GET /knowledgebases/{id}`; analyst-tier user without `analyst` on a KB cannot upload documents; owner can revoke their own admin grant only if at least one other admin remains.
- [ ] An emitted audit event `kb.access.granted` / `kb.access.revoked` is published via `_security.06`'s audit-log writer when ACL changes (cross-edge — guarded behind a feature flag until _security.06 lands).
- [ ] Coverage on `backend/api/middleware/rbac.py` and `backend/api/routers/knowledgebases.py` stays ≥ 85%.

### Verification
- `cd backend && pytest tests/api/test_knowledgebases_router.py tests/api/test_rbac_kb_access.py tests/knowledgebases/ --cov=api.middleware.rbac --cov=api.routers.knowledgebases --cov=knowledgebases --cov-fail-under=85`
- `cd backend && pyright api/middleware/rbac.py api/routers/knowledgebases.py knowledgebases/`
- Manual: seed two users with `viewer` tier, grant user A `viewer` on KB1, confirm user B receives 404 on `GET /knowledgebases/KB1` and KB1 is absent from user B's `GET /knowledgebases` listing.

### Code touch points
- `backend/api/middleware/rbac.py` (modify)
- `backend/api/routers/knowledgebases.py` (modify)
- `backend/knowledgebases/models.py` (modify)
- `backend/knowledgebases/protocols.py` (modify)
- `backend/knowledgebases/adapters/in_memory.py` (modify)
- `backend/knowledgebases/adapters/postgres.py` (modify)
- `backend/database/migrations/versions/` (new — ACL columns)
- `tests/api/test_rbac_kb_access.py` (new)
- `tests/api/test_knowledgebases_router.py` (modify)

---

## Story _security.03: Enforce tenant isolation across every persistence boundary

**ID:** _security.03
**Status:** planned
**Prerequisites:** [_multitenancy.01, _multitenancy.02, _multitenancy.03, api.21]
**Unblocks:** [_security.02, _security.06, storage.06]
**Estimated size:** L

**As a** platform operator running multi-tenant chiliAI,
**I need** every read and write to be scoped to the caller's tenant at the adapter layer,
**so that** a JWT carrying `tenant_id=A` cannot return, mutate, or correlate any data belonging to `tenant_id=B`.

### Current State
- `User` (`backend/api/middleware/auth.py:52-57`) carries `user_id`, `roles`, and `email` — no `tenant_id` claim.
- `_extract_user` (`backend/api/middleware/auth.py:218-228`) reads only `sub`, `email`, and the configured `roles_claim` — it does not look at `tenant_id`/`org_id`/`org`/`tid` claims.
- DI factories in `backend/api/dependencies.py:413-440` and below build process-singleton stores (`get_session_store`, `get_object_store`, `get_graph_repository`, `get_vector_store`, etc.) keyed only by env/config — there is no tenant axis anywhere in the dependency graph.
- `docs/architecture.md:1289-1294` (§12.3) promises adapter-layer tenant scoping (graph queries, vector searches, object-store paths) but no adapter today accepts or applies a tenant.
- `KnowledgeBase` IDs are global (no tenant prefix); event payloads in `backend/events/types.py` carry no `tenant_id`; structured logs do not bind `tenant_id` via `bind_contextvars` (`backend/shared/logging.py:129-148` only binds `correlation_id`).

### Acceptance Criteria
- [ ] `User` gains a `tenant_id: str | None` field, and `_extract_user` reads it from a configurable `tenant_claim` (default `"tenant_id"`, falling back to `"org_id"` then `"tid"`); when auth is enabled and the claim is absent, the request 401s with a clear message.
- [ ] `SessionRecord` (`backend/api/middleware/session_store.py:22-39`) gains `tenant_id`; the `/auth/callback` flow extracts it from `id_token` claims and persists it.
- [ ] A `TenantContext` contextvar is established and bound in middleware on every authenticated request; `bind_correlation_id` in `backend/shared/logging.py` is paired with `bind_tenant_id` so every log line is tenant-tagged.
- [ ] Every adapter that owns persistence (`graph.adapters.*`, `vectorstore.adapters.*`, `storage.adapters.*`, `database/`, `events/runtime.py`, KB/case/raw-records repositories) accepts a `tenant_id` argument on every read and write and refuses unscoped calls (raises `TenantScopeMissingError`) when auth is enabled.
- [ ] Object-store keys gain a `tenants/{tenant_id}/` prefix; Neo4j queries gain a `WHERE n.tenant_id = $tenant_id` filter; Qdrant searches restrict by `tenant_id` payload filter; Postgres tables gain a `tenant_id` column with row-level checks or explicit `WHERE` clauses.
- [ ] An integration test fixture mints two users in two tenants and asserts that every router endpoint returns 404 (not 403) when the resource exists in the other tenant.
- [ ] A "tenant escape" regression test attempts to call each adapter without a `tenant_id` in production mode and confirms the adapter raises rather than silently returning unscoped data.
- [ ] `docs/architecture.md` §12.3 is updated to reference this story's enforcement points (no longer "designed-for").

### Verification
- `cd backend && pytest tests/test_tenant_isolation.py tests/api/ tests/graph/ tests/vectorstore/ tests/storage/ tests/database/ tests/events/ -k tenant --cov-fail-under=85`
- `cd backend && pyright api/ graph/ vectorstore/ storage/ database/ events/ knowledgebases/`
- Manual: log in as user in tenant A, attempt to access a KB created by tenant B (whose ID is known), confirm 404; check structured logs and confirm every log line carries `tenant_id`.

### Code touch points
- `backend/api/middleware/auth.py` (modify)
- `backend/api/middleware/session_store.py` (modify)
- `backend/api/dependencies.py` (modify)
- `backend/shared/logging.py` (modify)
- `backend/graph/adapters/` (modify all adapters)
- `backend/vectorstore/adapters/` (modify all adapters)
- `backend/storage/adapters/` (modify all adapters)
- `backend/database/` (modify)
- `backend/events/runtime.py` (modify)
- `backend/knowledgebases/`, `backend/records/`, `backend/monitoring/` (modify repositories)
- `tests/test_tenant_isolation.py` (new)
- `docs/architecture.md` (modify §12.3)

---

## Story _security.04: Integrate a production secret manager with rotation

**ID:** _security.04
**Status:** planned
**Prerequisites:** [_infra.08, config.02]
**Unblocks:** [_cicd.16, _multitenancy.03, agent.16, rag.15, storage.04]
**Estimated size:** L

**As a** platform operator,
**I need** secrets resolved at runtime from a managed secret store (Vault, AWS Secrets Manager, GCP Secret Manager, Azure Key Vault) with hot rotation,
**so that** I can rotate the JWT client secret or DB password without rebuilding images or restarting pods.

### Current State
- All secret material is read from environment variables via the `*_env_var` pattern documented in `backend/config/schema.py:7-25` and implemented at the read sites (e.g., `LlmConfig.api_key_env_var:121`, `EmbeddingsConfig.api_key_env_var:137`, `ObjectStoreConfig.credentials_env_var:147`, `AuthConfig.client_secret_env_var:273`).
- The OIDC client secret is read with `os.environ.get(auth_config.client_secret_env_var)` at request time (`backend/api/routers/auth.py:49-54`, `backend/api/middleware/auth.py:268-272`); there is no caching, rotation hook, or fallback.
- `_infra.08` (per `_DRAFT_epics.md:82`) plans External Secrets Operator / CSI driver templates at the platform layer, but the backend has no adapter that reads from a secret store directly — every secret today must be marshalled into a Kubernetes Secret before the pod can see it.
- Cookie and session-store secrets cannot be rotated without dropping every active session because there is no key-version tracking.

### Acceptance Criteria
- [ ] A new `backend/secrets/` module is created with `SecretProvider` protocol exposing `get(name: str) -> str` and `subscribe(name: str, callback)`; adapters land for `env` (current behavior), `vault`, `aws_secrets_manager`, `gcp_secret_manager`, `azure_key_vault`, and `file` (for k8s CSI-mounted secret files).
- [ ] A `SecretsConfig` Pydantic section is added to `backend/config/schema.py` selecting the provider and provider-specific config; default remains `env` so dev behavior is unchanged.
- [ ] All current `*_env_var` read sites route through the configured `SecretProvider` (env adapter preserves today's behavior); the read sites accept either a literal env-var name (legacy) or a `secret://{provider}/{path}` URI (new).
- [ ] Each non-env adapter caches values with a configurable TTL (default 300 s) and supports background refresh; a `secrets.rotated` event is emitted via `events/runtime.py` when a watched secret's version changes.
- [ ] The OIDC client secret and database DSN, when supplied via the secret provider, refresh in-process without a restart — verified by an integration test that mutates the underlying secret and observes the next request using the new value within one TTL window.
- [ ] Provider unit tests are marked `@pytest.mark.integration` and gated behind extras (`[vault]`, `[aws-secrets]`, `[gcp-secrets]`, `[azure-secrets]`); the env and file adapters have unmarked unit tests.
- [ ] `pyright --strict` clean on `backend/secrets/`; coverage ≥ 85% on env, file, and the cache layer.
- [ ] `docs/architecture.md` and `infra/README.md` document the supported providers and the rotation contract.

### Verification
- `cd backend && pytest tests/secrets/ --cov=secrets --cov-fail-under=85`
- `cd backend && pytest -m integration tests/secrets/ -k "vault or aws or gcp or azure"` (each gated behind its extra)
- `cd backend && pyright secrets/`
- Manual: configure the `file` adapter against a CSI-mounted directory, change a secret on disk, observe the new value picked up within the TTL window and the `secrets.rotated` event emitted.

### Code touch points
- `backend/secrets/__init__.py` (new)
- `backend/secrets/protocols.py` (new)
- `backend/secrets/adapters/env_adapter.py` (new)
- `backend/secrets/adapters/file_adapter.py` (new)
- `backend/secrets/adapters/vault_adapter.py` (new)
- `backend/secrets/adapters/aws_secrets_adapter.py` (new)
- `backend/secrets/adapters/gcp_secrets_adapter.py` (new)
- `backend/secrets/adapters/azure_keyvault_adapter.py` (new)
- `backend/config/schema.py` (modify)
- `backend/api/dependencies.py` (modify)
- `backend/api/routers/auth.py` (modify)
- `backend/api/middleware/auth.py` (modify)
- `tests/secrets/` (new)
- `docs/architecture.md`, `infra/README.md` (modify)

---

## Story _security.05: Establish TLS termination posture and service-to-service mTLS

**ID:** _security.05
**Status:** planned
**Prerequisites:** [_infra.01, database.07, events.01]
**Unblocks:** [_observability.10, api.02, frontend.18, graph.13, monitoring.05, rag.17]
**Estimated size:** L

**As a** platform operator,
**I need** TLS enforced at ingress and on every backend-to-datastore hop, with optional mTLS for service-to-service traffic,
**so that** traffic to Redis/Postgres/Neo4j/Qdrant cannot be sniffed on the cluster network and the security checklist's §A02 promise is real.

### Current State
- `docs/security_checklist.md` §A02 declares "TLS terminates at ingress" but no manifest under `infra/k8s/` or `infra/helm/` enforces it (no `Ingress` with TLS, no cert-manager `Certificate`).
- `backend/events/runtime.py:51` carries the comment "Support TLS/auth env-only" — Redis Streams adapter does not honor `rediss://` URLs or expose CA cert configuration.
- `GraphDbConfig` (`backend/config/schema.py:97-104`) accepts only `uri`/`pool_size`/`auth_env_var` — no `tls`/`sslmode`/`cacert_path`.
- `DatabaseConfig` (`backend/config/schema.py:159-166`) has no `sslmode` field; `database.07` (per locked ID space) plans `sslmode: Literal["disable","require","verify-full"]` and a refusal to start in production with `sslmode=disable`.
- `VectorStoreConfig` (`backend/config/schema.py:106-113`) lacks any TLS toggle; Qdrant adapter cannot present a client cert.

### Acceptance Criteria
- [ ] `infra/k8s/ingress.yaml` (and the equivalent Helm template) require a `tls` block, reference a cert-manager-issued `Certificate`, and the `chili-app` and `chili-api` Services are reachable only via HTTPS in the production overlay.
- [ ] `EventBusConfig` gains a `tls: bool` and `ca_cert_env_var: str | None`; `events/runtime.py` honors `rediss://` URIs and loads the CA bundle when set.
- [ ] `DatabaseConfig` gains `sslmode`, `sslrootcert_env_var`, `sslcert_env_var`, `sslkey_env_var`; `database/engine._normalize_dsn` refuses production startup with `sslmode=disable` (overlaps with `database.07`; this story consumes that work).
- [ ] `GraphDbConfig` gains `tls: bool` and `ca_cert_env_var`; the Neo4j adapter uses `neo4j+s://` and a custom trust manager when configured.
- [ ] `VectorStoreConfig` gains `tls: bool`, `ca_cert_env_var`, `client_cert_env_var`, `client_key_env_var`; Qdrant adapter uses gRPC/HTTPS with the supplied chain.
- [ ] An optional `MTLSConfig` section selects mTLS for service-to-service calls (worker → API, API → secret manager); when enabled, the worker presents a client cert and the API verifies it.
- [ ] A new doc `docs/tls_posture.md` documents the supported posture per environment (dev: off, staging: on, prod: on + mTLS optional).
- [ ] A unit test asserts each adapter refuses to start in `CHILI_ENV=production` when TLS is disabled.
- [ ] `make prod` validates TLS settings before bringing the stack up (script in `infra/scripts/`).

### Verification
- `cd backend && pytest tests/test_tls_guardrails.py tests/database/test_engine.py tests/events/test_runtime.py tests/graph/test_neo4j_adapter.py -m "integration or not integration" --cov-fail-under=85`
- `cd backend && pyright config/schema.py events/runtime.py database/engine.py graph/adapters/neo4j_adapter.py vectorstore/adapters/qdrant_adapter.py`
- `kubectl apply --dry-run=client -f infra/k8s/ingress.yaml` succeeds and the rendered manifest includes a TLS block.
- Manual: stand up Redis with TLS, start the worker with `rediss://` and a CA bundle, confirm event publication succeeds; repeat for Postgres and Neo4j.

### Code touch points
- `backend/config/schema.py` (modify)
- `backend/events/runtime.py` (modify)
- `backend/database/engine.py` (modify)
- `backend/graph/adapters/neo4j_adapter.py` (modify)
- `backend/vectorstore/adapters/qdrant_adapter.py` (modify)
- `backend/api/app.py` (modify — startup guardrail)
- `infra/k8s/ingress.yaml` (modify)
- `infra/helm/templates/ingress.yaml` (modify)
- `infra/scripts/check_tls.sh` (new)
- `docs/tls_posture.md` (new)
- `tests/test_tls_guardrails.py` (new)

---

## Story _security.06: Add a durable audit log for analyst and admin actions

**ID:** _security.06
**Status:** planned
**Prerequisites:** [_security.03, database.01, events.01]
**Unblocks:** [_security.08, analytics.27, api.17, config.09, frontend.18, ingestion.07, knowledgebases.06, monitoring.04]
**Estimated size:** L

**As a** compliance owner,
**I need** every authenticated mutation (login, logout, KB grant/revoke, KB delete, config change, alert ack, evidence-pack mutation, role change, session revocation) recorded with actor, tenant, target, before/after, and timestamp in a tamper-evident, queryable log,
**so that** the §14.2 audit-log capability is fulfilled and we can answer "who did what, when, against which tenant" for any 90-day window.

### Current State
- `docs/architecture.md:1359` (§14.2) lists "Audit log" as a Medium-priority future capability with no concrete owner.
- `grep -R "audit" backend/` finds only the policy-registry startup check and vector-index artifact references — no model, no router, no event type carries audit data.
- `backend/api/routers/auth.py` emits no structured "login.success"/"login.failure"/"logout" log lines today; `backend/api/routers/knowledgebases.py:172` allows admin DELETE with no auditable trail.
- The 2026-05-08 design spec §10 calls out that "Audit logging hooks (login success/failure, logout, refresh)... belongs to the future observability spec" — this story is that owner.
- No Postgres table or Alembic migration for an `audit_log` table exists today.

### Acceptance Criteria
- [ ] A new `backend/auditlog/` module is added with `AuditEvent` Pydantic model (`event_id: UUID`, `occurred_at: datetime`, `tenant_id: str`, `actor_user_id: str`, `actor_email: str | None`, `actor_roles: list[str]`, `action: str` — e.g. `auth.login.success`, `kb.delete`, `kb.access.granted`, `config.update`, `alert.ack`, `evidence_pack.mutate`, `session.revoke` — `resource_type: str`, `resource_id: str`, `before: dict | None`, `after: dict | None`, `correlation_id: str`, `client_ip: str | None`, `user_agent: str | None`, `outcome: Literal["success","failure"]`, `failure_reason: str | None`).
- [ ] `AuditSinkProtocol` is defined with `record(event: AuditEvent)`; adapters land for `postgres` (default in production), `file` (JSONL append-only, dev/test), and `null` (auth-disabled local).
- [ ] An Alembic migration adds an `audit_log` table with the columns above plus a covering index on `(tenant_id, occurred_at DESC)` and `(actor_user_id, occurred_at DESC)`.
- [ ] Hooks are added at the source sites: `/auth/login`, `/auth/callback`, `/auth/logout`, `/auth/me` failures; `POST/DELETE /knowledgebases/{id}/grants`; `DELETE /knowledgebases/{id}`; `POST /config/...` writes (once `config.07` lands — cross-edge); `POST /alerts/{id}/ack`; evidence-pack mutations; session-revocation endpoints from `_security.08`.
- [ ] `GET /audit/events` admin-only endpoint supports filter by tenant, actor, action prefix, time range, and pagination.
- [ ] Audit writes never block the request: failures append to a bounded in-memory buffer that retries, and a metric `chili_audit_write_failures_total` is emitted.
- [ ] Coverage ≥ 85% on `backend/auditlog/`.

### Verification
- `cd backend && pytest tests/auditlog/ tests/api/test_audit_router.py --cov=auditlog --cov-fail-under=85`
- `cd backend && pyright auditlog/`
- Manual: log in, delete a KB, query `GET /audit/events?action_prefix=kb.delete`, confirm the entry shows actor + before/after.

### Code touch points
- `backend/auditlog/__init__.py` (new)
- `backend/auditlog/models.py` (new)
- `backend/auditlog/protocols.py` (new)
- `backend/auditlog/adapters/postgres.py` (new)
- `backend/auditlog/adapters/file.py` (new)
- `backend/auditlog/adapters/null.py` (new)
- `backend/auditlog/writer.py` (new — async buffered writer)
- `backend/database/migrations/versions/` (new — `audit_log` table)
- `backend/api/routers/auth.py` (modify — emit audit events)
- `backend/api/routers/knowledgebases.py` (modify)
- `backend/api/routers/alerts.py` (modify)
- `backend/api/routers/evidence.py` (modify)
- `backend/api/routers/audit.py` (new)
- `backend/api/app.py` (modify — register audit router)
- `tests/auditlog/` (new)
- `tests/api/test_audit_router.py` (new)

---

## Story _security.07: Wire structured PII/secret redaction into the logging pipeline

**ID:** _security.07
**Status:** planned
**Prerequisites:** [_observability.01]
**Unblocks:** [_cicd.06, _plugins.04, api.18, frontend.19]
**Estimated size:** M

**As an** operator reviewing structured logs,
**I need** request bodies, headers, tokens, emails, and other PII automatically scrubbed before they reach stdout or the log aggregator,
**so that** the §A05 checklist promise of "PII-stripping processors" is real and an aggregator compromise does not leak secrets we never intended to ship.

### Current State
- `configure_logging` in `backend/shared/logging.py:61-113` builds a structlog pipeline of `merge_contextvars`, `add_log_level`, `add_logger_name`, `_correlation_id_processor`, `timestamper`, `StackInfoRenderer`, `format_exc_info`, and a JSON or console renderer — no redaction processor is registered.
- `docs/security_checklist.md` historically claimed A05 was covered, but the only contextvar redaction today is `correlation_id` binding; tokens passed into log calls (e.g., access tokens during refresh failures) flow straight to stdout.
- No allowlist/denylist for log-event keys exists; nothing prevents a future contributor from logging `event_dict["password"] = ...` or `event_dict["authorization"] = request.headers["Authorization"]`.
- Frontend RUM events (when `_observability.07` lands) will need the same scrubbing on the way out.

### Acceptance Criteria
- [ ] A new `backend/shared/redaction.py` module is added defining a structlog processor `redact_sensitive(_logger, _method, event_dict)` that walks the event dict recursively and replaces values for keys matching `("password", "token", "access_token", "refresh_token", "id_token", "authorization", "cookie", "set-cookie", "secret", "api_key", "client_secret", "session_id", "sid", "ssn", "email", "phone", "dob", "date_of_birth")` with `"[redacted]"`.
- [ ] The processor also applies pattern-based redaction: JWTs (`eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+`), bearer-style auth headers, and email addresses inside free-text `event` strings.
- [ ] `configure_logging` registers `redact_sensitive` as the last processor before the renderer; ordering preserved so timestamps/correlation IDs remain.
- [ ] A `RedactionPolicy` Pydantic config (loadable from `LoggingConfig` in the domain config) lets operators add tenant-specific extra keys without code changes.
- [ ] Unit tests assert: a log call carrying `password=`, `access_token=`, an email, or a raw JWT in the `event` string emits `[redacted]` in the rendered output; correlation_id and tenant_id are NOT redacted; nested dict/list values are scrubbed; performance overhead is ≤ 5 µs per event in a microbenchmark.
- [ ] `docs/security_checklist.md` §A05 is updated to reference this story instead of an unimplemented claim.
- [ ] Coverage on `backend/shared/redaction.py` ≥ 95%.

### Verification
- `cd backend && pytest tests/shared/test_redaction.py tests/shared/test_logging.py --cov=shared.redaction --cov=shared.logging --cov-fail-under=85`
- `cd backend && pyright shared/redaction.py shared/logging.py`
- Manual: trigger a refresh-token failure path with `LOG_FORMAT=json`, grep stdout for `eyJ` or `refresh_token` and confirm zero hits.

### Code touch points
- `backend/shared/redaction.py` (new)
- `backend/shared/logging.py` (modify)
- `backend/config/schema.py` (modify — add `LoggingConfig.redaction`)
- `tests/shared/test_redaction.py` (new)
- `tests/shared/test_logging.py` (modify)
- `docs/security_checklist.md` (modify §A05)

---

## Story _security.08: Provide admin-side session revocation and refresh-token rotation policy

**ID:** _security.08
**Status:** planned
**Prerequisites:** [_security.06, api.23]
**Unblocks:** []
**Estimated size:** M
**Spec:** docs/superpowers/specs/2026-05-08-auth-rbac-enforcement-design.md

**As an** admin responding to a suspected credential compromise,
**I need** to revoke a user's sessions (one or all) and enforce refresh-token rotation-on-use,
**so that** a stolen `chiliai_session` or refresh token loses access immediately and rotation reuse is detected and quarantined.

### Current State
- `SessionStoreProtocol.delete` (`backend/api/middleware/session_store.py:48`) supports per-`sid` delete, but no router calls it on behalf of an admin; there is no `/auth/sessions/...` endpoint of any kind.
- `RedisSessionStore` and `InMemorySessionStore` (`backend/api/middleware/session_store.py:54-148`) index only by `session_id`; there is no `list_by_user(user_id)` or `delete_by_user(user_id)`.
- `_maybe_refresh_session` (`backend/api/middleware/auth.py:251-298`) calls the OIDC refresh grant and stores `tokens.refresh_token or record.refresh_token` — refresh tokens are stored verbatim in Redis, never encrypted, and there is no detection of refresh-token reuse (the same refresh token replayed twice both succeed).
- The 2026-05-08 spec §10 deferred refresh-token encryption-at-rest in Redis with the note "future work could encrypt the value with a server-side key" — this story addresses that.
- No audit hook fires today on logout or on session expiry; once `_security.06` lands, revocation events need to flow there.

### Acceptance Criteria
- [ ] `SessionStoreProtocol` gains `list_by_user(user_id, tenant_id)` and `delete_by_user(user_id, tenant_id) -> int`; both Redis and in-memory adapters implement them. Redis maintains a `session_index:{tenant_id}:{user_id}` SET keyed alongside the session record.
- [ ] A new admin router `/auth/sessions` exposes: `GET /auth/sessions?user_id=` (list sessions), `DELETE /auth/sessions/{sid}` (revoke one), `DELETE /auth/sessions?user_id=` (revoke all for user); all gated by `require_role("admin")` and tenant-scoped per `_security.03`.
- [ ] Refresh tokens are encrypted at rest in Redis using a key derived from a configurable env-var-named secret (`AuthConfig.refresh_token_encryption_env_var`); rotation of the encryption key supports a brief grace window where both old and new keys decrypt.
- [ ] Refresh-token rotation-on-use is enforced: when the IdP returns a new refresh token, the old one is invalidated; if a request arrives later carrying the old refresh token, the entire session for that user is revoked and an audit event `auth.refresh_reuse_detected` is emitted.
- [ ] `/auth/logout` and admin-driven revocation both publish audit events via `_security.06`.
- [ ] Frontend `SessionContext` reads a 401 with `WWW-Authenticate: Bearer, error="session_revoked"` and surfaces a "Your session was revoked by an admin" message instead of a generic redirect.
- [ ] Unit tests cover: admin lists/revokes own and other-user sessions (tenant-scoped); refresh-token reuse triggers full revocation + audit event; the encrypted Redis value is unreadable without the key.

### Verification
- `cd backend && pytest tests/api/test_session_revocation.py tests/api/test_refresh_rotation.py tests/api/test_auth_router.py --cov=api.middleware.session_store --cov=api.routers.auth --cov-fail-under=85`
- `cd backend && pyright api/middleware/session_store.py api/routers/auth.py api/routers/sessions.py`
- Manual: log in twice from two browsers, revoke session A from the admin UI as user B (after granting B admin), confirm session A's next request gets 401 and the audit log shows the revocation.

### Code touch points
- `backend/api/middleware/session_store.py` (modify)
- `backend/api/middleware/auth.py` (modify)
- `backend/api/routers/auth.py` (modify)
- `backend/api/routers/sessions.py` (new)
- `backend/api/app.py` (modify — register sessions router)
- `backend/config/schema.py` (modify — refresh-token encryption settings)
- `tests/api/test_session_revocation.py` (new)
- `tests/api/test_refresh_rotation.py` (new)

---

## Story _security.09: Add CSRF protection for cookie-authenticated unsafe methods

**ID:** _security.09
**Status:** planned
**Prerequisites:** []
**Unblocks:** [api.22]
**Estimated size:** M

**As a** security reviewer,
**I need** unsafe-method requests authenticated via `chiliai_session` to require a synchronizer token or double-submit cookie,
**so that** a malicious cross-origin form post or image tag cannot trigger state changes against an authenticated user's session.

### Current State
- The BFF auth flow (`backend/api/routers/auth.py:163-172`) sets `chiliai_session` with `samesite="lax"`, which protects top-level navigations but does NOT protect form posts that submit cross-origin via `<form method="POST">` or image preflights.
- `docs/security_checklist.md:156-168` explicitly flags this as a tracked finding: "No synchronizer-token or double-submit CSRF middleware exists yet... Follow-up recommendation: add a CSRF token endpoint plus unsafe-method validation when production cookie-auth deployment topology is finalized."
- `chili_app/src/lib/apiClient.ts` sends `credentials: 'include'` on every fetch, so an attacker page can ride the cookie if they reach an unsafe-method endpoint with same-site rules satisfied (sub-domain deployments).
- No CSRF middleware lives under `backend/api/middleware/`; no `X-CSRF-Token` header is read anywhere; no `/auth/csrf` endpoint exists.

### Acceptance Criteria
- [ ] A new `backend/api/middleware/csrf.py` implements double-submit-cookie CSRF: a non-HttpOnly `chiliai_csrf` cookie is set alongside `chiliai_session` carrying a per-session random token; unsafe-method (`POST`/`PUT`/`PATCH`/`DELETE`) requests with `chiliai_session` present must echo the token via the `X-CSRF-Token` header.
- [ ] The middleware skips: requests authenticated via `Authorization: Bearer` (service-to-service), `/auth/login` and `/auth/callback` (state-of-flow guarded by PKCE state), and safe methods (`GET`/`HEAD`/`OPTIONS`).
- [ ] `GET /auth/csrf` returns the current token in the response body (and refreshes the cookie); SPAs that lose the cookie mid-session can re-fetch.
- [ ] `chili_app/src/lib/apiClient.ts` is updated to read `chiliai_csrf` from `document.cookie` and attach `X-CSRF-Token` to every unsafe-method fetch.
- [ ] A failed CSRF check returns 403 with `detail="CSRF token missing or invalid"` and emits an audit event `csrf.failure`.
- [ ] Unit tests cover: safe method without token succeeds; unsafe method with cookie auth and matching token succeeds; unsafe method with cookie auth and missing/mismatched token 403s; unsafe method with Bearer auth and no token succeeds; token rotation on `/auth/login`.
- [ ] Vitest tests assert `apiClient` attaches `X-CSRF-Token` to POST/PUT/PATCH/DELETE.
- [ ] `docs/security_checklist.md:156-168` is updated to reference this story as the closing change.

### Verification
- `cd backend && pytest tests/api/test_csrf_middleware.py tests/api/ -k unsafe --cov=api.middleware.csrf --cov-fail-under=85`
- `cd backend && pyright api/middleware/csrf.py`
- `cd chili_app && npm run test:run -- src/lib/__tests__/apiClient.test.ts`
- Manual: attempt a `POST /knowledgebases` from a different-origin curl with only the `chiliai_session` cookie, confirm 403.

### Code touch points
- `backend/api/middleware/csrf.py` (new)
- `backend/api/app.py` (modify — register CSRF middleware)
- `backend/api/routers/auth.py` (modify — issue `chiliai_csrf` on `/auth/callback`, expose `/auth/csrf`)
- `chili_app/src/lib/apiClient.ts` (modify)
- `tests/api/test_csrf_middleware.py` (new)
- `chili_app/src/lib/__tests__/apiClient.test.ts` (modify)
- `docs/security_checklist.md` (modify)

---

## Story _security.10: Add API rate limiting and brute-force/abuse protection

**ID:** _security.10
**Status:** planned
**Prerequisites:** [api.18]
**Unblocks:** [analytics.29, api.22, records.10]
**Estimated size:** M

**As a** platform operator exposing chiliAI on the open internet,
**I need** per-IP, per-user, and per-tenant rate limits on sensitive endpoints,
**so that** `/auth/login`, the OIDC callback, `/chat`, and `/records/*/push` cannot be enumerated, brute-forced, or DDoS-bombed by a single client.

### Current State
- `docs/architecture.md:1303` (§12.4) lists rate limiting as "deferred, add when exposed to untrusted clients" — no middleware exists today.
- `backend/api/app.py:122-135` registers only `CORSMiddleware`, `register_metrics`, and tracing instrumentation; no rate-limit middleware between them.
- `/auth/login` and `/auth/callback` (`backend/api/routers/auth.py:58-173`) are reachable an unlimited number of times per second — credential-stuffing and OIDC-callback replay are unconstrained.
- `POST /chat/conversations/{id}/messages?stream=true` holds an LLM call open for the duration of the request (`backend/api/routers/rag.py:65-105`) with no per-user cap — a single user can pin every worker.
- `api.18` (per locked ID space) plans the actual rate-limit middleware with a Redis token-bucket; this story consumes that work and applies the policy table specifically for security-sensitive routes.

### Acceptance Criteria
- [ ] A `RateLimitPolicy` registry is added under `backend/api/middleware/rate_limit_policy.py` mapping (route_pattern → policy) where policy = `{key: "ip" | "user" | "tenant" | "ip+route", capacity: int, refill_per_second: float}`.
- [ ] Policies are populated for: `POST /auth/login` (10/min per IP), `GET /auth/callback` (10/min per IP), `POST /chat/conversations/*/messages` (60/min per user, 600/min per tenant), `POST /records/*/push` (30/min per user), `POST /knowledgebases/*/documents` (10/min per user, 60/min per tenant for upload bytes), `GET /knowledgebases` (300/min per user).
- [ ] When a limit is breached, the response is 429 with `Retry-After` header; the audit log captures `rate_limit.exceeded` with route and principal.
- [ ] Login-specific brute-force protection: after 5 consecutive `/auth/callback` failures from the same IP within 5 minutes, that IP receives 429 with `Retry-After: 900` for 15 minutes; on success the counter clears.
- [ ] Anonymous viewer (auth disabled in dev) is exempt from per-user policies but still subject to per-IP policies.
- [ ] Prometheus metric `chili_rate_limit_decisions_total{route,decision}` is emitted for `allowed`/`denied`.
- [ ] Unit tests use a fake clock to verify token-bucket math, policy lookup, audit emission, and 429 + Retry-After headers.

### Verification
- `cd backend && pytest tests/api/test_rate_limit_security.py tests/api/test_rate_limit_middleware.py --cov-fail-under=85`
- `cd backend && pyright api/middleware/rate_limit_policy.py`
- Manual: hammer `/auth/login` 20 times in 10 seconds with `httpie`, confirm 11th request returns 429 with a `Retry-After` ≥ 50.

### Code touch points
- `backend/api/middleware/rate_limit_policy.py` (new)
- `backend/api/app.py` (modify — wire policy)
- `backend/api/routers/auth.py` (modify — wire failed-login counter)
- `tests/api/test_rate_limit_security.py` (new)

---

## Story _security.11: Audit and tighten the existing 3-tier RBAC policy table

**ID:** _security.11
**Status:** planned
**Prerequisites:** []
**Unblocks:** [api.23, config.07]
**Estimated size:** M
**Spec:** docs/superpowers/specs/2026-05-08-auth-rbac-enforcement-design.md

**As a** security reviewer,
**I need** every router's `require_role` call audited against the design-spec policy table, with destructive endpoints uplifted to `admin` and missing guards added,
**so that** the 2026-05-08 default-deny audit is correct in spirit (the route walks pass) and in policy (the right role gates the right action).

### Current State
- `policy_registry.assert_complete` (`backend/api/middleware/policy_registry.py:40-`) walks routes and refuses startup when any non-`/auth/*`, non-`/health`, non-`/docs` route lacks a `require_role`; it does NOT verify the role chosen matches the design spec.
- `backend/api/routers/records.py` gates `POST /records/{knowledge_base_id}/files` and `POST /records/{knowledge_base_id}/push` at `analyst` only — there is no `admin`-only destructive path (deleting a feed's raw records, replaying), so any analyst can ingest unlimited raw_records.
- `backend/api/routers/knowledgebases.py` correctly gates `DELETE /knowledgebases/{id}` at `admin` but `DELETE /knowledgebases/{id}/documents/{doc_id}` is `analyst` — analysts can permanently delete documents with no admin gate.
- `backend/api/routers/cases.py` gates reads at `viewer` and create/promote/update/feedback at `analyst`; these routes now have explicit roles, but the expected-role table still needs a checked-in drift test.
- `backend/api/routers/workflows.py` gates list/detail at `viewer` and cancellation at `analyst`; the expected-role table still needs a checked-in drift test.
- `backend/api/routers/evidence.py:19` only declares one route at `viewer`; evidence mutations (when added) need a policy decision and the evidence router needs at least one `analyst` and one `admin` policy.
- The 2026-05-08 spec §4 contains the canonical policy table; no checked-in script enforces drift between code and table.

### Acceptance Criteria
- [ ] A new test `tests/api/test_policy_table_audit.py` declares the expected `{(method, path) → required_role}` mapping (sourced verbatim from `2026-05-08-auth-rbac-enforcement-design.md` §4 plus the gaps below) and walks `app.routes` asserting each match.
- [ ] `DELETE /knowledgebases/{kb_id}/documents/{document_id}` is uplifted to `admin` (currently `analyst` in `backend/api/routers/knowledgebases.py`).
- [ ] A new `DELETE /records/{feed}` admin-only route is added (or an existing destructive records path is uplifted) and the policy table reflects it.
- [ ] Evidence-pack mutation endpoints (per `api.NN` epics) receive explicit `analyst`/`admin` policies; the policy-audit test fails until they do.
- [x] Cases router mutations (`POST /cases`, `POST /cases/promote`, `PATCH /cases/{id}`, `POST /cases/{id}/feedback`) carry explicit `analyst` policies.
- [ ] A policy-table audit test verifies those case policies, workflow cancellation, and future mutations against the design-spec hierarchy.
- [ ] `policy_registry.assert_complete` is extended to optionally accept the expected-role map and fail startup when a route's policy disagrees (off by default, on under `CHILI_ENV=production`).
- [ ] `docs/superpowers/specs/2026-05-08-auth-rbac-enforcement-design.md` §4 is updated with the new rows for `records`/`cases`/`evidence`/`workflows` so the spec matches reality (or a follow-up spec amendment lands).

### Verification
- `cd backend && pytest tests/api/test_policy_table_audit.py tests/api/test_policy_registry.py --cov=api.middleware.policy_registry --cov-fail-under=85`
- `cd backend && pyright api/middleware/policy_registry.py`
- Manual: with `CHILI_ENV=production` and a single intentionally-wrong policy on a route, confirm the API refuses to start.

### Code touch points
- `backend/api/middleware/policy_registry.py` (modify)
- `backend/api/routers/knowledgebases.py` (modify)
- `backend/api/routers/records.py` (modify)
- `backend/api/routers/cases.py` (modify)
- `backend/api/routers/evidence.py` (modify)
- `backend/api/routers/workflows.py` (modify)
- `tests/api/test_policy_table_audit.py` (new)
- `docs/superpowers/specs/2026-05-08-auth-rbac-enforcement-design.md` (modify §4)

---

## Story _security.12: Operationalize the security checklist quarterly review and dependency-scan gating

**ID:** _security.12
**Status:** planned
**Prerequisites:** [_cicd.01]
**Unblocks:** [api.25]
**Estimated size:** S

**As a** Platform Security owner,
**I need** the quarterly review cadence and the pip-audit/npm audit gating thresholds codified as CI workflow files and a Findings register,
**so that** the security checklist is a living document with enforced cadence and an automated tripwire on HIGH/CRITICAL CVEs.

### Current State
- `docs/security_checklist.md` § "Review cadence" declares a quarterly cadence (Jan/Apr/Jul/Oct), names the owner ("Platform Security"), and reserves a "Findings" section — but the file's Findings list reads `_None yet — first scheduled review: 2026-07-26._` and no calendar/issue exists.
- The same file mentions `pip-audit` and `npm audit` as expected gates, but no CI workflow under `.github/workflows/` runs them with a failure threshold (no `pip-audit --strict` and no `npm audit --audit-level=high` step under this concern's ownership).
- The release/upgrade triggers ("new external integration, change to auth, new file-format parser, bump of `python-jose`/`httpx`") are listed but there is no automation that opens a tracking issue on those events.
- `_cicd.01` (per locked space) lands the baseline lint/type/test/build pipeline; this story bolts the security gates onto that pipeline.

### Acceptance Criteria
- [ ] A new `.github/workflows/security_audit.yml` runs on `push`, weekly cron, and on `dependabot` PRs; it runs `pip-audit --strict --ignore-vuln=` for any accepted-risk CVEs (file documents acceptances) and `npm audit --audit-level=high --omit=dev` against `chili_app/`.
- [ ] The workflow fails on any HIGH or CRITICAL vulnerability not present in `.github/security_accepted.yaml` (with rationale and review-by date per acceptance).
- [ ] A scheduled `.github/workflows/security_review_reminder.yml` runs on the 26th of Jan/Apr/Jul/Oct and opens a GitHub issue titled `Security checklist quarterly review — YYYY-QN` assigned to the Platform Security owner with a body referencing `docs/security_checklist.md` and the prior Findings entries.
- [ ] `docs/security_checklist.md` "Findings" section gains an enforced template (Date, Reviewer, Sections covered, Findings opened with backlog IDs, Sign-off) and the first entry stub for the 2026-07-26 review.
- [ ] `docs/security_checklist.md` "Last reviewed" line is moved to a YAML front-matter block so the consistency-check script can read it and warn if the review is overdue.
- [ ] An accompanying script `scripts/security_review_check.py` parses the front-matter and exits non-zero if the next review is overdue by more than 30 days; wired into `make check`.
- [ ] CLAUDE.md and `.github/copilot-instructions.md` reference the new workflow files in the "Authoritative References" / quality-gates section.

### Verification
- `cd backend && python ../scripts/security_review_check.py docs/security_checklist.md` (exits 0 when current, non-zero when overdue — covered by unit test in `tests/scripts/test_security_review_check.py`).
- `gh workflow view security_audit.yml` returns the workflow definition; a deliberate bump of a vulnerable `python-jose` version in a feature branch shows the workflow failing.
- `pytest tests/scripts/test_security_review_check.py --cov-fail-under=85`
- Manual: run `pip-audit --strict` and `npm audit --audit-level=high` locally and confirm clean output against current dependencies.

### Code touch points
- `.github/workflows/security_audit.yml` (new)
- `.github/workflows/security_review_reminder.yml` (new)
- `.github/security_accepted.yaml` (new)
- `scripts/security_review_check.py` (new)
- `tests/scripts/test_security_review_check.py` (new)
- `docs/security_checklist.md` (modify — front-matter + Findings template)
- `CLAUDE.md` (modify)
- `.github/copilot-instructions.md` (modify)
- `Makefile` (modify — `make check` includes the script)
