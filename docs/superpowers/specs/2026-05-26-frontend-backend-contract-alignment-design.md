# Frontend-Backend Contract Alignment Design

Date: 2026-05-26

## Goal

Make backend OpenAPI the source of truth for every frontend HTTP request and
response shape, while preserving chiliAI's domain-reconfigurable runtime model.
The frontend may build rich views and local view models, but it must not
hand-maintain wire DTOs that duplicate backend contracts.

This design intentionally locks the frontend to the backend API contract now.
That is acceptable because the backend gateway owns the HTTP boundary and the
frontend is part of the same product workspace. Future frontend views and
domain-specific functionality must extend the API contract first, regenerate
types second, then build UI behavior on top.

## Current Context

The repository already includes `openapi-typescript` and a frontend script:

```bash
npm run codegen:api
```

The script currently reads `http://localhost:8000/openapi.json` and writes
`chili_app/src/lib/api/schema.ts`, but the generated file is not present and
`chili_app/src/api/contracts.ts` remains manually maintained. This has already
allowed drift between backend Pydantic response models, frontend TypeScript
aliases, and dynamic validators.

Known drift examples motivating the change:

- RAG rich citations were added to backend and frontend contracts, but the
  streaming SSE citation payload omits fields from the declared response shape.
- Investigation relationships serialize backend `Relationship` objects with
  `metadata`, but the frontend `RuntimeRelationship` type omits `metadata`.
- Frontend structured-ingestion validation only partially mirrors backend
  record validation.
- Configured `max_query_length` and `max_rag_question_length` limits exist but
  are not consistently wired into route validators.

## Source Of Truth

Backend FastAPI OpenAPI is the source of truth for HTTP contracts.

Backend rules:

- Every frontend-consumed route must declare explicit Pydantic request and
  response models that appear in OpenAPI.
- Routes may adapt internal service models into API DTOs, but they must not
  expose accidental internal shapes unless those shapes are intended as public
  API contracts.
- Mixed response routes, such as normal JSON versus SSE streaming, must define
  separate documented payload contracts when the wire shapes differ.
- Domain configuration models remain backend-owned Pydantic models and are
  emitted through OpenAPI and `/config/domain`.

Frontend rules:

- Every HTTP request/response DTO used by `chili_app/src/api/*` must be imported
  from generated OpenAPI types, either directly or through aliases in
  `src/api/contracts.ts`.
- `src/api/contracts.ts` becomes a compatibility alias layer over
  `src/lib/api/schema.ts`. It must not define wire DTOs by hand.
- Feature components may define local UI/view-model types, but those types must
  be named and scoped as UI types and must be derived from generated API types
  through explicit adapter functions.
- Test mocks must satisfy generated API types. Mocks may be minimal, but they
  must still conform to the generated schema type used by the API wrapper.

## Domain Configuration Mechanics

Domain configuration is dynamic runtime data. The frontend must know the
structural shape of `DomainConfig`, but it must not hardcode domain-specific
entity types, relationship names, property names, record fields, capabilities,
or navigation pages.

Static typing boundary:

- Generated OpenAPI types describe the structure of `DomainConfig`,
  `RecordFeedConfig`, `PropertyDefinition`, and related configuration models.
- Domain-specific values inside those structures are runtime values and remain
  data-driven.
- The frontend may use string unions only for stable platform concepts such as
  HTTP response model names, alert statuses, or workflow statuses. It must not
  introduce static unions like `"claim" | "provider"` for domain entities.

Runtime behavior:

- Navigation, display labels, default entity type, role page access, record
  feeds, and validation constraints continue to come from `/config/domain` and
  `/config/features`.
- Unknown future capabilities and pages must be tolerated. Existing UI may
  ignore unsupported features, but it must not crash because a domain config
  contains extra fields or new capability keys.
- Structured-ingestion validators must read generated structural config types
  and evaluate constraints at runtime from `record_schema`.

## Architecture

### Backend Contract Export

Add a backend-owned OpenAPI export command that does not require a manually
running server. The export must create the FastAPI app with `CHILI_ENV=local`
and a default checked-in config, then write a deterministic JSON schema file.

Expected command shape:

```bash
uv run --project backend python -m tools.export_openapi --output chili_app/openapi.json
```

