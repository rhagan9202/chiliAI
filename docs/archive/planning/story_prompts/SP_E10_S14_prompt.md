# Story E10-S14: OpenTelemetry distributed tracing

## Story
As a platform operator, I want distributed tracing across API requests and pipeline events using OpenTelemetry, so that I can trace a single user action through all backend services and identify performance bottlenecks.

## Acceptance Criteria
1. `opentelemetry-api`, `opentelemetry-sdk`, and `opentelemetry-instrumentation-fastapi` are installed.
2. The FastAPI app creates spans for each request, propagating trace context.
3. The worker coordinator creates child spans for each pipeline stage, linked by `correlation_id`.
4. Traces are exported to a configurable OTLP endpoint (default: stdout for development).
5. A test verifies span creation and parent-child relationships.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P2       | M    | E10-S08      |

## Target Files
- `backend/shared/tracing.py` — new tracing setup module (TracerProvider, exporter config, span helpers)
- `backend/api/app.py` — integrate tracing at app startup
- `backend/agent/coordinator.py` — integrate span creation for pipeline stages
- `backend/tests/shared/test_tracing.py` — tracing configuration and span tests

## Reference Files to Read First
- `backend/api/app.py` — FastAPI app factory, existing middleware/startup hooks
- `backend/agent/coordinator.py` — pipeline stage execution loop
- `backend/shared/logging.py` — structlog config from E10-S08 (for trace-log correlation)
- `backend/events/types.py` — event types with `correlation_id` field
- `backend/pyproject.toml` — current dependencies

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- Use OpenTelemetry Python SDK — not Jaeger client or other vendor-specific SDKs
- Trace context must propagate from API request → event → worker pipeline stages via `correlation_id`
- Exporter is configurable: `OTEL_EXPORTER=otlp|console` (console/stdout for development, OTLP for production)
- Tracing setup goes in `shared/tracing.py` — reusable from both API and worker entry points
- Integrate with structlog: inject `trace_id` and `span_id` into log entries when tracing is active

## What NOT To Do
- Do NOT use vendor-specific tracing SDKs (Datadog, New Relic, etc.) — use OpenTelemetry only
- Do NOT instrument every function — focus on HTTP requests and pipeline stages as span boundaries
- Do NOT add tracing to the hot path of individual record processing — trace at the stage level
- Do NOT make tracing mandatory — it must be disableable via config or env var
- Do NOT install all OpenTelemetry contrib packages — only `opentelemetry-instrumentation-fastapi` and core SDK
- Do NOT break existing structlog output — trace fields are additive

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=shared tests/shared/test_tracing.py` >= 85% coverage for tracing module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
- [ ] OpenTelemetry packages added to `pyproject.toml` dependencies
