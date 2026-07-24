# Module: monitoring

**Verified against codebase:** 2026-07-23
**Source:** `backend/monitoring/`

## Purpose

Active monitoring service. Loads entity metric observations, resolves medium/high thresholds from request overrides or `MonitoringConfig` defaults, generates `Alert` instances with suppression, deduplication, rate limiting, grouping, and alert-history persistence.

Since **alerts.36** (durable alert read model), `alert_history` is not just an analytics-facing audit log — it is the sole backing store for `GET /alerts` and every other alert-reading surface (SSE `active_alerts`, `/analytics/overview`, `GET /graph/entities/{id}` related-alerts, and the KB-delete cascade). The API consumes it through `AlertFeedStoreProtocol` (below), injected via `api.dependencies.get_alert_feed_store()`. See `docs/wiki/modules/api.md`'s Route → Service Dispatch table.

---

## Protocols (`monitoring/protocols.py`)

### `MonitoringServiceProtocol`
```python
class MonitoringServiceProtocol(Protocol):
    def evaluate(self, request: MonitoringEvaluationRequest) -> MonitoringEvaluationResponse: ...
```

### `AlertsServiceProtocol`
```python
class AlertsServiceProtocol(Protocol):
    def list_alerts(self, request: AlertListRequest) -> AlertListResponse: ...
    def acknowledge_alert(self, alert_id: str) -> Alert: ...
    def resolve_alert(self, alert_id: str, request: ResolutionRequest) -> Alert: ...
```

---

## Internal Models (`monitoring/models.py`)

Last verified: 2026-05-28

```python
class MonitoringObservation(BaseModel):
    """A scored observation produced by upstream monitoring inputs.
    Defined in shared/types.py and re-exported from monitoring/models.py."""
    entity_id: str
    entity_type: str
    metric_name: str
    score: float = Field(ge=0.0, le=1.0)
    observed_at: datetime = Field(default_factory=utc_now)
    rationale: str
    evidence_pack_id: str | None = None

class MonitoringBatch(BaseModel):
    """A batch of monitoring observations for one knowledge base.
    Validation: requires at least one observation."""
    knowledge_base_id: str
    batch_id: str
    observations: list[MonitoringObservation] = Field(default_factory=list)

class AlertCandidate(BaseModel):
    """Internal candidate ready to become a surfaced alert."""
    entity_id: str
    entity_type: str
    severity: str
    title: str
    reasoning: str
    score: float = Field(ge=0.0, le=1.0)
    metric_name: str
    evidence_pack_id: str | None = None

class SuppressionRule(BaseModel):
    """A rule suppressing observations matching given dimensions in a time range.
    entity_type / metric_name accept None as wildcard.
    Validation: end_time must be after start_time."""
    entity_type: str | None = None
    metric_name: str | None = None
    start_time: datetime
    end_time: datetime
    reason: str

    def matches(self, *, entity_type: str, metric_name: str, now: datetime) -> bool:
        """Return True when the rule applies to the supplied observation context."""
        ...

class AlertGroup(BaseModel):
    """A correlation cluster of related alerts from the same evaluation."""
    group_id: str
    alert_ids: list[str]
    entity_type: str
    created_at: datetime
    correlation_reason: str

class AlertHistoryRecord(BaseModel):
    """A row in the alert_history table — the sole backing store for /alerts (alerts.36)."""
    knowledge_base_id: str
    alert_id: str
    entity_id: str
    entity_type: str
    severity: str
    status: str
    title: str
    reasoning: str
    metric_name: str
    evidence_pack_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    entity_label: str = ""    # alerts.36 (migration 0012) — falls back to "" or entity_id upstream
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)   # alerts.36
    tags: list[str] = Field(default_factory=list)            # alerts.36
```

`AlertGroup` is referenced by `MonitoringEvaluationResponse.alert_groups`. `MonitoringObservation` and `MonitoringBatch` are the input shapes consumed by `MonitoringServiceProtocol.evaluate()`.

---

