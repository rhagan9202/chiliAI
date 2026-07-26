# analytics contributor guide

This package owns analytical capabilities for chiliAI: time-series anomaly
detection, GNN-style graph analysis, risk scoring, explainability, and
entity-metric and peer-stat persistence. It is intentionally friendly to algorithms that begin
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
repository adapters and no service or events. `analytics/peerstats` computes
record-column peer z-scores and persists derived risk signals consumed by
`analytics/risk`.

`analytics/gnn` is a worked example of the protocol-plus-adapter pattern this
guide prescribes, now live end to end: `GraphRepositorySnapshotSource`
(`adapters/graph_repository_source.py`) implements `GraphSnapshotSourceProtocol`
against **any** `GraphRepository` (in-memory or Neo4j) rather than a
GNN-specific data source, bounding the node set it hands to `GnnService` by
`DomainConfig.gnn.snapshot_max_nodes`. Cluster results get their own small
protocol, `ClusterSummaryStoreProtocol` (`adapters/cluster_store.py`), with
in-memory and object-store adapters — a second protocol was worth adding here
because cluster persistence has a different lifecycle (write-once-per-analyze,
read-many by the clusters endpoint) than the read-only graph snapshot. See
`backend/README.md` § Analytics Runtime Notes for the full worker/API wiring
and cascade-delete behavior, and
`backend/tests/analytics/gnn/test_gnn_live_integration.py` for the live-Neo4j
round trip that proves the whole path (`@pytest.mark.integration`).

## Timeseries series-source contract

`analytics/timeseries` is wired end to end for self-history anomaly
detection (Sprint 2026-28 B2, BL-047). The series source splits by scope,
and picking the wrong one silently returns empty data instead of erroring —
worth stating explicitly:

- **Per-entity series** (used by `GET /analytics/timeseries/{entity_id}` and
  the worker's `run_timeseries_stage`) come from `raw_records` interval
  aggregates, not `observations`. `RecordAggregateTimeSeriesSource`
  (`analytics/timeseries/adapters/record_aggregates.py`) implements
  `TimeSeriesHistorySourceProtocol.load_series` by reusing
  `analytics/peerstats`'s `RecordColumnSourceProtocol.load_interval_aggregates`
  SQL — `to_peer_spec()` converts a `TimeseriesMetricSpec` into the peerstats
  `PeerMetricSpec` shape the aggregate query expects, so both submodules
  share one JSONB-aggregation implementation (peerstats reads it
  cross-sectionally per interval; timeseries reads it longitudinally per
  entity). `load_entity_series_map()` is the worker's batch form — one
  aggregate query per configured `TimeseriesMetricSpec`, not one per entity.
  `RecordAggregateTimeSeriesSource.load_metric_range` intentionally returns
  `[]`: it is a per-entity source, and graph-scope range reads are not its
  job.
- **Graph-scope series** (the `GET /analytics/timeseries?metric=...`
  metric-range route) stay on `PostgresTimeSeriesHistorySource` /
  `InMemoryTimeSeriesHistorySource` over `entity_metric_history`, which Flow
  2 writes only with `entity_id="__graph__"`. This path is unchanged by the
  B2 work.
- **`observations` is monitoring-only.** analytics.06 originally planned an
  `observations`-backed per-entity series path; that acceptance criterion is
  **superseded** — see `docs/backlog/analytics.md` story analytics.06 for
  the full rationale (`MonitoringObservation.score` is hard-bounded `[0,1]`
  with no headroom for raw payment amounts, `observed_at` collapses to
  `ingested_at` on a bulk demo ingest, and the `(kb, entity, metric,
  observed_at)` primary key silently drops same-day duplicate claims via
  `ON CONFLICT DO NOTHING`). `observations` remains the write target for
  `monitoring/adapters/postgres.py::PostgresObservationStore` and
  monitoring's own threshold evaluation only; the timeseries module never
  reads it.
- **Anomaly persistence.** Detected `AnomalyPoint`s are upserted to the
  `timeseries_anomalies` table (migration
  `backend/database/migrations/versions/0011_timeseries_anomalies.py`, PK
  `(knowledge_base_id, entity_id, metric_name, observed_at)`) via
  `TimeseriesAnomalyStoreProtocol` (`adapters/protocols.py`, with
  `adapters/in_memory.py` and `adapters/postgres.py` implementations). The
  same detection pass also upserts a `DerivedRiskSignal`
  (`metric_name = "timeseries_anomaly:<spec name>"`) to
  `entity_derived_signals`, so `PostgresRiskSignalSource` (in
  `analytics/risk`) picks up anomaly severities the same way it already
  reads peerstats z-scores.
- **KB-delete cascade membership.** `TimeseriesAnomalyStoreProtocol` also
  satisfies the structural `TimeseriesAnomalyPurger` protocol
  (`delete_by_kb`); `knowledgebases.cleanup.kb_deletion_steps` runs the
  `timeseries_anomalies` step directly after `derived_signals`, and the
  field is required on both the API's and the worker's `KbDeletionStores`
  bundles.

See `backend/README.md` § Analytics Runtime Notes for the full worker/API
wiring (`run_timeseries_stage`, its controlled-skip semantics, and the
`DomainConfig.timeseries` config surface).

## Explainability narrative + attribution seams

`analytics/explainability` composes two independently-selectable, config-driven
seams (Sprint 2026-28 B3, BL-048) inside `ExplainabilityService`. Both are
injected via constructor keywords defaulting to a no-op implementation, and
both adapters follow a hard **never-raise** contract — any internal failure
degrades to the fallback output and logs a WARNING, so a misconfigured or
unreachable backend never turns a pipeline stage into `analysis.failed`.

- **Narrative generation** (`NarrativeGeneratorProtocol.summarize`) — selected
  via `AnalyticsConfig.narrative_backend: Literal["deterministic","llm"]`
  (default `"deterministic"`). `DeterministicNarrativeGenerator`
  (`adapters/deterministic.py`) is the extracted, behavior-preserving form of
  the original space-joined-by-`source_type` narrative. `LlmNarrativeGenerator`
  (`adapters/llm_narrative.py`) wraps `llm.protocols.LlmServiceProtocol` with an
  injected `DeterministicNarrativeGenerator` as its fallback: it renders a
  markdown-instructed prompt from the selected `ExplanationItem`s (source id,
  quote, rationale, score) plus the alert title and score snapshot, then parses
  `## `-headed response sections into `NarrativeSection`s. Degrades to the
  fallback on any `LlmError`; any unexpected exception, including
  `GenerateRequest` construction itself (it sits inside the guard, so an
  out-of-range sampling param can't break the never-raise contract); an
  empty completion; or a malformed completion — no `## ` sections at all, or
  an empty opening summary (a completion that opens directly with a
  heading). Heading-less output is **not** accepted as a summary-only
  narrative: both shapes leave persisted packs with an empty
  `narrative_sections` list or an empty reasoning lead, so both degrade.
- **Feature attribution** (`FeatureAttributorProtocol.attribute`) — selected via
  `AnalyticsConfig.attribution_backend: Literal["none","shap"]` (default
  `"none"`). `NoopFeatureAttributor` (`adapters/shap_attribution.py`) returns
  `[]` unconditionally. `ShapRiskAttributor` (same file) attributes
  `analytics.risk`'s `LinearScoringStrategy` composite
  (`predict(X) = min(1.0, Σx_i)`) over the per-feature contributions already
  snapshotted in `context.scores` (every key except `"overall"`), running
  `shap.Explainer` against a zero-baseline background — for this linear model
  the SHAP values are exact per-feature marginal contributions, so the same
  seam attributes a trained model later without changing its shape. Lazily
  imports `shap`/`numpy`; a missing `[analytics]` extra, no risk-factor
  features, or any explainer exception degrades to `[]`.
- **Not the same seam as `adapters/shap_adapter.py`.** That module
  (`ShapExplainabilityContextSource`) implements the older
  `ExplainabilityContextSourceProtocol` — it explains a model callable and maps
  attributions to `ExplanationItem`s for the *context-loading* step. It
  predates B3, is still not selected anywhere in DI (the `in_memory|shap|lime`
  context-source literal from `docs/backlog/analytics.md` story analytics.14
  was never built), and is unrelated to `ShapRiskAttributor`'s pipeline
  *attribution* seam above beyond sharing the `shap` dependency.
- `agent.coordinator.build_narrative_generator`/`build_feature_attributor`
  construct both from `DomainConfig` at the Flow B assembly site; both are
  threaded into `create_explainability_service(...)` alongside the existing
  context source. See `backend/README.md` § Analytics Runtime Notes for the
  full worker wiring and default-pack enablement.
- Persisted `EvidencePack`s (`shared/types.py`) carry the results as
  `attribution: list[FeatureAttribution]` and
  `narrative_sections: list[EvidenceNarrativeSection]`, both defaulting to
  `[]` so pre-B3 persisted object-store packs deserialize unchanged.
  `EvidencePackResponse` (`api/contracts.py`) mirrors both fields 1:1 via
  `api/dependencies.py::_evidence_pack_to_response`.

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

**Records-ingested KBs run Flow B natively (analytics.34, 2026-07-24):**
GNN → risk → explainability → alerts fire at the end of
`handle_records_ingested` as a direct in-process call — gated by
`DomainConfig.records.analytics_trigger` (default off; the CMS pack enables
it), throttled per KB, capped to the batch's top-N entities by risk score.
No `graph.updated` event is published for records; the fan-out passes
inline `upserted_entity_ids`. See `docs/wiki/modules/agent.md` and
`backend/records/README.md` § Flow 1.

## Postgres and migrations

Use existing tables before adding new schema:

- `raw_records` for structured landed source records.
- `observations` for monitoring observations.
- `entity_metric_history` and `entity_metrics_current` for metric history and
  current snapshots.
- `risk_score_history` for risk assessment history.
- `alert_history` for alert history.
- `entity_derived_signals` for peerstats- and timeseries-derived risk
  signals (upserted by `analytics/peerstats` and `analytics/timeseries`,
  read by `PostgresRiskSignalSource` in `analytics/risk`).
- `timeseries_anomalies` for persisted self-history anomaly points (see
  "Timeseries series-source contract" above).

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
