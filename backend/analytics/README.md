# analytics contributor guide

This package owns analytical capabilities for chiliAI: time-series anomaly
detection, GNN-style graph analysis, risk scoring, explainability, and
entity-metric persistence. It is intentionally friendly to algorithms that begin
life as notebooks or scripts, but production code in this package must still
follow the backend architecture:

- Keep SQL and database access in adapters.
- Keep algorithms deterministic and testable in services or small helper
  functions.
- Expose typed Pydantic request/response models at service boundaries.
- Publish events from services only when the analysis has produced a valid
  result.
- Do not import from `api`, `ingestion`, records internals, or another analytics
  module's internals.

The goal is not to make data-science code look artificially enterprise-heavy.
The goal is to make useful analysis scripts repeatable, observable, testable,
and safe to run against production data.

## Current package shape

Most analytics modules use the standard backend module layout:

```text
analytics/<capability>/
├── __init__.py
├── adapters/
│   ├── __init__.py
│   ├── protocols.py      # adapter-side data access contracts
│   ├── in_memory.py      # test/local implementation
│   └── postgres.py       # optional, only when Postgres owns the data
├── exceptions.py
├── models.py             # internal domain models
├── protocols.py          # service protocol consumed by API/agent
├── service.py            # orchestration + algorithm dispatch
└── service_models.py     # public service/API request and response models
```

`analytics/metrics` is intentionally smaller: it is a persistence package with
repository adapters and no service or events.

## Where script code belongs

Use this mapping when converting a script or notebook into the codebase:

| Script concern | Production home |
| --- | --- |
| `SELECT ... FROM ...` | `adapters/postgres.py` |
| CSV/list fixtures for local runs | `adapters/in_memory.py` or tests |
| pandas dataframe cleanup | adapter mapping or a private pure helper |
| algorithm parameters | `service_models.py` request fields |
| output rows/scores | `models.py` internally, `service_models.py` externally |
| exceptions from missing data/config | `exceptions.py`, translated in `service.py` |
| endpoint shape | `api/routers/analytics.py` using service protocol |
| long-running workflow trigger | `agent/coordinator.py` using events |

The service should not know whether data came from Postgres, Neo4j, a fixture,
or a future warehouse. It asks an adapter protocol for typed inputs.

## Decision guide

1. Add a new strategy inside an existing module when the request and result
   shape stay the same. Example: adding a new time-series detection strategy to
   `analytics/timeseries`.
2. Add a new adapter when the algorithm is the same but the data source changes.
   Example: replacing in-memory risk signals with graph-derived or
   Postgres-derived signals behind `RiskSignalSourceProtocol`.
3. Add a new analytics module only when the capability has a different lifecycle,
   request model, result model, persistence model, or event type. Example:
   adding cohort analysis should probably be `analytics/cohorts`, not another
   method on `RiskService`.
4. Add a database migration only when the result needs durable storage or the
   adapter needs new relational tables. Existing analytical reads should use the
   tables already owned by migrations where possible.

## Worked example: moving a Postgres script into analytics

Assume a data scientist starts with this script:

```python
rows = conn.execute(
    """
    SELECT entity_id, count(*) AS claim_count, sum(amount) AS total_amount
    FROM raw_records
    WHERE knowledge_base_id = %s AND feed_name = 'claims'
    GROUP BY entity_id
    """,
    (kb_id,),
).fetchall()

scores = []
for entity_id, claim_count, total_amount in rows:
    score = min(1.0, (claim_count / 100.0) + (total_amount / 1_000_000.0))
    scores.append((entity_id, score))
```

Do not paste that into an API route or worker handler. Split it into four
pieces.

### 1. Define typed internal models

Create `analytics/cohorts/models.py`:

```python
from __future__ import annotations

from pydantic import BaseModel, Field


class ProviderClaimAggregate(BaseModel):
    knowledge_base_id: str
    entity_id: str
    claim_count: int = Field(ge=0)
    total_amount: float = Field(ge=0.0)


class ProviderCohortScore(BaseModel):
    entity_id: str
    score: float = Field(ge=0.0, le=1.0)
```

Use generic names unless the capability is truly domain-specific. chiliAI
domains are config-driven, so avoid hardcoded `Provider`, `Claim`, or
`Beneficiary` classes in shared code. If an analysis only makes sense for one
domain, keep that assumption in request parameters, config, or adapter queries.

### 2. Define an adapter protocol

