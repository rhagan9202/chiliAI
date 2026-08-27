# Audit Burn-Down — Design Spec

**Date:** 2026-08-27
**Status:** Approved design, pending implementation plan
**Scope decision:** Two sprints (`2026-35`, `2026-36`) closing the 27 remaining actionable
findings from the 2026-08-25 full-codebase audit. The 4 domain-genericity findings are
deferred to their own initiative.
**Predecessor:** commit `b8e1ffef` closed the audit's 2 criticals and 8 highs.

## Why

A nine-agent audit of the whole tree on 2026-08-25 raised 42 findings; triage kept 41 (39
confirmed, 2 likely). Commit `b8e1ffef` closed the two criticals and all eight highs. The
remaining 31 are 22 medium and 9 low.

The audit's value was not the individual defects but what it showed about how they got
there. Every one of the six quality gates was green the whole time — `pyright --strict` at
zero errors, ruff, `tsc`, eslint, 1084 frontend tests, 96% backend coverage. The two
criticals both had tests sitting over them that could not fail: one overrode the code under
test with a hand-built object, the other used a fake connection provider that executed no
SQL and therefore could never observe which row an `ORDER BY` selects.

That is the through-line for this burn-down. Several of these findings exist because a test
proved something other than what it claimed, and a fix that does not correct the test leaves
the next defect equally invisible.

## Scope

**In scope — 27 findings across 14 stories.** Everything whose failure mode is silent data
corruption, a security hole, a wrong answer, a stuck UI, or a test that cannot fail.

**Deferred — 4 findings.** The domain-genericity cluster: Air Force housing vocabulary
leaking into layers specified to be domain-agnostic. These are not defects with a patch;
they need a design decision about how domain packs carry vocabulary, and that decision
belongs in its own spec.

- `backend/api/_housing_read_model.py:175` — 707 lines of Air Force housing domain business logic live inside the api/ gateway, which is specified to hold no business logic
- `backend/config/schema.py:677` — Air Force housing vocabulary (UH/MFH, majcom, installation) is hardcoded as closed Literal types in the generic DomainConfig schema, scorecards module and API contracts
- `chili_app/src/components/investigation/IdentityPanel.tsx:18` — The identity panel's sensitive-reference redaction list hardcodes Medicare/PHI vocabulary and the sole production caller never overrides it
- `chili_app/src/data/airForceInstallations.ts:18` — 90+ Air Force installations with coordinates are hardcoded as a TypeScript module compiled into the shared SPA bundle

Architecture rule 3 is well observed for the exemplar domain — `shared/types.py` is genuinely
clean. It was not applied to the second domain onboarded, which erodes the reconfigurability
claim at exactly the point that claim is supposed to be proven. That is worth a deliberate
design, not an opportunistic refactor inside a defect sprint.

**Explicitly not carried forward**, decided during the critical/high fixes:

- ACK-per-delivery in the Redis consume loop. Defaulting `reclaim_min_idle_ms` to 60 s means
  stranded entries now redeliver, which substantially mitigates the batch-flush strand. The
  remaining change is a riskier edit to the hot consume path.
- Broadening the `medicare_fraud`-only gates on `analytics.peer_context` and
  `evidence.checklist.generate`. That is a product decision about capability exposure, unlike
  `af_housing`, which was a string matching no shipped pack.

## What the audit did not reach

Absence from this spec means unexamined, not clean. No auditor owned `graph/` or
`vectorstore/` Cypher and query construction or their multi-tenant filtering; `execution/`;
`embeddings/`; monitoring threshold evaluation; or most per-module persistence adapters
(their DDL was read, their adapters were not). A second audit pass over those surfaces would
likely add findings and should be scheduled independently of this burn-down.

## Sprint frame

Two-week sprints on the existing ISO-week cadence, sized against sprint `2026-28`'s 25 SP
baseline.

