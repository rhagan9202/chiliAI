# Sprint Slice (DRAFT) — Ingestion Failure-Path Observability & Per-Document Status

> **Status: DRAFT slice — not a committed sprint.** Authored as input for the PM agent's 2026-26 planning. Draftable into 2026-26 as a headline core, or folded into a hardening sprint.
> Theme: **make ingestion failures and empty results visible end-to-end.**
> Bundles backlog [`ingestion.32`](../../backlog/ingestion.md) + [`ingestion.18`](../../backlog/ingestion.md) + [`ingestion.35`](../../backlog/ingestion.md) + a logs/counters subset of [`ingestion.17`](../../backlog/ingestion.md).

## Slice goal

Today a document can fail mid-pipeline or extract nothing and **the user/operator sees no signal** — it either dead-letters silently or completes as `kb.ready` with zero entities. This slice closes that hole: every failure becomes a clean per-document `DocumentsFailedEvent`, those transitions land in a **durable status projection** the Studio can read, empty/dropped extractions reach a **distinct terminal state**, and SREs get **failure counters** to alert on.

By end of slice: ingest a malformed doc → it shows `FAILED` with a reason in `GET /knowledgebases/{kb_id}/documents`; ingest a doc that extracts nothing → it shows `EXTRACTED_EMPTY`, not a clean "ready"; `/metrics` exposes `ingestion_documents_failed_total{stage,error_class}`.

## Predecessor state (code-verified, not backlog status)

A code-level audit was run before scoping (the 2026-25 retro flagged systemic backlog estimate-drift — every story is verified against code at kickoff, not trusted from SP).

- **Gap #1 confirmed** — `safe_parse_content`/`safe_parse_source` (`backend/ingestion/orchestrators/parser.py:86,109`) catch only `ParserError`/`RemoteFetchError`; `ingest_task` reads bytes unguarded (`backend/ingestion/service.py:290`); `handle_documents_parsed` (`backend/agent/coordinator.py:1004`) and `handle_documents_chunked` (`coordinator.py:1069`) `raise ValueError`. These escape to `run_handler_with_retry` → burn retries on a deterministic error → DLQ, with **no `DocumentsFailedEvent`**.
- **Gap #2 confirmed** — `IngestionStatus` enum already exists on `SourceDocument` (`backend/ingestion/models.py:40-68`) but is **never persisted**; no `SourceDocumentStatusStore`, no per-KB list endpoint.
- **Gap #3 confirmed** — `validate_extraction` records drops in `entity_errors`/`relationship_errors` (`backend/ingestion/validator.py`) but the coordinator emits only `valid_entity_count`, and a zero-entity doc still emits `KnowledgeBaseReadyEvent` (`coordinator.py:~1258-1267`).
- **Retry/DLQ + stale-pending reclaim already solid** (`coordinator.py:3001-3242`) — this slice rides on existing infra; no event-bus rework needed.

## Stories

| ID | Title | Pri | Est. (verified) | Depends on | Notes |
|---|---|---|---|---|---|
| **IFO-1** (`ingestion.32`) | Convert all parse/read failures → `DocumentsFailedEvent` | P1 | **2 SP** *(M→2; localized)* | — | Foundation — produces the clean failure event the projection consumes |
| **IFO-2** (`ingestion.18` slice) | `SourceDocumentStatusStore` + projection consumer + list endpoint | P1 | **5 SP** *(L→5; FE deferred)* | IFO-1; prereqs `database.04` / `events.04` | The durable read surface |
| **IFO-3** (`ingestion.35`) | Surface empty extractions + validation drops as distinct status | P1 | **3 SP** | IFO-2 (status surface) | Adds `EXTRACTED_EMPTY` + drop-reason propagation |
| **IFO-4** (`ingestion.17` subset) | Structured stage logs + failure/dedup counters | P2 | **2 SP** *(carve-out; OTel+Grafana stay in `.17`)* | IFO-1 (failure counter) | Logs + Prometheus only |
| | **Slice core total** | | **12 SP** | | |

## Dependency order

```
IFO-1 (clean failure events) ──┬──> IFO-2 (status projection) ──> IFO-3 (empty-extraction status)
                               └──> IFO-4 (counters)  [logs/validator-side work is independent; can start day 1]
```

Critical path is **IFO-1 → IFO-2 → IFO-3**. IFO-1 is small and unblocks everything — do it first. IFO-4's logging + validator-side warning work is independent and can run in parallel from day 1; only its *failure counter* wants IFO-1's typed failures.

## Acceptance criteria (slice-level highlights — full AC in the parent backlog stories)

