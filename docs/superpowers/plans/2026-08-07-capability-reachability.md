# Capability Reachability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every capability a workflow may reference either actually run, or say precisely why it cannot — and stop the identifier drift that produced two halves of one feature under different names.

**Architecture:** No new machinery. `execute()` and the executor map already exist; this binds real services to them, corrects three drifted identifiers, and widens `CapabilityExecutor` so the calling actor stops riding in the business payload.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, pytest.

**Spec:** `docs/superpowers/specs/2026-08-07-execution-gap-closure-design.md` §2 Tier 2, §3 D2, D3

**Depends on:** `2026-08-07-approval-and-replay-resume.md` **Task 5 only**, and only for Task 5 of this plan (`case.note.draft` is approval-gated, so it cannot be verified end to end until approval resumes a run). Tasks 1–4 here are independent.

## Global Constraints

- Python 3.12. Full type annotations; **no `Any`**. Bare `backend/.venv/bin/pyright` must report 0 errors.
- `backend/.venv/bin/ruff check --no-cache .` must pass.
- Tests run from `backend/`; resolve paths from `__file__`, never the cwd.
- Coverage ≥ 85% per package.
- **Authorization runs before dispatch, always.** `execute()` owns that order; nothing added here may reorder it.
- A capability manifest id is a **published contract** — workflow definitions reference it and the browse API returns it. When an id must change, the *implementation* changes, not the manifest.
- Any frontend-consumed Pydantic change requires OpenAPI export + `npm run codegen:api` + **`npm run build`**.

## Verification Doctrine (inherited — spec §4)

1. **Break the guard to prove it works.** Every coherence test in this plan names the mutation that must turn it red.
2. **In-process tests cannot discover unreachability.** Task 6 is a live-stack task.
3. **Assert the projection.** Capability state is visible through the browse API; assert what a client receives.

## File Structure

| File | Responsibility |
|---|---|
| `backend/capabilities/executors.py` | `CapabilityExecutor` signature + `ExecutionContext` |
| `backend/capabilities/service.py` | pass context to the executor rather than the payload |
| `backend/capabilities/builtin_executors.py` | bind `rag.query`, `analytics.peer_context`, `case.note.draft` |
| `backend/capabilities/registry.py` | correct `evidence.checklist.generate`'s module |
| `backend/analytics/peerstats/capability.py` | adopt the manifest's capability id |
| `backend/tests/capabilities/test_coherence.py` | the drift guards (D3) |

---

### Task 1: Coherence guards for the drift class

Do this **first**. It is the only task that prevents recurrence, and writing it
first means the corrections in Tasks 2–4 are verified by a test that already
exists rather than one written to match what was done.

**Files:**
- Create: `backend/tests/capabilities/test_coherence.py`

- [ ] **Step 1: Write the tests (they will fail — that is the point)**

```python
"""Coherence guards for capability identifier drift.

Four instances of one mistake have shipped: an adapter whose id no manifest
declares, a manifest naming a module that does not exist, an event type with no
producer, and a built-in capability list naming a capability with no manifest.
Each half was individually correct, so unit tests passed.
"""


def test_every_manifest_names_an_importable_module() -> None:
    """`module` is a browse-API filter, not documentation.

    `evidence.checklist.generate` declared `module="evidence.packs"`, which does
    not exist — the real module is `analytics.explainability`. A filter that
    names a phantom module returns a capability nobody can locate.
    """
    import importlib

    for manifest in create_default_capability_registry_service().list_capabilities().items:
        try:
            importlib.import_module(manifest.module)
        except ImportError as exc:  # pragma: no cover - the assertion is the report
            pytest.fail(
                f"Capability '{manifest.capability_id}' names module "
                f"'{manifest.module}', which does not import: {exc}"
            )


def test_every_capability_adapter_id_is_a_registered_manifest_id() -> None:
    """The G10 guard.

    `analytics/peerstats/capability.py` implemented a complete adapter under
    `analytics.peer_analysis`, which no manifest declares, while the manifest
    declared `analytics.peer_context`, which nothing implemented. Two halves of
    one feature, both correct, neither reachable.
    """
    registered = {
        m.capability_id
        for m in create_default_capability_registry_service().list_capabilities().items
    }

    for module_name, id_symbol in _ADAPTER_CAPABILITY_IDS:
        module = importlib.import_module(module_name)
        declared = getattr(module, id_symbol)
        # A Literal type alias or a plain str constant both resolve here.
        values = get_args(declared) or (declared,)
        for value in values:
            assert value in registered, (
                f"{module_name}.{id_symbol} is '{value}', which no manifest "
                "declares — the adapter is unreachable through the registry."
            )


def test_every_declared_event_type_has_a_producer_or_is_listed_as_notification_only() -> None:
    """The G8 guard.

    `alert.created` is declared and decodable and is constructed nowhere outside
    a test, so the WebSocket alert stream it documents has no producer.
    """
    producers = _event_types_constructed_in_production_code()
    for event_type in _declared_event_types():
        assert (
            event_type in producers or event_type in NOTIFICATION_ONLY_EVENT_TYPES
        ), (
            f"'{event_type}' is declared in the codec, constructed nowhere in "
            "production code, and not listed as notification-only. It is either "
            "dead or missing its producer."
        )
```

