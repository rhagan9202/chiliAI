# Sprint 2026-35 — Correctness and Security Implementation Plan

## STATUS: EXECUTED — read this before the task bodies

This plan was executed in full over commits `3aaddad1..a35c2640` (13 tasks,
each reviewed independently; sprint close-out gates: 3549 backend tests
passing at 96% coverage, pyright and ruff clean, `make check` green, no
OpenAPI drift, frontend tsc/eslint/vitest clean).

**The unchecked `- [ ]` boxes below are historical.** They record what was
planned, not what remains. Do not work from them, and do not treat an
unchecked box as an open item — the work is in git history.

**Three of the approaches prescribed below were deliberately rejected during
implementation, and the code does the opposite of what those task bodies
say.** The task bodies are left intact on purpose: a plan is a record of what
was planned, and the deviations are the interesting part.

| Task | What this plan prescribes | What shipped, and why |
|------|---------------------------|-----------------------|
| **6** | Raise `StageStillRunningError` on timeout and have `drain_ingestion_events` **skip the ACK** so the delivery returns to the PEL. | **Rejected.** Redis `XAUTOCLAIM` claims entries idle past the threshold from *any* consumer in the group — it does not exclude the caller's own pending entries — and reclaim is now on by default at 60s in both compose files. An un-ACKed delivery would be reclaimed by the same worker ~60s later, spawning another `asyncio.to_thread` while the original thread still runs, repeating until the bounded executor is exhausted. Worse, a slow-but-healthy stage finishing at t=70s would be re-run at t=60s and **re-publish its successor event**, re-running the whole downstream pipeline. The prescription would have converted one orphaned thread into an unbounded thread leak plus a data-integrity hazard. What shipped: `timeout_seconds` is an alarm rather than a deadline — `asyncio.wait` (which does not cancel) applies the budget, an overrun logs at error, and the handler is awaited to completion so the retry/DLQ/ACK decision reflects the stage's real outcome. |
| **8** | Check `Content-Length` **inside the handler** to bound the request body. | **Rejected.** FastAPI's `routing.py` reads and decodes the body (`await request.json()` / `request.form()`) *before* `solve_dependencies`, so with a Pydantic body param declared the body is fully buffered before any handler code runs. The check would have fired after the memory spike it was meant to prevent — a late rejection dressed up as a limit. What shipped: a custom `APIRoute` (`_SizeLimitedPushRoute`) wrapping the ASGI `receive()` channel so the cap applies as the body streams in, with `RecordPushRequest` kept as a bound param so the OpenAPI/frontend contract is preserved. It bounds a chunked body with no `Content-Length` identically. |
| **12** | Migration `0020`'s downgrade **`DELETE`s** per-KB duplicate playbook snapshots (keeping the lowest `knowledge_base_id`) before `ADD CONSTRAINT`. | **Rejected.** Published playbook snapshots are documented as immutable (`docs/onboarding.md`, `backend/playbooks/repository.py`), and no migration in the tree contains a `DELETE FROM` — every other downgrade drops a table or a column, never rows. Silently destroying documented-immutable history to satisfy a constraint is exactly the failure class this sprint exists to close. What shipped: the downgrade `RAISE EXCEPTION`s first with an actionable message naming what to fix. Accepted trade-off: the downgrade now permanently refuses on genuine multi-KB duplicate data rather than ever succeeding unattended. |

Two further corrections to this document's own content, recorded rather than
edited into the task bodies:

- Task 5 closes only the `documents.parsed` half of its audit finding. The
  second writer (`handle_entities_validated`) accumulates across pipeline
  stages by design, so the absolute setter there would trade a replay bug for
  a data-loss bug. Tracked as backlog story `agent.22`.
- Task 11's brief says the revision id is "31 characters"; it is 30.
  Immaterial (the cap is 32), recorded because stale numbers are what this
  sprint was watching for.

---

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the twelve audit findings whose failure mode is silent data corruption or a security hole — concurrent writes that lose data, event handlers that corrupt state on retry, a login flow an attacker can initiate, and three Postgres-layer defects.

**Architecture:** Every write that reads-then-writes becomes a compare-and-set against the value it read, so a concurrent writer loses loudly instead of silently. Event handlers become replayable, because Redis Streams is at-least-once and a handler body that is not replayable corrupts state on every redelivery. The gateway grows the request limits it already applies elsewhere. No new subsystems.

**Tech Stack:** Python 3.12 / FastAPI / Pydantic, psycopg 3, Alembic, pytest, pyright strict.

**Spec:** `docs/superpowers/specs/2026-08-27-audit-burndown-design.md` (sprint 2026-35 section, stories BL-053…BL-058)

## Global Constraints

- `pyright` run bare from `backend/` must be clean. Its `tool.pyright.include` covers much of `tests/**`, so test code is strict-checked too. Per-file `pyright <file>` misses include-scoped errors — always run bare.
- `backend/.venv/bin/ruff check --no-cache .` clean. The ruff cache dir is not writable in the sandbox; `--no-cache` is required.
- pytest coverage ≥ 85% per package.
- **Never point `DATABASE_URL` at the dev `chili` database.** `tests/database/test_migrations.py` runs `alembic downgrade base` → `upgrade head`, emptying every app table. `tests/conftest.py` defaults to `…:5432/chili_test`; an explicit export still wins, so export `postgresql://chili:chili@localhost:5432/chili_test` or nothing at all.
- Integration tests need Postgres and Redis: `docker compose -f docker-compose.dev.yaml up -d --wait postgres redis`.
- Never import private `_helpers` into a pyright-included test directory — it triggers `reportPrivateUsage`. Test through the public surface; promote a helper to public if needed.
- A new read needs a protocol method and an implementation in **every** adapter, in-memory included.
- Backend modules communicate only through the FastAPI gateway, the agent coordinator, or `shared/`. No ad-hoc cross-module imports.
- After ANY frontend-consumed Pydantic change, regenerate from the repo root: `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json` then `cd chili_app && npm run codegen:api`. CI fails on drift.
- **Every test in this plan must be watched failing against the real defect before the fix lands.** This is the sprint's added Definition of Done. Both criticals closed in `b8e1ffef` had green tests over them.
- Commit after every task, conventional-commit subjects.

## Findings from exploration that change the work

Read these before task 1. Each contradicts something the spec or a reasonable reader would assume.