- **IFO-1** (`ingestion.32`) — parse path catches any exception (not just `ParserError`) → `DocumentParseFailure`; empty-content `ValidationError` mapped to a typed failure; `ingest_task` `get_bytes` guarded (missing key → failure, not `KeyError`); `handle_documents_parsed/chunked` missing-key raises converted to per-document failures so one bad doc doesn't poison its batch. Tests cover mid-iteration non-`ParserError`, empty-TXT, missing object → each emits `DocumentsFailedEvent`, rest of batch unaffected.
- **IFO-2** (`ingestion.18` slice) — `SourceDocumentStatusStore` protocol + Postgres adapter; schema `(kb_id, source_document_id, current_status, last_error, transition_log, updated_at)` with monotonic transitions (stale `parsing` after `failed` ignored); consumer subscribes to uploaded/parsed/failed; `GET /knowledgebases/{kb_id}/documents` returns status + last_error, filterable by status. **Frontend wiring explicitly out of this slice** (own FE story).
- **IFO-3** (`ingestion.35`) — zero-valid-entity doc reaches a distinct durable signal (`EXTRACTED_EMPTY`), not silent ready; `entity_errors`/`relationship_errors` counts + bounded sample exposed via the IFO-2 surface; the "one extra property drops the whole entity" sharp edge mitigated (strip-to-metadata or typed warning).
- **IFO-4** (`ingestion.17` subset) — each stage logs `stage=/source_document_id=/kb_id=/duration_ms=/outcome=`; counters `ingestion_documents_failed_total{stage,error_class}`, `ingestion_documents_empty_extraction_total`, `ingestion_dedup_suppressed_total`. **OTel spans + Grafana JSON remain in `ingestion.17`** (blocked on `_observability.03/.05/.07`).

## Pre-slice prerequisites (verified 2026-06-16 against code)

`ingestion.18` declares prereqs `database.04` and `events.04`. Both were verified against the actual codebase: **both are genuinely unstarted** (backlog status accurate), **but neither is a hard runtime blocker for IFO-2** — so the 12 SP estimate holds, IFO-2 does not absorb either M story.

- **`database.04` (CI migration drift gate) — NOT STARTED, NOT A BLOCKER.** Verified absent: `scripts/ci_migration_check.sh`, `backend/database/migrations/snapshots/head.sql`, a `make migrate-check` target, and any alembic step in `.github/workflows/*.yml`. It is a *CI quality gate*, not a schema capability — IFO-2 adds its `SourceDocumentStatusStore` Alembic revision and applies it with the existing `alembic upgrade head` flow (`Makefile:33`). database.04 would only *protect* that revision after the fact. **Recommendation:** schedule database.04 alongside or just after this slice so the new migration gets drift protection, but do not gate IFO-2 on it.
- **`events.04` (auto-register event subclasses) — NOT STARTED, NOT A BLOCKER.** Verified: `EVENT_TYPE_REGISTRY` (`backend/events/codec.py:43`) is still the hand-maintained literal and the `TODO(production)` at `codec.py:44-47` is present verbatim; no `__init_subclass__` hook in `types.py`. IFO-2's consumer subscribes to **already-registered** events (`documents.uploaded/parsed/failed`). If IFO-3 introduces an `EXTRACTED_EMPTY` event, it is **one manual registry line** under the current scheme — trivial. **Recommendation:** prefer modeling `EXTRACTED_EMPTY` as a *status transition* on the existing `documents.*` flow (no new event type) to avoid touching the registry at all.
- **Status enum reuse** — `IngestionStatus` (`backend/ingestion/models.py:40-68`) already has the lifecycle states; extend with `EXTRACTED_EMPTY` for IFO-3 rather than inventing a parallel enum.

## Risks

- **R-1 — IFO-2 is the cost center.** It is the only L-sized story and the slice's critical path. Its declared prereqs (`database.04`/`events.04`) were verified as unstarted-but-not-blocking (see Prerequisites), so the risk is *internal scope* (status schema + monotonic-transition consumer + endpoint), not external dependency. Mitigation: IFO-2's migration uses the existing local `alembic upgrade head` flow; model `EXTRACTED_EMPTY` as a status transition (not a new event) so the hand-maintained event registry is untouched. If IFO-2 slips, IFO-1/-3(validator-side)/-4 are all self-contained and still ship value.
- **R-2 — `ingestion.17` scope creep.** The parent is L with an observability-epic dependency. Mitigation: the carve-out (IFO-4) is logs+counters only; OTel/Grafana stay in `.17` — do **not** let spans/dashboards leak into this slice.
- **R-3 — Empty-extraction false positives** (legitimately entity-free docs). Mitigation: `EXTRACTED_EMPTY` is a *warning* status, not a failure; the KB can still go ready in aggregate.

## Definition of done

- IFO-1/-2/-3 (+IFO-4 if pulled) meet AC; `pyright --strict` clean + pytest ≥ 85% on `ingestion/`, `agent/`, and touched packages; full green.
- Manual: malformed doc → `FAILED` w/ reason in the list endpoint; zero-entity doc → `EXTRACTED_EMPTY`; `/metrics` shows the new failure series.
- Backlog updated: `ingestion.32`/`.18`/`.35` flipped to `done` (or `.18`/`.17` to `in-progress (sliced)`) citing this slice; `ingestion.17` annotated "logs+counters delivered; OTel+Grafana remain."
- Any frontend-consumed contract change (the new list endpoint) follows export-OpenAPI → `npm run codegen:api`, no drift.

## Open decisions for the PM

1. Schedule as the headline core of **2026-26**, or fold into a broader hardening sprint?
2. ~~Are IFO-2's prereqs green?~~ **Resolved 2026-06-16:** `database.04`/`events.04` are both unstarted but verified *non-blocking* — the 12 SP estimate stands (see Prerequisites). Optional: bundle `database.04` (M, ~3 SP) into the same sprint so the new status-table migration ships with CI drift protection.
