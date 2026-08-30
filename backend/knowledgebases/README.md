# knowledgebases — KB and Document Metadata Persistence

Persistence boundary for knowledge base and document metadata: KB records
(name, description, status, entity/relationship/document counts) and
per-document records (filename, status, content hash, ingestion warnings).
Lives outside both `api/` and `agent/` so neither feature module needs to
import from the other, honoring CLAUDE.md Hard Rule 1 — `api/` (gateway
routers: create/list/delete KB, document registration and inventory) and
`agent/` (worker coordinator: pipeline status/warning writes, KB-delete
cascade) both depend on `KnowledgeBaseRepository` only.

## Layout

- `models.py` — `DocumentRecord` (per-document metadata, including the
  per-stage warning ledger — see below) and `MAX_DOCUMENT_WARNING_REASONS`
  (the reasons-sample cap shared by every adapter).
- `protocols.py` — `KnowledgeBaseRepository`, the persistence protocol.
- `_helpers.py` — internal helpers shared by both adapters so their
  update math cannot diverge: `build_knowledge_base_summary_updates`
  (`update_summary`) and `build_stage_document_warning_updates`
  (`set_stage_document_warnings`, see below).
- `adapters/in_memory.py` — `InMemoryKnowledgeBaseRepository`, a process-local
  dict-backed repository (tests, local dev without an object store).
- `adapters/object_store.py` — `ObjectStoreKnowledgeBaseRepository`, durable
  storage via a single JSON snapshot (`KnowledgeBaseStoreSnapshot`,
  `snapshots.py`) written through the configured `ObjectStore` (local FS, S3,
  MinIO). This is the repository used by the running dev/prod stack.
- `cleanup.py` — `KbDeletionStores` / `kb_deletion_steps`: the ordered,
  shared KB-delete cascade (every other durable per-KB store this repository
  does not own) so the API's synchronous delete path and the worker's
  event-driven retry use the same step list.

**There is no Postgres adapter for `KnowledgeBaseRepository`.** Only
`in_memory.py` and `object_store.py` exist; any change to the protocol must
be implemented, and tested, in both.

## Per-stage document warning accounting (agent.22)

`DocumentRecord.warning_count` / `warning_reasons` surface ingestion
diagnostics on the KB document inventory (`DocumentSummary.warning_count` /
`warning_reasons`, `api/routers/knowledgebases.py`) — the parse stage's
parser warnings and the extract stage's entity/relationship validation
warnings, combined into one document-level total.

Two worker handlers write these (`agent/coordinator.py`, see
`backend/agent/README.md` § Per-stage document warning accounting):
`handle_documents_parsed` (`stage="parse"`) and `handle_entities_extracted`
(`stage="extract"`). Both write through the single method
`set_stage_document_warnings(knowledge_base_id, document_id, *, stage,
count, reasons)`, which is **absolute per `(document, stage)`, not additive
overall**:

- `stage_warning_counts: dict[str, int]` and `stage_warning_reasons:
  dict[str, list[str]]` on `DocumentRecord` are the source of truth, keyed
  by stage. A write to `stage="extract"` replaces exactly that key; it never
  touches `stage_warning_counts["parse"]`.
- `warning_count` (`sum(stage_warning_counts.values())`) and
  `warning_reasons` (the per-stage reason samples concatenated in stage
  insertion order, capped at `MAX_DOCUMENT_WARNING_REASONS`) are recomputed
  and stored on **every** stage write, by the shared helper
  `_helpers.build_stage_document_warning_updates` — not derived lazily on
  read. Both adapters call this one helper, so the fold/derive math cannot
  drift between them; only the KB/document lookup and snapshot
  load/save differ per adapter.

This closes two failure modes at once that neither a single flat counter
(the pre-Sprint-2026-35 state) nor a stage-blind absolute setter (the
Sprint-2026-35-Task-5 partial fix, `set_document_warnings`) could close
together:

- **Replay inflation.** Both handler bodies re-run on retry and on
  at-least-once Redis Streams redelivery. An additive write inflates its own
  stage's contribution on every replay.
- **Cross-stage data loss.** A stage-blind absolute write has nowhere to
  keep a *different* stage's prior contribution, so the later stage to run
  overwrites the earlier one's warnings outright.

Per-stage keying rules both out structurally: replaying `stage="extract"`
converges (same key, same absolute value), and `stage="extract"` writing
can never touch the `"parse"` entry.

**Reasons cap.** `reasons` passed to a single stage write are truncated to
`MAX_DOCUMENT_WARNING_REASONS` (10) before being stored for that stage;
`warning_reasons` on the document is capped again after combining every
stage's sample, so the document-level total never exceeds 10 even though
each stage could in principle contribute up to 10 of its own. `warning_count`
is never capped — it is an exact sum.

**Documents from before this ledger existed.** A document persisted before
Sprint 2026-36 carries a non-zero flat `warning_count` (from
`set_document_warnings`/`record_document_warnings`, both since removed — no
callers remain) but empty `stage_warning_counts` / `stage_warning_reasons`.
That flat total was itself the *sum* of both stages under the old additive
scheme — parse wrote absolutely, extract added its own count on top — so
there is no way to recover which portion of it belonged to which stage.

The first stage write for such a document therefore **discards** the old
flat total rather than folding it in: `stage_warning_counts` starts fresh
with only that stage's own contribution. Folding the whole prior total into
a synthetic entry was considered and rejected — it double-counts every
stage that goes on to rewrite (a document already showing `5` gains its own
stage's count *again* on top of the old `5`), and since nothing ever clears
that entry, it never converges; a later replay of the *same* stage would
even keep re-adding it. Discarding instead means a document transiently
**under**-reports right after this deploy — it shows only the stages that
have rewritten since, until every stage has — but the count can never
inflate, and it converges to the correct sum once every stage has run
again. That is the safer failure direction for an advisory count. No
standalone backfill script exists or is needed: the old scheme never
recorded the per-stage breakdown, so there is no data a backfill could
recover that the write path itself doesn't already reconstruct correctly
over time. A document that is never re-processed by any pipeline stage
after upgrade is untouched and keeps showing its pre-existing flat total
(nothing writes to it).

## KB-Scoped Delete

`cleanup.py::kb_deletion_steps` is the ordered cascade purging every durable
per-KB store `KnowledgeBaseRepository` does not itself own (graph, vector,
raw records, derived signals, risk history/projections, observations, alert
history, GNN clusters, metrics, conversations, cases, policy items,
evidence packs, scorecard runs, document status, object-store payloads under
the KB's key prefix). `KnowledgeBaseRepository.delete` and
`mark_pending_cleanup` handle only this module's own KB/document metadata;
the API's `DELETE /knowledgebases/{id}` and the worker's
`KnowledgeBaseDeletedEvent` retry both assemble a `KbDeletionStores` bundle
from DI and run these shared steps before removing the KB record itself.

## Commands

```bash
pytest tests/knowledgebases -q
```
