# Module: analytics

**Verified against codebase:** 2026-06-16 · **Sub-module list reconciled:** 2026-08-06
**Source:** `backend/analytics/`

## Purpose

ML/AI capability modules. **Nine** sub-modules, most following the standard module shape (`protocols.py`, `service_models.py`, `service.py`, `adapters/`). The three added by the SAFE-CMS surge are documented in `docs/ledger/module-map.md` and are **not** detailed below — `features/` (catalog reads; `list_entity_values` is a stub), `identity_resolution/` (canonical links; no production writer), `score_runs/` (run state; no executor):

| Sub-module | Responsibility |
|-----------|---------------|
| `timeseries/` | Time-series anomaly detection on entity metric observations |
| `gnn/` | Graph neural network link prediction and community detection |
| `risk/` | Risk scoring engine — linear combination of weighted signals |
| `explainability/` | Evidence pack generation — pluggable narrative (deterministic/LLM) and feature-attribution (noop/SHAP) seams over an in-memory or SHAP-based context source |
| `metrics/` | Entity-metric persistence; no events, no service entrypoint |
| `peerstats/` | Record-column peer z-score analytics that persist derived risk signals |

---

## `timeseries/`

### Protocol

Last verified: 2026-06-16

```python
class TimeseriesServiceProtocol(Protocol):
    def analyze(self, request: TimeseriesAnalysisRequest) -> TimeseriesAnalysisResponse: ...
    def query_metric(self, request: TimeseriesQueryRequest) -> MetricTimeseriesResponse: ...
```

### Service Models (`analytics/timeseries/service_models.py`)

```python
DetectionStrategy = Literal["z_score", "stl_decomposition", "isolation_forest"]

class TimeseriesAnalysisRequest(BaseModel):
    knowledge_base_id: str; entity_id: str; metric_name: str
    baseline_window: int = Field(default=5, gt=1)
    min_history: int = Field(default=6, gt=2)    # must exceed baseline_window
    z_threshold: float = Field(default=2.0, gt=0.0)
    detection_strategy: DetectionStrategy = "z_score"
    contamination: float = Field(default=0.05, gt=0.0, le=0.5)
    window_size: int | None = None

class TimeseriesAnomaly(BaseModel):
    observed_at: datetime; observed_value: float
    expected_value: float; deviation: float; z_score: float

class TimeseriesAnalysisResponse(BaseModel):
    request_id: str; knowledge_base_id: str
    entity_id: str; metric_name: str
    observation_count: int; anomaly_count: int
    anomalies: list[TimeseriesAnomaly] = []

class TimeseriesQueryRequest(BaseModel):
    knowledge_base_id: str; metric_name: str
    start: datetime; end: datetime     # end must be after start

class TimeseriesPoint(BaseModel):
    observed_at: datetime; value: float

class MetricTimeseriesResponse(BaseModel):
    knowledge_base_id: str; metric_name: str
    start: datetime; end: datetime
    points: list[TimeseriesPoint] = []
```

### Adapters
| Backend | File |
|---------|------|
| In-memory | `adapters/in_memory.py::InMemoryTimeSeriesHistorySource` |
| Postgres | `adapters/postgres.py::PostgresTimeSeriesHistorySource` |

---

## `gnn/`

### Protocol

Last verified: 2026-06-16

```python
class GnnServiceProtocol(Protocol):
    def analyze(self, request: GnnAnalysisRequest) -> GnnAnalysisResponse: ...
    def list_clusters(self, request: GnnClusterRequest) -> GnnClusterResponse: ...
```

### Service Models (`analytics/gnn/service_models.py`)

```python
class GnnAnalysisRequest(BaseModel):
    knowledge_base_id: str
    similarity_threshold: float = Field(default=0.9, ge=0.0, le=1.0)
    top_k_predictions: int = Field(default=5, gt=0)
    embedding_dimension: int = Field(default=8, gt=0, le=256)

class GnnNodeScore(BaseModel):
    entity_id: str; score: float; cluster_id: str

class GnnLinkPrediction(BaseModel):
    source_id: str; target_id: str; confidence: float   # [0, 1]

class GnnCommunityResult(BaseModel):
    community_id: str; member_entity_ids: list[str]; density: float  # [0, 1]

class GnnAnalysisResponse(BaseModel):
    request_id: str; knowledge_base_id: str
    node_count: int; edge_count: int
    scored_nodes: list[GnnNodeScore] = []
    predicted_links: list[GnnLinkPrediction] = []
    communities: list[GnnCommunityResult] = []
    node_embeddings: dict[str, list[float]] = {}

class GnnClusterRequest(BaseModel):
    knowledge_base_id: str

class ClusterResult(BaseModel):
    cluster_id: str; entity_ids: list[str]
    anomaly_score: float; label: str | None

class GnnClusterResponse(BaseModel):
    knowledge_base_id: str; clusters: list[ClusterResult] = []
```