`_ADAPTER_CAPABILITY_IDS` is an explicit list of
`(module, symbol)` pairs — do **not** try to discover adapters by scanning, which
would silently pass when a new adapter is added without being listed. Start with:

```python
_ADAPTER_CAPABILITY_IDS = [
    ("connectors.status_adapter", "CONNECTOR_SYNC_STATUS_CAPABILITY_ID"),
    ("workflow_definitions.rag_adapter", "RAG_QUERY_CAPABILITY_ID"),
    ("analytics.peerstats.capability", "PeerAnalysisCapabilityId"),
]
```

`NOTIFICATION_ONLY_EVENT_TYPES` is a frozenset **with a comment per entry**
saying who consumes it (SSE, projections, operator tooling). An entry with no
justification is how a dead event hides in an allow-list.

- [ ] **Step 2: Run to confirm all three fail**

Run: `cd backend && .venv/bin/pytest tests/capabilities/test_coherence.py -v`
Expected: FAIL ×3 — `evidence.packs` does not import; `analytics.peer_analysis`
is unregistered; `alert.created` has no producer.

Record the exact failures in the commit message. These are the gaps; the tests
are the specification of what "closed" means.

- [ ] **Step 3: Commit the failing guards, marked xfail with a reason**

```python
@pytest.mark.xfail(reason="G7 — closed by Task 2", strict=True)
```

`strict=True` matters: when the gap is closed, an xfail that unexpectedly passes
is itself a failure, so the marker cannot be left behind after the fix. Remove
each marker in the task that closes its gap.

```bash
git add backend/tests/capabilities/test_coherence.py
git commit -m "test(capabilities): guard the identifier-drift class (3 known failures, xfail-strict)"
```

---

### Task 2: Correct the phantom module reference

**Files:**
- Modify: `backend/capabilities/registry.py`
- Test: `backend/tests/capabilities/test_coherence.py` (remove one xfail)

- [ ] **Step 1: Confirm the real module**

`evidence.checklist.generate` declares `module="evidence.packs"`. There is no
`evidence/` package. Evidence packs live in `analytics/explainability/`
(`ObjectStoreEvidencePackRepository`, `NarrativeGeneratorProtocol`). Verify with
`ls backend/analytics/explainability/` before changing the string — do not guess.

- [ ] **Step 2: Change the manifest and drop the xfail**

`module="analytics.explainability"`.

The capability stays **unimplemented** — this corrects where it says it lives,
not whether it runs. Its `capability_not_executable` behaviour is deliberate
(spec §6) and there is already a test asserting it.

- [ ] **Step 3: Run tests**

Run: `cd backend && .venv/bin/pytest tests/capabilities/ tests/api/test_capabilities_router.py -v`
Expected: PASS, and `test_every_manifest_names_an_importable_module` now passes
without xfail.

- [ ] **Step 4: Commit**

```bash
git add backend/capabilities/registry.py backend/tests/capabilities/test_coherence.py
git commit -m "fix(capabilities): point evidence.checklist.generate at the module that exists"
```

---

### Task 3: Give the peer-analysis adapter the manifest's id

**Files:**
- Modify: `backend/analytics/peerstats/capability.py`
- Test: `backend/tests/analytics/peerstats/test_capability.py`, `backend/tests/capabilities/test_coherence.py`

This is G10. A complete, tested adapter exists under `analytics.peer_analysis`;
no manifest declares it. The manifest declares `analytics.peer_context`; nothing
implements it.

**The adapter's id changes, not the manifest's** — the manifest id is the
published contract that workflow definitions reference and the browse API
returns.

