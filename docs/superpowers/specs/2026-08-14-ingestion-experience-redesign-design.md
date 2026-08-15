# Ingestion Experience Redesign — Design Spec

**Date:** 2026-08-14
**Status:** Approved design, pending implementation plan
**Supersedes:** `docs/superpowers/specs/2026-05-17-ingestion-studio-ui-ux-design.md` (the left-stepper Ingestion Studio)
**Scope decision:** Full ingestion experience — frontend restructure, backend semantics fixes, first connectors UI.

## Why

A live UAT session (2026-08-14) plus a five-dimension deconstruction (frontend structure,
backend surface, heuristic UX audit, design history, user journeys) found the
`/knowledge-bases` page painful to use for five structural reasons, not cosmetic ones:

1. **Unresolved wizard-vs-workspace identity.** A six-step stepper that gates nothing and is
   not clickable renders above cards labeled with a different "Step 1 / Step 2" numbering,
   on a page where every stage is visible at once. `currentStep` is mutated as a side effect
   from 10+ call sites; the `submit` step can never be current; "Watch runs" only re-tints a
   stepper tile.
2. **Client draft state is not scoped to its subject.** `ingestionStudioStore` is a global
   singleton (staged `File` handles, parsed rows, receipts, validation issues) never reset on
   KB switch or navigation — files staged for KB A submit into KB B; KB A's receipts render
   in KB B's timeline.
3. **No shared status vocabulary.** The backend computes rich states (per-component readiness
   with blockers/actions, an 8-state document lifecycle, drop counts) and the UI flattens
   them ad hoc: a binary "Blocked" chip that stays Blocked forever for manually-fed KBs,
   green READY for zero-entity documents, no `:disabled` styling anywhere, raw ISO
   timestamps in two panels while others format correctly.
4. **Validation rigor is spent before submit, not where the stakes are.** Three validators
   pre-submit, but KB/document deletion is one un-confirmed click, file pickers silently
   replace prior staging, and score runs fire with hidden hardcoded CMS parameters.
5. **The page absorbed seven jobs instead of linking to them.** KB admin, staging,
   validation, submit, run monitoring, score-run ops, and full-text document reading share
   one scroll (the preview lives in a 320px rail).

The backend meanwhile offers capabilities the UI hides entirely: the connectors subsystem
(zero frontend code), the durable per-document projection (`current_status`, `last_error`,
dropped counts), document list filtering/pagination, replace-on-reupload semantics,
suppressed-row receipt counts, and score-run parameterization/history. Ordered multi-feed
ingest is script-only because each upload 409s while the previous workflow runs.

## Approach

**Library → Workspace (hub-and-spoke).** Split the jobs across a shallow hierarchy matching
the app's existing deep-linked-workbench idiom, fix the backend semantics that force any UI
to lie, and give connectors a first surface.

## 1. Information architecture & routes

```
/knowledge-bases                    → Library
/knowledge-bases/:kbId              → Workspace · Overview
/knowledge-bases/:kbId/add          → Workspace · Add data
/knowledge-bases/:kbId/data        → Workspace · Data (inventory + preview)
/knowledge-bases/:kbId/runs        → Workspace · Runs (ingestion, score runs, connector syncs)
/knowledge-bases/:kbId/settings    → Workspace · Settings
```

- **Library:** KB cards scoped to the active domain (keep the "show all domains (N hidden)"
  toggle and warn-only mismatch badges). Card = name, description, status digest (docs /
  entities / last activity / per-activity health per §3). "New knowledge base" opens a
  focused create form; on create, land in the new KB's Add data. No delete here.
- **Workspace:** persistent header (KB name, domain badge, status digest, section tabs) over
  five sections. **Overview** generalizes the next-actions manifest: one sentence stating
  the KB's situation plus the existing handoff buttons (Investigate / Alerts / RAG).
  Empty-state doctrine (UXA-305) carries over.
- **URL is the single source of truth for KB selection.** Selecting a KB is navigation.
  The workspace route syncs the app-wide `useActiveKnowledgeBase` (restoring UXA-101
  compliance — the current page derives its own selection in violation). The top-bar KB
  picker navigates between workspaces.
