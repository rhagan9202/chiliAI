# execution

The **executor dispatch seam**. The worker (`agent/coordinator.py`) keeps
owning the Redis Streams loop (consume, reclaim, retry, dead-letter, ack); for
executor events it hands each event to `execution.dispatch`, which routes it
to the handler a module registered for that `event_type`. Executors receive a
deliberately narrow `ExecutionDeps` instead of the full worker dependency
container.

## Layout

| File | Responsibility |
|------|----------------|
| `__init__.py` | Re-exports `ExecutionDeps`, `ExecutionHandler`, `dispatch`, `register_handler`, `registered_event_types`. Imports the executor modules for their side effect (registration): `analytics.score_runs.executor`, `connectors.executor`, `workflow_definitions.executor`. |
| `registry.py` | Module-level handler table. `ExecutionHandler = Callable[[AnyEvent, ExecutionDeps], int]`; `register_handler(event_type, handler)` (last registration wins); `registered_event_types()`; `dispatch(event, deps)`. |
| `deps.py` | `ExecutionDeps` — frozen, slotted dataclass of the dependencies executors may use (event bus, risk service, score-run repository, graph repository, domain config, connector repository, records service/config, workflow definition repository, workflow run store, capability registry, audit service, workflow domain/environment tag, connector source adapters). |

## Registered handlers

| Event type | Handler | Module |
|------------|---------|--------|
| `score.run.queued` | `handle_score_run_queued` | `analytics/score_runs/executor.py` |
| `score.batch.queued` | `handle_score_batch_queued` | `analytics/score_runs/executor.py` |
| `connector.page.queued` | `handle_connector_page_queued` | `connectors/executor.py` |
| `workflow.step.queued` | `handle_workflow_step_queued` | `workflow_definitions/executor.py` |

The event models live in `events/types.py` (`ScoreRunQueuedEvent`,
`ScoreBatchQueuedEvent`, `ConnectorPageQueuedEvent`, `WorkflowStepQueuedEvent`)
and are registered in `events/codec.py`; see
[docs/ledger/event-catalog.md](../../docs/ledger/event-catalog.md).

## Invariants

- **Registration is an import side effect.** If nothing on the worker's import
  path imported the executor modules, `dispatch` would find an empty registry
  and return 0 for every event. `tests/execution/test_registration.py` checks
  this in a fresh interpreter.
- **Subscription superset.** `WORKER_EVENT_TYPES` in `agent/coordinator.py`
  must contain every type in `registered_event_types()`, or a registered
  executor never receives its events.
- **Exceptions propagate.** `dispatch` does not catch; the coordinator calls it
  inside the retried handler (`run_handler_with_retry`), so executor failures
  get the same retry + DLQ treatment as pipeline failures.
- **Unregistered types return 0** rather than raising.
- **Missing dependencies degrade, not fail.** Every `ExecutionDeps` field is
  optional; a handler returns 0 when a dependency it needs is absent.
- **Narrow deps.** A handler needing something new adds one explicit field to
  `ExecutionDeps` rather than receiving the whole worker container.
- `deps.py` imports `WorkflowRunStoreProtocol` and `WorkflowDefinitionRepository`
  under `TYPE_CHECKING` only, to avoid an import cycle through the coordinator.

## Persistence

None. Executors persist through the repositories passed in `ExecutionDeps`.

## Tests

- `tests/execution/test_registry.py` — routing, last-wins, unregistered → 0,
  exception propagation.
- `tests/execution/test_registration.py` — fresh-interpreter check that the
  expected four event types are registered.

See also [agent/README.md](../agent/README.md) and
[docs/architecture.md](../../docs/architecture.md).