The exact module name can vary, but the export must be scriptable in CI and
must not depend on a developer manually starting `uvicorn`.

### Frontend Generated Schema

Generate and commit:

```text
chili_app/src/lib/api/schema.ts
```

`schema.ts` is generated output. Humans and agents must not edit it manually.
Changes flow from backend Pydantic models and routes through the OpenAPI export
and codegen commands.

### Frontend Compatibility Alias Layer

Rewrite `chili_app/src/api/contracts.ts` to alias generated schemas.

Example pattern:

```ts
import type { components } from '../lib/api/schema'

type Schemas = components['schemas']

export type ChatConversationResponse = Schemas['ChatConversationResponse']
export type RuntimeRelationship = Schemas['Relationship']
```

Only three categories are allowed in `contracts.ts`:

- Aliases to generated OpenAPI component schemas.
- Small helper aliases that compose generated schemas without changing wire
  fields.
- Clearly marked UI-only compatibility aliases during migration, each with a
  removal note and no use in API wrapper return types.

### API Wrappers

Keep the existing `src/api/*.ts` TanStack Query wrappers and `apiFetch` helper.
They provide useful ergonomic query keys, cache invalidation, and mutation
behavior.

Each wrapper must type its payloads and responses from `src/api/contracts.ts`,
which in turn aliases generated OpenAPI types. Wrappers must not introduce
parallel inline DTO shapes.

### UI Adapters

When a component needs a different shape from the wire contract, define an
adapter near the consuming feature.

Adapter rules:

- Input type is generated API type.
- Output type is a local UI type.
- Adapter must copy every API field that the UI type claims to preserve.
- Dropped fields must be intentional and documented when there is a realistic
  chance a downstream component might need them.

This prevents comments claiming structural compatibility while silently dropping
fields such as relationship `metadata`.

## Guardrails

These guardrails are intentionally strict. They are designed to stop drift by
default, including drift introduced by coding agents.

### Repository Rules

Add or update contributor instructions in the repo so agents see these rules
before editing:

- Do not hand-write frontend API DTOs.
- Do not edit `src/lib/api/schema.ts` manually.
- Do not add `type FooResponse = { ... }` or `interface FooRequest { ... }`
  under `chili_app/src/api/` unless it aliases generated OpenAPI schemas.
- Do not use `src/types/api.ts` for HTTP wire contracts. Existing leftovers
  must be migrated or clearly marked as UI-only.
- When adding or changing a backend route consumed by the frontend, update the
  Pydantic request/response model first, regenerate OpenAPI types, and update
  wrappers/components afterward.
- If TypeScript fails after codegen, fix the backend contract, alias, adapter,
  or component. Do not patch around generated types with `as any`.

### Generated File Header

The generated `schema.ts` must include a clear header:

```ts
// Generated from backend OpenAPI. Do not edit by hand.
// Run: npm run codegen:api
```

If the generator does not support this directly, add a small post-processing
step that prepends the comment deterministically.

### ESLint / Static Checks

Add lightweight static checks that fail fast:

- Reject manual exported object DTOs in `chili_app/src/api/contracts.ts` unless
  the line aliases `Schemas[...]` or another generated type.
- Reject imports from `chili_app/src/types/api.ts` in production API/client
  modules.
- Reject `as any` and `Record<string, any>` in `chili_app/src/api/`.
- Require `schema.ts` imports to flow through `src/api/contracts.ts` for app
  code, except in the contracts alias file itself.

These checks start as a small repository script using text/AST scanning. Moving
them into ESLint later is allowed only if the same failure cases remain covered
in CI.

### CI Drift Gate

CI must fail when generated frontend schema is stale:

```bash
uv run --project backend python -m tools.export_openapi --output chili_app/openapi.json
cd chili_app
npm run codegen:api
git diff --exit-code -- src/lib/api/schema.ts openapi.json src/api/contracts.ts
```

The final file list can be tuned, but the important invariant is this:

> A PR that changes backend OpenAPI without regenerating committed frontend
> contract artifacts must fail.

### Backend OpenAPI Completeness Gate

Backend tests must assert that frontend-consumed routes have response models.
Frontend-consumed routes that are part of generated clients or external docs
must also have stable operation IDs. Routes that remain internal to the current
hand-written wrapper layer may defer operation ID stabilization, but they still
must expose response schemas.