## Service Models (`monitoring/service_models.py`)

Last verified: 2026-05-20

```python
class MonitoringEvaluationRequest(BaseModel):
    knowledge_base_id: str
    batch_id: str
    medium_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    high_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    window_minutes: int = Field(default=60, gt=0)
    min_observations_in_window: int = Field(default=1, gt=0)
    # Validation: when both are supplied, high_threshold must exceed medium_threshold.
    # When omitted, service constructor defaults from DomainConfig.monitoring are used.

class MonitoringEvaluationResponse(BaseModel):
    knowledge_base_id: str
    batch_id: str
    processed_observation_count: int   # >= 0
    alert_count: int                   # >= 0
    alerts: list[Alert] = []
    suppressed_count: int = 0
    suppressed_by_rule_count: int = 0
    rate_limited_count: int = 0
    alert_groups: list[AlertGroup] = []   # AlertGroup from monitoring/models.py (see above)

class AlertListRequest(BaseModel):
    severity: str | None = None
    entity_type: str | None = None
    status: str | None = None
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)

class AlertListResponse(BaseModel):
    items: list[Alert] = []
    total: int   # >= 0

class ResolutionRequest(BaseModel):
    resolved_by: str   # min_length=1
    notes: str | None = None

class AlertActionResponse(BaseModel):
    """Returned by alert lifecycle actions (acknowledge, resolve)."""
    alert: Alert
```

---

## Threshold Evaluation

`MonitoringService.evaluate()` resolves effective thresholds from `MonitoringEvaluationRequest.medium_threshold` / `high_threshold`, falling back to service constructor defaults. `api/dependencies.py::get_monitoring_service()` passes those defaults from `DomainConfig.monitoring.medium_threshold` and `high_threshold`.

---

## Adapters

| Backend | File |
|---------|------|
| In-memory | `adapters/in_memory.py::InMemoryAlertHistoryWriter` |
| Postgres | `adapters/postgres.py::PostgresAlertHistoryStore` + observation adapters |

Both adapters implement `adapters/protocols.py::AlertFeedStoreProtocol` (superset of `AlertHistoryWriter`, alerts.36):

```python
class AlertHistoryWriter(Protocol):
    def write_alerts(self, records: list[AlertHistoryRecord]) -> int: ...
    def count_open_alerts(self, *, knowledge_base_id: str, entity_id: str) -> int: ...
    def delete_by_kb(self, knowledge_base_id: str) -> int: ...

class AlertFeedStoreProtocol(Protocol):   # supersets AlertHistoryWriter
    def write_alerts(self, records: list[AlertHistoryRecord]) -> int: ...
    def list_alerts(
        self, *, statuses: list[str] | None = None, limit: int, offset: int,
    ) -> tuple[list[AlertHistoryRecord], int]: ...
    def get_alert(self, alert_id: str) -> AlertHistoryRecord | None: ...
    def acknowledge(self, alert_id: str) -> AlertHistoryRecord | None: ...
    def count_by_statuses(self, statuses: set[str]) -> int: ...
    def delete_by_kb(self, knowledge_base_id: str) -> int: ...
```

`AlertHistoryWriter` remains importable on its own for the worker's write-only construction sites (`agent/coordinator.py`); `api.dependencies.get_alert_feed_store()` injects the same concrete adapter as an `AlertFeedStoreProtocol` for the API's read/mutate routes (Postgres when a connection provider resolves, in-memory otherwise — no dedicated env var, see `docs/wiki/contracts/domain-config.md`).

---

## Module Dependencies

- `shared/types.py` — `Alert`
- `events/` — consumes `RiskScoredEvent`, publishes `AlertsCreatedEvent`
- `database/` — Postgres alert history store
- `config/schema.py` — `MonitoringConfig`, `AlertsConfig`
- `api/` — consumes `AlertFeedStoreProtocol` via DI (alerts.36); no cross-module business logic, DI-only per the cross-module interaction rule

---

## Tests

Location: `backend/tests/monitoring/`
