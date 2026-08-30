# Sprint 2026-36 — Stabilisation: Close What 2026-35 Broke or Left Half-Done

**Date:** 2026-08-28
**Status:** Approved design, pending implementation plan
**Predecessor:** sprint `2026-35` (`docs/project/planning/sprints/2026-35.md`), merged as `824072db`
**Scope decision:** regressions and half-closed work only. The audit burn-down remainder (`BL-059`–`BL-066`) moves to `2026-37`.

## Why

Sprint 2026-35 closed 12 medium-severity audit findings and shipped clean by every
gate. Its own whole-branch review then found that the work had introduced or left
open a set of defects of exactly the kind the audit existed to find — silent,
green under test, and in three cases now running in production.

That is not a failure of the sprint so much as evidence about where defects
concentrate. Three facts shaped this plan:

1. **The one commit that skipped review produced all three criticals.** Thirteen
   task commits went through independent spec-and-quality review and produced
   none. `b8e1ffef` did not, and its regression silently dropped fraud alerts for
   every entity after the first in a batch.
2. **Every regression here is an adapter-parity defect or a half-applied fix.**
   `api.30`, `conversations.06` and `monitoring.22` all exist because two adapters
   behind one protocol diverged and the in-memory one is what the tests saw —
   which the 2026-08-25 audit named as its *first* recurring theme, and which this
   sprint's predecessor re-created three times while fixing it elsewhere.
3. **Findings evaporate unless they become stories immediately.** Four Important
   findings from the final review were never converted and existed nowhere on
   disk once the working notes were cleared; they were recoverable only by
   accident. `api.30`, `records.18`, `conversations.06` and `cicd.22` are those
   four.

## Scope

**In scope — 6 stories, 21 SP.** Everything sprint 2026-35 broke, left half-done,
or shipped with a defect.

**Capacity is deliberately under the 25 SP baseline.** 2026-35 committed 26 SP and
every one of its 13 tasks surfaced something unplanned: three of the plan's
prescribed fixes were wrong, three of its tests could not have failed for the
right reason, and the final review found a critical regression. Budgeting to
capacity again would ignore that evidence.

## Stories

| ID | Story | SP | Origin |
|---|---|---:|---|
| `api.30` | Pagination correct for both workflow-run stores | 3 | Defect shipped by 2026-35 Task 9, live on `prod` |
| `monitoring.22` | Signal a lost write race instead of returning 500 | 5 | Contract divergence created across Tasks 1–4 |
| `conversations.06` | Guard the conversation read-modify-write | 3 | The one race Task 13 touched and left open |
| `records.18` | Atomic rollback; stop masking the publish error | 3 | Task 7's rollback is two transactions |
| `agent.22` | Per-stage document warning accounting | 5 | Task 5 closed half its finding |
| `cicd.22` | Gate every live-stack skip, not just the probe | 2 | Gap in the e2e gating Task 10 introduced |
| | **Total** | **21** | |

### `api.30` is the only story fixing a defect currently in production

`backend/api/routers/workflows.py:77` returns `scan_offset + consumed`, counting
items in the **filtered** page. That matches `InMemoryWorkflowRunStore`
(`offset + len(items)`, filtered) and not `RedisWorkflowRunStore`
(`index_position + 1`, an offset into the **unfiltered** ZSET). Redis is the
production store, so a run can be returned on two consecutive pages or skipped
entirely. Every test in `tests/api/test_workflows_router.py` uses the in-memory
store, which is why it passed review and shipped.

### `monitoring.22` is the sprint's design story and gates one other

The codebase currently holds three different answers to "what happens when you
lose a write race": `cases` raises a dedicated `CaseConcurrentModificationError`
and locks its in-memory adapter; `monitoring` overloads `MonitoringSourceError`
for both a lost race and a generic database failure, and its in-memory adapter has
no compare-and-set at all; and no caller anywhere converts either into a 409 —
every path produces an opaque 500. That decision should be made once.

`conversations.06` must adopt whatever `monitoring.22` settles rather than adding
a fourth contract, so it is sequenced after it.

## Sequencing

`api.30` first — it is the only production defect.

`monitoring.22` → `conversations.06` is the sprint's one hard dependency.

`records.18`, `agent.22` and `cicd.22` are independent. `cicd.22` pairs naturally
with running the CI backend job to completion for the first time: that job has
never finished, because the wait step it depended on could only time out until it
was fixed on the same branch, and its `DATABASE_URL` was pointed at `chili_test`
only in `f265a6ef`.

## Definition of done

Standing repo gates: `pyright` strict 0 errors, `ruff check --no-cache .` clean,
coverage ≥ 85%, contract regeneration on any frontend-consumed Pydantic change,
live verification against `make dev`, full-stack e2e with no mocked subject.

**Carried from 2026-35 because it worked:** every story's test must be watched
failing against the real defect before the fix lands. That clause caught three
tests in the previous plan that could not have gone RED, and it is the reason the
predecessor's regressions were found at all.

**Two additions, both earned in 2026-35:**

1. **Adapter parity is a test requirement, not a code requirement.** Three of the
   six stories exist because two adapters diverged and only the in-memory one was
   exercised. Any fix touching one adapter must be tested against both,
   parametrised, with the non-default adapter genuinely executing — a skipped half
   and a passing half are indistinguishable in a pytest summary line.
2. **A finding becomes a backlog story when it is raised, not at close-out.** Four
   Important findings were lost this way and recovered only by accident.

**Per story:** the cited defect no longer reproduces, verified against a running
stack rather than only a green suite.

**Per sprint:** every committed story closed; the CI backend job run to completion
at least once.

## Deferred, recorded explicitly

- **`events.17`** — reclaim threshold vs unbounded stage runtime. A real 2026-35
  regression (`b8e1ffef` enabled reclaim; Task 6 made stage wall-clock unbounded),
  but the exposure is **k8s/helm only**: `replicas: 2` is shipped there and
  `CHILI_EVENT_RECLAIM_MIN_IDLE_MS` is set nowhere, while both compose files are
  single-worker and safe. It also needs a design decision about bounding stage
  runtime. → `2026-37`.
- **`BL-059`–`BL-066`** — the entire audit burn-down remainder, 27 SP: RAG scope
  and citation honesty, streaming transcript persistence, KB-switch state reset,
  alert-feed search and evidence-review errors, test honesty, module boundary
  restoration, unwired config, contract leftovers. → `2026-37`, which needs its
  own capacity conversation.
- **The 4 domain-genericity findings** — Air Force housing vocabulary in
  domain-agnostic layers. Still an unstarted initiative needing its own spec.

## Known unverified

Live-stack verification has not run for 2026-35 or this sprint's predecessor work.
`make dev` requires a Neo4j port held by an unrelated project on the development
host. Two things remain unverified against a running system: the keep-alive
behaviour of `_SizeLimitedPushRoute` after aborting mid-`receive()` under real
uvicorn (the test transport is in-process, not TCP/h11), and the end-to-end
exercise of each finding 2026-35 closed.

## Process change

Every commit gets an independent review, including the controller's own. The
evidence is unambiguous and is recorded here so it is not relearned: the single
commit that skipped review produced three critical regressions, one of which
reached production and silently dropped fraud alerts.

## Open questions

None. The scope decision — regressions only, under capacity, burn-down remainder
deferred — is settled and should not be relitigated during planning.
