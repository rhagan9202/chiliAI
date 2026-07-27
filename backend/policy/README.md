# policy

Durable, KB-scoped **policy intelligence** (BL-011). Rule packs defined in the domain configuration are evaluated against KB state; each match produces a persisted `PolicyItem` that analysts triage (accept / reject / defer / escalate-to-case). This module replaces the old seeded "policy gap" surface (`/policy/gaps`, `_seed_policy_gaps`, `PolicyGap*` / `PolicyBrief*` contracts), which have been removed.

> **Authoring rule packs:** see [`docs/adding_rulesets.md`](../../docs/adding_rulesets.md) — how the worker-vs-dev-seed paths differ, the `PolicyRulePack` schema, and a worked example (the demo packs shipped in `medicare_fraud_cms_desynpuf.yaml`).

## Layout

| File | Responsibility |
|------|----------------|
| `models.py` | `PolicyItem`, `PolicyDisposition`, `PolicyCitation` domain models; `PolicyItemStatus`, `PolicySeverity`, `PolicyTargetKind`, `TriageAction` literals; `ACTION_TO_STATUS` mapping. |
| `evaluation.py` | Pure `evaluate(rule_packs, state) -> list[PolicyMatch]` - no I/O. Receives freshly-stored entities + (throttled) graph metrics; returns one `PolicyMatch` per rule hit. |
| `service.py` | `PolicyService` - `record_match(...)` upserts new items; `triage(...)` records analyst disposition; `link_case(...)` attaches an escalated case id; `get` / `list` / `count_by_status` delegate to the repository. |
| `exceptions.py` | `PolicyError`, `PolicyPersistenceError`, `PolicyItemNotFoundError`, `PolicyItemAlreadyTriagedError`. |
| `adapters/protocols.py` | `PolicyItemRepository` protocol - `upsert / get / list / count_by_status / update / delete_by_kb`. |
| `adapters/in_memory.py` | `InMemoryPolicyItemRepository` (dict keyed by natural key) for tests / local dev. |
| `adapters/postgres.py` | `PostgresPolicyItemRepository` over `database.ConnectionProvider`; disposition stored as jsonb; migration `0003_policy`. |

## Natural identity and lifecycle

Every policy item is uniquely identified by the **natural key** `(knowledge_base_id, rule_id, target_ref)`.

- `upsert`: if no item exists, inserts as `open`; if the item is already `open`, refreshes it in place; if the item has already been disposed (status ≠ `open`), leaves it untouched. **Disposed items never reopen.**
- `triage`: transitions an `open` item to one of `accepted`, `rejected`, `deferred`, or `escalated`. Raises `PolicyItemAlreadyTriagedError` if the item is not `open`.

```
           ┌──────────────────────────────────────────┐
           │              open (initial)               │
           └────────┬──────────┬──────────┬────────────┘
                    │ accept   │ reject   │ defer   │ escalate
                    ▼          ▼          ▼         ▼
               accepted   rejected   deferred  escalated
                    (terminal - upsert leaves disposed items untouched)
```

## evaluate contract

`evaluation.evaluate(rule_packs, state)` is a pure function (no I/O, no side effects):

```python
class PolicyEvalState(BaseModel):
    entities: list[Entity]
    alerts: list[Alert]
    metrics: dict[str, float]

def evaluate(rule_packs: list[PolicyRulePack], state: PolicyEvalState) -> list[PolicyMatch]: ...
```

Each `PolicyMatch` carries `rule_id`, `rule_pack_id`, `target_kind`, `target_ref`, `title`, `severity`, `matched_fields`, and `citations`. The worker passes each match to `PolicyService.record_match(...)` which upserts it as a durable `PolicyItem`.

## Worker fold-in (D-EVAL-IMPL)

**Deviation D-EVAL-IMPL**: policy evaluation is folded directly into `handle_records_ingested` in `backend/agent/coordinator.py` rather than running as a standalone pipeline stage. This makes evaluation best-effort (failures are logged, not fatal) and throttles metrics-based rules using the same `MetricsRecomputeThrottle` that governs Flow 2. Alert-target rules (`target_kind == "alert"`) are **defined but not yet evaluated** in v1 — `_iter_targets` returns an empty list for alert targets; this is a documented non-goal.

## Escalate-to-case (D-ESCALATE-IMPL)

**Deviation D-ESCALATE-IMPL**: the `escalate` triage action is orchestrated directly in `api/routers/policy.py` via `CaseService.create(...)` with an additive `timeline` parameter. It does not reuse the `POST /cases/promote` alert->case promotion path; the two paths remain independent. The router triages first, creates the case only after that succeeds, then calls `PolicyService.link_case(...)` so the disposition records the created `case_id`.

## API surface

Routed by `api/routers/policy.py`, all routes require `?knowledge_base_id=`:

| Method | Path | Role | Notes |
|--------|------|------|-------|
| `GET` | `/policy/items` | `viewer` | List KB-scoped items; paginated. `?status=` **repeats** (`?status=open&status=escalated`) and matches any of the given values, so "open **or** escalated" is one request; a single `?status=open` still parses to a one-element list, so the pre-multi-select form keeps working. `?q=` is a case-insensitive substring match on the title (LIKE wildcards in the term are escaped, so `50%` searches for a literal `50%`). The response carries `status_counts`, a per-status tally over the **whole** KB — the filter UI shows a count beside every option, and a count taken from the filtered page would zero every other option the moment one was selected (UXA-401). |
| `GET` | `/policy/items/{item_id}` | `viewer` | Item detail (item + disposition + citations). |
| `POST` | `/policy/items/{item_id}/triage` | `analyst` | Accept / reject / defer / escalate-to-case; persists `PolicyDisposition`; escalate creates a case via `CaseService` and links its `case_id` back onto the disposition. |

## v1 non-goals

- **Single predicate per rule** - each `PolicyRule` has exactly one `PolicyPredicate`; multi-predicate (AND/OR) rules are deferred.
- **Alert-target evaluation** - `target_kind = "alert"` rules are parsed and stored in config but not evaluated (`_iter_targets` returns `[]` for alert targets).
- **Auto-resolution of de-matched items** - when a previously matched entity no longer satisfies the rule predicate, its `PolicyItem` remains in its current status; de-match auto-closure is not implemented.

## Persistence

The `policy_items` table is created by Alembic migration `database/migrations/versions/0003_policy.py` (`down_revision = 0002_cases`). `disposition` is stored as a jsonb column (D-DISPOSITION-JSONB). Backend selection mirrors `cases/`: `get_policy_item_repository` in `api/dependencies.py` returns the in-memory adapter when no connection provider is configured, otherwise the Postgres adapter.

## Tests

- `tests/policy/test_in_memory_store.py` - repository CRUD, KB isolation, natural-key upsert semantics, no-reopen invariant, multi-status/title filtering and `count_by_status`.
- `tests/policy/test_postgres_store.py` - `@pytest.mark.integration` (skipped without `DATABASE_URL`). Covers the SQL the in-memory adapter cannot: `status = ANY(%s)`, `GROUP BY status`, and that a searched `%` stays literal rather than matching every row.
- `tests/policy/test_service.py` - service upsert + triage, already-triaged guard.
- `tests/policy/test_evaluation.py` - pure evaluator: entity/metric targets, predicate operators, threshold config refs.
- `tests/api/test_policy_router.py` - KB-scoped routes + triage flow.
- `chili_app/e2e/policy-triage.spec.ts` - Playwright: seed item -> triage -> escalate-to-case end-to-end.