| Sprint | Dates | SP | Theme |
|---|---|---:|---|
| `2026-35` | 2026-08-27 → 2026-09-09 | 26 | Correctness and security |
| `2026-36` | 2026-09-10 → 2026-09-23 | 27 | RAG truth, frontend state, test honesty, layering |

Sprint 1 takes every finding whose failure is silent data corruption or a security hole.
Sprint 2 takes every finding whose failure is a wrong answer, a stuck UI, or a test that
cannot fail. Story ids continue from `BL-052`.

### Sprint 2026-35

| ID | Story | SP | Findings |
|---|---|---:|---:|
| `BL-053` | Concurrency-safe writes at the persistence boundary | 8 | 3 |
| `BL-054` | Replayable event handlers under at-least-once delivery | 5 | 2 |
| `BL-055` | Worker dependency-graph lifecycle on domain hot-swap | 2 | 1 |
| `BL-056` | Gateway request limits | 3 | 2 |
| `BL-057` | Bind the OIDC login flow to the browser | 3 | 1 |
| `BL-058` | Postgres read-path and migration integrity | 5 | 3 |
| | **Total** | **26** | **12** |

### Sprint 2026-36

| ID | Story | SP | Findings |
|---|---|---:|---:|
| `BL-059` | RAG answers tell the truth about scope and citations | 5 | 2 |
| `BL-060` | Streaming chat persists its transcript | 3 | 1 |
| `BL-061` | KB switch resets dependent page state | 3 | 2 |
| `BL-062` | Alert-feed search and evidence-review error surfacing | 2 | 2 |
| `BL-063` | Tests that can actually fail | 4 | 2 |
| `BL-064` | Module boundary restoration | 4 | 2 |
| `BL-065` | Declared-but-unwired config | 3 | 2 |
| `BL-066` | Contract and recovery leftovers | 3 | 2 |
| | **Total** | **27** | **15** |

## Story cut

Stories group by **shared fix**, not by directory. Three groupings are load-bearing rather
than filing convenience: `BL-053` is one compare-and-set pattern at three call sites,
`BL-054` is the audit's non-idempotent-write theme, and `BL-061` is a single root cause
surfacing on two pages. Grouping this way means one design decision per story instead of
re-deciding it at each site.

Where a group is merely two small leftovers sharing no fix — `BL-062`, `BL-066` — the spec
says so rather than inventing a theme.

### BL-053 — Concurrency-safe writes at the persistence boundary

**8 SP** · sprint 2026-35

Findings closed:

- `backend/monitoring/adapters/postgres.py:424` — *medium* — Alert lifecycle validation is a TOCTOU: SELECT-then-UPDATE with no row lock lets forbidden transitions commit and writes a false audit trail
  Failure: Alert X is 'investigating'. T1 transitions to 'resolved', T2 to 'dismissed'. Both
  read status='investigating' and both pass validate_alert_transition. T1 commits
  'resolved'. T2's UPDATE, blocked on the row lock, re-evaluates its WHERE against the now-
  resolved row and commits 'dismissed' — a transition ALERT_TRANSITIONS['resolved'] ==
  {'open'} explicitly forbids. Worse, T2 appends a triage event claiming
  from_status='investigating', so the persisted triage_history is a false audit trail on a
  compliance-facing platform. The same hole exists in acknowledge.

- `backend/cases/adapters/postgres.py:43` — *medium* — Case updates are unversioned read-modify-write over whole jsonb arrays, silently dropping concurrent alert attachments and analyst feedback
  Failure: Two analysts attach different alerts to case C at the same time. Both
  CaseService.attach_alert calls read alert_ids=['A'], both pass the duplicate check, and
  both issue _UPDATE_SQL, which overwrites the entire alert_ids and timeline jsonb columns
  from their stale in-process copies. Whoever commits second wins: one alert's attachment
  and its 'Alert attached' timeline entry are gone, with a 200 returned to the loser
  claiming success. The same pattern loses an AnalystFeedback entry when two add_feedback
  calls interleave.

