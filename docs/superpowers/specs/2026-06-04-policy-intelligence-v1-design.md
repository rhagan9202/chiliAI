# Policy Intelligence v1 — Design (BL-011)

> Status: **Approved** (2026-06-04) · Sprint: **2026-24** · Requirements: REQ-POLICY-001..004 · Drift: D-15
> Backlog: [docs/project/planning/backlog.md](../../project/planning/backlog.md) BL-011 · Sprint plan: [docs/project/planning/sprints/2026-24.md](../../project/planning/sprints/2026-24.md)

## 1. Problem & current state

The product ships a **Policy Intelligence** page, a backend `/policy/gaps` router, and a typed client — but the data is entirely seeded (`ApiState._seed_policy_gaps`), the domain config has no policy-rule surface, and nothing generates items. The existing surface models a **Policy *Gap*** (an analytical aggregation with a brief-builder), which is a different concept from what REQ-POLICY requires: a **Policy *Item*** queue of discrete, rule-fired review items that analysts triage (accept / reject / defer / escalate-to-case) with persisted disposition, sourced from domain-configured rule packs and scoped by `knowledge_base_id`.

This design makes Policy Intelligence real and durable, and **reconciles the two concepts by replacing gaps with items** — there must be exactly one policy surface (no parallel gaps + items).

### Verified predecessor facts (2026-06-04)
- Frontend: `chili_app/src/pages/PolicyIntelligencePage.tsx`, `chili_app/src/api/policy.ts`, tests in `chili_app/src/pages/__tests__/PolicyIntelligencePage.test.tsx` and `chili_app/src/api/__tests__/policy.test.ts`. Single router route (`router.tsx` → `path: 'policy'`). No supervisor dashboard consumes the gap contracts directly.
- Backend: `backend/api/routers/policy.py` (`GET /policy/gaps`, `GET /policy/gaps/{id}`, `GET /policy/gaps/{id}/cases`, `POST /policy/briefs`); payload builders in `backend/api/dependencies.py` + `backend/api/contracts.py`; seed in `backend/api/state.py::_seed_policy_gaps` (~L790).
- Config: `backend/config/schema.py` has no `policy_rules` / `PolicyRulePack`.
- Cases promote machinery (BL-010) already shipped: `backend/cases/` + `POST /cases/promote`; reused here for escalate-to-case.

## 2. Decisions (settled during brainstorming, 2026-06-04)

| # | Decision | Choice |
|---|---|---|
| D-RECONCILE | Reconcile gaps vs. items | **Items replace gaps.** `PolicyItem` is canonical; `/policy/gaps` + `PolicyGap*` contracts + `_seed_policy_gaps` are removed. Brief-gen is preserved as an optional per-item action. |
| D-RULE | Rule expressiveness | **Typed predicate rules.** Each rule = target + a single bounded predicate (fixed operator set) against config-supplied thresholds. No Turing-complete engine. |
| D-EVAL | Evaluation lifecycle | **Reactive + throttled upsert.** Worker evaluates a KB's rule packs on `RecordsIngested` + metrics-recompute, reusing the per-KB throttle; items keyed by `(kb_id, rule_id, target_ref)`; triaged items never reopen. |
| D-PERSIST | Persistence | Durable repo following the BL-010 Cases pattern: protocol + in-memory + Postgres adapter + Alembic migration. |
| D-ESCALATE | Escalate-to-case | `triage(action=escalate)` reuses the generalized `CaseService` promote machinery; resulting `case_id` is stored on the item disposition. |
| D-CONFIG | Config field | `DomainConfig.policy_rules` is **additive/optional** (default `[]`); both shipped default configs still validate. |

### v1 non-goals (explicit)
- No auto-resolution of items whose match no longer holds (a de-matched open item persists; future story).
- **One predicate per rule** — no boolean composition (`AND`/`OR`) across predicates in v1. Multiple rules approximate conjunction via separate items.
- No rule-authoring UI — rules are authored in domain config (config-write is BL-016, a separate sprint).
- Metric-target predicates read existing computed metrics only; no new metrics introduced.

## 3. Architecture & module boundary