### Adapters
| Backend | File |
|---------|------|
| In-memory | `adapters/in_memory.py::InMemoryGraphSnapshotSource` |

Inner protocol: `adapters/protocols.py::GraphSnapshotSourceProtocol`.

---

## `risk/`

### Protocol

Last verified: 2026-06-16

```python
class RiskServiceProtocol(Protocol):
    def assess(self, request: RiskAssessmentRequest) -> RiskAssessmentResponse: ...
    def list_scores(self, request: RiskScoreListRequest) -> RiskScoreListResponse: ...

class RiskScoringStrategyProtocol(Protocol):
    """Pluggable strategy mapping risk signals to weighted risk factors."""
    def score(self, signals: list[RiskSignal]) -> list[RiskFactor]: ...
```

### Internal Models (`analytics/risk/models.py`)

Last verified: 2026-06-16

```python
class RiskSignal(BaseModel):
    """A normalized input signal used to derive a composite risk score."""
    signal_name: str
    value: float = Field(ge=0.0, le=1.0)
    weight: float = Field(gt=0.0)
    rationale: str | None = None

class RiskProfile(BaseModel):
    """A set of risk signals for one entity in one knowledge base.
    Validation: requires at least one signal; signal_name values must be unique."""
    knowledge_base_id: str
    entity_id: str
    signals: list[RiskSignal] = Field(default_factory=list)

class RiskFactor(BaseModel):
    """A weighted factor contributing to the final risk score."""
    factor_name: str
    raw_value: float = Field(ge=0.0, le=1.0)
    weight: float = Field(gt=0.0)
    contribution: float = Field(ge=0.0, le=1.0)
    rationale: str | None = None

class RiskAssessmentResult(BaseModel):
    """Internal result returned after scoring an entity (not a service_model)."""
    request_id: str
    knowledge_base_id: str
    entity_id: str
    overall_score: float = Field(ge=0.0, le=1.0)
    risk_level: str
    factor_count: int = Field(ge=0)
    factors: list[RiskFactor] = Field(default_factory=list)

class RankedRiskEntry(BaseModel):
    """A pre-aggregated ranking entry returned from a signal source."""
    knowledge_base_id: str
    entity_id: str
    entity_type: str
    overall_score: float = Field(ge=0.0, le=1.0)
    risk_level: str

class RiskAssessmentRecord(BaseModel):
    """A row destined for the risk_score_history log."""
    knowledge_base_id: str
    entity_id: str
    request_id: str
    overall_score: float = Field(ge=0.0, le=1.0)
    risk_level: str
    factors: list[RiskFactor] = Field(default_factory=list)
    assessed_at: datetime = Field(default_factory=utc_now)
```

`RiskSignal` and `RiskFactor` are the core input/output shapes for `RiskScoringStrategyProtocol.score()`. `RiskProfile` wraps signals per-entity. `RankedRiskEntry` is returned by `RiskSignalSourceProtocol` (inner adapter protocol) and consumed by the risk service returned from `api/dependencies.py::get_risk_service`.

See also: `events/types.py::RiskFactorReference` — the event-wire shape mirrors `RiskFactor` fields exactly (`factor_name`, `raw_value`, `weight`, `contribution`, `rationale`).

### Service Models (`analytics/risk/service_models.py`)

```python
RiskTrend = Literal["increasing", "stable", "decreasing"]

class RiskAssessmentRequest(BaseModel):
    knowledge_base_id: str; entity_id: str
    medium_risk_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    high_risk_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    # Validation: when both are supplied, high must exceed medium.
    # When omitted, service constructor defaults from DomainConfig.analytics are used.

class RiskFactorScore(BaseModel):
    factor_name: str; raw_value: float; weight: float
    contribution: float; rationale: str | None

class RiskAssessmentResponse(BaseModel):
    request_id: str; knowledge_base_id: str; entity_id: str
    overall_score: float; risk_level: str; factor_count: int
    factors: list[RiskFactorScore] = []
    trend: RiskTrend | None; previous_score: float | None

class RiskScoreListRequest(BaseModel):
    knowledge_base_id: str; entity_type: str | None = None
    limit: int = Field(default=20, gt=0, le=500)

class RiskScore(BaseModel):
    entity_id: str; entity_type: str
    overall_score: float; risk_level: str

class RiskScoreListResponse(BaseModel):
    knowledge_base_id: str
    items: list[RiskScore] = []
    total: int
```