- `backend/api/routers/alerts.py:188` — *medium* — Bulk alert status update commits per alert and audits only after the whole loop, so a mid-loop failure commits transitions with no audit record
  Failure: POST /alerts/bulk/status with 200 alert ids (no cap — alert_ids has min_length
  only). The builder calls store.transition_status once per alert, each opening its own
  pooled connection and committing independently. If alert 120 trips the session
  statement_timeout, MonitoringSourceError is raised; the builder catches only
  AlertLifecycleError, so it escapes as a 500. Alerts 1-119 are already committed as
  transitioned, but the router's audit loop never runs, so zero audit_log rows exist for 119
  material state changes. Even on the success path, all N transitions commit before the
  first audit row is written.

**Why these are one story.** One compare-and-set pattern at three call sites. The alert transition and the case update are both SELECT-then-write with no guard; the bulk endpoint commits per alert and audits only after the loop, so a mid-loop failure leaves committed transitions with no audit record. Splitting these would mean deciding the same locking approach three times.

**Risk.** The tests are harder than the fix: proving a lost update needs two real connections racing on one row. Produces migration `0029`.

### BL-054 — Replayable event handlers under at-least-once delivery

**5 SP** · sprint 2026-35

Findings closed:

- `backend/agent/coordinator.py:1577` — *medium* — Retrying a documents.parsed / entities.extracted handler re-applies the non-idempotent document warning counter
  Failure: A DocumentsParsedEvent carries warning_count=2. handle_documents_parsed records
  the warnings at the very top of the per-document loop, then chunk_document or the
  following put_bytes raises a transient error (MinIO blip, chunker timeout).
  run_handler_with_retry re-invokes the WHOLE handler with RetryPolicy(max_retries=3), so
  the increment runs 4 times and the stored warning_count is 8 with the same reason repeated
  four times. At-least-once redelivery (a reclaimed PEL entry) produces the same corruption
  with no handler failure. The inflated value is surfaced to users via the KB document
  inventory warning chip.

- `backend/agent/coordinator.py:4403` — *medium* — A stage timeout dead-letters and ACKs the event while the handler thread keeps running and completes its writes and publishes
  Failure: With a stage timeout configured via CHILI_STAGE_POLICY_JSON, asyncio.wait_for
  cancels the awaiting task but asyncio.to_thread submits to the default executor and a
  running thread cannot be cancelled. run_handler_with_retry breaks immediately (timeouts
  get zero retries), marks the run FAILED, publishes a DLQ entry and returns 0;
  drain_ingestion_events then unconditionally ACKs the delivery. Seconds later the orphaned
  thread finishes, writes its artifacts and publishes the next event — the pipeline marches
  on under a run permanently displaying FAILED, with a DLQ record inviting a replay that
  would duplicate the work. Hung handlers also permanently consume executor threads (bounded
  at min(32, cpu+4)). The DLQ error_message is the empty string because str(TimeoutError())
  is ''.

**Why these are one story.** Both are the audit's recurring theme: a non-idempotent write inside a region that is retried. Redis Streams is at-least-once, so a handler body must be replayable. The warning counter is a blind read-modify-write at the top of a retried handler; the stage timeout ACKs and dead-letters while the handler thread keeps running and completes its writes.

**Risk.** **Highest-risk story in either sprint.** The timeout half needs cooperative cancellation — a thread cannot be safely killed mid-write. `StagePolicy.timeout_seconds` defaults to `None` and `CHILI_STAGE_POLICY_JSON` is set in no compose file or pack, so reachability is low today. If it slips, land the idempotency half alone and re-scope the remainder.

### BL-055 — Worker dependency-graph lifecycle on domain hot-swap

**2 SP** · sprint 2026-35

Findings closed:

