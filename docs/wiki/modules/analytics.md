# Module: analytics

**Verified against codebase:** 2026-05-20
**Source:** `backend/analytics/`

## Purpose

ML/AI capability modules. Five sub-modules, each following the standard module shape (`protocols.py`, `service_models.py`, `service.py`, `adapters/`):

| Sub-module | Responsibility |
|-----------|---------------|
| `timeseries/` | Time-series anomaly detection on entity metric observations |
| `gnn/` | Graph neural network link prediction and community detection |
| `risk/` | Risk scoring engine — linear combination of weighted signals |
| `explainability/` | Evidence pack generation (SHAP-based or in-memory stub) |
| `metrics/` | Entity-metric persistence; no events, no service entrypoint |

---

## `timeseries/`

### Protocol

Last verified: 2026-05-20

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
| Postgres | `adapters/postgres.py::PostgresObservationStore` / `PostgresObservationSource` |

---

## `gnn/`

### Protocol

Last verified: 2026-05-20

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

Last verified: 2026-05-20

```python
class RiskServiceProtocol(Protocol):
    def assess(self, request: RiskAssessmentRequest) -> RiskAssessmentResponse: ...
    def list_scores(self, request: RiskScoreListRequest) -> RiskScoreListResponse: ...

class RiskScoringStrategyProtocol(Protocol):
    """Pluggable strategy mapping risk signals to weighted risk factors."""
    def score(self, signals: list[RiskSignal]) -> list[RiskFactor]: ...
```

### Internal Models (`analytics/risk/models.py`)

Last verified: 2026-05-20

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

`RiskSignal` and `RiskFactor` are the core input/output shapes for `RiskScoringStrategyProtocol.score()`. `RiskProfile` wraps signals per-entity. `RankedRiskEntry` is returned by `RiskSignalSourceProtocol` (inner adapter protocol) and used by the `@lru_cache` stub in `api/routers/analytics.py`.

See also: `events/types.py::RiskFactorReference` — the event-wire shape mirrors `RiskFactor` fields exactly (`factor_name`, `raw_value`, `weight`, `contribution`, `rationale`).

### Service Models (`analytics/risk/service_models.py`)

```python
RiskTrend = Literal["increasing", "stable", "decreasing"]

class RiskAssessmentRequest(BaseModel):
    knowledge_base_id: str; entity_id: str
    medium_risk_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    high_risk_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    # Validation: high must exceed medium

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

Inner protocols: `adapters/protocols.py::RiskHistoryWriter`, `RiskSignalSourceProtocol`.

---

## `explainability/`

### Protocol

Last verified: 2026-05-20

```python
class ExplainabilityServiceProtocol(Protocol):
    def generate(self, request: ExplainabilityRequest) -> ExplainabilityResponse: ...
```

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
    evidence_pack: EvidencePack           # from shared/types.py
    evidence_items: list[ExplainabilityEvidence] = []
    narrative: ExplanationNarrative       # from analytics/explainability/models.py
```

### Adapters
| Backend | File |
|---------|------|
| In-memory | `adapters/in_memory.py::InMemoryExplainabilityContextSource` |
| SHAP | `adapters/shap_adapter.py` |

Inner protocol: `adapters/protocols.py::ExplainabilityContextSourceProtocol`.

---

## `metrics/`

No service entrypoint, no events. Purely persistence + throttling.

### Models (`analytics/metrics/models.py`)

Last verified: 2026-05-20

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

Last verified: 2026-05-20

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

**Source:** `backend/api/routers/analytics.py` — file-level `@lru_cache` stub factories

Last verified: 2026-05-20

The analytics API router is **not wired to production analytics services**. All three capability services (risk, timeseries, gnn) are instantiated with `@lru_cache(maxsize=1)` in-memory stub data seeded at startup:

- `_stub_risk_signal_source()` — hardcoded `RankedRiskEntry` rows for `kb-demo` entities `provider-1`, `provider-2`, `claim-9`
- `_stub_timeseries_history_source()` — three hardcoded `claim_volume` observations for `kb-demo`
- `_stub_graph_snapshot_source()` — empty `InMemoryGraphSnapshotSource`

The real analytics services (`RiskService`, `TimeseriesService`, `GnnService`) exist in the analytics sub-modules and are exercised by worker pipeline handlers. The gap is that `api/dependencies.py` (`get_analytics_overview_payload`, `get_risk_score_payload`, `get_timeseries_payload`) provides static data to the three entity-scoped routes (`/overview`, `/risk-scores/{entity_id}`, `/timeseries/{entity_id}`). Response shapes for these routes are documented in [contracts/api-routes.md — Static payload shapes](../contracts/api-routes.md#static-payload-shapes-apicontractspy).

**Implication for callers:** Analytics route responses will reflect stub seed data until wired to live stores. The worker-side analytics pipeline is functional; the router-facing query path is the gap.

---

## Module Dependencies

- `shared/types.py` — `Entity`, `Alert`
- `events/` — publishes timeseries/gnn/risk/explainability events
- `database/` — Postgres adapters depend on `ConnectionProvider`
- `config/schema.py` — `AnalyticsConfig`, `MonitoringConfig`

---

## Tests

Location: `backend/tests/analytics/`
