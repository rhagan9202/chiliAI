# analytics/risk

Composite entity risk scoring. `RiskService` loads an entity's derived risk
signals, maps them to weighted factors through a pluggable scoring strategy,
classifies the overall score into a `low` / `medium` / `high` level, computes
a trend against the entity's previous score, and publishes `RiskScoredEvent`.
The module also owns the `risk_projections` read model behind the
`/analytics/risk-projections` queue.

See the package-level guide, [`../README.md`](../README.md), for the shared
analytics conventions, and for how `analytics/peerstats` and
`analytics/timeseries` produce the signals this module reads.

## Layout

| File | Responsibility |
|------|----------------|
| `models.py` | `RiskSignal`, `RiskProfile`, `RiskFactor`, `RiskAssessmentResult`, `RankedRiskEntry`, `RiskAssessmentRecord`. |
| `service_models.py` | `RiskAssessmentRequest` / `RiskAssessmentResponse` (with `RiskFactorScore`, `RiskTrend`), `RiskScoreListRequest` / `RiskScoreListResponse` / `RiskScore`. |
| `protocols.py` | `RiskServiceProtocol` (`assess`, `list_scores`) and `RiskScoringStrategyProtocol` (`score`). |
| `service.py` | `RiskService` / `create_risk_service`. |
| `adapters/linear_strategy.py` | `LinearScoringStrategy` — the default; each factor's contribution is `value * weight / total_weight`, capped at 1.0. |
| `adapters/protocols.py` | `RiskSignalSourceProtocol` (`load_profile`, `list_ranked_entries`, `load_historical_score`) and `RiskHistoryWriter` (`write_assessment`, `load_historical_score`, `delete_by_kb`). |
| `adapters/in_memory.py` | `InMemoryRiskSignalSource`, `InMemoryRiskHistoryWriter`. |
| `adapters/postgres.py` | `PostgresRiskSignalSource`, `PostgresRiskHistoryStore`, `PostgresRiskProjectionRepository`, `PostgresRiskProjectionRebuildSource`. |
| `projections.py` | `RiskProjectionRow`, `RiskProjectionQuery`, `RiskProjectionPage`, `RiskProjectionRepositoryProtocol`, `InMemoryRiskProjectionRepository`. |
| `projection_service.py` | `RiskProjectionService` (`project_assessment`, `rebuild_knowledge_base`) and `RiskProjectionRebuildSourceProtocol`. |
| `exceptions.py` | `RiskError` and subclasses `RiskConfigurationError`, `RiskInsufficientSignalsError`, `RiskSourceError`, `RiskHistoryError`, `RiskProjectionError`. |

## Contracts and invariants

- `assess` requires at least `min_signals` signals (`AnalyticsConfig.min_risk_signals`,
  default 2) or raises `RiskInsufficientSignalsError`.
- Level thresholds resolve per request, falling back to the service defaults
  (`AnalyticsConfig.medium_risk_threshold` / `high_risk_threshold`, defaults
  0.5 / 0.8); a resolved `high <= medium` raises `RiskConfigurationError`.
- The overall score is the sum of factor contributions, capped at 1.0. Trend
  is `None` with no prior score, otherwise `increasing` / `decreasing` /
  `stable` against `DEFAULT_TREND_DELTA_THRESHOLD`.
- `request.request_id` and `request.correlation_id` are carried onto the
  published event, so callers that pass a deterministic request id get
  idempotent history writes.
- `RiskService` does not write history itself; the worker's `risk.scored`
  handler does.
- `project_assessment` never replaces a projection row with an older
  `scored_at`, and is a no-op when the row is unchanged.
  `rebuild_knowledge_base` replaces a KB's rows only when the rebuilt set
  differs.

## How it is reached

- **Worker:** Flow B's `_run_risk_stage` and the records fan-out in
  `agent/coordinator.py` call `assess` per entity. `risk.scored` is handled by
  `handle_risk_scored_for_graph`, which writes `risk_score_history` through
  `RiskHistoryWriter`, writes properties back to the graph, and upserts the
  projection through `RiskProjectionService.project_assessment`. Failures
  propagate to the retry/DLQ wrapper.
- **Score runs:** `analytics/score_runs/executor.py` calls `assess` for each
  batch member (see [`../score_runs/README.md`](../score_runs/README.md)).
- **API** (`api/routers/analytics.py`, prefix `/analytics`):
  `GET /risk-scores` and `GET /risk-scores/{entity_id}` (viewer),
  `GET /risk-projections` (viewer), and `POST /risk-projections/rebuild`
  (analyst; rebuilds from `PostgresRiskProjectionRebuildSource`, 503 when no
  rebuild source is configured).

## Persistence

| Table | Migration | Access |
|-------|-----------|--------|
| `risk_score_history` | `0001_persistence_baseline` | `PostgresRiskHistoryStore` writes; `PostgresRiskSignalSource` reads ranking and the latest score. |
| `entity_derived_signals` | `0006_entity_derived_signals` | `PostgresRiskSignalSource.load_profile` reads the latest signal per metric. |
| `risk_projections` | `0013_risk_projections` | `PostgresRiskProjectionRepository`. |

`PostgresRiskProjectionRebuildSource` builds rows from `risk_score_history`
plus `alert_history`. KB deletion runs the `risk_history` and
`risk_projections` steps in `knowledgebases/cleanup.py`.

## Current gaps (from `TODO(production)` in code)

- `RiskSignalSourceProtocol` has no batch `load_profiles` or signal streaming.

## Tests

`tests/analytics/risk/` — models, service, in-memory adapters, projections and
projection service, and Postgres history / projection / signal-source tests
(`test_postgres_history_store.py` and
`test_postgres_signal_source_integration.py` run against a live database).