- `backend/agent/coordinator.py:1521` — *medium* — Domain hot-swap rebuilds the whole worker dependency graph and drops the previous one without closing it
  Failure: An operator switches domain packs; the worker's apply_pending_config_updates
  calls build_worker_dependencies(), which opens a fresh Postgres pool (min_size=10, opened
  eagerly with wait=True), two Redis clients, a Neo4j driver and a Qdrant client, then does
  `current = rebuilt` and returns. The old WorkerDependencies is garbage with none of those
  closed, and neither a psycopg pool nor a Neo4j driver is released deterministically by GC.
  Ten pack switches leave ~100 idle Postgres connections held by one worker; against the
  default max_connections=100 shared with the API, the next pool creation fails with
  DatabaseConnectionError, which is caught and logged as 'CONFIG RELOAD FAILED' — so the
  worker silently stops honouring config switches while holding the connections that caused
  it. Process shutdown leaks the same way.

**Why these are one story.** Standalone resource-lifecycle defect with no shared fix.

### BL-056 — Gateway request limits

**3 SP** · sprint 2026-35

Findings closed:

- `backend/api/routers/records.py:219` — *medium* — POST /records/{kb}/push accepts an unbounded JSON body, bypassing the configured upload size limit that nginx was deliberately stripped of
  Failure: A caller with the analyst role POSTs a multi-gigabyte JSON array to
  /records/kb-1/push. Starlette buffers the entire body in memory before Pydantic
  validation, and nothing in the handler caps it, so the API container's RSS grows to the
  body size and it is OOM-killed for every tenant. The sibling file route rejects the same
  volume with 413 at validation.max_file_size_mb.

- `backend/api/routers/workflows.py:69` — *low* — Entitlement-filtered workflow pagination drops accessible runs that fall past the limit inside a page
  Failure: A principal restricted to one KB calls GET /workflows?limit=2. Page 2 returns
  [run-C, run-D], both accessible; C fills the limit and the inner loop breaks with D
  unconsumed, yet next_offset is reported as the end of the WHOLE page. The client's follow-
  up request starts past D, so a run the analyst is entitled to see never appears in any
  page of the pipeline-status UI.

**Why these are one story.** Both are request-boundary limits missing at the gateway: an unbounded body that bypasses the configured upload cap, and a paginator that filters by entitlement after slicing, so accessible runs falling past the limit inside a page are dropped.

### BL-057 — Bind the OIDC login flow to the browser

**3 SP** · sprint 2026-35

Findings closed:

