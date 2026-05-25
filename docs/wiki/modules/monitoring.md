# Module: monitoring

**Verified against codebase:** 2026-05-20
**Source:** `backend/monitoring/`

## Purpose

Active monitoring service. Evaluates entity metric observations against configured alert thresholds (`AlertsConfig.thresholds`), generates `Alert` instances with deduplication, and persists alert history.

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

Last verified: 2026-05-20

```python
class MonitoringObservation(BaseModel):
    """A scored observation produced by upstream monitoring inputs."""
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
    """A row destined for the analytics-facing alert_history log."""
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
```

`AlertGroup` is referenced by `MonitoringEvaluationResponse.alert_groups`. `MonitoringObservation` and `MonitoringBatch` are the input shapes consumed by `MonitoringServiceProtocol.evaluate()`.

---

## Service Models (`monitoring/service_models.py`)

Last verified: 2026-05-20

```python
class MonitoringEvaluationRequest(BaseModel):
    knowledge_base_id: str
    batch_id: str
    medium_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    high_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    window_minutes: int = Field(default=60, gt=0)
    min_observations_in_window: int = Field(default=1, gt=0)
    # Validation: high_threshold must exceed medium_threshold

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

## Threshold Evaluation (`monitoring/metrics.py`)

Helpers for comparing entity metric values against `AlertsConfig.thresholds` (keyed by entity_type → metric_name → threshold float).

---

## Adapters

| Backend | File |
|---------|------|
| In-memory | `adapters/in_memory.py` |
| Postgres | `adapters/postgres.py::PostgresAlertHistoryStore` + observation adapters |

Inner protocol: `adapters/protocols.py`.

---

## Module Dependencies

- `shared/types.py` — `Alert`
- `events/` — consumes `RiskScoredEvent`, publishes `AlertsCreatedEvent`
- `database/` — Postgres alert history store
- `config/schema.py` — `MonitoringConfig`, `AlertsConfig`

---

## Tests

Location: `backend/tests/monitoring/`