- [ ] **Step 1: Write the failing test**

```python
def test_the_adapter_uses_the_published_capability_id() -> None:
    """The manifest id is the contract; the adapter id is an implementation
    detail. They were `analytics.peer_context` and `analytics.peer_analysis`,
    so the adapter was unreachable and the manifest unimplemented."""
    assert get_args(PeerAnalysisCapabilityId) == ("analytics.peer_context",)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/analytics/peerstats/test_capability.py -k published -v`
Expected: FAIL — `('analytics.peer_analysis',) != ('analytics.peer_context',)`

- [ ] **Step 3: Rename the id, keeping the symbol**

```python
PeerAnalysisCapabilityId = Literal["analytics.peer_context"]
```

Grep for `analytics.peer_analysis` across `backend/`, `chili_app/src/` and
`config/defaults/*.yaml` before finishing. If a domain pack references the old
id, that reference is now broken and must move too — check
`capabilities:`/`allowed_capability_refs` blocks.

- [ ] **Step 4: Check the output shapes agree**

The manifest promises `{entity_id, metric_name, peer_count, z_score}` — one
metric, flat. `PeerAnalysisResponse` returns `{knowledge_base_id, entity_id,
metrics: [PeerMetricComparison]}` — a list.

They do not match. Decide and record which is right:

- If the manifest is right, the executor binding (Task 4) flattens to the
  requested `metric_name`.
- If the adapter is right, the **manifest's `output_schema` changes** — and
  since the schema is returned by the browse API, that is a contract change
  requiring OpenAPI export and codegen.

Prefer flattening in the binding: the manifest is the published contract, and
`analytics.peer_context` names a single-metric context. Record the decision in
the commit message either way.

- [ ] **Step 5: Run tests and drop the xfail**

Run: `cd backend && .venv/bin/pytest tests/analytics/ tests/capabilities/ -v`
Expected: PASS, `test_every_capability_adapter_id_is_a_registered_manifest_id`
now passing without xfail.

- [ ] **Step 6: Commit**

```bash
git add backend/analytics/peerstats backend/tests
git commit -m "fix(peerstats): adopt the published analytics.peer_context id so the adapter is reachable"
```

---

### Task 4: Widen `CapabilityExecutor` to take an execution context

**Files:**
- Modify: `backend/capabilities/executors.py`, `backend/capabilities/service.py`, `backend/capabilities/builtin_executors.py`, `backend/workflow_definitions/executor.py`
- Test: `backend/tests/capabilities/test_execute.py`, `backend/tests/workflow_definitions/test_executor.py`

This is G9. `CapabilityExecutor` is `Mapping -> Mapping`, so the workflow
executor puts `actor_user_id` and `actor_roles` into the **business payload**.
That works and is documented, but it mixes authorization context with tool
input, and every new capability needing context makes it worse.

- [ ] **Step 1: Write the failing tests**

```python
def test_the_executor_receives_context_separately_from_payload() -> None:
    """Authorization context is not tool input.

    It rode in the payload because the signature had nowhere else to put it,
    so every capability saw `actor_roles` as a business field.
    """
    seen: list[tuple[Mapping[str, object], ExecutionContext]] = []

    def _capture(payload: Mapping[str, object], context: ExecutionContext):
        seen.append((payload, context))
        return {}

    register_executor("test.ctx", _capture)
    _execute(service, "test.ctx", audit=_audit())

    payload, context = seen[0]
    assert "actor_roles" not in payload
    assert context.actor_user_id == _ACTOR
    assert context.actor_roles == ["analyst"]
    assert context.knowledge_base_id == _KB_ID


def test_context_carries_the_domain_and_environment_that_were_authorized() -> None:
    """A capability that re-checks must check the same thing execute() did."""
    ...
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/capabilities/test_execute.py -k context -v`
Expected: FAIL — executors take one argument

- [ ] **Step 3: Add the context and change the signature**

```python
@dataclass(frozen=True, slots=True)
class ExecutionContext:
    """Who is calling and under what authorization, separate from tool input.

    `execute()` has already authorized using exactly these values. An executor
    reading them is re-checking, not deciding — but a capability that needs to
    know the caller now has a channel that is not the business payload.
    """

    actor_user_id: str
    actor_roles: tuple[str, ...]
    domain_name: str | None
    environment_tag: str | None
    knowledge_base_id: str | None


CapabilityExecutor = Callable[[Mapping[str, object], ExecutionContext], Mapping[str, object]]
```