- **BL-053 needs no version column, and therefore no migration.** The spec's sequencing note assigned it migration `0029`. It does not need one: `alert_history` already carries `status` and `cases` already carries `updated_at`, and both are sufficient compare-and-set tokens. **`0029` therefore belongs to BL-058** (the `alert_history` index), and there is no `0030` in this sprint.
- **The workflow-pagination finding is no longer unreachable.** The audit ranked it low because it required `user.knowledge_base_ids` to be non-`None`, "which never happens on the cookie path". Commit `b8e1ffef` fixed exactly that, so this defect is now live in every cookie session carrying an entitlement claim. Treat it as a real defect, not a latent one.
- **The alert TOCTOU has a second site the finding's title does not name.** `transition_status` is cited, but `_ALERT_ACK_SQL` / `_ALERT_ACK_SCOPED_SQL` (`monitoring/adapters/postgres.py:76-88`) have the same unguarded `WHERE`. The audit's evidence says so in its last sentence. Task 2 covers it; do not skip it because the title only mentions transitions.
- **`_ALERT_GET_SQL` and `_ALERT_ACK_SQL` match on `alert_id` alone**, unscoped by `knowledge_base_id`, which is why BL-058's index is on `alert_id` rather than a composite. Do not "fix" this into a scoped lookup as part of BL-058 — the scoped variants already exist and are used by the KB-scoped routes; changing the unscoped ones is a separate behavioural change.
- **`cases.update()` takes only the mutated `Case`.** The service loads, copies with a new `updated_at`, and passes the copy — so the pre-modification timestamp is already lost by the time the repository sees it. The CAS token must be threaded explicitly; task 3 changes the protocol signature.
- **`run_handler_with_retry` gives timeouts zero retries** (`agent/coordinator.py:4411-4414` breaks immediately on `asyncio.TimeoutError`). The orphan-thread problem is therefore not a retry-storm; it is a single thread that outlives its own ACK.

## File Structure

| File | Responsibility | Tasks |
|---|---|---|
| `backend/monitoring/adapters/postgres.py` | Alert CAS on status; unscoped-lookup SQL unchanged | 1, 2 |
| `backend/cases/adapters/protocols.py` | `update()` gains `expected_updated_at` | 3 |
| `backend/cases/adapters/postgres.py` | CAS on `updated_at` | 3 |
| `backend/cases/adapters/in_memory.py` | Same CAS semantics as Postgres | 3 |
| `backend/cases/exceptions.py` | `CaseConcurrentModificationError` | 3 |
| `backend/cases/service.py` | Threads the loaded timestamp through | 3 |
| `backend/api/routers/alerts.py` | Bulk transition audits per transition | 4 |
| `backend/agent/coordinator.py` | Idempotent warnings; timeout no longer ACKs; deps teardown | 5, 6, 7 |
| `backend/api/routers/records.py` | Push body budget | 8 |
| `backend/api/routers/workflows.py` | Cursor reflects the first unconsumed item | 9 |
| `backend/api/routers/auth.py` | Login state bound to the browser | 10 |
| `backend/database/migrations/versions/0029_alert_history_alert_id_ix.py` | `ix_alert_history_alert_id` | 11 |
| `backend/database/migrations/versions/0020_playbook_snapshot_kb_scope.py` | Downgrade collapses duplicates first | 12 |
| `backend/conversations/service.py` | Service owns `updated_at` | 13 |
| `backend/conversations/adapters/in_memory.py` | Stops re-stamping | 13 |

---

### Task 1: Alert status transition is a compare-and-set

**Files:**
- Modify: `backend/monitoring/adapters/postgres.py:97-102` (`_ALERT_STATUS_SQL`), `:414-454` (`transition_status`)
- Test: `backend/tests/monitoring/test_postgres_alert_history.py`

**Interfaces:**
- Consumes: `validate_alert_transition(current, new)` from `monitoring/lifecycle.py`, raising `AlertLifecycleError`.
- Produces: `transition_status(...)` unchanged in signature; it now raises `AlertLifecycleError` when the row changed under it.

- [ ] **Step 1: Write the failing test**

```python
def test_a_concurrent_transition_loses_instead_of_committing_a_forbidden_one(
    database_url: str,
) -> None:
    """Two analysts transition one alert at once; the loser must not commit.

    ALERT_TRANSITIONS['resolved'] == {'open'}, so 'resolved' -> 'dismissed' is
    forbidden. Without a compare-and-set both callers read 'investigating',
    both validate, and the second commits the forbidden transition anyway --
    and appends a triage event claiming from_status='investigating', which is
    a false audit trail.
    """
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    store = PostgresAlertFeedStore(provider)
    _seed_alert(provider, alert_id="alert-cas-1", status="investigating")

    # Simulate the interleave: read happens for both, then the first commits.
    store.transition_status(
        "alert-cas-1",
        knowledge_base_id=_KB,
        status="resolved",
        actor="analyst-1",
    )

    with pytest.raises(AlertLifecycleError):
        store.transition_status(
            "alert-cas-1",
            knowledge_base_id=_KB,
            status="dismissed",
            actor="analyst-2",
        )

    row = store.get_alert_scoped(knowledge_base_id=_KB, alert_id="alert-cas-1")
    assert row is not None
    assert row.status == "resolved"
    assert [e.to_status for e in row.triage_history] == ["resolved"]
```

- [ ] **Step 2: Run the test and watch it fail**

Run: `cd backend && DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest tests/monitoring/test_postgres_alert_history.py -k concurrent_transition -v`

Expected: FAIL — no `AlertLifecycleError` is raised, and `triage_history` contains two events.

- [ ] **Step 3: Add the status guard to the UPDATE**

```python
_ALERT_STATUS_SQL = f"""
    UPDATE alert_history
    SET status = %s, updated_at = %s, triage_history = triage_history || %s::jsonb
    WHERE knowledge_base_id = %s AND alert_id = %s AND status = %s
    RETURNING {_ALERT_COLUMNS}
"""
```

- [ ] **Step 4: Pass the observed status and react to a lost race**

In `transition_status`, pass `record.status` as the final parameter and handle the empty result:

```python
                row = conn.execute(
                    _ALERT_STATUS_SQL,
                    (
                        status,
                        event.occurred_at,
                        _encode_triage_history([event]),
                        knowledge_base_id,
                        alert_id,
                        record.status,
                    ),
                ).fetchone()
                if row is None:
                    # Someone transitioned this row between our read and our
                    # write. Nothing has been written, so re-read and let the
                    # lifecycle rules judge the request against reality.
                    conn.commit()
                    current = conn.execute(
                        _ALERT_GET_SCOPED_SQL, (knowledge_base_id, alert_id)
                    ).fetchone()
                    if current is None:
                        return None
                    validate_alert_transition(_row_to_alert_record(current).status, status)
                    raise MonitoringSourceError(
                        "Alert status changed concurrently; retry the transition."
                    )
                conn.commit()
```

- [ ] **Step 5: Run the test and watch it pass**

Run: `cd backend && DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest tests/monitoring/test_postgres_alert_history.py -v`

Expected: PASS, all tests in the file.

- [ ] **Step 6: Commit**

```bash
git add backend/monitoring/adapters/postgres.py backend/tests/monitoring/test_postgres_alert_history.py
git commit -m "fix(monitoring): make the alert status transition a compare-and-set"
```

---

### Task 2: Alert acknowledge is a compare-and-set