Minimum checks:

- Every protected frontend route appears in `/openapi.json`.
- Every JSON route consumed by the frontend has a non-empty response schema.
- Routes that intentionally stream or return non-JSON payloads are explicitly
  allowlisted and documented.
- Domain config schema appears and includes core runtime fields:
  `capabilities`, `validation`, `records`, `ui`, and `alerts`.

### Contract Alias Coverage Gate

Add a TypeScript test or script that validates `src/api/contracts.ts` exports
the expected aliases for all API modules. This is a migration guard rather than
business logic.

Example invariant:

- Every type imported by `src/api/*.ts` from `./contracts` resolves to a
  generated schema alias or an approved UI-only migration alias.

### Validator Parity Tests

Add focused tests for runtime validators that cannot be solved by static
OpenAPI types alone:

- Frontend structured-ingestion validation matches backend acceptance for:
  required fields, integer, decimal, boolean, date coercion, enum values,
  min/max numeric bounds, min/max lengths, pattern matching, optional empty
  typed fields, and `allow_extra_fields`.
- Query and RAG message length limits are enforced by actual routes, not just
  helper tests.
- Streaming RAG final-event citation payloads either match a documented SSE
  schema or are tested against a separate streaming type.
- Investigation relationship payloads preserve fields claimed by frontend UI
  adapters, including `metadata`.

### Agent Checklist

Any agent changing frontend/backend API behavior must complete this checklist
before finishing:

1. Did I change a backend request/response model or route shape?
2. If yes, did I regenerate OpenAPI and frontend schema?
3. Did I avoid hand-writing frontend wire DTOs?
4. Did I update or add adapter code for UI-only transformations?
5. Did I add parity coverage for validators or dynamic domain behavior?
6. Did `git diff` show generated schema changes only where expected?

This checklist must appear in contributor docs or agent instructions, not
only in this design document.

## Migration Plan

1. Add backend OpenAPI export script.
2. Generate and commit `chili_app/openapi.json` or another stable schema
   snapshot location if offline codegen needs it.
3. Generate and commit `chili_app/src/lib/api/schema.ts`.
4. Rewrite `chili_app/src/api/contracts.ts` as generated schema aliases.
5. Fix immediate type errors by updating aliases, feature adapters, and tests.
6. Add route/query validation fixes for known gaps:
   RAG question length, investigation search length, streaming citation shape,
   relationship metadata, and record validator parity.
7. Add CI drift gate.
8. Add static guardrail script and wire it into frontend CI.
9. Update README/contributor docs with the contract workflow and agent
   checklist.
10. Remove or demote legacy `src/types/api.ts` wire-contract usage.

## Error Handling

Generated types do not replace runtime error handling. API wrappers continue to
use `apiErrorMessage()` and existing fetch behavior.

Backend validation errors must remain FastAPI/Pydantic errors where possible.
When custom validation is needed, routes must return consistent HTTP status
codes and `detail` messages that the frontend can display.

Frontend validators must be treated as preflight UX, not security boundaries.
Backend validators remain authoritative.

## Testing

Backend:

- Existing OpenAPI smoke tests remain.
- Add OpenAPI completeness tests for response schemas and route allowlists.
- Add route-level tests for query length and RAG question length enforcement.
- Add tests for any dedicated SSE event schema.

Frontend:

- Run `npm run codegen:api`.
- Run TypeScript build against generated aliases.
- Run ingestion validator parity tests.
- Run API wrapper unit tests using generated response/request aliases.

CI:

- Run backend tests.
- Export OpenAPI.
- Generate frontend schema.
- Fail on generated artifact drift.
- Run static guardrail script.
- Run frontend lint, typecheck, tests, and build.

## Non-Goals

- Do not generate a full runtime API client in this increment.
- Do not statically type domain-specific entity names or record fields.
- Do not replace TanStack Query wrappers.
- Do not make the frontend accept arbitrary backend contract changes silently;
  lockstep failure is the intended behavior.
- Do not move internal service models directly into frontend code unless the API
  boundary explicitly exposes them.

## Decision

The approved direction is lockstep generated OpenAPI types with strong CI,
repository, and agent guardrails. Domain configuration remains dynamic runtime
data, with generated types describing structure rather than domain-specific
values.