Create `analytics/cohorts/adapters/protocols.py`:

```python
from __future__ import annotations

from typing import Protocol, runtime_checkable

from analytics.cohorts.models import ProviderClaimAggregate


@runtime_checkable
class ClaimAggregateSource(Protocol):
    def load_provider_claim_aggregates(
        self,
        *,
        knowledge_base_id: str,
    ) -> list[ProviderClaimAggregate]: ...
```

The protocol returns validated Python objects, not raw database rows.

### 3. Put SQL in a Postgres adapter

Create `analytics/cohorts/adapters/postgres.py`:

```python
from __future__ import annotations

from typing import cast

from analytics.cohorts.exceptions import CohortSourceError
from analytics.cohorts.models import ProviderClaimAggregate
from database.protocols import ConnectionProvider, Row


_CLAIM_AGGREGATES_SQL = """
    SELECT entity_id, count(*) AS claim_count, coalesce(sum(amount), 0) AS total_amount
    FROM raw_records
    WHERE knowledge_base_id = %s AND feed_name = %s
    GROUP BY entity_id
    ORDER BY entity_id
"""


class PostgresClaimAggregateSource:
    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def load_provider_claim_aggregates(
        self,
        *,
        knowledge_base_id: str,
    ) -> list[ProviderClaimAggregate]:
        try:
            with self._provider.connection() as conn:
                rows = conn.execute(
                    _CLAIM_AGGREGATES_SQL,
                    (knowledge_base_id, "claims"),
                ).fetchall()
        except Exception as exc:
            raise CohortSourceError("Failed to load claim aggregates.") from exc
        return [_row_to_aggregate(knowledge_base_id, row) for row in rows]


def _row_to_aggregate(knowledge_base_id: str, row: Row) -> ProviderClaimAggregate:
    return ProviderClaimAggregate(
        knowledge_base_id=knowledge_base_id,
        entity_id=cast(str, row[0]),
        claim_count=int(cast(int, row[1])),
        total_amount=float(cast(float, row[2])),
    )
```

Rules for adapter SQL:

- Always use parameterized queries. Never build SQL with f-strings.
- Depend on `database.ConnectionProvider`, not psycopg directly.
- Convert `Row` values into Pydantic models at the adapter boundary.
- Raise module-specific exceptions, then let the service translate them if
  needed.
- Keep optional dependencies lazy. Import pandas, sklearn, SHAP, torch, or
  statsmodels inside the function or adapter path that uses them.

### 4. Keep scoring deterministic in the service

Create `analytics/cohorts/service.py`:

```python
from __future__ import annotations

from analytics.cohorts.adapters.protocols import ClaimAggregateSource
from analytics.cohorts.models import ProviderClaimAggregate, ProviderCohortScore
from analytics.cohorts.service_models import CohortScoreRequest, CohortScoreResponse


class CohortService:
    def __init__(self, aggregate_source: ClaimAggregateSource) -> None:
        self._aggregate_source = aggregate_source

    def score(self, request: CohortScoreRequest) -> CohortScoreResponse:
        aggregates = self._aggregate_source.load_provider_claim_aggregates(
            knowledge_base_id=request.knowledge_base_id,
        )
        scores = [_score_provider(row) for row in aggregates]
        scores.sort(key=lambda item: item.score, reverse=True)
        return CohortScoreResponse(
            knowledge_base_id=request.knowledge_base_id,
            scores=scores[: request.limit],
        )


def _score_provider(row: ProviderClaimAggregate) -> ProviderCohortScore:
    score = min(
        1.0,
        (row.claim_count / 100.0) + (row.total_amount / 1_000_000.0),
    )
    return ProviderCohortScore(entity_id=row.entity_id, score=score)
```

The pure `_score_provider` helper is easy to test without a database. Keep as
much math as possible in helpers like this.

### 5. Define service-boundary models

Create `analytics/cohorts/service_models.py`:

```python
from __future__ import annotations

from pydantic import BaseModel, Field

from analytics.cohorts.models import ProviderCohortScore


class CohortScoreRequest(BaseModel):
    knowledge_base_id: str
    limit: int = Field(default=20, gt=0, le=500)


class CohortScoreResponse(BaseModel):
    knowledge_base_id: str
    scores: list[ProviderCohortScore] = Field(default_factory=list[ProviderCohortScore])
```

`service_models.py` is what API routers and other modules should import.
Internal-only records stay in `models.py`.

## Adding an algorithm to an existing service