**Files:**
- Modify: `backend/monitoring/adapters/postgres.py:76-88` (`_ALERT_ACK_SQL`, `_ALERT_ACK_SCOPED_SQL`) and their callers
- Test: `backend/tests/monitoring/test_postgres_alert_history.py`

**Interfaces:**
- Consumes: the CAS pattern established in task 1.
- Produces: `acknowledge` behaviour unchanged on the uncontended path.

- [ ] **Step 1: Write the failing test**

```python
def test_acknowledging_a_resolved_alert_does_not_reopen_it(database_url: str) -> None:
    """Acknowledge has the same unguarded WHERE as transition_status had.

    'resolved' -> 'acknowledged' is not in ALERT_TRANSITIONS['resolved'], so an
    acknowledge racing a resolve must lose rather than silently move a closed
    alert back into the queue.
    """
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    store = PostgresAlertFeedStore(provider)
    _seed_alert(provider, alert_id="alert-cas-2", status="resolved")

    with pytest.raises(AlertLifecycleError):
        store.acknowledge_scoped(
            knowledge_base_id=_KB, alert_id="alert-cas-2", actor="analyst-2"
        )

    row = store.get_alert_scoped(knowledge_base_id=_KB, alert_id="alert-cas-2")
    assert row is not None
    assert row.status == "resolved"
```

- [ ] **Step 2: Run the test and watch it fail**

Run: `cd backend && DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest tests/monitoring/test_postgres_alert_history.py -k acknowledging_a_resolved -v`

Expected: FAIL — the alert is silently set to `acknowledged`.

- [ ] **Step 3: Validate before writing, and guard the write**

Give both acknowledge paths the same read → `validate_alert_transition(record.status, "acknowledged")` → guarded UPDATE shape task 1 established:

```python
_ALERT_ACK_SCOPED_SQL = f"""
    UPDATE alert_history
    SET status = 'acknowledged', updated_at = %s, triage_history = triage_history || %s::jsonb
    WHERE knowledge_base_id = %s AND alert_id = %s AND status = %s
    RETURNING {_ALERT_COLUMNS}
"""
```

- [ ] **Step 4: Run the tests and watch them pass**

Run: `cd backend && DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest tests/monitoring/ -v`

Expected: PASS. If an existing test asserted that acknowledging a resolved alert succeeds, read it before changing it — it may be encoding the defect, in which case update it and say so in the commit body.

- [ ] **Step 5: Commit**

```bash
git add backend/monitoring/adapters/postgres.py backend/tests/monitoring/test_postgres_alert_history.py
git commit -m "fix(monitoring): validate and guard the alert acknowledge transition"
```

---

### Task 3: Case updates are optimistic-locked

**Files:**
- Modify: `backend/cases/adapters/protocols.py:34-36`, `backend/cases/adapters/postgres.py:43-50` and `:118+`, `backend/cases/adapters/in_memory.py`, `backend/cases/exceptions.py`, `backend/cases/service.py:139+`
- Test: `backend/tests/cases/test_service.py`, `backend/tests/cases/test_postgres_store.py`

**Interfaces:**
- Produces: `CaseRepository.update(case: Case, *, expected_updated_at: datetime) -> Case`, raising `CaseConcurrentModificationError(knowledge_base_id, case_id)` when no row matches the expected timestamp.

- [ ] **Step 1: Write the failing test**

```python
def test_a_concurrent_attach_does_not_silently_drop_the_other_alert() -> None:
    """Two analysts attach different alerts to one case at the same time.

    Both read alert_ids=['A'], both pass the duplicate check, and both write
    the whole jsonb array from their own stale copy. Whoever commits second
    wins and the other attachment is gone -- with a 200 returned to the loser.
    """
    repository = InMemoryCaseRepository()
    service = create_case_service(repository)
    case = _open_case(service, alert_ids=["A"])

    stale = repository.get(knowledge_base_id=_KB, case_id=case.case_id)
    assert stale is not None

    service.attach_alert(
        knowledge_base_id=_KB, case_id=case.case_id, alert=_alert("B")
    )

    with pytest.raises(CaseConcurrentModificationError):
        repository.update(
            stale.model_copy(update={"alert_ids": [*stale.alert_ids, "C"]}),
            expected_updated_at=stale.updated_at,
        )

    final = repository.get(knowledge_base_id=_KB, case_id=case.case_id)
    assert final is not None
    assert final.alert_ids == ["A", "B"]
```

- [ ] **Step 2: Run the test and watch it fail**

Run: `cd backend && .venv/bin/pytest tests/cases/ -k concurrent_attach -v`

Expected: FAIL with `TypeError: update() got an unexpected keyword argument 'expected_updated_at'`.

- [ ] **Step 3: Add the exception**

In `backend/cases/exceptions.py`:

```python
class CaseConcurrentModificationError(CaseError):
    """Raised when a case changed between the caller's read and its write."""

    def __init__(self, knowledge_base_id: str, case_id: str) -> None:
        super().__init__(
            f"Case '{case_id}' in knowledge base '{knowledge_base_id}' was modified "
            "concurrently; reload it and retry."
        )
        self.knowledge_base_id = knowledge_base_id
        self.case_id = case_id
```

- [ ] **Step 4: Widen the protocol**

In `backend/cases/adapters/protocols.py`:

```python
    def update(self, case: Case, *, expected_updated_at: datetime) -> Case:
        """Update an existing case, failing if it changed since it was read.

        ``expected_updated_at`` is the ``updated_at`` the caller loaded, not the
        new one it is writing. Raises ``CaseNotFoundError`` if absent and
        ``CaseConcurrentModificationError`` if another writer got there first.
        """
        ...
```

- [ ] **Step 5: Guard the Postgres write**

```python
_UPDATE_SQL = """
    UPDATE cases
    SET title = %s, status = %s, priority = %s, assignee = %s,
        originating_alert_id = %s, evidence_pack_id = %s,
        alert_ids = %s::jsonb, timeline = %s::jsonb,
        feedback_history = %s::jsonb, playbook_ref = %s::jsonb, updated_at = %s
    WHERE knowledge_base_id = %s AND case_id = %s AND updated_at = %s
"""
```

In `update`, append `expected_updated_at` to the parameter tuple. When `cursor.rowcount == 0`, re-read to tell the two failures apart:

```python
                if cursor.rowcount == 0:
                    conn.commit()
                    existing = conn.execute(
                        _GET_SQL, (case.knowledge_base_id, case.case_id)
                    ).fetchone()
                    if existing is None:
                        raise CaseNotFoundError(case.knowledge_base_id, case.case_id)
                    raise CaseConcurrentModificationError(
                        case.knowledge_base_id, case.case_id
                    )
                conn.commit()
```

- [ ] **Step 6: Give the in-memory adapter the same semantics**

The in-memory adapter is what most tests see, so divergence here hides the Postgres behaviour — the audit's first recurring theme.