### Adapters
| Backend | File |
|---------|------|
| In-memory signal source | `adapters/in_memory.py::InMemoryRiskSignalSource` |
| In-memory history writer | `adapters/in_memory.py::InMemoryRiskHistoryWriter` |
| Linear strategy | `adapters/linear_strategy.py` |
| Postgres history | `adapters/postgres.py::PostgresRiskHistoryStore` |
| Postgres signal/history source | `adapters/postgres.py::PostgresRiskSignalSource` |

Inner protocols: `adapters/protocols.py::RiskHistoryWriter`, `RiskSignalSourceProtocol`.

---

## `explainability/`

### Protocol

Last verified: 2026-07-23 (Sprint 2026-28 B3, BL-048)

```python
class ExplainabilityServiceProtocol(Protocol):
    def generate(self, request: ExplainabilityRequest) -> ExplainabilityResponse: ...
    def generate_from_context(
        self, context: ExplanationContext, *, max_evidence_items: int = 3
    ) -> ExplainabilityResponse: ...

class NarrativeGeneratorProtocol(Protocol):
    """Never raises — degrades to a fallback narrative + WARNING log."""
    def summarize(
        self, *, context: ExplanationContext, items: Sequence[ExplanationItem]
    ) -> ExplanationNarrative: ...

class FeatureAttributorProtocol(Protocol):
    """Never raises — degrades to [] + WARNING log."""
    def attribute(self, *, context: ExplanationContext) -> list[FeatureAttribution]: ...
```

`ExplainabilityService.__init__(context_source, *, event_bus, narrative_generator=None, feature_attributor=None)`
(both keyword-only, default to `DeterministicNarrativeGenerator()` / `NoopFeatureAttributor()`).
`generate_from_context` calls `narrative_generator.summarize(...)` and
`feature_attributor.attribute(...)`, then composes the `EvidencePack`'s
`reasoning` (= `narrative.summary`), `narrative_sections`, and `attribution`
fields from the results (`shared.types.EvidenceNarrativeSection` /
`FeatureAttribution`).

### Service Models (`analytics/explainability/service_models.py`)

```python
class ExplainabilityRequest(BaseModel):
    knowledge_base_id: str
    alert_id: str
    max_evidence_items: int = Field(default=3, gt=0)

class ExplainabilityEvidence(BaseModel):
    source_id: str; source_type: str
    quote: str; rationale: str
    score: float   # [0.0, 1.0]

class ExplainabilityResponse(BaseModel):
    request_id: str; knowledge_base_id: str; alert_id: str
    evidence_pack: EvidencePack           # from shared/types.py — now carries attribution + narrative_sections
    evidence_items: list[ExplainabilityEvidence] = []
    narrative: ExplanationNarrative       # from analytics/explainability/models.py
```

### Context-source adapters
| Backend | File |
|---------|------|
| In-memory | `adapters/in_memory.py::InMemoryExplainabilityContextSource` |
| SHAP (context-source, unwired from DI) | `adapters/shap_adapter.py::ShapExplainabilityContextSource` |

Inner protocol: `adapters/protocols.py::ExplainabilityContextSourceProtocol`. `shap_adapter.py`
predates B3 and is a different seam (analytics.14's original context-source
literal, `in_memory|shap|lime`, is still not built — see `docs/backlog/analytics.md`
analytics.14) — do not confuse it with `adapters/shap_attribution.py` below.

### Narrative generators (B3, analytics.13 sprint slice)
| Backend | File | Behavior |
|---------|------|----------|
| Deterministic (default) | `adapters/deterministic.py::DeterministicNarrativeGenerator` | Groups selected items by `source_type` in first-seen order; body = space-joined rationales per group; `summary` = space-joined rationales of all selected items. Extracted, behavior-preserving, from the pre-B3 `_build_narrative`/`_build_reasoning`. |
| LLM | `adapters/llm_narrative.py::LlmNarrativeGenerator` | Wraps `llm.protocols.LlmServiceProtocol`; renders a markdown-instructed prompt (per-item `source_id`/`quote`/`rationale`/score, alert title, score snapshot); parses `## `-headed response sections into `NarrativeSection`s (`evidence_refs` = item ids whose text appears in the section body, else all selected ids). Degrades to an injected fallback generator (`DeterministicNarrativeGenerator`) on any `LlmError`; any unexpected exception (including `GenerateRequest` construction, which sits inside the never-raise guard); an empty completion; or a malformed completion — no `## ` sections, or an empty opening summary (completion opens directly with a heading). Heading-less completions are **not** treated as summary-only — both malformed shapes degrade — logs WARNING, never raises. |