`actor_roles` is a `tuple`, not a `list`: the context is frozen, and a mutable
field on a frozen dataclass is a lie about immutability.

- [ ] **Step 4: Remove the actor from the workflow payload**

In `workflow_definitions/executor.py`, `_payload_for` currently injects
`actor_user_id` and `actor_roles` with a comment explaining the workaround.
Delete both, and the comment — the workaround is gone.

- [ ] **Step 5: Update the one bound executor**

`builtin_executors.py`'s `connector.sync.status` closure currently reads
`payload.get("actor_roles")`. It takes them from the context now, which also
removes the `cast(list[object], …)` narrowing that existed only because the
payload was untyped.

- [ ] **Step 6: Run the affected suites**

Run: `cd backend && .venv/bin/pytest tests/capabilities/ tests/workflow_definitions/ tests/connectors/ -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/capabilities backend/workflow_definitions backend/tests
git commit -m "refactor(capabilities): give executors an ExecutionContext instead of smuggling the actor through the payload"
```

---

### Task 5: Bind the three capabilities that have services

**Files:**
- Modify: `backend/capabilities/builtin_executors.py`, `backend/agent/coordinator.py`
- Test: `backend/tests/capabilities/test_builtin_executors.py`

**Interfaces:**
- Consumes: `ExecutionContext` (Task 4), the corrected id (Task 3), `RagServiceProtocol`, `PeerAnalysisService`, `CaseService`.

Bind `rag.query`, `analytics.peer_context` and `case.note.draft`.
`evidence.checklist.generate` stays unbound by decision (spec §3 D2).

- [ ] **Step 1: Confirm what each service actually offers**

Do not assume. Read each before binding:

| Capability | Service | Method |
|---|---|---|
| `rag.query` | `RagServiceProtocol` | `answer_question(*, knowledge_base_ids, question) -> RagAnswer` |
| `analytics.peer_context` | `PeerAnalysisService` | via `peerstats/capability.py`, which already wraps it |
| `case.note.draft` | `CaseService` + a narrative generator | see Step 4 — this one is **not** pure wiring |

- [ ] **Step 2: Write the failing tests**

```python
def test_rag_query_is_bound_and_returns_an_answer() -> None:
    bound = register_builtin_capability_executors(**_deps())
    assert "rag.query" in bound

    envelope = service.execute("rag.query", payload={"question": "why?",
                               "knowledge_base_ids": ["kb-1"]}, ...)

    assert envelope.success is True
    assert "answer" in envelope.output


def test_peer_context_is_bound_and_flattens_to_the_manifest_shape() -> None:
    """The manifest promises one metric flat; the service returns a list."""
    envelope = service.execute("analytics.peer_context",
                               payload={"entity_id": "e-1", "metric_name": "billing_amount"}, ...)

    assert set(envelope.output) >= {"entity_id", "metric_name", "peer_count", "z_score"}


def test_an_unbindable_capability_is_reported_not_silently_skipped() -> None:
    """A service that is absent must produce a logged, returnable absence —
    not a capability that appears bound and fails at dispatch."""
    bound = register_builtin_capability_executors(rag_service=None, ...)
    assert "rag.query" not in bound
```

- [ ] **Step 3: Bind rag.query and analytics.peer_context**

Both wrap existing adapters that return a `CapabilityExecutionEnvelope`. Keep
the established pattern from `connector.sync.status`: call the adapter, raise on
`not envelope.success` so `execute()` reports it as a failed capability call
with the adapter's own reason, return `envelope.output or {}`.

Note in the code that the adapters authorize internally, so authorization runs
twice on this path — a redundant read, not a weaker check, and reusing the
tested adapter is worth more than saving it. Collapsing the two conventions is
out of scope (spec §6).

- [ ] **Step 4: `case.note.draft` — decide and record the scope**

This one is **not** pure wiring. The manifest promises
`{draft_note: str, requires_human_approval: bool}`. `CaseService` has no
note-drafting method; `Case.notes` is a plain string field.

Two honest options — pick one and say so in the commit:

- **(a) Deterministic draft.** Compose the note from the case's own fields plus
  the `summary` input, using `DeterministicNarrativeGenerator` from
  `analytics/explainability/adapters/`. No LLM dependency, works offline, and
  the capability genuinely runs.