```python
    def update(self, case: Case, *, expected_updated_at: datetime) -> Case:
        key = (case.knowledge_base_id, case.case_id)
        existing = self._cases.get(key)
        if existing is None:
            raise CaseNotFoundError(case.knowledge_base_id, case.case_id)
        if existing.updated_at != expected_updated_at:
            raise CaseConcurrentModificationError(
                case.knowledge_base_id, case.case_id
            )
        self._cases[key] = case
        return case
```

- [ ] **Step 7: Thread the loaded timestamp through the service**

Every `self._repository.update(...)` call in `cases/service.py` already has the loaded `existing` in scope. Pass `expected_updated_at=existing.updated_at` at each call site.

- [ ] **Step 8: Run the tests and watch them pass**

Run: `cd backend && .venv/bin/pytest tests/cases/ -v && DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest tests/cases/ -m integration -v`

Expected: PASS in both.

- [ ] **Step 9: Commit**

```bash
git add backend/cases backend/tests/cases
git commit -m "fix(cases): optimistic-lock case updates so concurrent writes cannot be lost"
```

---

### Task 4: Bulk alert transitions audit every committed change

**Files:**
- Modify: `backend/api/routers/alerts.py:176-215`
- Test: `backend/tests/api/test_alerts_router.py`

**Interfaces:**
- Consumes: `record_alert_audit_event(...)` as already used by the single-alert route.
- Produces: no signature change; a mid-loop failure leaves no committed-but-unaudited transition.

- [ ] **Step 1: Write the failing test**

```python
def test_a_failure_midway_through_a_bulk_update_leaves_no_unaudited_transition() -> None:
    """Each transition commits on its own connection.

    If alert 3 raises, alerts 1 and 2 are already committed, but the router's
    audit loop runs only after the whole batch -- so material state changes
    exist with no audit_log row. On a compliance-facing platform that is the
    part that matters.
    """
    audit = RecordingAuditLogService()
    store = _StoreFailingOn("alert-3")
    client = _client(store=store, audit=audit)

    response = client.post(
        "/alerts/bulk/status",
        json={
            "knowledge_base_id": "kb-1",
            "alert_ids": ["alert-1", "alert-2", "alert-3"],
            "status": "acknowledged",
        },
    )

    assert response.status_code == 500
    transitioned = store.transitioned_ids
    audited = {e.resource_id for e in audit.events}
    assert audited == set(transitioned), (
        f"committed {sorted(transitioned)} but audited {sorted(audited)}"
    )
```

- [ ] **Step 2: Run the test and watch it fail**

Run: `cd backend && .venv/bin/pytest tests/api/test_alerts_router.py -k midway -v`

Expected: FAIL — two transitions committed, zero audited.

- [ ] **Step 3: Audit each transition as it lands**

Replace the after-the-loop audit block with a per-transition callback so the audit row is written immediately after the transition it describes, and let the exception propagate afterwards:

```python
    def _audit(alert: AlertSummary) -> None:
        before_record = before_records.get(alert.id)
        record_alert_audit_event(
            audit_service,
            knowledge_base_id=payload.knowledge_base_id,
            actor_user_id=user.user_id,
            actor_email=user.email,
            actor_roles=user.roles,
            action="alert.status.update",
            alert_id=alert.id,
            before=(
                {"status": before_record.status} if before_record is not None else None
            ),
            after={"status": alert.status},
            alert=alert,
            metadata={"bulk": True, "reason_present": payload.reason is not None},
        )

    response = build_alert_bulk_status_update_payload(
        payload=payload,
        store=store,
        actor=user.user_id,
        on_transitioned=_audit,
    )
    return response
```

Add the `on_transitioned: Callable[[AlertSummary], None] | None = None` parameter to `build_alert_bulk_status_update_payload` and invoke it immediately after each successful `store.transition_status`, inside the same `try` that already handles `AlertLifecycleError`.

- [ ] **Step 4: Run the tests and watch them pass**

Run: `cd backend && .venv/bin/pytest tests/api/test_alerts_router.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/alerts.py backend/tests/api/test_alerts_router.py
git commit -m "fix(api): audit each bulk alert transition as it commits"
```

---

### Task 5: The document warning counter is idempotent

**Files:**
- Modify: `backend/agent/coordinator.py:1577-1584`
- Test: `backend/tests/agent/test_coordinator.py`

**Interfaces:**
- Consumes: `KnowledgeBaseRepository.record_document_warnings(kb_id, doc_id, *, additional_count, reasons)`.
- Produces: `set_document_warnings(kb_id, doc_id, *, count, reasons)` on `KnowledgeBaseRepository` and both adapters — an absolute set, not an increment.

- [ ] **Step 1: Write the failing test**

```python
def test_replaying_a_parsed_event_does_not_inflate_the_warning_count() -> None:
    """The handler body runs again on retry and on redelivery.

    record_document_warnings is a blind read-modify-write at the very top of
    handle_documents_parsed, before the work that can fail. With
    RetryPolicy(max_retries=3) a transient chunker error runs the increment
    four times, so a document with 2 warnings reports 8 -- and the value is
    shown to users on the KB document inventory chip. Redis Streams is
    at-least-once, so redelivery reproduces this with no handler failure at
    all.
    """
    repository = InMemoryKnowledgeBaseRepository()
    _seed_document(repository, kb_id="kb-1", document_id="doc-1")
    event = _parsed_event(knowledge_base_id="kb-1", document_id="doc-1", warning_count=2)

    handle_documents_parsed(event, **_deps(kb_repository=repository))
    handle_documents_parsed(event, **_deps(kb_repository=repository))

    document = repository.get_document("kb-1", "doc-1")
    assert document is not None
    assert document.warning_count == 2
    assert document.warning_reasons == ["truncated table"]
```

- [ ] **Step 2: Run the test and watch it fail**

Run: `cd backend && .venv/bin/pytest tests/agent/test_coordinator.py -k replaying_a_parsed_event -v`

Expected: FAIL — `warning_count == 4` and the reasons list is doubled.

- [ ] **Step 3: Add the absolute setter to the protocol and both adapters**

The event carries the document's total warning count, not a delta, so the handler has everything it needs to state the value rather than accumulate it. In `knowledgebases/adapters/protocols.py`:

```python
    def set_document_warnings(
        self,
        knowledge_base_id: str,
        document_id: str,
        *,
        count: int,
        reasons: list[str],
    ) -> None:
        """Set a document's warning count and reasons to exactly these values.

        Absolute rather than additive so that replaying the event that carries
        them -- a retry, or an at-least-once redelivery -- converges instead of
        accumulating.
        """
        ...
```

Implement in the in-memory and Postgres adapters. The Postgres statement assigns rather than adds:

```sql
    UPDATE source_document_status
    SET warning_count = %s, warning_reasons = %s::jsonb
    WHERE knowledge_base_id = %s AND source_document_id = %s
```

- [ ] **Step 4: Call the absolute setter from the handler**