Selected via `AnalyticsConfig.narrative_backend: Literal["deterministic", "llm"]` (default `"deterministic"`), built by `agent.coordinator.build_narrative_generator`.

### Feature attributors (B3, analytics.14 sprint slice — pipeline-attributor seam)
| Backend | File | Behavior |
|---------|------|----------|
| Noop (default) | `adapters/shap_attribution.py::NoopFeatureAttributor` | Returns `[]` unconditionally. |
| SHAP | `adapters/shap_attribution.py::ShapRiskAttributor` | Attributes `analytics.risk`'s `LinearScoringStrategy` composite (`predict(X) = min(1.0, Σx_i)`) over the per-feature contributions already snapshotted in `context.scores` (excluding `"overall"`), via `shap.Explainer` against a zero-baseline background. Lazy `shap`/`numpy` import; missing extra, no risk-factor features, or any explainer exception degrades to `[]` + WARNING, never raises. Sorted by `abs(contribution)` descending. |

Selected via `AnalyticsConfig.attribution_backend: Literal["none", "shap"]` (default `"none"`), built by `agent.coordinator.build_feature_attributor`. This is a distinct seam from `shap_adapter.py`'s `ShapExplainabilityContextSource` (context-source protocol, still DI-unwired) — see analytics.14 in the backlog for the two adapters' relationship.

---

## `metrics/`

No service entrypoint, no events. Purely persistence + throttling.

### Models (`analytics/metrics/models.py`)

Last verified: 2026-06-16

```python
GRAPH_SCOPE_ENTITY_ID = "__graph__"   # sentinel for KB-level metrics with no single owner
METRIC_ENTITY_COUNT = "entity_count"
METRIC_RELATIONSHIP_COUNT = "relationship_count"
METRIC_AVG_DEGREE = "avg_degree"

class EntityMetricSample(BaseModel):
    """One metric value for one entity at a point in time."""
    knowledge_base_id: str; entity_id: str; metric_name: str
    value: float
    observed_at: datetime   # default_factory=utc_now
    correlation_id: str

class EntityMetricValue(BaseModel):
    """Current snapshot — latest value of one metric for one entity."""
    knowledge_base_id: str; entity_id: str; metric_name: str
    value: float; updated_at: datetime
```

### Protocol (`analytics/metrics/adapters/protocols.py`)

Last verified: 2026-06-16

```python
class EntityMetricRepository(Protocol):
    def record_metrics(self, samples: list[EntityMetricSample]) -> int:
        """Append samples; upsert current snapshot. Returns inserted history rows.
        Idempotent on (knowledge_base_id, entity_id, metric_name, observed_at)."""
        ...

    def load_current_metrics(
        self, *, knowledge_base_id: str, entity_id: str
    ) -> list[EntityMetricValue]:
        """Return latest value of every metric for one entity."""
        ...
```

### Adapters
| Backend | File |
|---------|------|
| In-memory | `adapters/in_memory.py::InMemoryEntityMetricRepository` |
| Postgres | `adapters/postgres.py::PostgresEntityMetricRepository` |

### Throttle
`throttle.py::MetricsRecomputeThrottle` — per-KB rate limiter. Uses `AnalyticsConfig.metrics_recompute_min_interval_seconds`.

---

## API Exposure

Analytics endpoints in `api/routers/analytics.py`:
- `GET /analytics/risk-scores` → `RiskScoreListResponse`
- `GET /analytics/timeseries` → `MetricTimeseriesResponse`
- `GET /analytics/gnn/clusters` → `GnnClusterResponse`
- `GET /analytics/overview` → `AnalyticsOverviewResponse`
- `GET /analytics/risk-scores/{entity_id}` → `RiskScoreResponse`
- `GET /analytics/timeseries/{entity_id}` → `EntityTimeseriesResponse`