- **Redirects:** `/knowledge-bases?kb=X` → `/knowledge-bases/X`;
  `?kb=X&document=Y` → `/knowledge-bases/X/data?document=Y`; `/knowledgebases` legacy
  redirect preserved.
- **Role gating:** create + add data = analyst; Settings delete + connector registration =
  admin; reads = viewer. Client-side gating mirrors the backend `require_role` guards that
  become live when a pack enables auth.
- **Deletions:** the orphaned `components/knowledgebase/` cluster (`KbTable`,
  `KbDetailView`, `CreateKbForm`, `DropZone`, `DocumentTable`, `StatusBadge`, duplicate
  `UploadProgress`) is removed. Salvage: `DropZone`'s drag-drop + input-reset semantics
  inform §2 staging; the dead `ConfirmDialog` wiring becomes the live pattern in Settings.

## 2. The Add-data flow

One entry (`/add`), three source cards: **Documents**, **Structured records**,
**Connector** (admin-gated). Each is a self-contained two-stage flow — **stage → confirm**
— genuinely gated (confirm is unreachable with nothing staged). The six-step stepper is
deleted.

**Documents**
- Drag-drop zone + file/folder pickers that **append** to the staged list; per-file remove;
  `accept` derived from the pack's `allowed_content_types`; input `value` reset after every
  pick so re-selecting a corrected file fires `change`.
- Staged list shows per-file size + client validation verdict inline (prerequisite-vs-content
  taxonomy preserved).
- Confirm stage previews consequences: N files, target KB, and **replace warnings** — staged
  files whose sha256 matches an existing document are flagged "will replace X and rebuild
  its graph artifacts" before submit (uses the §4 precheck endpoint).
- Submit → navigate to Runs with the new run focused.

**Structured records**
- Feed picker grouped by source kind; only inputs the feed's `source` supports render
  (file input for `file_upload`; paste/JSON editor only for `api_push` feeds).
- Parse → preview with honest truncation ("showing 25 of 4,812 rows · 3 more columns"),
  row-level issues, and full receipt anatomy (accepted / duplicate / rejected /
  **suppressed-existing** — already returned by the API, currently dropped by the UI).
- **Multi-feed queue:** stage several feed files, order them, submit as a queue. The client
  submits sequentially, absorbing the per-KB busy gate (409) and showing progress
  ("2 of 6 — inpatient_claims waiting for nppes_providers to finish"). Client-side queue
  ships first (no API change); a server-side queue is chartered as follow-up (§4).
