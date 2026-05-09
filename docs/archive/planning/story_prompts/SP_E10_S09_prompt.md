# Story E10-S09: Prometheus metrics endpoint

## Story
As a platform operator, I want a `/metrics` endpoint exposing Prometheus-format metrics (request count, latency, pipeline stage duration, error counts), so that the platform is observable via standard monitoring tools.

## Acceptance Criteria
1. `prometheus-client` is installed.
2. `GET /metrics` returns Prometheus text-format metrics.
3. Instrumented metrics: `http_requests_total` (by method, path, status), `http_request_duration_seconds` (histogram), `pipeline_stage_duration_seconds` (by stage), `pipeline_errors_total` (by stage), `active_alerts_total` (gauge).
4. A FastAPI middleware collects HTTP metrics automatically.
5. A test verifies the `/metrics` endpoint returns valid Prometheus format.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | M    | None         |

## Target Files
- `backend/api/middleware/metrics.py` — HTTP metrics middleware and `/metrics` route
- `backend/api/app.py` — register metrics middleware
- `backend/monitoring/metrics.py` — pipeline metrics helpers (counters, histograms for stages)
- `backend/tests/api/test_metrics.py` — metrics endpoint and middleware tests

## Reference Files to Read First
- `backend/api/app.py` — FastAPI app factory, existing middleware registration
- `backend/agent/coordinator.py` — pipeline stage execution (where stage metrics are emitted)
- `backend/monitoring/service.py` — existing monitoring service patterns
- `backend/pyproject.toml` — current dependencies

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- Use `prometheus-client` library — do not build a custom metrics format
- The `/metrics` endpoint must not require authentication (Prometheus scraper access)
- HTTP metrics middleware must not significantly impact request latency (< 1ms overhead)
- Pipeline metrics helpers in `monitoring/metrics.py` must be usable from the worker coordinator without importing API code
- Metric names must follow Prometheus naming conventions: `snake_case`, units as suffix

## What NOT To Do
- Do NOT create a custom metrics format — use Prometheus text exposition format
- Do NOT add authentication to the `/metrics` endpoint — it must be scrapeable
- Do NOT use high-cardinality labels (e.g., user ID, document ID) — stick to method, path, status, stage
- Do NOT instrument every function — focus on HTTP requests and pipeline stages
- Do NOT add Grafana dashboards or alerting rules in this story — just the metrics endpoint
- Do NOT use the multiprocess mode of prometheus-client unless deploying with gunicorn workers

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=api tests/api/test_metrics.py` >= 85% coverage for metrics module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
- [ ] `prometheus-client` added to `pyproject.toml` dependencies