- `backend/api/routers/auth.py:142` — *medium* — OIDC login flow does not bind the PKCE/state record to the browser, enabling login CSRF (session fixation into an attacker's account)
  Failure: An attacker starts GET /auth/login in their own browser, authenticates at the IdP
  as themselves, and captures the final callback URL without following it. They induce a
  victim analyst to load that URL. The callback pops the state from the shared server-side
  store, exchanges the attacker's code, mints a session for the attacker's sub, and sets
  chiliai_session on the VICTIM's browser followed by a 307 to /. The victim then works
  inside the attacker's identity: documents they upload and cases they create land in the
  attacker's account and KBs, readable by the attacker later.

**Why these are one story.** Standalone. Sits on the auth flow changed by the audit-fix commit, so it builds on that rather than conflicting.

### BL-058 — Postgres read-path and migration integrity

**5 SP** · sprint 2026-35

Findings closed:

- `backend/monitoring/adapters/postgres.py:65` — *medium* — alert_history has no index leading with alert_id, so every alert detail read and triage action sequentially scans the table
  Failure: _ALERT_GET_SQL filters on alert_id alone while every existing index leads with
  knowledge_base_id, so a btree prefix match is impossible and get_alert() is a full
  sequential scan. It sits on the hot path of acknowledge, assign, status and bulk
  operations. A bulk status update over 50 alert ids performs 100 sequential scans before
  doing any work, and each blocks the asyncio event loop because the async router handlers
  call synchronous psycopg.

- `backend/database/migrations/versions/0020_playbook_snapshot_kb_scope.py:66` — *low* — Migration 0020's downgrade re-adds a primary key that duplicate rows make impossible, so it cannot run on any populated database
  Failure: 0020 exists precisely to let two knowledge bases hold the same playbook, widening
  the PK to include knowledge_base_id. Playbook snapshots are seeded from the shared
  DomainConfig per KB, so two KBs on the same pack deterministically produce rows with
  identical (domain_name, playbook_id, version). alembic downgrade 0019 drops the composite
  PK and re-adds PRIMARY KEY (domain_name, playbook_id, version), which aborts on the
  duplicate key. The transaction rolls back and the downgrade is unavailable — exactly when
  an operator needs it during a rollback.

- `backend/conversations/service.py:50` — *medium* — Conversation updated_at never advances in Postgres, so the "most recently updated first" list is ordered by creation time
  Failure: Create conversation A, then B, then post a message to A. append_messages builds
  existing.model_copy(update={'messages': ...}) carrying the original updated_at, and the
  Postgres upsert writes `updated_at = EXCLUDED.updated_at` — the stale value. GET
  /conversations?knowledge_base_id=... orders by updated_at DESC and returns B first even
  though A is the thread the analyst was just in, and A's updated_at in the summary response
  reports its creation time forever. The in-memory adapter silently re-stamps the timestamp,
  so tests never catch the divergence.

**Why these are one story.** Three Postgres-layer defects with no behavioural overlap but a shared migration/verification setup: an index the read path needs, a downgrade that cannot run, and an adapter whose semantics diverge from its in-memory sibling.

**Risk.** Produces migration `0030`; must be ordered after BL-053 so revision ids do not collide.

### BL-059 — RAG answers tell the truth about scope and citations

**5 SP** · sprint 2026-36

Findings closed:

- `backend/rag/service.py:129` — *medium* — RagService retrieves from knowledge_base_ids[0] only while reporting the full scope, silently dropping the reference (policy) KB
  Failure: A domain pack sets default_reference_kb_id. resolve_kb_scope returns [primary,
  reference] and the router builds RagQueryRequest with both ids, but _prepare_state embeds
  and retrieves against knowledge_base_ids[0] only, and _expand_graph_context and
  _build_generation_request do the same. Not one chunk from the policy KB is searched, so
  the LLM answers 'the context is insufficient' about a fully-ingested policy — while
  RagQueryResponse.knowledge_base_ids echoes BOTH ids, so the API and any UI or audit
  consumer records that the answer spanned the policy KB.

- `backend/rag/service.py:78` — *medium* — RAG citations are built from the full retrieved set, including evidence the context budget dropped or truncated before the LLM saw it
  Failure: With a large configured chunk_size, ServiceAnswerGenerator.generate computes a
  character budget, and _fit_context_to_budget admits only some retrieved chunks — one
  arriving truncated mid-sentence, the rest dropped. That trimming happens inside
  api/_rag_bridges.py and is never reported back. RagService.answer then builds citations
  from the ORIGINAL untrimmed list, so the response and the SSE citations array attribute
  the answer to sources the model never received a character of, with snippets taken from
  the untruncated content. On a fraud platform where citations are the evidence-pack audit
  trail, that is a fabricated provenance record.

**Why these are one story.** Two halves of the same promise: the service reports a KB scope it does not actually retrieve from, and cites evidence the context budget dropped before the model saw it. Both are 'the answer misrepresents what produced it'.

### BL-060 — Streaming chat persists its transcript

**3 SP** · sprint 2026-36

Findings closed:

- `backend/api/routers/rag.py:147` — *medium* — The ?stream=true chat branch never persists the transcript, unlike the non-streaming branch on the same route
  Failure: POST /chat/conversations/{id}/messages has two behaviours on one route. Without
  stream it delegates to a builder that calls append_messages and durably stores both the
  user message and the assistant reply. With ?stream=true the handler resolves the KB scope
  and returns a StreamingResponse over _stream_sse, which receives only rag_service and
  never touches conversation_service. A client using the streaming variant gets a 200,
  renders the answer from client state, and loses the entire exchange on reload — GET
  /chat/conversations/{id} returns messages: []. Nothing in the OpenAPI contract signals
  that durability is conditional on a query parameter.

**Why these are one story.** Standalone: one branch of a route persists the transcript and the other does not.

### BL-061 — KB switch resets dependent page state

**3 SP** · sprint 2026-36

Findings closed:

- `chili_app/src/pages/CaseManagementPage.tsx:237` — *medium* — Case Management pins a stale case id across a knowledge-base switch, leaving the detail pane permanently blank
  Failure: Select case-A1 on /cases?kb=kb-A, then switch the workspace KB to kb-B via the
  top bar (same route, so the page does not unmount and selectedCaseId survives).
  requestedCaseId is correctly rejected because it is not in kb-B's list, but the fallback
  chain reads selectedCaseId WITHOUT validating it, so activeCaseId stays case-A1.
  useCase('kb-B','case-A1') 404s, caseQuery.data is undefined, and the detail panel is gated
  on `caseQuery.data ?` so it renders nothing — no error, no empty state — and never
  recovers, because the items[0] fallback is unreachable while selectedCaseId is non-null.

- `chili_app/src/pages/RagChatPage.tsx:189` — *medium* — RAG Chat's knowledge-base picker keeps the previous KB's launch context, sending foreign alert/entity ids as retrieval filters
  Failure: Arrive from an alert in kb-A via 'Ask AI' (/rag-
  chat?kb=kb-A&source=alert&alert=alert-1&entity=e1&evidence=ep-9&q=...), then switch KB
  with the page's own picker. setActiveKnowledgeBase rewrites only ?kb=;
  source/alert/entity/evidence stay. selectedKnowledgeBaseId becomes kb-B but launchContext
  still describes kb-A, the context chips still display kb-A's ids beside kb-B, and 'Start
  with this context' still submits filters {source_type:'alert', alert_id:'alert-1',
  entity_id:'e1', evidence_pack_id:'ep-9'} against kb-B — records that do not exist there —
  so the assistant answers kb-A's question against a filtered-to-nothing kb-B corpus while
  the UI attributes the answer to kb-A's alert.