- **Correction honesty:** a banner on record staging states the insert-only rule ("rows
  whose IDs already exist are skipped, not updated"); receipts with
  `suppressed_existing_count > 0` link to that explanation. True upsert is out of scope.

**Connector (admin)**
- Register (name, source type `filesystem`, path, feed binding); "Sync now" from Runs;
  sync-run receipts show pulled/accepted/quarantined/failed counters; a quarantine drawer
  lists per-row reasons. Schedule offers only `manual`, labeled as the only implemented
  mode — no dead dropdown options.

**Shared:** upload progress with retry-verbatim (retry rebuilds from current staged state,
not a stale closure); the push path gains the same progress/retry treatment; errors surface
once, in the flow's validation panel (not toast + panel + progress simultaneously).

## 3. The status system

**3a. Per-activity readiness replaces binary Blocked.** The readiness aggregate is
recomposed around what the user can do:

| Activity | Ready when |
|---|---|
| Queryable (investigate / RAG) | entities > 0 |
| Alertable (monitoring) | ≥1 entity metric evaluated for this KB (alerts can fire) |
| Scorable (score runs) | entities > 0 and catalog resolves |
| Auto-fed (connectors) | ≥1 connector healthy |

Each activity reports `ready | not_ready | not_configured | failed` with reasons. The
top-bar chip becomes the activity summary ("Queryable · 53 entities"; "Empty" for a new
KB). "Blocked"/danger presentation is reserved for genuine failures (failed connector,
failed run, `pending_cleanup`) — never for absent optional setup, which renders as quiet
"not set up" rows in Overview with action text.

**3b. Document lifecycle honesty.** Inventory renders the durable `current_status`:
`failed` = danger with `last_error` inline; `extracted_empty` = a distinct neutral
"No entities" state (never green READY + tooltip); validated-with-drops shows
"12 kept · 3 dropped" with reasons expandable in place. Inventory gains the status filter
and pagination the API already supports.

**3c. A `Status` design-system primitive.** One shared component + token map
(state → color/icon/label/hint) used by KB chips, document rows, run timeline, score runs,
readiness. Ships with:
- `:disabled` styling for `page-button` (reduced opacity, no hover response,
  `cursor: not-allowed`) and an "explain why disabled" convention: disabled primaries render
  their reason as adjacent text, not tooltip.
- One timestamp formatter: relative in timelines ("2m ago"), absolute local elsewhere; raw
  ISO strings and correlation IDs demoted to a copyable details row.
- Collapse duplicated helpers (two `toneForKnowledgeBaseStatus`, three date formatters, two
  `UploadProgress` components) into the shared module.
- Normalized heading hierarchy (h2 sections / h3 cards); the decorative wizard `<nav>` a11y
  lie disappears with the stepper.

## 4. Backend changes

**Changed:**
1. **Readiness recomposition** (`backend/readiness/`): response gains `activities` (per §3a).
   Component blockers survive internally, classified required vs optional —
   `no_connectors` / `no_workflows` / `no_capabilities` become `not_configured`, never
   blockers. `ready` = no failure and ≥1 activity available. Regenerate frontend contracts.
2. **Document pre-check:** `POST /knowledgebases/{kb}/documents/precheck` — request:
   filename + sha256 list; response: which uploads would replace existing documents.
3. **Durable receipts:** the record-ingest receipt (accepted/duplicate/rejected/suppressed +
   rejected rows) is attached to the workflow record it enqueues; the Runs timeline hydrates
   entirely from `GET /workflows`. The client-side ghost receipt log is deleted.
4. **Score-run defaults from config:** the domain pack declares
   `score_runs: {catalog_version, model_version, batch_size}`, surfaced via
   `GET /config/domain`; the UI displays them (admin-editable) before start. The hardcoded
   `cms-fraud-features-v1` / `risk-linear-v1` fallbacks are deleted. Run history uses the
   existing paginated list + batch detail.
5. **Ingestion is auditable:** `document.upload`, `document.delete`, `records.submit`,
   `knowledge_base.delete` write audit-log rows (UAT ruling: ingestion is material).
6. **Worker log hygiene:** "no derived risk signals registered" drops to debug with one
   per-run summary; the Neo4j `relationship.weight` read/write mismatch is resolved in the
   adapter (remove the read or write the property, per adapter audit).

**Explicitly not changed:**
- Document list status filter/pagination, `suppressed_existing_count`,
  `replaced_document_id`, durable `current_status` / `last_error` — already exist; the UI
  starts rendering them.
- Connectors API — sufficient for the MVP surface; `manual` schedule only.
- The per-KB busy gate (409) stays; the client queue works with it. A server-side ingest
  queue is chartered as follow-up (aligns with backlog `records.14–17`), not designed here.
- Records remain insert-only (made visible, not changed); URI ingestion stays unexposed.

## 5. Frontend state model & decomposition

**Ownership (three layers, no overlap):**

| State | Owner | Consequence |
|---|---|---|
| KB selection, workspace section, focused document/run | URL (route + search params) | shareable, refresh-safe; no `selectedX` shadow state |
| All server truth (KBs, documents, runs, receipts, readiness, score runs) | React Query only | timeline renders `useWorkflows` alone |
| In-flight drafts (staged files, parsed rows, queue order) | Per-flow draft store keyed by `kbId` | destroyed on submit-success, KB delete, workspace leave — cross-KB leakage unrepresentable |

`ingestionStudioStore` is deleted. `currentStep`, mixed `validationIssues`, `receipts`, and
`activeTimelineEntryId` cease to exist as state — validation is derived (memoized on
`(rows, feedSchema)`), backend errors live on their mutations, stages are real routes.

**Decomposition** (restoring the thin-page-coordinator intent):

```
pages/KnowledgeBaseLibraryPage.tsx        (~150 lines)
pages/KnowledgeBaseWorkspacePage.tsx      (~100 lines: header, tabs, outlet)
features/kb/overview/
features/kb/add-data/{documents,records,connectors}/
features/kb/data/
features/kb/runs/
features/kb/settings/
components/status/        (Status primitive, timestamp formatter, ConfirmDialog)
```

No file above ~300 lines; store subscriptions via selectors only; validation memoized so
typing never re-validates the full parsed row set.

**Liveness:** the 3s polls for runs/score-runs mount only while the Runs section is mounted;
Overview subscribes to `useRealtimeWorkspaceStream` for the status digest.

## 6. Error prevention

- **KB delete** (Settings, admin): typed-name confirmation stating live blast radius
  ("deletes 8 documents, 53 entities, all runs"). A 207 partial failure renders a
  `pending_cleanup` state with the per-step report and a "Retry cleanup" action
  (re-invokes delete).
- **Document remove:** confirm dialog (lighter copy); both delete mutations get progress and
  error surfacing.
- **Replace-on-upload:** precheck warning at confirm stage (§2/§4).
- **Staged-work protection:** leaving Add data with staged drafts prompts once
  ("Discard staged files for this KB?") — the only place work can be lost.
- **Disabled controls explain themselves** in adjacent text (§3c convention).

## 7. Testing

- Playwright e2e per journey against the full running stack (project rule): create → add →
  runs; multi-feed queue incl. busy-gate absorption; validation-failure recovery;
  delete-with-confirm; connector register → sync → quarantine review; legacy-URL redirects.
- Vitest: Status primitive mapping, draft-store KB scoping (regression test for the
  cross-KB leak), validators, timestamp formatter.
- Backend: pytest for readiness recomposition, precheck, receipt-on-workflow, audit rows;
  coverage ≥85%; pyright strict; contract regen checked in CI.

## 8. Delivery phasing (each phase independently shippable)

1. **Truth & safety on the current page:** `:disabled` styles, Status primitive +
   timestamps, confirmations, file-input append/remove/reset, draft store keyed by KB,
   receipts-from-workflows, document `current_status` / `last_error` / drop counts in
   inventory.
2. **IA split:** Library + Workspace routes, sections, redirects, stepper deleted, orphaned
   cluster deleted, URL-owned selection, UXA-101 compliance.
3. **Backend truth:** readiness recomposition + activity chip, precheck endpoint, score-run
   config defaults + history, ingestion audit rows, worker log hygiene.
4. **New capability:** multi-feed queue, connectors surface, insert-only banners +
   suppressed-count surfacing.

## 9. Decisions carried forward vs overturned (vs the 2026-05-17 spec)

**Carried forward:** one onboarding surface for documents + records (now `/add`); document
and records submissions remain separate runs/receipts; feeds are config-defined (no feed-
mapping editor); backend is authoritative for validation with client pre-checks labeled by
source; prerequisite-vs-content validation taxonomy; UXA-305 empty-state doctrine; warn-only
domain scoping.

**Overturned:** the left-rail wizard stepper (deleted — stages are real routes);
client-side receipt log (server-hydrated); global wizard store (per-KB drafts); page-owned
KB selection (URL + shared active-KB hook per UXA-101); binary readiness chip (per-activity
model); hardcoded score-run parameters (pack config).

**Preserved verbatim (the good parts):** ValidationPanel's prerequisite/content +
before/after-upload grouping; per-document warning reasons; rejected-row receipts with
per-row reasons and truncation; duplicate no-op receipts; retry-verbatim upload; two-step
reasoned rejection of approval gates; next-actions handoff pattern (promoted to Overview).

## 10. Out of scope

Record upsert/correction semantics; server-side ingest queue (chartered separately); URI
document ingestion; connector schedule execution (backend scheduler); RBAC enablement in dev
packs; score-run entity-subset scoping UI.
