# chiliAI Security Audit Checklist

> Owner: Platform Security · Last reviewed: 2026-04-27 · Cadence: **quarterly**
> (Jan / Apr / Jul / Oct), plus ad-hoc when a new external integration lands.

This checklist maps OWASP Top 10 (2021) categories to specific chiliAI
mitigations and the modules / story IDs that implement them. It is intentionally
*not* generic — each item names a file, configuration, or story so reviewers can
trace the control to code.

## How to use this document

1. At each quarterly review, walk through every OWASP item below.
2. For each row, confirm the control still exists (run the linked tests / read
   the linked file) and capture deviations in the **Findings** section.
3. Update the *Last reviewed* date at the top once findings are tracked in the
   backlog.

---

## Dependency vulnerability scanning (continuous)

| Layer    | Tool                              | CI step                            | Failure threshold |
|----------|-----------------------------------|------------------------------------|-------------------|
| Backend  | `pip-audit` (PyPA)                | `.github/workflows/ci.yml` backend | HIGH or CRITICAL  |
| Frontend | `npm audit --audit-level=high`    | `.github/workflows/ci.yml` frontend| HIGH or CRITICAL  |

LOW / MODERATE findings are tracked but do not fail the build. Suppressions
require a documented justification in this file.

---

## OWASP Top 10 (2021) — chiliAI mitigations

### A01:2021 — Broken Access Control

- **Authentication.** When auth is enabled, protected HTTP routes require a
  `chiliai_session` cookie or Bearer token. Auth middleware lives in
  `backend/api/middleware/auth.py`; `/auth/*`, docs/openapi, metrics, and
  health endpoints are intentionally exempt. Auth-disabled development runs as
  an anonymous `viewer`.
- **RBAC.** Route policy is enforced per-router via FastAPI
  `Depends(require_role(...))` using `viewer`, `analyst`, and `admin`.
  Reads/exploration are generally `viewer`; mutations are generally
  `analyst` or `admin`; configuration and destructive admin paths require
  `admin`.
- **Tenant isolation.** Every persisted artifact is keyed by
  `knowledge_base_id`. Graph queries filter on `knowledge_base_id` at the
  protocol boundary (`graph/protocols.py`). Cross-KB reads are rejected at the
  service layer.
- **Tested by.** `tests/api/test_*_router.py` (401/403 paths), plus the e2e
  suite that validates the public surface end-to-end
  (`tests/e2e/test_full_pipeline.py`).

### A02:2021 — Cryptographic Failures

- **TLS.** Production traffic terminates at the ingress / nginx edge (see
  `infra/`). The Python services accept only loopback HTTP inside the cluster.
- **Secrets at rest.** Credentials are read from environment variables only;
  see the `*_env_var` fields on `config/schema.py` (`auth_env_var`,
  `api_key_env_var`, `credentials_env_var`). No secret values are stored in
  YAML config or committed to the repo.
- **Hashing.** Where password hashing applies (future SSO bridge), use
  `argon2-cffi` defaults — never MD5/SHA1.

### A03:2021 — Injection

- **Input validation.** All API request bodies are Pydantic v2 models with
  field-level constraints; query params use `fastapi.Query` with bounds
  (story **E10-S10**). File uploads are parsed by content-type-aware parsers
  (`ingestion/parsers/`) that never `eval`/`exec` input.
- **Graph queries.** Cypher is composed only via the parameterised driver API
  in `graph/adapters/neo4j_adapter.py`. No string concatenation builds a query
  body. The in-memory adapter mirrors the same protocol so tests catch
  regressions.
- **Vector queries.** Qdrant filters are built as typed `FieldCondition`
  objects (`vectorstore/adapters/qdrant_adapter.py`) — no raw payload strings.
- **LLM prompt injection.** RAG prompts wrap retrieved context inside fenced
  delimiters and instruct the model to ignore embedded instructions
  (`rag/service.py`). System prompts come from validated config templates.

### A04:2021 — Insecure Design

- **Protocol-first architecture.** Every external system is accessed through a
  `Protocol` in `<module>/protocols.py`. This means tests run against the
  in-memory adapter and production swaps in real backends without changing
  business logic — see `CLAUDE.md` § Architecture Hard Rules.
- **Threat-model surface.** The API gateway is the only public entry; the
  worker consumes from Redis Streams only. There is no direct database
  exposure to the frontend.