**Why these are one story.** One root cause on two pages — state derived from the previous knowledge base is not reset when the knowledge base changes.

### BL-062 — Alert-feed search and evidence-review error surfacing

**2 SP** · sprint 2026-36

Findings closed:

- `chili_app/src/pages/AlertFeedPage.tsx:489` — *medium* — Alert Feed search box writes every keystroke straight to the router, dropping characters and pushing a history entry per key
  Failure: Typing 'redwood' into the Search box at normal speed leaves a truncated string
  such as 'wd' in the box and ?q=wd in the URL, because value={filters.search} is fed from
  router state that React Router commits inside React.startTransition, so the urgent render
  still carries the previous value and React reverts the DOM input. Seven history entries
  are also pushed, so the analyst must press Back seven times to leave the page. The same
  push-per-interaction applies to every control routed through setFilters.

- `chili_app/src/components/investigation/EvidencePackViewer.tsx:171` — *low* — Explanation-review submission fails silently: the mutation's error is never surfaced
  Failure: An analyst marks a narrative review 'not useful', picks a reason, and submits
  while the API rejects the write (409 duplicate, 422, or 5xx). createReview.mutate is
  called with no onError and the hook declares only onSuccess, so the button un-disables
  when isPending clears, the local error state is untouched (it is only ever set by the
  client-side 'Select at least one reason' check), and the header chip still reads
  'Unreviewed'. The analyst sees the form return to normal and reasonably concludes the
  review was recorded; nothing was persisted and the governance ledger has no entry.

**Why these are one story.** Two small frontend-correctness defects with no shared fix, grouped only because each is 1 SP and both are in the alert/evidence path.

### BL-063 — Tests that can actually fail

**4 SP** · sprint 2026-36

Findings closed:

- `backend/tests/api/test_kb_cleanup.py:14` — *medium* — The KB-delete cascade completeness test cannot detect a forgotten deletion step — the exact drift it claims to guard
  Failure: A developer adds a new per-KB durable store field to KbDeletionStores and wires
  it in get_kb_deletion_stores but forgets the matching entry in kb_deletion_steps. The
  completeness test still passes: _STORE_FIELDS (a hand-typed literal) lacks the new name,
  so the SimpleNamespace simply lacks that attribute and _EXPECTED_STEP_NAMES is likewise
  unchanged. pyright is silent because cast(KbDeletionStores, SimpleNamespace(...)) erases
  the type, and the route-level test asserts on only 4 of 18 stores. DELETE
  /knowledgebases/{id} then returns 204 while that store's rows are orphaned forever — a
  data-retention leak on a documented cascade contract.

- `chili_app/e2e/config-manager.spec.ts:91` — *medium* — Every test in the Config Manager e2e spec skips under the project's own make test-e2e command
  Failure: Someone breaks the domain hot-swap — the pack switcher stops re-rendering the
  sidebar from the refetched /config/domain, or the confirm step stops POSTing to
  /config/switch. make test-e2e reports 5 skipped tests and a green suite. The spec that
  exists to prove the platform's central claim (a single YAML retargets the same code to
  different domains) has never executed under any command the repo provides.

**Why these are one story.** Both are tests that report success while verifying nothing — the cascade test compares two hand-maintained literals to each other, and every spec in the config-manager file skips under the project's own e2e target.

**Risk.** May grow. The config-manager specs skip because they need an admin session nothing grants; making them run can surface real failures never previously visible. Budget as discovery, not as a fixed 4 SP.

### BL-064 — Module boundary restoration

**4 SP** · sprint 2026-36

Findings closed:

- `backend/readiness/service.py:34` — *low* — readiness/ and capabilities/ import concrete service classes from other business modules, creating direct implementation coupling
  Failure: ReadinessService.__init__ accepts connector_service: ConnectorService and
  workflow_definition_service: WorkflowDefinitionService — concrete classes, not Protocols.
  Any change to ConnectorService's constructor signature or method set breaks readiness/,
  capabilities/ and their tests, and readiness/ cannot be unit-tested without instantiating
  the real connectors stack. CLAUDE.md Rule 1 restricts cross-module communication to api/,
  agent/ and shared/ and explicitly forbids direct implementation coupling.

- `backend/api/middleware/session_store.py:117` — *low* — RedisSessionStore uses the redis SDK directly inside api/middleware/, outside any adapters/ directory, so Redis failures surface as 500s from auth middleware
  Failure: Redis session storage sits outside the adapter/factory selection machinery: there
  is no session_store backend literal in DomainConfig and no factory wiring, and the store's
  failure modes (connection loss, redis.exceptions.RedisError) are handled nowhere. A Redis
  outage therefore surfaces as an unhandled exception from get()/save() inside auth
  middleware — a 500 traceback on every request — rather than a typed adapter error the
  gateway can map to 503.

**Why these are one story.** Both are architecture-rule violations of the same kind: a module reaching past the three permitted interaction paths, and an external system used outside its adapters/ directory.

### BL-065 — Declared-but-unwired config

**3 SP** · sprint 2026-36

Findings closed:

- `backend/scorecards/evaluation.py:379` — *low* — fail_max / fail_min thresholds are dead configuration whenever a pass/warn bound is set, collapsing the undefined middle band to "fail"
  Failure: A pack author writes thresholds { pass_min: 10.0, fail_max: 5.0 } — legal config,
  since validate_threshold_direction only requires pass/warn bounds to exceed fail_max and
  warn_min is optional. A value of 7.0 fails the pass check, skips the absent warn check,
  fails the fail_max check, and then hits the catch-all, which returns 'fail'. The metric is
  graded FAIL even though the author's explicit failing band is 5.0 or below. More
  generally, once pass_min or warn_min is set, fail_max can never change the outcome, so the
  field is inert. Shipped packs dodge this only by placing fail_max immediately adjacent to
  warn_min — a workaround a new pack will not replicate.