See [contracts/api-routes.md](../contracts/api-routes.md) for full route table.

---

## Current Wiring Status

**Source:** `backend/api/dependencies.py` — analytics dependency factories

Last verified: 2026-07-19

The analytics API router now depends on service factories from `api/dependencies.py`:

- `get_risk_service()` builds `RiskService` from `DomainConfig.analytics` thresholds and `get_risk_signal_source()`.
- `get_timeseries_service()` builds `TimeseriesService` from `get_timeseries_history_source()` (graph-scope metric-range queries).
- `get_entity_series_source()` builds the per-entity `RecordAggregateTimeSeriesSource` used directly by `get_timeseries_payload` (entity-scoped chart route), independent of `TimeseriesService`.
- `get_gnn_service()` builds `GnnService` and honors the active `capabilities.gnn` flag.

`get_risk_signal_source()` selects `PostgresRiskSignalSource` when a DB connection provider exists; otherwise it falls back to `InMemoryRiskSignalSource`. `get_timeseries_history_source()` (the graph-scope `/analytics/timeseries?metric=...` range query) follows the same DI-switch pattern: `PostgresTimeSeriesHistorySource` over `entity_metric_history` when a DB is configured, else `InMemoryTimeSeriesHistorySource`. `get_graph_snapshot_source()` is repository-backed since B1: `GraphRepositorySnapshotSource` over `get_graph_repository()` with cluster summaries from an `ObjectStoreClusterSummaryStore` over the configured object store (`InMemoryGraphSnapshotSource` remains the test override). `/analytics/overview` is now computed from durable alert projections, durable cases, and KB metadata.

The entity-scoped `/analytics/timeseries/{entity_id}` route (B2, analytics.07) no longer reads `ApiState`: it is built from `get_entity_series_source()` — a `RecordAggregateTimeSeriesSource` over `get_record_column_source()` (`InMemoryRecordColumnSource`/`PostgresRecordColumnSource`, DI-switched the same way) and the metric specs in `DomainConfig.timeseries.metrics` — joined with persisted anomalies from `get_timeseries_anomaly_store()` (`InMemoryTimeseriesAnomalyStore`/`PostgresTimeseriesAnomalyStore`). It reports `availability_status: "unavailable"` when no configured spec has data for the entity.

The entity-scoped `/analytics/risk-scores/{entity_id}` route (B2, fix 42ef186) no longer reads `ApiState` either: `get_risk_score_payload(entity_id, kb_id, risk_service)` calls `risk_service.assess(RiskAssessmentRequest(knowledge_base_id=kb_id, entity_id=entity_id))` against the same DI `get_risk_service()` used by the list route (`PostgresRiskSignalSource` when a DB connection provider exists, else `InMemoryRiskSignalSource`). `RiskConfigurationError`, `RiskInsufficientSignalsError`, and `ValueError` from `assess()` are caught and mapped to an `availability_status: "unavailable"` payload (`unavailable_reason="No risk profile has been generated for this entity."`); any other (infrastructure) exception propagates rather than being reported as a missing profile. `_normalize_risk_level` (promotes to `"critical"` at `overall_score >= 0.9`, otherwise passes through a known level or defaults to `"medium"`) now lives in `api/dependencies.py` alongside `get_risk_score_payload`.

**No static read-model gap remains on the analytics router: every analytics route (`/overview`, `/risk-scores`, `/risk-scores/{entity_id}`, `/timeseries`, `/timeseries/{entity_id}`, `/gnn/clusters`) reads from a DI-provided service or durable store, never from `ApiState`.** `ApiState` (`api/state.py`) now owns only the RAG service handle used by chat streaming — its seeded risk-profile composition (`get_risk_score`, `_risk_service`, `_build_risk_profiles`, `_normalize_risk_level`) was deleted. Response shapes for these routes are documented in [contracts/api-routes.md - Static payload shapes](../contracts/api-routes.md#static-payload-shapes-apicontractspy).

**Implication for callers:** List-style risk and timeseries-range routes, and both entity-scoped routes, can read persisted history when Postgres is configured; the list-style GNN route still returns empty data until backed by a live store.

---

## Module Dependencies

- `shared/types.py` — `Entity`, `Alert`
- `events/` — publishes timeseries/gnn/risk/explainability events
- `database/` — Postgres adapters depend on `ConnectionProvider`
- `config/schema.py` — `AnalyticsConfig`, `MonitoringConfig`

---

## Tests

Location: `backend/tests/analytics/`