For a new time-series detection strategy:

1. Add the literal value to `DetectionStrategy` in
   `analytics/timeseries/service_models.py`.
2. Add request parameters with validation if the strategy needs them.
3. Add a private helper in `analytics/timeseries/service.py`, for example
   `_detect_anomalies_quantile(...)`.
4. Dispatch it from `TimeseriesService._dispatch_detection`.
5. Add unit tests for the helper and service dispatch.
6. If it requires an optional dependency, lazy import it and raise
   `TimeseriesConfigurationError` with installation guidance when missing.

Example dispatch shape:

```python
if strategy == "quantile":
    return _detect_anomalies_quantile(
        observations,
        lower_quantile=lower_quantile,
        upper_quantile=upper_quantile,
    )
```

Do not change API routes until the service behavior is covered by tests.

## Adding a new analytics module

Use this checklist:

1. Create `analytics/<name>/` with the standard module files.
2. Define internal Pydantic models in `models.py`.
3. Define public request/response Pydantic models in `service_models.py`.
4. Define adapter protocols in `adapters/protocols.py`.
5. Add `InMemory...` adapters for tests and local development.
6. Add `Postgres...` adapters only when the data is truly relational or
   time-series data. Otherwise use graph, vector, or object-store protocols
   through the existing module boundaries.
7. Implement a service class that accepts protocols in `__init__`.
8. Add a service protocol in `<module>/protocols.py`.
9. Export only the public surface from `__init__.py`.
10. Add tests under `backend/tests/analytics/<name>/`.
11. Wire API endpoints or worker handlers only after the service is tested.
12. Update `backend/README.md` and `docs/architecture.md` if the new capability
    changes the platform surface, config, events, or persistence model.

## API and worker wiring

API routers should validate HTTP inputs and call a service protocol. They should
not contain scoring logic, SQL, dataframe code, or script orchestration.

Worker handlers in `agent/coordinator.py` are for pipeline composition:

- consume a typed event;
- load or build the service and adapters;
- call one service method;
- persist or publish the next typed event.

If a capability is expensive or batch-oriented, prefer event-driven worker
wiring over synchronous API execution.

## Postgres and migrations

Use existing tables before adding new schema:

- `raw_records` for structured landed source records.
- `observations` for monitoring observations.
- `entity_metric_history` and `entity_metrics_current` for metric history and
  current snapshots.
- `risk_score_history` for risk assessment history.
- `alert_history` for alert history.

When a new table is required:

1. Add an Alembic migration under `backend/database/migrations/versions/`.
2. Keep migration SQL in the database module; do not hide schema changes in
   adapters.
3. Add repository/adapter tests for insert, idempotency, read order, and empty
   result behavior.
4. Document the table in `backend/database/README.md` and
   `docs/architecture.md`.

## Testing expectations

Every analytics contribution should include:

- model validation tests for new request/result models;
- pure algorithm tests using small deterministic fixtures;
- service tests with in-memory adapters;
- adapter tests for Postgres reads/writes when SQL is added;
- API tests when routes are added or changed;
- worker/coordinator tests when event flow changes.

Keep fixtures small and explicit. Prefer named rows and expected scores over
large copied datasets. For probabilistic algorithms, set seeds or test
invariants rather than exact floating point internals.

Useful commands from `backend/`:

```bash
uv run pytest tests/analytics/<module>
uv run pytest tests/api/test_analytics_router.py
uv run pyright
uv run ruff check .
```

Use integration markers for tests that require running Postgres/TimescaleDB or
optional ML packages.

## Common review failures

- SQL inside an API route, service helper, or notebook-style utility.
- Raw database rows crossing into service logic.
- Untyped dictionaries used as model substitutes.
- Unbounded queries with no knowledge-base scope.
- Domain-specific classes added to `shared/types.py`.
- Optional ML dependencies imported at module import time.
- Algorithms that mutate global state or rely on hidden files.
- Tests that only check "does not crash" instead of exact outputs or invariants.
- Cross-module imports that bypass protocols.

## Before opening a PR

Run this checklist:

1. The module imports cleanly without optional analytics extras installed.
2. All public models are typed and validated.
3. SQL is parameterized and scoped by `knowledge_base_id` where applicable.
4. The algorithm can be tested without a database.
5. The adapter can be tested without running the whole API.
6. Events are published only after successful analysis.
7. README and architecture docs are updated for new capabilities, config, or
   persistence.