```python
        if kb_repository is not None and document.warning_count > 0:
            # Absolute, not additive: this handler body is re-entered on retry
            # and on at-least-once redelivery, and the event already carries
            # the document's total.
            kb_repository.set_document_warnings(
                document.knowledge_base_id,
                document.source_document_id,
                count=document.warning_count,
                reasons=list(document.warning_samples),
            )
```

- [ ] **Step 5: Run the tests and watch them pass**

Run: `cd backend && .venv/bin/pytest tests/agent/ tests/knowledgebases/ -v`

Expected: PASS. Leave `record_document_warnings` in place only if another caller still uses it — `grep -rn record_document_warnings backend --include='*.py'` — otherwise remove it so the additive path cannot be reintroduced.

- [ ] **Step 6: Commit**

```bash
git add backend/agent/coordinator.py backend/knowledgebases backend/tests
git commit -m "fix(agent): set document warning counts absolutely so replay cannot inflate them"
```

---

### Task 6: A stage timeout stops dead-lettering work that is still running

**Files:**
- Modify: `backend/agent/coordinator.py:4400-4420` (`run_handler_with_retry`)
- Test: `backend/tests/agent/test_coordinator.py`

**Interfaces:**
- Produces: on timeout, `run_handler_with_retry` raises `StageStillRunningError` rather than returning 0, so `drain_ingestion_events` leaves the delivery un-ACKed.

- [ ] **Step 1: Write the failing test**

```python
def test_a_timed_out_stage_is_not_acked_while_its_thread_is_still_running() -> None:
    """asyncio.to_thread cannot be cancelled; wait_for only abandons the await.

    Today the timeout marks the run FAILED, writes a DLQ record and returns,
    and drain_ingestion_events unconditionally ACKs -- then the orphaned thread
    finishes, writes its artifacts and publishes the next event. The pipeline
    marches on under a run permanently displaying FAILED, with a DLQ entry
    inviting a replay that would duplicate the work.

    A delivery whose handler is still running must not be acknowledged.
    """
    started = threading.Event()
    release = threading.Event()

    def slow_handler() -> int:
        started.set()
        release.wait(timeout=5)
        return 1

    policy = StagePolicy(retry_policy=RetryPolicy(max_retries=0), timeout_seconds=0.05)

    with pytest.raises(StageStillRunningError):
        asyncio.run(run_handler_with_retry(slow_handler, stage_policy=policy))

    assert started.is_set()
    release.set()
```

- [ ] **Step 2: Run the test and watch it fail**

Run: `cd backend && .venv/bin/pytest tests/agent/test_coordinator.py -k timed_out_stage -v`

Expected: FAIL — no exception is raised; the call returns and the caller would ACK.

- [ ] **Step 3: Add the exception**

In `backend/agent/exceptions.py`, alongside the existing `AgentError` hierarchy:

```python
class StageStillRunningError(AgentError):
    """A stage exceeded its timeout while its worker thread kept running.

    The thread cannot be cancelled, so the delivery must stay un-acknowledged:
    acknowledging it would let the pipeline advance under a run marked FAILED
    while the abandoned thread completes its writes.
    """
```

- [ ] **Step 4: Raise it instead of dead-lettering**

Replace the timeout branch:

```python
        except asyncio.TimeoutError as exc:
            # asyncio.to_thread submits to the default executor and a running
            # thread cannot be cancelled -- wait_for abandons the await, not
            # the work. Dead-lettering and ACKing here would duplicate that
            # work on replay, so refuse the ACK and let the delivery return to
            # the PEL, where reclaim (CHILI_EVENT_RECLAIM_MIN_IDLE_MS) governs
            # redelivery.
            raise StageStillRunningError(
                f"Stage exceeded its {policy.timeout_seconds}s timeout and its worker "
                "thread is still running; the delivery was left un-acknowledged."
            ) from exc
```

- [ ] **Step 5: Let the drain loop skip the ACK**

In `drain_ingestion_events`, catch `StageStillRunningError` around the handler call, log it at `error`, and continue **without** adding the delivery to the ackable set. Every other exception keeps its current path.

- [ ] **Step 6: Run the tests and watch them pass**

Run: `cd backend && .venv/bin/pytest tests/agent/ -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/agent backend/tests/agent
git commit -m "fix(agent): never ack a delivery whose handler thread is still running"
```

> **If this task overruns**, stop here and re-scope. Task 5's idempotency fix stands alone and is the higher-frequency defect; `StagePolicy.timeout_seconds` defaults to `None` and `CHILI_STAGE_POLICY_JSON` is set in no compose file or shipped pack, so this path is not reachable in any current deployment. Record the remainder as a follow-up story rather than half-landing a cancellation mechanism.

---

### Task 7: Worker dependencies are closed on hot-swap and shutdown

**Files:**
- Modify: `backend/agent/coordinator.py:463-493` (`WorkerDependencies`), `:1521-1540` (hot-swap), `:4919-4924` (`run_worker` teardown)
- Test: `backend/tests/agent/test_coordinator.py`

**Interfaces:**
- Produces: `WorkerDependencies.close() -> None`, safe to call on a partially built instance.

- [ ] **Step 1: Write the failing test**

```python
def test_a_domain_hot_swap_closes_the_dependencies_it_replaces() -> None:
    """build_worker_dependencies constructs a fresh connection provider, Neo4j
    driver, Qdrant client and two Redis clients on every call. The hot-swap
    replaces `current` and drops the old set on the floor -- `.close()` appears
    exactly once in the whole 4,946-line module, on the health server. Every
    config reload therefore leaks a full set of connections.
    """
    first = _fake_deps()
    second = _fake_deps()
    deps_iter = iter([second])

    handle_config_updated(
        _config_updated_event(pack_name="housing"),
        deps=first,
        state=_ConfigReloadState(),
        deps_factory=lambda: next(deps_iter),
    )

    assert first.closed is True
    assert second.closed is False
```

- [ ] **Step 2: Run the test and watch it fail**

Run: `cd backend && .venv/bin/pytest tests/agent/test_coordinator.py -k hot_swap_closes -v`

Expected: FAIL with `AttributeError: 'WorkerDependencies' object has no attribute 'close'`.

- [ ] **Step 3: Give WorkerDependencies a close()**

```python
    def close(self) -> None:
        """Release every resource this dependency set owns.

        Each call is suppressed independently so a half-built set -- one whose
        factory raised partway through -- is still fully releasable.
        """
        for closeable in (
            self.connection_provider,
            self.graph_repository,
            self.vector_store,
            self.event_bus,
            self.workflow_run_store,
        ):
            close = getattr(closeable, "close", None)
            if close is None:
                continue
            with contextlib.suppress(Exception):
                close()
```

- [ ] **Step 4: Close the replaced set, and the rejected one**

In the hot-swap `else` branch, close the outgoing dependencies immediately after the swap succeeds; in the `except` branch there is nothing to close because the factory raised. If the factory returned but the swap is abandoned for any later reason, close `rebuilt`:

```python
        else:
            previous = current
            current = rebuilt
            state.last_applied_correlation_id = latest.correlation_id
            previous.close()
```

- [ ] **Step 5: Close on shutdown too**

In `run_worker`'s `finally`, alongside the health server:

```python
    finally:
        if deps is not None:
            deps.close()
        if health_server is not None:
            health_server.close()
```

- [ ] **Step 6: Run the tests and watch them pass**

Run: `cd backend && .venv/bin/pytest tests/agent/ -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/agent/coordinator.py backend/tests/agent/test_coordinator.py
git commit -m "fix(agent): close worker dependencies on hot-swap and shutdown"
```

---

### Task 8: The records push route enforces the configured size budget

**Files:**
- Modify: `backend/api/routers/records.py:33-38` (`RecordPushRequest`), `:213-250` (`push_records`)
- Test: `backend/tests/api/test_records_router.py`

**Interfaces:**
- Consumes: `config.validation.max_file_size_mb`, already read by `upload_record_file`.
- Produces: `push_records` rejects with 413 before parsing an oversized body.

- [ ] **Step 1: Write the failing test**

```python
def test_an_oversized_push_body_is_rejected_before_it_is_parsed() -> None:
    """nginx sets client_max_body_size 0 in both configs on purpose --
    docs/security_checklist.md names the application config gate as 'the single
    authority'. But that gate names only the two read_upload_file_with_limit
    readers, and this route is not one of them: it takes an unbounded JSON array
    straight into memory.
    """
    client = _client(max_file_size_mb=1)
    oversized = {
        "feed_name": "claims_feed",
        "rows": [{"claim_id": f"c{i}", "amount": "1"} for i in range(200_000)],
    }

    response = client.post(
        "/records/kb-1/push",
        json=oversized,
        headers={"Content-Length": str(4 * 1024 * 1024)},
    )

    assert response.status_code == 413
    assert "size" in response.json()["detail"].lower()
```

- [ ] **Step 2: Run the test and watch it fail**

Run: `cd backend && .venv/bin/pytest tests/api/test_records_router.py -k oversized_push -v`

Expected: FAIL — 202, the whole array parsed into memory.

- [ ] **Step 3: Bound the model**

```python
class RecordPushRequest(BaseModel):
    feed_name: str = Field(min_length=1)
    # Upper bound as well as lower: this route parses the whole array into
    # memory and nginx is deliberately configured with client_max_body_size 0,
    # so the application is the only gate.
    rows: list[dict[str, object]] = Field(min_length=1, max_length=50_000)
```

- [ ] **Step 4: Reject on declared size before parsing**

Take `request: Request` in the handler and check the declared length against the configured budget first:

```python
    max_bytes = config.validation.max_file_size_mb * 1024 * 1024
    declared = request.headers.get("content-length")
    if declared is not None and int(declared) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"Request body exceeds the configured maximum size of "
                f"{config.validation.max_file_size_mb} MB."
            ),
        )
```

- [ ] **Step 5: Run the tests and watch them pass**

Run: `cd backend && .venv/bin/pytest tests/api/test_records_router.py -v`

Expected: PASS.

- [ ] **Step 6: Update the security checklist**

`docs/security_checklist.md` states the config gate is the single authority while naming only the two `read_upload_file_with_limit` readers. Add the push route to that list so the document matches the code.

- [ ] **Step 7: Commit**

```bash
git add backend/api/routers/records.py backend/tests/api/test_records_router.py docs/security_checklist.md
git commit -m "fix(api): enforce the configured size budget on the records push route"
```

---

### Task 9: Entitlement-filtered pagination returns a usable cursor

**Files:**
- Modify: `backend/api/routers/workflows.py:50-82`
- Test: `backend/tests/api/test_workflows_router.py`

**Interfaces:**
- Produces: the returned `next_offset` is the offset of the first unconsumed item, not the end of the underlying page.

> This was ranked low as unreachable — it needed `user.knowledge_base_ids` to be non-`None`, which never happened on the cookie path. Commit `b8e1ffef` fixed that, so this is now live for every entitled cookie session.

- [ ] **Step 1: Write the failing test**

```python
def test_pagination_does_not_drop_accessible_runs_inside_a_page() -> None:
    """The inner loop breaks when the limit is filled, but next_offset is still
    taken from the end of the underlying page -- so every accessible run after
    the one that filled the limit is skipped on the following request.
    """
    runs = [_run(f"wf-{i}", knowledge_base_id="kb-1") for i in range(10)]
    client = _client(
        runs=runs,
        user=User(user_id="a", roles=["analyst"], knowledge_base_ids=["kb-1"]),
    )

    first = client.get("/workflows?limit=3").json()
    assert [item["workflow_id"] for item in first["items"]] == ["wf-0", "wf-1", "wf-2"]

    second = client.get(f"/workflows?limit=3&offset={first['next_offset']}").json()
    assert [item["workflow_id"] for item in second["items"]] == ["wf-3", "wf-4", "wf-5"]
```

- [ ] **Step 2: Run the test and watch it fail**

Run: `cd backend && .venv/bin/pytest tests/api/test_workflows_router.py -k does_not_drop_accessible -v`

Expected: FAIL — the second page starts past `wf-3`.

- [ ] **Step 3: Track where the page was actually consumed to**

```python
        consumed = 0
        filled_early = False
        for index, run in enumerate(page.items):
            consumed = index + 1
            if _can_access_workflow(user, run.knowledge_base_id):
                runs.append(run)
                if len(runs) == limit:
                    filled_early = consumed < len(page.items)
                    break

        if filled_early:
            # Resume at the first item this page did not consume, not at the
            # page boundary -- everything between the two would be skipped.
            return runs, True, scan_offset + consumed

        has_more = page.has_more
        next_offset = page.next_offset if page.has_more else None
```

- [ ] **Step 4: Run the tests and watch them pass**

Run: `cd backend && .venv/bin/pytest tests/api/test_workflows_router.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/workflows.py backend/tests/api/test_workflows_router.py
git commit -m "fix(api): resume workflow pagination at the first unconsumed run"
```

---

### Task 10: The OIDC login flow is bound to the browser that started it

**Files:**
- Modify: `backend/api/routers/auth.py:120-145` (`login`), `:250-345` (`callback`)
- Test: `backend/tests/api/test_auth_router.py`

**Interfaces:**
- Produces: `LOGIN_STATE_COOKIE_NAME = "chiliai_login_state"`, set by `login`, required and cleared by `callback`.

- [ ] **Step 1: Write the failing test**

