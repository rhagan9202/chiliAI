# analytics/score_runs

Durable "score-all" runs (SAFE-CMS-002): re-assess risk for every entity in a
knowledge base, or an explicit list, in sequenced batches that survive worker
restarts. `ScoreRunService` records run and batch state and publishes the work
events. It never scores inline: the worker-side executor claims each batch,
calls `analytics/risk`'s `RiskService.assess` per entity, and chains to the
next batch.

See the package-level guide, [`../README.md`](../README.md), and the risk
module, [`../risk/README.md`](../risk/README.md).

## Layout

| File | Responsibility |
|------|----------------|
| `models.py` | `ScoreRun` and `ScoreBatch` (with `ScoreRunStatus` / `ScoreBatchStatus`). Each carries scored / failed / skipped counters. |
| `protocols.py` | `ScoreRunRepositoryProtocol` (runs, batches, `claim_batch`, `list_stale_runs`, `delete_by_kb`) and `ScoreRunPage`. |
| `service.py` | `ScoreRunService` / `create_score_run_service`: `start_score_all`, `cancel_run`, `replay_failed_batches`, `list_runs`, `get_run`, `list_batches`. Also defines `ScoreRunConflictError` and `ScoreRunStartResult`. |
| `executor.py` | `handle_score_run_queued` and `handle_score_batch_queued`, registered with `execution.registry.register_handler` for `score.run.queued` and `score.batch.queued`. |
| `reconciler.py` | `ScoreRunReconciler.reconcile_stale_runs` — fails `queued`/`running` runs that have stopped progressing. |
| `adapters/in_memory.py`, `adapters/postgres.py` | `ScoreRunRepositoryProtocol` implementations; the Postgres one is `PostgresScoreRunRepository`. |

## Contracts and invariants

- **One active run per KB.** `start_score_all` raises `ScoreRunConflictError`
  (HTTP 409) while the KB has a `queued` or `running` run. An
  `idempotency_key` that matches an existing run returns that run, and that
  check runs before the conflict check.
- **Deferred enumeration.** With `entity_ids=None`, the service publishes
  `ScoreRunQueuedEvent`. `handle_score_run_queued` then pages entity ids from
  the graph repository (`get_entities_page`), creates the batches, and
  publishes the first `ScoreBatchQueuedEvent`. A redelivery that finds batches
  already present does nothing.
- **Sequenced batches.** Only the first batch is published. After each batch,
  `_advance` publishes the next queued batch, or marks the run `completed`
  when none remain.
- **Idempotent scoring.** Each assessment's request id is
  `risk:<run_id>:batch-<n>:<entity_id>` (`score_request_id`), so redelivered
  or replayed batches converge on the same `risk_score_history` rows. Run
  counters are recomputed as sums over batch state, never incremented.
- **Catalog pinning.** A batch whose run `catalog_version` differs from the
  active pack's `feature_catalog.version` fails the run with
  `error_summary="catalog_version_changed"`.
- **Per-entity outcomes.** `RiskInsufficientSignalsError` and
  `RiskConfigurationError` count as *skipped*. Any other exception propagates
  to the worker's retry/DLQ wrapper.
- **Takeover.** A batch left `running` longer than
  `CHILI_SCORE_BATCH_STALE_SECONDS` (default 900) can be reclaimed by another
  worker. Once its `attempts` reach `CHILI_SCORE_BATCH_MAX_ATTEMPTS` (default
  5), it is failed with `max_attempts_exceeded`. Enumeration page size is
  `CHILI_SCORE_ENUMERATION_PAGE_SIZE` (default 1000).
- **Replay** creates a new run (`replay_of_run_id` set) holding only the
  original run's failed batches, and publishes its first batch.
- `ScoreRunStatusChangedEvent` (`score_run.status_changed`) is a notification
  only; no worker handler acts on it.

## How it is reached

- **API** (`api/routers/score_runs.py`, prefix
  `/knowledgebases/{knowledge_base_id}/score-runs`): `POST ""` (analyst,
  start), `GET ""` and `GET /{run_id}` (viewer), `POST /{run_id}/cancel` and
  `POST /{run_id}/replay` (analyst).
- **Worker:** the two executor handlers run through the `execution/` dispatch
  seam, using `ExecutionDeps.score_run_repository`, `risk_service`,
  `graph_repository`, `event_bus` and `domain_config`. `run_worker` in
  `agent/coordinator.py` runs `ScoreRunReconciler` on the same periodic tick
  and stale cutoff as workflow-run reconciliation.

## Persistence

`score_runs` and `score_batches` (FK `run_id` with `ON DELETE CASCADE`),
created by migration `0024_score_runs`; `0027_score_run_skipped_entities` adds
the skipped counters.

## Current gaps (verified in code)

- `ScoreRunRepositoryProtocol.delete_by_kb` has no caller:
  `knowledgebases/cleanup.py` has no score-run step, so deleting a KB leaves
  its runs and batches behind.

## Tests

`tests/analytics/score_runs/` — service, executor, reconciler, and in-memory
and Postgres repositories.