New backend module `backend/policy/`, parallel to `backend/cases/`, reachable only through the three allowed cross-module paths (API gateway, worker coordinator, shared contracts). Rule *definitions* live in `config/` (`DomainConfig.policy_rules`), never in `policy/` — rules are configured, the evaluator is generic (hard rules #3/#4).

```
backend/policy/
  __init__.py
  models.py           # internal: PolicyItem, PolicyDisposition, PolicyItemStatus
  service_models.py   # API DTOs: PolicyItemSummary, PolicyItemDetail, TriageRequest, ...
  protocols.py        # PolicyItemRepository (Protocol)
  service.py          # PolicyService (orchestration; triage; escalate)
  evaluation.py       # pure rule evaluator: (rules, kb_state) -> list[PolicyMatch]
  exceptions.py
  adapters/
    in_memory.py      # PolicyItemRepository in-memory impl (tests / make dev)
    postgres.py       # PolicyItemRepository Postgres impl (real path)
```

Rule-pack/predicate Pydantic types live under `config/` (with the rest of `DomainConfig`), exported via `shared/` only if both API and worker need the literal types; the evaluator imports them from config.

## 4. Domain model

```python
class PolicyItemStatus(StrEnum):
    OPEN = "open"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DEFERRED = "deferred"
    ESCALATED = "escalated"

class PolicyDisposition(BaseModel):
    action: Literal["accept", "reject", "defer", "escalate"]
    actor: str                 # subject from the auth principal
    note: str | None
    decided_at: datetime
    case_id: str | None        # set only when action == "escalate"

class PolicyCitation(BaseModel):
    citation_id: str
    title: str
    source_ref: str            # policy/document reference from the rule
    excerpt: str | None

class PolicyItem(BaseModel):
    id: str
    knowledge_base_id: str
    rule_id: str
    rule_pack_id: str
    target_kind: Literal["entity", "alert", "metric"]
    target_ref: str            # entity_id | alert_id | metric key
    title: str                 # rendered from rule.title_template + match context
    severity: Literal["medium", "high", "critical"]
    matched_fields: dict[str, str | float | int | bool]   # the snapshot that triggered the match
    citations: list[PolicyCitation]
    status: PolicyItemStatus
    disposition: PolicyDisposition | None
    created_at: datetime
    updated_at: datetime
```

**Natural identity (unique):** `(knowledge_base_id, rule_id, target_ref)`.

**Lifecycle:**
- A match **upserts** by natural key. New → create `open`. Existing & `open` → refresh `matched_fields` + `updated_at`. Existing & disposed (any non-`open` status) → **left untouched** (never reopened).
- `triage` transitions `open → accepted|rejected|deferred|escalated`, writes the disposition, and is idempotent-safe (triaging an already-disposed item is a 409).

## 5. Config schema (additive)

In `backend/config/schema.py`:

```python
class PolicyPredicateValue(BaseModel):
    # exactly one of literal / config_ref
    literal: str | float | int | bool | None = None
    config_ref: str | None = None     # resolves against a thresholds map on the pack/config

class PolicyPredicate(BaseModel):
    field: str                         # "properties.<name>" | "risk_score" | "metric.<name>"
    op: Literal["eq", "neq", "gt", "gte", "lt", "lte", "in", "not_in"]
    value: PolicyPredicateValue

class PolicyCitationRef(BaseModel):
    citation_id: str
    title: str
    source_ref: str
    excerpt: str | None = None

class PolicyRule(BaseModel):
    id: str
    title_template: str                # e.g. "Claim {entity_id} exceeds billing threshold"
    severity: Literal["medium", "high", "critical"]
    target_kind: Literal["entity", "alert", "metric"]
    target_selector: dict[str, str]    # e.g. {"entity_type": "claim"}
    predicate: PolicyPredicate
    citations: list[PolicyCitationRef] = []

class PolicyRulePack(BaseModel):
    id: str
    name: str
    description: str | None = None
    thresholds: dict[str, str | float | int | bool] = {}   # config_ref targets
    rules: list[PolicyRule]

class DomainConfig(BaseModel):
    ...
    policy_rules: list[PolicyRulePack] = []                 # additive, optional
```

- Medicare default config (`config/defaults/medicare_fraud.yaml`) ships 1–2 example packs (e.g. a billing-threshold rule and a risk-band rule).
- The food-supply default config may omit `policy_rules` entirely.
- A loader test asserts **both** default configs validate with and without the field present.

## 6. API contract

All routes KB-scoped via `?knowledge_base_id=`. RBAC: reads `require_role("viewer")`, triage `require_role("analyst")` (matches the existing brief-create role).

| Method & path | Purpose | Response |
|---|---|---|
| `GET /policy/items?knowledge_base_id=&status=` | List items, optional status filter | `PolicyItemListResponse { items: list[PolicyItemSummary] }` |
| `GET /policy/items/{id}?knowledge_base_id=` | Item detail (match context, citations, disposition) | `PolicyItemDetailResponse` (404 if absent/wrong KB) |
| `POST /policy/items/{id}/triage` | Triage; body `{action, note?}`. `escalate` also creates+links a case | `PolicyItemDetailResponse` (updated); 409 if already disposed |
| `POST /policy/items/{id}/brief` *(retained, optional)* | Generate a brief for one item | `PolicyBriefResponse` |

**Removed** (this is the BL-011-owned policy-gaps de-seed; the sprint plan assigns it here, not to BL-012): `GET /policy/gaps`, `GET /policy/gaps/{id}`, `GET /policy/gaps/{id}/cases`, `POST /policy/briefs`, the `PolicyGap*` Pydantic contracts, their `api/dependencies.py` payload builders, and `ApiState._seed_policy_gaps`.

Frontend-consumed change → follow the generated-contract workflow: update Pydantic models → `python -m tools.export_openapi --output chili_app/openapi.json` → `cd chili_app && npm run codegen:api` → update `api/policy.ts` + page. No hand-written wire DTOs.

## 7. Worker evaluation (reactive + throttled)

A new worker stage in the coordinator:
1. Consumes the existing `RecordsIngestedEvent` and the metrics-recompute signal for a KB.
2. Loads `DomainConfig.policy_rules` for the active config; loads the KB's evaluable state (entities of the selected `entity_type`, alerts, computed metrics) via the existing graph/monitoring/metrics read paths.
3. Calls `evaluation.evaluate(rules, kb_state) -> list[PolicyMatch]` — a **pure function** (no I/O), independently unit-testable.
4. Upserts a `PolicyItem` per match by natural key via `PolicyService` (open-create / open-refresh / disposed-skip).
5. Reuses the per-KB throttle (the Plan C `MetricsRecomputeThrottle` precedent) so re-ingest storms don't thrash evaluation. **No new scheduler/cron.**

`evaluation.evaluate` resolves each predicate's `field` against the target snapshot (`properties.*` from entity properties, `risk_score`, `metric.<name>`), applies `op` against the resolved `value` (`literal` or `config_ref` → `thresholds`), and renders `title_template` with the match context. `in`/`not_in` take list values; type coercion mirrors `records/validation.py` conventions.

## 8. Escalate-to-case

`PolicyService.triage(item, action="escalate", ...)`:
1. Builds a **policy-item origin** payload (rule id, target entity/ref, citations, `matched_fields`, KB).
2. Calls the generalized `CaseService` promote path (BL-010). Minimal generalization: the promote input gains a policy-item origin variant alongside the existing alert origin; the case captures the item as its initiating context.
3. Stores the returned `case_id` on `PolicyDisposition.case_id`, flips the item to `escalated`.

The case lands KB-scoped on the Case Management surface, satisfying REQ-POLICY-002's escalate action against the shipped Cases vertical.

## 9. Frontend

`PolicyIntelligencePage` rebuilt around the item queue (re-using existing UI primitives — `Card`, `Chip`, `SectionHeader`, `EmptyState`, list-item buttons):
- **List:** KB-threaded, status filter (open/accepted/rejected/deferred/escalated), severity chips, rule/title, updated timestamp.
- **Detail:** match context (`matched_fields`), citations, the affected entity (link-through to entity detail), disposition state.
- **Triage action bar:** accept / reject / defer / escalate, each with an optional note; optimistic update + toast; escalate navigates to / links the created case.
- **Brief builder:** retained as a collapsed per-item action (`POST /policy/items/{id}/brief`).

Client (`api/policy.ts`) and tests (`PolicyIntelligencePage.test.tsx`, `api/policy.test.ts`) rewritten for the items contract. Playwright e2e `policy-triage.spec.ts` on the full running stack: seed/ingest a KB so a rule fires → see the item → triage it → escalate → assert the case appears KB-scoped. No axe regressions on the page.

## 10. Persistence

`backend/database/migrations/versions/0003_policy.py` (next after the cases `0002`):
- `policy_items` table: columns mirroring `PolicyItem`; **unique constraint** on `(knowledge_base_id, rule_id, target_ref)`; index on `(knowledge_base_id, status)` for the filtered list query.
- Disposition stored as columns on `policy_items` (action/actor/note/decided_at/case_id, nullable) — a single-row item carries at most one disposition, so no separate table is needed (YAGNI).
- In-memory adapter mirrors the same upsert + no-reopen semantics for tests and `make dev` without Postgres; Postgres adapter uses `INSERT ... ON CONFLICT (knowledge_base_id, rule_id, target_ref)` to implement open-create / open-refresh, with a guard that `ON CONFLICT` does **not** touch a disposed row.

## 11. Testing & quality gates

- **Unit:** `evaluation.evaluate` (every operator, each `target_kind`, `config_ref` resolution, title rendering, no-match); `PolicyService` upsert lifecycle (create / refresh-open / skip-disposed) and triage transitions incl. 409-on-disposed; both adapters against a shared contract test; config schema load (both defaults, field present/absent).
- **Integration:** Postgres adapter against live TimescaleDB (natural-key conflict, disposed-row guard); worker stage emits items on `RecordsIngested` end-to-end.
- **Frontend:** Vitest for client + page (list/detail/triage/escalate, empty + error states); Playwright `policy-triage.spec.ts` on the full stack.
- **Gates:** `pyright --strict` clean across `policy/`, touched `config/`, `api/`, worker; pytest ≥ 85% for affected packages; ESLint clean + TS strict; generated contracts regenerated (no drift); axe clean on the page.

## 12. Acceptance criteria (BL-011)

- [ ] `DomainConfig.policy_rules: list[PolicyRulePack]` added (additive); both default configs validate with and without it.
- [ ] Worker generates durable, KB-scoped `PolicyItem`s from configured rule packs (no `_seed_policy_gaps`), reactively + throttled, idempotent by natural key, never reopening disposed items.
- [ ] `GET /policy/items`, `GET /policy/items/{id}`, `POST /policy/items/{id}/triage` (accept/reject/defer/escalate) exist, KB-scoped; disposition persists across API + worker.
- [ ] **D-RECONCILE:** `/policy/gaps` + `PolicyGap*` contracts + `_seed_policy_gaps` removed; exactly one policy surface remains.
- [ ] escalate-to-case reuses the shipped `POST /cases/promote` machinery; `case_id` linked on the item.
- [ ] `PolicyIntelligencePage` lists items, supports all four triage actions, KB-threaded; brief-builder retained as a per-item action.
- [ ] Generated contracts regenerated; no hand-written wire DTOs.
- [ ] pyright --strict clean; pytest ≥ 85% for touched backend packages; ESLint clean; Playwright `policy-triage.spec.ts` (incl. escalate→case) green on the full stack; no axe regressions.
- [ ] D-15 → `RESOLVED` in the backlog; BL-011 → `done` citing Sprint 2026-24.

## 13. Open questions / risks

- **R-01 (sprint):** reconciliation + config + worker may exceed 8 SP. Mitigation: land the model + config schema + repository (stable contract) first; the worker evaluator and page rewire integrate against the frozen shape; if week-2 burndown lags, the brief-builder retention (§6 optional route + §9) is the first cut.
- **Promote generalization:** generalizing the cases promote payload to accept a policy-item origin must not regress the alert→case path — covered by re-running the BL-010 promote tests plus the new policy escalate test.
- **Metric-target predicates** depend on metrics already being computed for the KB; if absent, those rules simply don't match (documented, not an error).