```python
def test_a_callback_without_the_login_cookie_is_rejected() -> None:
    """Login CSRF / session fixation.

    login() stores the PKCE state server-side and redirects with no cookie, and
    callback() looks the state up in the process-wide store with no reference
    to the requesting browser. An attacker who starts a login, captures their
    own `code`+`state`, and induces a victim's browser to hit the callback logs
    that victim into the ATTACKER's account -- the nonce binds the id_token to
    the authorization request, not to the user agent, so it validates fine.
    """
    client, session_store = _client_with_oidc()
    session_store.save_pkce_state(state="s-1", verifier="v-1", nonce="n-1")

    response = client.get(
        "/auth/callback?code=abc&state=s-1", follow_redirects=False
    )

    assert response.status_code == 400
    assert "login" in response.json()["detail"].lower()


def test_a_callback_whose_cookie_disagrees_with_the_state_is_rejected() -> None:
    client, session_store = _client_with_oidc()
    session_store.save_pkce_state(state="s-1", verifier="v-1", nonce="n-1")
    client.cookies.set("chiliai_login_state", "s-other")

    response = client.get(
        "/auth/callback?code=abc&state=s-1", follow_redirects=False
    )

    assert response.status_code == 400


def test_the_login_redirect_sets_the_binding_cookie() -> None:
    client, _ = _client_with_oidc()

    response = client.get("/auth/login", follow_redirects=False)

    assert response.status_code == 307
    cookie = response.headers["set-cookie"]
    assert "chiliai_login_state=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie
```

- [ ] **Step 2: Run the tests and watch them fail**

Run: `cd backend && .venv/bin/pytest tests/api/test_auth_router.py -k login_cookie or login_state -v`

Expected: FAIL — the callback returns a redirect and mints a session; no cookie is set on login.

- [ ] **Step 3: Set the binding cookie on login**

```python
LOGIN_STATE_COOKIE_NAME = "chiliai_login_state"
LOGIN_STATE_TTL_SECONDS = 600

    response = RedirectResponse(url=url, status_code=307)
    # Binds the authorization request to THIS browser. Without it the callback
    # accepts any state present in the process-wide store, so an attacker can
    # hand a victim their own code+state and log the victim into the attacker's
    # account. Lax survives the IdP's top-level redirect back to us.
    response.set_cookie(
        LOGIN_STATE_COOKIE_NAME,
        state,
        max_age=LOGIN_STATE_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=auth_config.cookie_secure,
        domain=auth_config.cookie_domain,
        path="/",
    )
    return response
```

- [ ] **Step 4: Require it in the callback**

Before `pop_pkce_state`, and clearing the cookie on every exit path:

```python
    bound_state = request.cookies.get(LOGIN_STATE_COOKIE_NAME)
    if bound_state is None or not secrets.compare_digest(bound_state, state):
        record_auth_audit_event(
            audit_service,
            action="auth.callback.failure",
            resource_type="auth_flow",
            resource_id="callback",
            before=None,
            after={"session_created": False},
            outcome="failure",
            failure_reason="login_state_not_bound_to_browser",
            client_ip=_request_client_ip(request),
            user_agent=_request_user_agent(request),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This login was not started in this browser.",
        )
```

On the success path, `response.delete_cookie(LOGIN_STATE_COOKIE_NAME, path="/")` alongside the session cookie.

- [ ] **Step 5: Run the tests and watch them pass**

Run: `cd backend && .venv/bin/pytest tests/api/test_auth_router.py tests/api/test_auth_middleware.py -v`

Expected: PASS. Existing callback tests will need the cookie set — update them; that is the point of the change, not a regression.

- [ ] **Step 6: Update the auth flow doc**

`docs/wiki/flows/auth-flow.md` step 2 describes the login redirect. Add the binding cookie so the documented flow matches the code.

- [ ] **Step 7: Commit**

```bash
git add backend/api/routers/auth.py backend/tests/api docs/wiki/flows/auth-flow.md
git commit -m "fix(auth): bind the OIDC login flow to the browser that started it"
```

---

### Task 11: alert_history gains the index its read path needs

**Files:**
- Create: `backend/database/migrations/versions/0029_alert_history_alert_id_ix.py`
- Modify: `backend/database/migrations/snapshots/head.sql` (regenerated, not hand-edited)
- Test: `backend/tests/database/test_migration_0029.py`

**Interfaces:**
- Produces: index `ix_alert_history_alert_id` on `alert_history (alert_id)`.

> Revision ids are capped at `varchar(32)` by `alembic_version.version_num`. `0029_alert_history_alert_id_ix` is 31 characters — at the limit the existing revisions use. A longer name fails at the very end of `alembic upgrade head` with `StringDataRightTruncation`.

- [ ] **Step 1: Write the failing test**

```python
def test_alert_detail_reads_are_index_backed(database_url: str) -> None:
    """_ALERT_GET_SQL and _ALERT_ACK_SQL match on alert_id alone, but every
    index on the table leads with knowledge_base_id: the PK is
    (knowledge_base_id, alert_id), ix_alert_history_entity leads with it, and
    so does ix_alert_history_kb_assignee. So the alert detail read and every
    triage action sequentially scan alert_history.
    """
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    with provider.connection() as conn:
        rows = conn.execute(
            "SELECT indexdef FROM pg_indexes WHERE tablename = 'alert_history'"
        ).fetchall()

    definitions = " ".join(str(row[0]).lower() for row in rows)
    assert "(alert_id)" in definitions, (
        f"no index leads with alert_id; indexes present: {definitions}"
    )
```

- [ ] **Step 2: Run the test and watch it fail**

Run: `cd backend && DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest tests/database/test_migration_0029.py -v`

Expected: FAIL — only the three `knowledge_base_id`-leading indexes are listed.

- [ ] **Step 3: Write the migration**

```python
"""Index alert_history by alert_id for the unscoped detail read.

``_ALERT_GET_SQL`` and ``_ALERT_ACK_SQL`` match on ``alert_id`` alone, but
every existing index leads with ``knowledge_base_id``, so both sequentially
scan. UNIQUE rather than a plain index because the adapter's own comment
already assumes global uniqueness ("a UUID minted upstream and globally unique
in practice") -- this enforces the assumption instead of restating it.

Revision ID: 0029_alert_history_alert_id_ix
Revises: 0028_derived_signal_interval_ix
"""

from __future__ import annotations

from alembic import op

revision: str = "0029_alert_history_alert_id_ix"
down_revision: str | None = "0028_derived_signal_interval_ix"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX ix_alert_history_alert_id ON alert_history (alert_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_alert_history_alert_id")
```

- [ ] **Step 4: Apply and verify**

Run:
```bash
cd backend && DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/alembic upgrade head
DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest tests/database/test_migration_0029.py -v
```

Expected: PASS.

> If `CREATE UNIQUE INDEX` fails on a populated database, the uniqueness assumption in the adapter's comment is false and that is a finding in its own right. Fall back to a non-unique index, and report the duplicate `alert_id`s rather than silently weakening the constraint.

- [ ] **Step 5: Regenerate the schema snapshot**

