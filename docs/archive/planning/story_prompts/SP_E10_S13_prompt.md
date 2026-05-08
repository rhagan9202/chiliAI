# Story E10-S13: E2E integration test suite

## Story
As a platform developer, I want an end-to-end test suite that validates the full pipeline (upload → ingest → graph → analytics → alerts) against in-memory adapters, so that cross-module integration is continuously verified.

## Acceptance Criteria
1. `tests/e2e/test_full_pipeline.py` starts the API app and worker coordinator with in-memory adapters.
2. The test uploads a document, waits for pipeline completion (polling or event subscription), and asserts: document parsed, entities extracted, graph populated, analytics run, alerts generated.
3. At least three E2E scenarios: single document happy path, multi-document batch, document with extraction errors (graceful degradation).
4. E2E tests run in CI but are tagged `@pytest.mark.e2e` for optional exclusion in local development.
5. Test duration < 30 seconds per scenario.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | L    | E7-S10, E8-S07 |

## Target Files
- `backend/tests/e2e/__init__.py` — e2e test package init
- `backend/tests/e2e/test_full_pipeline.py` — full pipeline integration tests
- `backend/tests/e2e/conftest.py` — shared fixtures (app client, in-memory adapters, worker setup)
- `backend/pyproject.toml` — add `e2e` pytest marker

## Reference Files to Read First
- `backend/api/app.py` — FastAPI app factory (for TestClient setup)
- `backend/api/dependencies.py` — dependency injection (for overriding with in-memory adapters)
- `backend/agent/coordinator.py` — worker coordinator (for in-process pipeline execution)
- `backend/events/adapters/` — in-memory event bus adapter
- `backend/ingestion/service.py` — ingestion pipeline entry point
- `backend/graph/service.py` — graph operations
- `backend/analytics/` — analytics sub-modules
- `backend/monitoring/service.py` — alert generation

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All E2E tests use in-memory adapters — no external services (no Redis, no DB, no LLM API)
- Use `httpx.AsyncClient` with `ASGITransport` (or FastAPI `TestClient`) for API calls
- Worker coordinator must run in-process (not as a separate process) for test isolation
- Tests must be deterministic — no timing-dependent assertions, use polling with timeout
- Tag all E2E tests with `@pytest.mark.e2e` so they can be excluded with `pytest -m "not e2e"`

## What NOT To Do
- Do NOT start real Redis or database processes in E2E tests
- Do NOT use `time.sleep()` for waiting — use polling loops with explicit timeouts
- Do NOT make tests depend on execution order — each test must set up and tear down its own state
- Do NOT test individual module internals — E2E tests validate cross-module integration only
- Do NOT exceed 30 seconds per scenario — if tests are slow, the fixture setup is too heavy
- Do NOT import from module internals — use only public service APIs and the HTTP API

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created
- [ ] Tests written and passing
- [ ] At least 3 E2E scenarios implemented
- [ ] `@pytest.mark.e2e` marker registered in `pyproject.toml`
- [ ] Each scenario completes in < 30 seconds
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