- **(b) Leave unbound.** If (a) produces something not worth a reviewer's time,
  do not ship a capability whose output is filler. Say so, and leave it
  reporting `capability_not_executable` alongside `evidence.checklist.generate`.

Prefer (a) — the capability is approval-gated, so a human reads the draft before
it lands, and a deterministic starting point is useful. But **do not** wire an
LLM here to make it look richer: that adds a provider dependency to a workflow
step and an unbounded failure mode, for a capability whose whole point is that a
person reviews it.

`requires_human_approval: true` is always returned — it is a statement about the
capability, not a computed value.

- [ ] **Step 5: Wire the services in the worker**

`register_builtin_capability_executors` gains `rag_service`, `peer_analysis_service`
and `case_service` parameters. The worker builds them the same way it builds
`ConnectorService`. Each is optional; an absent service means that capability is
not bound, is reported in the returned set, and is logged.

- [ ] **Step 6: Assert the browse projection (spec §4.4)**

Add a router test: `GET /knowledgebases/{kb}/capabilities` and assert the
response distinguishes executable from registered-only. If the contract has no
such field, **add one** — an author picking a capability from the browse API
cannot currently tell which ones can run, which is the same class of problem as
a status that lies. This is a frontend-consumed contract change: export OpenAPI,
`npm run codegen:api`, `npm run build`.

- [ ] **Step 7: Run the full gates**

```bash
cd backend && .venv/bin/pytest --cov -q && .venv/bin/pyright && .venv/bin/ruff check --no-cache .
cd ../chili_app && npm run lint && npm run test:run && npm run build
```

- [ ] **Step 8: Commit**

```bash
git add backend chili_app
git commit -m "feat(capabilities): bind rag.query, analytics.peer_context and case.note.draft"
```

---

### Task 6: Live-stack verification

**Files:**
- Modify: `backend/tests/e2e/test_workflow_run_flow.py`
- Modify: `docs/ledger/module-map.md`, `docs/project/planning/backlog.md`

**Depends on:** Plan 1 Task 5 (approval), because `case.note.draft` is
approval-gated and cannot complete without it.

- [ ] **Step 1: Extend the live workflow tests**

```python
def test_a_workflow_runs_every_bound_capability(base_url: str) -> None:
    """One definition, one step per bound capability, run to completion.

    The registry advertises what a workflow may reference; this asserts the
    advertisement is true rather than aspirational.
    """
    executable = [c for c in _browse_capabilities(base_url) if c["executable"]]
    assert len(executable) >= 4, executable
    ...


def test_an_unbound_capability_is_visibly_unbound_in_the_browse_api(base_url: str) -> None:
    """An author must be able to tell before authoring, not after running."""
```

- [ ] **Step 2: Run against the live stack**

```bash
make dev
cd backend && .venv/bin/pytest tests/e2e/ -v -m integration
```

- [ ] **Step 3: Verify through the worker, not only the API**

For each bound capability, confirm the persisted step reached `completed` with
`attempts >= 1` and that its output landed in the step metadata. A run can reach
`completed` with every step skipped.

- [ ] **Step 4: Update the docs**

`module-map.md` under `capabilities/` currently says only
`connector.sync.status` is bound and *"the other four manifests are registered
but not implemented"*. Replace with the real count, and keep naming what is
still unbound and why — the honest statement is the point, not the number.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/e2e docs
git commit -m "test(capabilities): live-stack verification that advertised capabilities actually run"
```

---

## Self-review notes

- **Spec coverage:** G7 (Task 2), G10 (Task 3), G9 (Task 4), G3 (Task 5), D3
  (Task 1 — the guards, written first on purpose).
- **Ordering:** Task 1 first is deliberate. Writing the guards before the fixes
  means each fix is verified by a test that predates it, rather than one shaped
  to match what was built.
- **The xfail-strict pattern** in Task 1 Step 3 is what stops a "temporary"
  marker outliving its gap: when the fix lands, an unexpectedly-passing xfail
  fails the suite until the marker is removed.
- **Type consistency:** `ExecutionContext` (Task 4) is consumed by Task 5's
  bindings; do not implement Task 5 before Task 4, or the bindings get written
  against the old one-argument signature and have to be rewritten.
- **Open decision recorded, not hidden:** Task 3 Step 4 (flatten in the binding
  vs change the manifest schema) and Task 5 Step 4 (deterministic draft vs leave
  unbound) both have a recommendation and both require the implementer to state
  what they chose.