Run: `make migrate-snapshot` from the repo root. CI diffs `snapshots/head.sql` and fails on drift. Never hand-edit it.

- [ ] **Step 6: Update the database README**

`backend/database/README.md` names the head revision and table count. Update the head to `0029_alert_history_alert_id_ix`; the table count is unchanged.

- [ ] **Step 7: Commit**

```bash
git add backend/database backend/tests/database/test_migration_0029.py
git commit -m "perf(database): index alert_history by alert_id for the detail read path"
```

---

### Task 12: Migration 0020's downgrade can run on a populated database

**Files:**
- Modify: `backend/database/migrations/versions/0020_playbook_snapshot_kb_scope.py:58-84`
- Test: `backend/tests/database/test_migration_0020.py`

**Interfaces:**
- Produces: `downgrade()` collapses per-KB duplicates before narrowing the primary key.

- [ ] **Step 1: Write the failing test**

```python
def test_downgrade_survives_snapshots_from_two_knowledge_bases(
    database_url: str,
) -> None:
    """The downgrade adds PRIMARY KEY (domain_name, playbook_id, version) while
    the per-KB duplicate rows the upgrade allowed are still present, then drops
    knowledge_base_id only afterwards. On any populated database that ADD
    CONSTRAINT fails.

    tests/database/test_migrations.py only ever downgrades a freshly migrated
    EMPTY database, which is why this has never been caught.
    """
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    _seed_snapshot(provider, knowledge_base_id="kb-a", playbook_id="p1", version=1)
    _seed_snapshot(provider, knowledge_base_id="kb-b", playbook_id="p1", version=1)

    subprocess.run(
        [".venv/bin/alembic", "downgrade", "0019_fraud_playbooks"],
        cwd="backend",
        check=True,
    )

    with provider.connection() as conn:
        remaining = conn.execute(
            "SELECT count(*) FROM fraud_playbook_snapshots"
        ).fetchone()
    assert remaining is not None
    assert int(remaining[0]) == 1
```

- [ ] **Step 2: Run the test and watch it fail**

Run: `cd backend && DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest tests/database/test_migration_0020.py -k two_knowledge_bases -v`

Expected: FAIL — alembic exits non-zero, `could not create unique index "pk_fraud_playbook_snapshots"`.

- [ ] **Step 3: Collapse duplicates before narrowing the key**

Immediately before the `ADD CONSTRAINT` in `downgrade()`:

```python
    # The upgrade widened uniqueness to include knowledge_base_id, so a
    # populated table can legitimately hold one row per KB for the same
    # (domain_name, playbook_id, version). Narrowing the key back cannot
    # succeed while those rows exist. Keep the lowest knowledge_base_id
    # deterministically and drop the rest -- the column is about to be dropped
    # anyway, so the surviving row is the only one the narrowed schema can
    # represent.
    op.execute(
        """
        DELETE FROM fraud_playbook_snapshots a
        USING fraud_playbook_snapshots b
        WHERE a.domain_name = b.domain_name
          AND a.playbook_id = b.playbook_id
          AND a.version = b.version
          AND a.knowledge_base_id > b.knowledge_base_id
        """
    )
```

- [ ] **Step 4: Run the test and watch it pass**

Run: `cd backend && DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest tests/database/ -v`

Expected: PASS. Then confirm the full cycle still works: `make migrate-snapshot` replays `upgrade head` → `downgrade base` → `upgrade head` and must report `OK`.

- [ ] **Step 5: Commit**

```bash
git add backend/database/migrations/versions/0020_playbook_snapshot_kb_scope.py backend/tests/database/test_migration_0020.py
git commit -m "fix(database): make migration 0020's downgrade runnable on a populated database"
```

---

### Task 13: Conversation ordering reflects when the conversation changed

**Files:**
- Modify: `backend/conversations/service.py:45-57`, `backend/conversations/adapters/in_memory.py:24-27`
- Test: `backend/tests/conversations/test_service.py`, `backend/tests/conversations/test_postgres_store.py`

**Interfaces:**
- Produces: `ConversationRepository.save` persists exactly the `Conversation` it is given; the service owns `updated_at`.

- [ ] **Step 1: Write the failing test**

```python
def test_appending_messages_advances_updated_at_in_every_adapter() -> None:
    """The in-memory adapter re-stamps updated_at inside save(); the Postgres
    one writes back whatever it was handed. So `/chat/conversations` ordered
    "most recently updated first" is really ordered by creation time -- but
    only in production, because the adapter the tests use hides it.

    The service owns the timestamp so both adapters agree.
    """
    for repository in (InMemoryConversationRepository(), _postgres_repository()):
        service = create_conversation_service(repository)
        created = service.create(_new_conversation())
        original = created.updated_at

        appended = service.append_messages(created.id, [_message("hello")])

        assert appended.updated_at > original, f"{type(repository).__name__} did not advance updated_at"
        reloaded = repository.get(created.id)
        assert reloaded is not None
        assert reloaded.updated_at == appended.updated_at
```

- [ ] **Step 2: Run the test and watch it fail**

Run: `cd backend && DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest tests/conversations/ -k advances_updated_at -v`

Expected: FAIL on the Postgres repository — `updated_at` is unchanged.

- [ ] **Step 3: Move the timestamp into the service**

```python
        updated = existing.model_copy(
            update={
                "messages": [*existing.messages, *messages],
                # Owned here rather than in an adapter: the in-memory adapter
                # used to re-stamp this inside save() and the Postgres one did
                # not, so "most recently updated first" was really creation
                # order -- in production only.
                "updated_at": utc_now(),
            }
        )
        return self._repository.save(updated)
```

- [ ] **Step 4: Stop the in-memory adapter re-stamping**

```python
    def save(self, conversation: Conversation) -> Conversation:
        self._conversations[conversation.id] = conversation
        return conversation
```

- [ ] **Step 5: Run the tests and watch them pass**

Run: `cd backend && DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest tests/conversations/ -v`

Expected: PASS for both adapters.

- [ ] **Step 6: Commit**

```bash
git add backend/conversations backend/tests/conversations
git commit -m "fix(conversations): let the service own updated_at so both adapters agree"
```

---

## Sprint close-out

- [ ] **Run every gate**

```bash
cd backend && .venv/bin/pyright
.venv/bin/ruff check --no-cache .
DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest --cov -q
cd .. && make check
```

Expected: pyright 0 errors, ruff clean, pytest green at ≥ 85% coverage, `make check` green.

- [ ] **Verify against a running stack, not just a green suite**

`make dev`, then exercise each closed finding: two concurrent alert transitions, a bulk update, a config reload (`worker` logs should show dependencies rebuilt with no connection growth), an oversized push, a login without the binding cookie.

- [ ] **Update the audit artifact** at the URL in the session record so the closed set is accurate.

- [ ] **Write the sprint doc** `docs/project/planning/sprints/2026-35.md` in the format of `2026-28.md`: committed table, sequencing, DoD, outcome.
