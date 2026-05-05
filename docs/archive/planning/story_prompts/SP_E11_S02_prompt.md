# Story E11-S02: Config hot-reload — file watcher and API-triggered reload

## Story
As a platform operator, I want the running API and worker processes to pick up config changes without restarting, either by watching the config file for changes or by calling a reload endpoint.

## Acceptance Criteria
1. `config/loader.py` exposes a `ConfigCache` class that holds the current `DomainConfig` and exposes a thread-safe `reload()` method.
2. A `watch_config(path, cache, interval_seconds)` function polls for file mtime changes and calls `cache.reload()` when the file changes; it runs in a background thread and is stoppable via a stop event.
3. The FastAPI app registers `ConfigCache` as a singleton in the DI layer (`api/dependencies.py`) so all routes see the same cached instance.
4. Tests cover: initial load, reload on file change, concurrent reads during reload (no torn state), and stop event halting the watcher.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | M    | E11-S01      |

## Target Files
- `backend/config/loader.py` — add `ConfigCache` class and `watch_config()` function
- `backend/api/dependencies.py` — expose `ConfigCache` singleton via FastAPI `Depends`
- `backend/tests/config/test_loader.py` — extend with hot-reload tests

## Reference Files to Read First
- `backend/config/loader.py` — current loader implementation (post E11-S01)
- `backend/api/dependencies.py` — current dependency injection helpers
- `backend/api/app.py` — app factory to understand lifespan context
- `backend/tests/config/test_loader.py` — existing config test patterns

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- Thread safety: `ConfigCache` must guard against readers seeing a half-replaced config during reload — use a threading lock or atomic reference swap
- No new third-party dependencies (no watchdog) — simple `os.path.getmtime` polling is sufficient
- The watcher must not crash the process on a bad config file; it should log the error and keep the previous config
- See `docs/config_engine_plan.md` for the full config engine design

## What NOT To Do
- Do not implement the config management API endpoint here — that is E11-S03
- Do not use `inotify` or OS file-event APIs; polling is intentional for portability
- Do not reload eagerly on every poll tick; check mtime and skip if unchanged

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=config tests/config/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
