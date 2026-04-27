# Story E4-S06: Graceful shutdown for the worker process

## Story
As a platform operator, I want the worker to handle SIGTERM/SIGINT gracefully by finishing the current event before exiting.

## Acceptance Criteria
1. `agent/coordinator.py` registers signal handlers for SIGTERM and SIGINT.
2. On signal receipt, the worker sets a shutdown flag and stops polling for new events.
3. The currently processing event (if any) completes before the process exits.
4. Logging outputs "Shutdown requested, finishing current event..." and "Worker stopped gracefully."
5. Test simulates shutdown during processing and verifies the in-flight event completes.

## Priority / Size / Dependencies
| Field        | Value       |
|--------------|-------------|
| Priority     | P1          |
| Size         | S           |
| Dependencies | None        |

## Target Files
- `backend/agent/coordinator.py` — add signal handlers, shutdown flag, graceful shutdown logic
- `backend/tests/agent/test_coordinator.py` — test simulating shutdown during event processing

## Reference Files to Read First
- `backend/agent/coordinator.py` — current event loop / polling structure
- `backend/agent/models.py` — existing coordinator models
- `backend/events/protocols.py` — `EventBus` protocol (subscribe/poll interface)
- `backend/tests/agent/test_coordinator.py` — existing test patterns

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- Use `asyncio`-compatible signal handling (`loop.add_signal_handler`) or `signal.signal` as appropriate for the coordinator's execution model
- The shutdown flag must be checked between event polls, not mid-processing
- The in-flight event must complete fully (including any publishes) before the worker exits
- Log messages must match exactly: "Shutdown requested, finishing current event..." and "Worker stopped gracefully."

## What NOT To Do
- Do not forcefully terminate in-flight event processing on signal receipt
- Do not use `os._exit()` or `sys.exit()` while an event is being processed
- Do not add a hard timeout that kills the process if the current event takes too long (that is a separate concern)
- Do not modify event handler logic — only the coordinator's main loop and signal handling
- Do not introduce new dependencies for signal handling

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=agent tests/agent/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)

## Implementation Note
Completed on April 26, 2026. `agent/coordinator.run_worker` now creates an
`asyncio.Event` and calls `install_signal_handlers(loop, event)` before
entering the drain loop. `install_signal_handlers` registers
`loop.add_signal_handler` callbacks for `SIGTERM` and `SIGINT`; the
fallback for non-Unix platforms uses `signal.signal` with a typed callback
shim. On signal receipt the coordinator logs
`"Shutdown requested, finishing current event..."` exactly once via
`SHUTDOWN_LOG_REQUESTED` and sets the shutdown event. The main loop checks
the event between batches and exits cleanly, emitting
`"Worker stopped gracefully."` (the `SHUTDOWN_LOG_DONE` constant) in the
`finally` block. Tests cover the signal handler path
(`os.kill(os.getpid(), SIGTERM)`), the manual flag-flip path, and a
graceful-shutdown sequence that asserts the final log message.

## Validation Note
From `backend/`: `pytest tests/agent tests/events tests/api --cov=agent
--cov=events --cov=api --cov-report=term-missing` passed with 91 tests;
agent coverage 87%. `ruff check agent events api tests/agent tests/events
tests/api` passed. `pyright agent events api tests/agent tests/events
tests/api` reported 0 errors.