- `backend/analytics/peerstats/peer_analysis.py:91` — *low* — PeerCohortDefinitionConfig.min_cohort_size is validated but never wired into PeerAnalysisService
  Failure: A pack author sets peer_stats.cohorts[0].min_cohort_size: 30 to mark small
  cohorts as statistically unreliable. get_peer_analysis_service passes only
  cohort_definitions and never min_cohort_size, so the service keeps its hardcoded default
  of 5. A 6-member cohort is returned to the analyst with confidence='normal' and
  confidence_reason=None — exactly the reliability signal the author configured against.

**Why these are one story.** Both are configuration the schema validates and the code never consults.

### BL-066 — Contract and recovery leftovers

**3 SP** · sprint 2026-36

Findings closed:

- `chili_app/src/api/contracts.ts:36` — *medium* — RealtimeSnapshotResponse is a hand-written wire DTO in contracts.ts, exempt from the OpenAPI drift gate and applied via an unchecked cast
  Failure: The backend model is used only as the SSE payload for GET /events/stream, which
  FastAPI types as StreamingResponse, so it never enters the exported OpenAPI document.
  Rename active_alerts to open_alerts on the Pydantic model and: npm run codegen:api
  produces no diff, the CI drift check passes, tsc and ESLint pass, and the workspace header
  silently renders undefined alerts forever — exactly the breakage Rule 5 exists to prevent.

- `backend/ingestion/service.py:160` — *low* — Ingestion recovery markers for remote-URI documents can never be replayed, so an event-bus failure permanently blocks that URI
  Failure: register_documents with a URI submission while the event bus is down: the remote
  marker object is written, publish raises, and a recovery marker is stored with
  storage_key=None. replay_recovery_markers skips exactly those markers, and re-submitting
  the same URI computes should_publish = not object_store.exists(marker_key) -> False, so no
  DocumentReference is produced and no event is ever published. Both recovery avenues are
  closed and the URI is permanently un-ingestible for that KB until an operator manually
  deletes the marker object.

**Why these are one story.** Two unrelated leftovers, grouped to avoid two 1-2 SP rows: a hand-written wire DTO that escapes the contract drift gate, and a recovery marker that can never be replayed.

**Risk.** Changes a frontend-consumed model, so it regenerates the contract. Land after BL-061/062 to avoid re-running codegen against churn.

## Sequencing

**2026-35.** `BL-053` → `BL-058` (migration ordering: `0029` then `0030`). `BL-054` →
`BL-055` (both edit `agent/coordinator.py`). `BL-057` builds on the `/auth/callback` change
in `b8e1ffef`. `BL-056` is independent and may run in parallel.

**2026-36.** `BL-059` → `BL-060` (both in `rag/` and `api/routers/rag.py`). `BL-061` →
`BL-062` (both in `src/pages/`). `BL-066` lands after the page stories because it
regenerates the frontend contract. `BL-063`, `BL-064`, `BL-065` are independent.

## Definition of done

Repo gates unchanged: `pyright` strict 0 errors, `ruff check --no-cache .` clean, pytest
coverage ≥ 85%, contract regeneration on any frontend-consumed Pydantic change, browser
verification for UI work, live verification against `make dev`, full-stack Playwright e2e
with no mocked subject.

**One addition specific to this burn-down: every story's test must have been watched failing
against the real defect before the fix lands.** This is not ceremony. Both criticals closed
in `b8e1ffef` had green tests over them, and a test written after the fix would have passed
either way. Where a finding exists because the existing test could not fail, correcting that
test is part of the story, not a follow-up.

Per-story: the finding's cited code no longer exhibits the failure scenario, verified against
a running stack rather than only a green suite.

Per-sprint: every committed finding closed and re-verified, gates green, and the audit
artifact updated to reflect the closed set.

## Open questions

None. The four decisions taken during brainstorming — burn-down as the theme, genericity
deferred, two sprints with all 27 committed, stories grouped by shared fix — are settled and
should not be relitigated during planning.