### A05:2021 — Security Misconfiguration

- **Logging hygiene.** All logs go through `structlog` with PII-stripping
  processors (story **E10-S08**). No raw request bodies, no API keys, no JWT
  contents. Correlation IDs are emitted; payloads are not.
- **CORS.** Allowed origins are loaded from the `ALLOWED_ORIGINS` env var (no
  `*` in production); see the `TODO(production)` in `api/app.py` and
  story **E10-S09** which replaces the dev-only allowlist.
- **Default-deny config.** `config/schema.py` ships with conservative defaults
  (in-memory adapters, no remote fetches). Optional features (Neo4j, Qdrant,
  OpenAI) require explicit configuration to enable.
- **No debug endpoints in prod.** FastAPI's `/docs` and `/redoc` are gated by
  the `CHILI_ENABLE_DOCS` env var.

### A06:2021 — Vulnerable and Outdated Components

- **Continuous scanning.** `pip-audit` and `npm audit` run on every PR.
- **Pinned ranges.** `backend/pyproject.toml` and `chili_app/package.json` use
  bounded version ranges for every direct dependency.
- **Optional extras isolated.** Production-only adapters (Neo4j, Qdrant, S3,
  OpenAI, Anthropic) live behind extras so the base install surface is small.

### A07:2021 — Identification and Authentication Failures

- **JWT validation.** Tokens are verified against the configured JWKS endpoint
  with audience and issuer checks (story **E10-S06**). Expiry, `nbf`, and
  signature failures all return 401.
- **No long-lived API keys.** External credentials (OpenAI, Anthropic, S3) are
  loaded from env vars at process start and never logged.
- **WebSocket auth.** `api/routers/ws.py` rejects connections without a valid
  bearer token in the `Authorization` header on upgrade.

### A08:2021 — Software and Data Integrity Failures

- **Event audit trail.** Every event in `events/types.py` carries
  `correlation_id`, `event_id`, and `created_at`. Stories **E1-S01** /
  **E1-S02** added `created_at` / `updated_at` / `version` to `Entity` and
  `Relationship` so graph upserts support optimistic concurrency.
- **DLQ.** Handlers that exhaust retries route the original event to the DLQ
  via `event_bus.publish_to_dlq()` (`agent/coordinator.py`). DLQ entries
  preserve the original payload, traceback, and retry count for forensics.
- **Build provenance.** CI uploads `coverage.xml` and `dist/` as artifacts so
  releases are reproducible from the workflow run.

### A09:2021 — Security Logging and Monitoring Failures

- **Correlation IDs.** Every event carries `correlation_id`; the FastAPI
  middleware (story **E10-S09**) propagates it as a response header so client
  reports can be tied to server logs.
- **Structured logs.** `structlog` emits JSON to stdout in prod for ingest by
  the platform log aggregator. Failure paths log at WARNING/ERROR with the
  event type and correlation ID.
- **Metrics.** `prometheus-client` exposes pipeline counters and histograms;
  alerting on the DLQ rate is the primary integrity signal.

### A10:2021 — Server-Side Request Forgery (SSRF)

- **URL validation.** The remote document fetcher
  (`ingestion/parsers/remote.py`) restricts schemes to `https://`, rejects
  RFC1918 / loopback / link-local hosts after DNS resolution, and enforces a
  configured allow-list of domains (story **E10-S11**).
- **No user-controlled webhooks.** The platform never POSTs to a URL supplied
  by an end user without an admin-curated allow-list.
- **LLM tool use.** When LLM tool-calling is wired (future work), tool URLs
  are constants in code; user input never selects an outbound endpoint.

---

## Review cadence and ownership

- **Cadence.** Quarterly (Jan / Apr / Jul / Oct), plus immediately when any of
  the following land:
  - A new external integration (vendor SDK, network endpoint, queue topic).
  - A change to authentication / authorisation logic.
  - A new file-format parser or remote-fetch path.
  - A bump of `python-jose`, `httpx`, or any auth-adjacent dependency.
- **Owner.** Platform Security (escalation: Platform Lead).
- **Output.** Each review produces an entry under **Findings** below and an
  updated *Last reviewed* date at the top of this file. Open findings flow
  into the backlog with priority P0/P1.

## Findings

_None yet — first scheduled review: 2026-07-26._
