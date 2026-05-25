# Theme 2 — Drive Analytics Behavior from DomainConfig Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded Medicare-flavored stubs and threshold defaults in the analytics surface so the three production endpoints (`/analytics/risk-scores`, `/analytics/timeseries`, `/analytics/gnn/clusters`) and the monitoring/risk services honor the active `DomainConfig` — matching the contract already established by `get_graph_service` and `get_monitoring_service`.

**Architecture:** The analytics router currently constructs `@lru_cache`'d stub sources (`_stub_risk_signal_source`, `_stub_timeseries_history_source`, `_stub_graph_snapshot_source`) hardcoded with `kb-demo`/`provider`/`claim` data and serves them on the live router endpoints — a hard violation of "domain config drives everything." The fix has two parts: (1) move analytics service construction into `api/dependencies.py` following the existing `get_monitoring_service` pattern, with empty-by-default in-memory sources, and (2) extend `MonitoringConfig` and `AnalyticsConfig` (already in the schema) with severity-tier threshold fields so the per-request `medium_threshold`/`high_threshold` and `medium_risk_threshold`/`high_risk_threshold` are populated from config rather than from Pydantic field defaults that bypass the domain.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, pytest

**Dependencies on other themes:** None. Theme 2 does not depend on Theme 1 (the new `knowledgebases/` module is unrelated to analytics) and is independent of Themes 3, 4, 5. It can run in parallel.

---

## Background — what exists today vs. what the fix needs

After reading `backend/api/dependencies.py`, `backend/api/routers/analytics.py`, `backend/config/schema.py`, and `backend/monitoring/service_models.py`:

- `DomainConfig.monitoring: MonitoringConfig | None` already exists (`config/schema.py:363`) and `MonitoringConfig` already has `dedup_window_seconds`, `max_alerts_per_evaluation`, `grouping_window_seconds`. **It does NOT have threshold fields** — that's the schema gap for Theme 2.2.
- `DomainConfig.analytics: AnalyticsConfig | None` already exists (`config/schema.py:368`) and `AnalyticsConfig` has only `metrics_recompute_min_interval_seconds`. **Risk thresholds need to be added.**
- `get_monitoring_service` (`dependencies.py:590-599`) already reads `MonitoringConfig.dedup_window_seconds` etc. from `DomainConfig`. **It does NOT pass thresholds** because the fields don't exist yet — Theme 2.2 adds them.
- `get_risk_service`, `get_timeseries_service`, `get_gnn_service` **do NOT exist in `dependencies.py`** — they're defined inside `routers/analytics.py` and return cached stubs.
- `RiskAssessmentRequest.medium_risk_threshold` and `high_risk_threshold` (`analytics/risk/service_models.py:18-19`) are Pydantic field defaults at `0.5` and `0.8`. The router currently does not populate these explicitly, so the Pydantic defaults always apply, bypassing `DomainConfig`.
- `MonitoringEvaluationRequest.medium_threshold` and `high_threshold` (`monitoring/service_models.py:16-17`) are the same shape — defaults at `0.6` and `0.85`.

---

## File Structure

**Modify (schema extension):**
- `backend/config/schema.py:169-176` — add `medium_threshold` and `high_threshold` to `MonitoringConfig`
- `backend/config/schema.py:179-182` — add `medium_risk_threshold` and `high_risk_threshold` to `AnalyticsConfig`
- `backend/config/defaults/*.yaml` — populate the new fields in domain default YAMLs

**Modify (analytics router and DI):**
- `backend/api/dependencies.py` — add `get_risk_service`, `get_timeseries_service`, `get_gnn_service` (and their source factories `get_risk_signal_source`, `get_timeseries_history_source`, `get_graph_snapshot_source`)
- `backend/api/routers/analytics.py` — delete the `_stub_*` factories and `get_*_service` helpers; the router consumes the DI helpers from `dependencies.py`
- `backend/api/routers/analytics.py` — populate threshold fields in the request models from `DomainConfig`

**Modify (monitoring + risk factories):**
- `backend/monitoring/service.py` `create_monitoring_service` — optional threshold parameters that populate config-derived defaults
- `backend/analytics/risk/service.py` `create_risk_service` — optional threshold parameters that populate config-derived defaults

**Test additions:**
- `backend/tests/config/test_schema.py` (or equivalent) — schema tests for new fields
- `backend/tests/api/test_analytics_router.py` (find via grep) — replace hardcoded-Medicare-stub assertions with empty-domain assertions; add threshold-from-config assertion
- `backend/tests/api/test_dependencies.py` — add tests for the new DI helpers

---

## Pre-Flight Sanity Check (do this once)

- [ ] **Baseline test pass**

```bash
cd backend && pytest --no-cov -q 2>&1 | tail -5
```

- [ ] **Confirm the schema gaps**

```bash
grep -n "medium_threshold\|high_threshold\|medium_risk_threshold\|high_risk_threshold" backend/config/schema.py
```

Expected: no matches (thresholds are not in the config schema today).

- [ ] **Confirm the stub factories exist**

```bash
grep -n "_stub_\|@lru_cache" backend/api/routers/analytics.py
```

Expected: matches at lines ~40, 45, 74, 89 (4 `@lru_cache` decorators) and the corresponding stub function bodies.

- [ ] **Confirm the production endpoints currently call the stubs**

```bash
grep -n "Depends(get_risk_service)\|Depends(get_timeseries_service)\|Depends(get_gnn_service)" backend/api/routers/analytics.py
```

Expected: 3 matches (the dependency injection on each endpoint). These will be redirected to `api/dependencies.py` in Task 6.

- [ ] **Confirm no other `kb-demo`/literal stub data outside the router**

```bash
grep -rn "kb-demo\|claim-9\|provider-1.*high\|provider-2.*medium" backend/ --include="*.py" | grep -v test
```

Expected: only matches in `backend/api/routers/analytics.py`. If there are matches elsewhere (`backend/api/state.py` for example), those are independent demo seed and out of scope here.

---

## Task 1: Extend `MonitoringConfig` with severity-tier thresholds

**Files:**
- Modify: `backend/config/schema.py:169-176`
- Modify: `backend/tests/config/test_schema.py` (or whichever existing test covers MonitoringConfig)

- [ ] **Step 1: Write failing schema test**

Append to `backend/tests/config/test_schema.py` (find the file via `ls backend/tests/config/`; if no schema test file exists, create `test_monitoring_config.py` under the same directory):

```python
def test_monitoring_config_defaults_include_severity_thresholds() -> None:
    from config.schema import MonitoringConfig

    config = MonitoringConfig()
    assert config.medium_threshold == 0.6
    assert config.high_threshold == 0.85


def test_monitoring_config_threshold_validation() -> None:
    """high_threshold must exceed medium_threshold, matching the per-request rule."""
    from config.schema import MonitoringConfig

    with pytest.raises(ValueError, match="high_threshold must exceed medium_threshold"):
        MonitoringConfig(medium_threshold=0.8, high_threshold=0.8)
```

- [ ] **Step 2: Run new tests, verify fail**

```bash
cd backend && pytest tests/config/test_schema.py::test_monitoring_config_defaults_include_severity_thresholds -v
```

Expected: FAIL with `AttributeError: 'MonitoringConfig' object has no attribute 'medium_threshold'`.

- [ ] **Step 3: Extend `MonitoringConfig`**

In `backend/config/schema.py`, replace the `MonitoringConfig` class (lines 169-176) with:

```python
class MonitoringConfig(BaseModel):
    """Configuration for alert deduplication, evaluation cadence, and severity tiers."""

    evaluation_interval_seconds: int = Field(default=300, gt=0)
    dedup_window_seconds: int = Field(default=3600, gt=0)
    max_alerts_per_entity: int = Field(default=10, gt=0)
    max_alerts_per_evaluation: int = Field(default=100, gt=0)
    grouping_window_seconds: int = Field(default=300, gt=0)
    medium_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    high_threshold: float = Field(default=0.85, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_thresholds(self) -> MonitoringConfig:
        if self.high_threshold <= self.medium_threshold:
            raise ValueError(
                "MonitoringConfig high_threshold must exceed medium_threshold."
            )
        return self
```

Ensure `from pydantic import BaseModel, Field, model_validator` is already imported at the top of the file (it should be — other config models use `model_validator`). The defaults match the existing `MonitoringEvaluationRequest` defaults so existing callers see no behavioral change.

- [ ] **Step 4: Run tests pass**

```bash
cd backend && pytest tests/config/test_schema.py -v
```

Expected: PASS. Existing schema tests continue to pass since the new fields have defaults.

- [ ] **Step 5: Commit**

```bash
cd backend && git add config/schema.py tests/config/test_schema.py
git commit -m "$(cat <<'EOF'
feat(config): MonitoringConfig gains medium_threshold and high_threshold

Adds the severity-tier thresholds to the domain config so they can drive
per-evaluation alerting rather than relying on the Pydantic field
defaults on MonitoringEvaluationRequest, which silently bypass
DomainConfig. Defaults match the existing per-request defaults so
existing deployments see no behavioral change.
EOF
)"
```

---

## Task 2: Extend `AnalyticsConfig` with risk-tier thresholds

**Files:**
- Modify: `backend/config/schema.py:179-182`
- Modify: same test file as Task 1

- [ ] **Step 1: Write failing schema test**

Append to the test file:

```python
def test_analytics_config_defaults_include_risk_thresholds() -> None:
    from config.schema import AnalyticsConfig

    config = AnalyticsConfig()
    assert config.medium_risk_threshold == 0.5
    assert config.high_risk_threshold == 0.8


def test_analytics_config_risk_threshold_validation() -> None:
    from config.schema import AnalyticsConfig

    with pytest.raises(ValueError, match="high_risk_threshold must exceed medium_risk_threshold"):
        AnalyticsConfig(medium_risk_threshold=0.7, high_risk_threshold=0.7)
```

- [ ] **Step 2: Run, verify fail**

```bash
cd backend && pytest tests/config/test_schema.py::test_analytics_config_defaults_include_risk_thresholds -v
```

Expected: FAIL.

- [ ] **Step 3: Extend `AnalyticsConfig`**

In `backend/config/schema.py`, replace the `AnalyticsConfig` class (lines 179-182) with:

```python
class AnalyticsConfig(BaseModel):
    """Configuration for analytics persistence, recompute behavior, and risk tiers."""

    metrics_recompute_min_interval_seconds: int = Field(default=300, gt=0)
    medium_risk_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    high_risk_threshold: float = Field(default=0.8, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_risk_thresholds(self) -> AnalyticsConfig:
        if self.high_risk_threshold <= self.medium_risk_threshold:
            raise ValueError(
                "AnalyticsConfig high_risk_threshold must exceed medium_risk_threshold."
            )
        return self
```

- [ ] **Step 4: Tests pass**

```bash
cd backend && pytest tests/config/test_schema.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd backend && git add config/schema.py tests/config/test_schema.py
git commit -m "$(cat <<'EOF'
feat(config): AnalyticsConfig gains medium_risk_threshold and high_risk_threshold

Mirrors the MonitoringConfig threshold work in the prior commit, this
time for risk scoring. Defaults match the per-request defaults so
existing deployments are unaffected.
EOF
)"
```

---

## Task 3: Update default YAMLs to include the new threshold fields (optional override)

**Files:**
- Modify: `backend/config/defaults/medicare_fraud_cms_desynpuf.yaml` (and any other YAML in `backend/config/defaults/`)

- [ ] **Step 1: Inventory default YAMLs**

```bash
ls backend/config/defaults/*.yaml
```

Expected: at least one YAML (e.g. `medicare_fraud_cms_desynpuf.yaml`). Read each to find the existing `monitoring:` and `analytics:` sections.

- [ ] **Step 2: Append the new fields where appropriate**

For each YAML that has a `monitoring:` block, ensure the block can include `medium_threshold` and `high_threshold`. If the existing YAML doesn't override them, you don't need to add them — Pydantic defaults apply. If the domain genuinely wants different thresholds (e.g. Medicare fraud favors a high recall, so `medium_threshold: 0.5`), add the override explicitly.

For this plan, the safe default is to NOT change any existing YAML — letting the new Pydantic defaults take over silently. The schema change in Tasks 1-2 makes it possible to override; whether to override is a domain decision.

- [ ] **Step 3: If no YAML changes are needed, skip the commit**

If YAMLs are unchanged, Task 3 is a no-op verification. Document the decision in the commit log of Task 9 (the wrap-up).

If a YAML IS changed (because the domain owner explicitly wants different defaults), commit it:

```bash
cd backend && git add config/defaults/<file>.yaml
git commit -m "config(<domain>): override monitoring/analytics thresholds per domain"
```

---

## Task 4: Update `create_monitoring_service` to accept threshold parameters

**Files:**
- Modify: `backend/monitoring/service.py`
- Modify: `backend/tests/monitoring/test_service.py`

- [ ] **Step 1: Find `create_monitoring_service`**

```bash
grep -n "def create_monitoring_service\|class MonitoringService" backend/monitoring/service.py
```

The signature today (find the exact line) takes `observation_source`, `event_bus`, `dedup_window_seconds`, `max_alerts_per_evaluation`, `grouping_window_seconds`, `suppression_rules`. It does NOT take threshold parameters. Thresholds are passed per-request via `MonitoringEvaluationRequest`.

- [ ] **Step 2: Write a failing test that threshold defaults can be set at service construction**

Append to `backend/tests/monitoring/test_service.py`:

```python
def test_create_monitoring_service_accepts_default_thresholds() -> None:
    """Service factories must accept domain-config thresholds so the router
    no longer has to pass them on every request."""
    service = create_monitoring_service(
        _stub_observation_source(),
        event_bus=_stub_event_bus(),
        default_medium_threshold=0.55,
        default_high_threshold=0.9,
    )
    assert service.default_medium_threshold == 0.55
    assert service.default_high_threshold == 0.9
```

- [ ] **Step 3: Run, verify fail**

Expected: FAIL — `unexpected keyword argument`.

- [ ] **Step 4: Add the parameters**

In `backend/monitoring/service.py`:

1. Add `default_medium_threshold` and `default_high_threshold` parameters to `MonitoringService.__init__`:

```python
def __init__(
    self,
    observation_source: ObservationSourceProtocol,
    *,
    event_bus: EventBus,
    dedup_window_seconds: int = 3600,
    max_alerts_per_evaluation: int = 100,
    suppression_rules: list[SuppressionRule] | None = None,
    grouping_window_seconds: int = 300,
    default_medium_threshold: float = 0.6,
    default_high_threshold: float = 0.85,
) -> None:
    # ... existing initialization ...
    self.default_medium_threshold = default_medium_threshold
    self.default_high_threshold = default_high_threshold
```

2. Update `create_monitoring_service` to accept and pass these through:

```python
def create_monitoring_service(
    observation_source: ObservationSourceProtocol,
    *,
    event_bus: EventBus,
    dedup_window_seconds: int = 3600,
    max_alerts_per_evaluation: int = 100,
    grouping_window_seconds: int = 300,
    default_medium_threshold: float = 0.6,
    default_high_threshold: float = 0.85,
) -> MonitoringService:
    return MonitoringService(
        observation_source,
        event_bus=event_bus,
        dedup_window_seconds=dedup_window_seconds,
        max_alerts_per_evaluation=max_alerts_per_evaluation,
        grouping_window_seconds=grouping_window_seconds,
        default_medium_threshold=default_medium_threshold,
        default_high_threshold=default_high_threshold,
    )
```

The service exposes the defaults as attributes so the router can read them when constructing `MonitoringEvaluationRequest`. The thresholds remain configurable per-request (per the original `MonitoringEvaluationRequest` shape); the service-level defaults are a fallback used by callers that don't override.

- [ ] **Step 5: Test passes**

```bash
cd backend && pytest tests/monitoring/test_service.py::test_create_monitoring_service_accepts_default_thresholds -v
```

Expected: PASS.

- [ ] **Step 6: Full monitoring test suite**

```bash
cd backend && pytest tests/monitoring/ -q --no-cov 2>&1 | tail -10
```

Expected: all PASS. Existing tests use the default thresholds and aren't affected by the new parameter.

- [ ] **Step 7: Commit**

```bash
cd backend && git add monitoring/service.py tests/monitoring/test_service.py
git commit -m "$(cat <<'EOF'
feat(monitoring): service factory accepts default thresholds from config

MonitoringService and create_monitoring_service now accept
default_medium_threshold and default_high_threshold. The router will
populate them from DomainConfig.monitoring in a subsequent commit.
The thresholds are still configurable per-request via
MonitoringEvaluationRequest; the service-level values are the fallback.
EOF
)"
```

---

## Task 5: Update `create_risk_service` to accept threshold parameters

**Files:**
- Modify: `backend/analytics/risk/service.py`
- Modify: `backend/tests/analytics/risk/test_service.py` (or wherever risk service tests live)

- [ ] **Step 1: Mirror Task 4 for `RiskService`**

Write a failing test:

```python
def test_create_risk_service_accepts_default_thresholds() -> None:
    service = create_risk_service(
        _stub_risk_signal_source(),
        event_bus=_stub_event_bus(),
        default_medium_risk_threshold=0.55,
        default_high_risk_threshold=0.82,
    )
    assert service.default_medium_risk_threshold == 0.55
    assert service.default_high_risk_threshold == 0.82
```

- [ ] **Step 2: Run, verify fail**

Expected: FAIL.

- [ ] **Step 3: Add parameters**

In `backend/analytics/risk/service.py`:

1. Add to `RiskService.__init__`:

```python
def __init__(
    self,
    signal_source: RiskSignalSourceProtocol,
    *,
    event_bus: EventBus,
    scoring_strategy: RiskScoringStrategyProtocol | None = None,
    delta_threshold: float = DEFAULT_TREND_DELTA_THRESHOLD,
    default_medium_risk_threshold: float = 0.5,
    default_high_risk_threshold: float = 0.8,
) -> None:
    # ... existing init body ...
    self.default_medium_risk_threshold = default_medium_risk_threshold
    self.default_high_risk_threshold = default_high_risk_threshold
```

2. Add the same parameters to `create_risk_service` and pass them through.

- [ ] **Step 4: Run tests pass + suite green**

```bash
cd backend && pytest tests/analytics/risk/ -q --no-cov 2>&1 | tail -10
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd backend && git add analytics/risk/service.py tests/analytics/risk/
git commit -m "$(cat <<'EOF'
feat(risk): service factory accepts default thresholds from config

Mirrors the monitoring threshold work — RiskService and
create_risk_service now accept default_medium_risk_threshold and
default_high_risk_threshold. The router will populate them from
DomainConfig.analytics in a subsequent commit.
EOF
)"
```

---

## Task 6: Add `get_risk_service`, `get_timeseries_service`, `get_gnn_service` to `api/dependencies.py`

**Files:**
- Modify: `backend/api/dependencies.py`

- [ ] **Step 1: Find the existing analytics-related imports**

```bash
grep -n "from analytics\|MonitoringConfig\|AnalyticsConfig" backend/api/dependencies.py | head -20
```

Expected: `MonitoringConfig` is already imported (line 40). `AnalyticsConfig` may not be — confirm and add if needed.

- [ ] **Step 2: Add source factories and service factories**

After the existing `get_monitoring_service` (line 590), append:

```python
# ---------------------------------------------------------------------------
# Analytics services (E12+).
#
# Built from DomainConfig like monitoring is, with empty-by-default
# in-memory sources. Real data lands in these sources via background workers
# (risk scoring) or projection layers (timeseries, GNN snapshots); the API
# router returns whatever the sources hold at request time.
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_risk_signal_source() -> RiskSignalSourceProtocol:
    """Return the risk signal source. In-memory by default; persistence
    is layered on by the worker once Postgres-backed risk history exists."""
    return InMemoryRiskSignalSource()


@lru_cache(maxsize=1)
def get_risk_service() -> RiskServiceProtocol:
    """Return the risk service assembled from DomainConfig."""
    analytics_config = get_domain_config().analytics or AnalyticsConfig()
    return create_risk_service(
        get_risk_signal_source(),
        event_bus=get_event_bus(),
        default_medium_risk_threshold=analytics_config.medium_risk_threshold,
        default_high_risk_threshold=analytics_config.high_risk_threshold,
    )


@lru_cache(maxsize=1)
def get_timeseries_history_source() -> TimeSeriesHistorySourceProtocol:
    """Return the timeseries history source. In-memory by default."""
    return InMemoryTimeSeriesHistorySource()


@lru_cache(maxsize=1)
def get_timeseries_service() -> TimeseriesServiceProtocol:
    """Return the timeseries service assembled from DomainConfig."""
    return create_timeseries_service(
        get_timeseries_history_source(),
        event_bus=get_event_bus(),
    )


@lru_cache(maxsize=1)
def get_graph_snapshot_source() -> GraphSnapshotSourceProtocol:
    """Return the GNN graph snapshot source. In-memory by default."""
    return InMemoryGraphSnapshotSource()


def _gnn_capability_enabled() -> bool:
    return bool(get_domain_config().capabilities.gnn)


@lru_cache(maxsize=1)
def get_gnn_service() -> GnnServiceProtocol:
    """Return the GNN service assembled from DomainConfig.

    Honors the gnn capability flag — when disabled in config, the service
    returns empty results on every endpoint."""
    return create_gnn_service(
        get_graph_snapshot_source(),
        event_bus=get_event_bus(),
        gnn_enabled=_gnn_capability_enabled,
    )
```

- [ ] **Step 3: Add the imports**

At the top of `backend/api/dependencies.py`, add (next to the existing `MonitoringConfig` import):

```python
from analytics.gnn.adapters.in_memory import InMemoryGraphSnapshotSource
from analytics.gnn.protocols import GnnServiceProtocol, GraphSnapshotSourceProtocol
from analytics.gnn.service import create_gnn_service
from analytics.risk.adapters.in_memory import InMemoryRiskSignalSource
from analytics.risk.adapters.protocols import RiskSignalSourceProtocol
from analytics.risk.protocols import RiskServiceProtocol
from analytics.risk.service import create_risk_service
from analytics.timeseries.adapters.in_memory import InMemoryTimeSeriesHistorySource
from analytics.timeseries.protocols import TimeseriesServiceProtocol
from analytics.timeseries.service import create_timeseries_service
```

Add `AnalyticsConfig` next to the existing `MonitoringConfig` import:

```python
from config.schema import (
    # ... existing imports ...
    AnalyticsConfig,
    # ... existing imports ...
)
```

Verify the exact symbol names by reading the existing imports in `analytics/risk/adapters/in_memory.py` etc. — if the protocol name is `RiskServiceProtocol` from `protocols.py` but the importable lives elsewhere, adjust.

- [ ] **Step 4: Update the `__all__` list**

In `backend/api/dependencies.py`, find the `__all__` list at the top (around line 107-130) and add the six new helpers:

```python
__all__ = [
    # ... existing entries ...
    "get_gnn_service",
    "get_graph_snapshot_source",
    "get_risk_service",
    "get_risk_signal_source",
    "get_timeseries_history_source",
    "get_timeseries_service",
    # ... existing entries ...
]
```

(Alphabetize per the file's existing convention.)

- [ ] **Step 5: Run tests to confirm dependencies module imports cleanly**

```bash
cd backend && python -c "from api.dependencies import get_risk_service, get_timeseries_service, get_gnn_service; print('ok')"
```

Expected: prints `ok`. If an import fails, the message identifies the bad symbol; fix and retry.

- [ ] **Step 6: pyright on dependencies.py**

```bash
cd backend && pyright api/dependencies.py
```

Expected: 0 errors.

- [ ] **Step 7: Commit**

```bash
cd backend && git add api/dependencies.py
git commit -m "$(cat <<'EOF'
feat(api): DI helpers for risk/timeseries/gnn services driven by DomainConfig

Adds get_risk_service, get_timeseries_service, get_gnn_service and their
backing source factories to api/dependencies.py. Sources are in-memory
by default and empty; persistence is layered on as the worker populates
them. Mirrors the existing get_monitoring_service / get_graph_service
patterns.

Analytics router still uses its own stub factories; the next commit
redirects the router to these new DI helpers.
EOF
)"
```

---

## Task 7: Redirect `routers/analytics.py` to use the new DI helpers and remove stubs

**Files:**
- Modify: `backend/api/routers/analytics.py`

- [ ] **Step 1: Write the failing router test**

Find or create the analytics router test file:

```bash
ls backend/tests/api/test_analytics* backend/tests/api/test_*analytics* 2>/dev/null
```

If a test file exists, read it to understand the existing assertions. If it doesn't, create `backend/tests/api/test_analytics_router.py`.

The failing test asserts that the production endpoints return empty results when no analytics data has been written for the active domain:

```python
def test_risk_scores_returns_empty_when_no_data() -> None:
    """When no risk signals have been written for the active domain,
    the router should return an empty list — not the hardcoded Medicare
    fixture data that previously leaked from the @lru_cache stub."""
    response = test_client.get("/analytics/risk-scores?kb_id=empty-kb")
    assert response.status_code == 200
    body = response.json()
    assert body["knowledge_base_id"] == "empty-kb"
    assert body["items"] == []
    assert body["total"] == 0


def test_timeseries_returns_empty_when_no_data() -> None:
    response = test_client.get(
        "/analytics/timeseries"
        "?kb_id=empty-kb&metric=any&start=2026-01-01T00:00:00Z&end=2026-02-01T00:00:00Z"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["points"] == []
```

The exact response shape for timeseries depends on the `MetricTimeseriesResponse` model — read it via `grep -n "class MetricTimeseriesResponse" backend/analytics/timeseries/service_models.py` and adjust the assertion.

- [ ] **Step 2: Run, verify fail**

```bash
cd backend && pytest tests/api/test_analytics_router.py::test_risk_scores_returns_empty_when_no_data -v
```

Expected: FAIL — current router returns the hardcoded `kb-demo` fixtures.

- [ ] **Step 3: Replace the router contents**

Replace `backend/api/routers/analytics.py` entirely with the version that uses `api/dependencies.py` helpers. The new file:

```python
"""Analytics API endpoints for risk scores, timeseries, and GNN clusters."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from analytics.gnn.protocols import GnnServiceProtocol
from analytics.gnn.service_models import GnnClusterRequest, GnnClusterResponse
from analytics.risk.protocols import RiskServiceProtocol
from analytics.risk.service_models import RiskScoreListRequest, RiskScoreListResponse
from analytics.timeseries.protocols import TimeseriesServiceProtocol
from analytics.timeseries.service_models import (
    MetricTimeseriesResponse,
    TimeseriesQueryRequest,
)
from api.contracts import (
    AnalyticsOverviewResponse,
    EntityTimeseriesResponse,
    RiskScoreResponse,
)
from api.dependencies import (
    get_analytics_overview_payload,
    get_gnn_service,
    get_risk_score_payload,
    get_risk_service,
    get_timeseries_payload,
    get_timeseries_service,
)
from api.middleware.rbac import require_role

__all__ = ["router"]

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get(
    "/risk-scores",
    response_model=RiskScoreListResponse,
    dependencies=[Depends(require_role("viewer"))],
)
def list_risk_scores(
    kb_id: str = Query(..., min_length=1),
    entity_type: str | None = Query(default=None),
    limit: int = Query(default=20, gt=0, le=500),
    risk_service: RiskServiceProtocol = Depends(get_risk_service),
) -> RiskScoreListResponse:
    """Return ranked risk scores for entities in a knowledge base."""
    request = RiskScoreListRequest(
        knowledge_base_id=kb_id,
        entity_type=entity_type,
        limit=limit,
    )
    return risk_service.list_scores(request)


@router.get(
    "/timeseries",
    response_model=MetricTimeseriesResponse,
    dependencies=[Depends(require_role("viewer"))],
)
def query_timeseries(
    kb_id: str = Query(..., min_length=1),
    metric: str = Query(..., min_length=1),
    start: datetime = Query(...),
    end: datetime = Query(...),
    timeseries_service: TimeseriesServiceProtocol = Depends(get_timeseries_service),
) -> MetricTimeseriesResponse:
    """Return data points for one metric over a bounded time range."""
    if end <= start:
        raise HTTPException(status_code=422, detail="end must be after start")
    request = TimeseriesQueryRequest(
        knowledge_base_id=kb_id,
        metric_name=metric,
        start=start,
        end=end,
    )
    return timeseries_service.query_metric(request)


@router.get(
    "/gnn/clusters",
    response_model=GnnClusterResponse,
    dependencies=[Depends(require_role("viewer"))],
)
def list_gnn_clusters(
    kb_id: str = Query(..., min_length=1),
    gnn_service: GnnServiceProtocol = Depends(get_gnn_service),
) -> GnnClusterResponse:
    """Return GNN-derived clusters for a knowledge base.

    Returns an empty list when the GNN capability is disabled in config.
    """
    return gnn_service.list_clusters(GnnClusterRequest(knowledge_base_id=kb_id))


@router.get(
    "/overview",
    response_model=AnalyticsOverviewResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def get_analytics_overview(
    payload: AnalyticsOverviewResponse = Depends(get_analytics_overview_payload),
) -> AnalyticsOverviewResponse:
    """Return dashboard overview metrics for the analytics page."""
    return payload


@router.get(
    "/risk-scores/{entity_id}",
    response_model=RiskScoreResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def get_risk_score(
    payload: RiskScoreResponse = Depends(get_risk_score_payload),
) -> RiskScoreResponse:
    """Return the risk score breakdown for one entity."""
    return payload


@router.get(
    "/timeseries/{entity_id}",
    response_model=EntityTimeseriesResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def get_entity_timeseries(
    payload: EntityTimeseriesResponse = Depends(get_timeseries_payload),
) -> EntityTimeseriesResponse:
    """Return chartable time-series points for one entity."""
    return payload
```

This drops:
- `@lru_cache _stub_event_bus`
- `@lru_cache _stub_risk_signal_source` (with the Medicare-flavored `RankedRiskEntry` fixtures)
- `@lru_cache _stub_timeseries_history_source` (with the `claim_volume` Medicare seed)
- `@lru_cache _stub_graph_snapshot_source`
- `_gnn_disabled` (replaced by `_gnn_capability_enabled` in `dependencies.py` which reads the real config)
- local `get_risk_service`, `get_timeseries_service`, `get_gnn_service` (replaced by imports from `api.dependencies`)

The router file becomes purely about endpoint wiring — no business logic, no demo seed, no caching.

- [ ] **Step 4: Confirm no stub strings remain**

```bash
grep -n "kb-demo\|claim-9\|provider-1\|provider-2" backend/api/routers/analytics.py
```

Expected: no output.

```bash
grep -n "@lru_cache\|_stub_" backend/api/routers/analytics.py
```

Expected: no output.

- [ ] **Step 5: Run the analytics router tests**

```bash
cd backend && pytest tests/api/test_analytics_router.py -v 2>&1 | tail -20
```

Expected: the new empty-data tests PASS. Other tests in the file may need updating — any test that asserts on the hardcoded `kb-demo` / `provider-1` / `claim-9` data is testing the wrong thing and should be rewritten to:

1. Inject seed data via `app.dependency_overrides[get_risk_signal_source]` (etc.) before the request, or
2. Assert empty results when no data is injected.

- [ ] **Step 6: pyright + ruff on the new router**

```bash
cd backend && pyright api/routers/analytics.py
cd backend && ruff check api/routers/analytics.py
```

Expected: clean.

- [ ] **Step 7: Commit**

```bash
cd backend && git add api/routers/analytics.py tests/api/test_analytics_router.py
git commit -m "$(cat <<'EOF'
fix(analytics): router consumes services from api/dependencies, drops stub seed

The analytics router previously held @lru_cache stub factories with
hardcoded kb-demo/provider/claim Medicare seed data, served on the
production /analytics/{risk-scores,timeseries,gnn/clusters} endpoints.
Replaced with DI imports from api/dependencies; the router now returns
empty results when no analytics data has been written for the active
domain.

Test fixtures that previously asserted on the stub seed are rewritten
to either inject seed via dependency_overrides or assert empty results.
EOF
)"
```

---

## Task 8: Have the router populate request thresholds from DomainConfig (or let services do it)

**Files:**
- Modify: `backend/monitoring/service.py` — `evaluate()` uses `self.default_medium_threshold` / `self.default_high_threshold` as the request defaults when caller omits them
- Modify: `backend/analytics/risk/service.py` — `assess()` uses `self.default_medium_risk_threshold` / `self.default_high_risk_threshold` as the request defaults when caller omits them

**Design note:** Two viable approaches:
1. The router reads `DomainConfig.monitoring.medium_threshold` and populates the `MonitoringEvaluationRequest` explicitly per request.
2. The service stores defaults as instance attributes (already done in Tasks 4-5) and `MonitoringEvaluationRequest` becomes structurally optional for those fields — when missing, the service uses its defaults.

Approach 2 is cleaner: the request model stays the same, but the per-request fields become optional, and the service is the single source of truth for "what threshold applies when the caller didn't say." Approach 2 is the one used here.

- [ ] **Step 1: Make thresholds optional in `MonitoringEvaluationRequest`**

In `backend/monitoring/service_models.py`, change the threshold fields to be optional:

```python
class MonitoringEvaluationRequest(BaseModel):
    """A caller-supplied request to evaluate a batch of monitoring observations."""

    knowledge_base_id: str
    batch_id: str
    window_minutes: int = Field(default=5, gt=0)
    min_observations_in_window: int = Field(default=1, gt=0)
    medium_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    high_threshold: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_thresholds(self) -> MonitoringEvaluationRequest:
        if (
            self.medium_threshold is not None
            and self.high_threshold is not None
            and self.high_threshold <= self.medium_threshold
        ):
            raise ValueError(
                "MonitoringEvaluationRequest high_threshold must exceed medium_threshold."
            )
        return self
```

- [ ] **Step 2: Make `MonitoringService.evaluate` resolve `None` via defaults**

In `backend/monitoring/service.py`, inside `evaluate()`, before the thresholds are first used (find via grep `request.medium_threshold` and `request.high_threshold`):

```python
        effective_medium = (
            request.medium_threshold
            if request.medium_threshold is not None
            else self.default_medium_threshold
        )
        effective_high = (
            request.high_threshold
            if request.high_threshold is not None
            else self.default_high_threshold
        )
        if effective_high <= effective_medium:
            raise MonitoringConfigurationError(
                "Resolved thresholds invalid: high must exceed medium."
            )
```

Then replace every subsequent `request.medium_threshold` with `effective_medium` and `request.high_threshold` with `effective_high` inside `evaluate()`.

- [ ] **Step 3: Mirror the same change for `RiskAssessmentRequest` and `RiskService.assess`**

Same shape: make `medium_risk_threshold` and `high_risk_threshold` optional in `analytics/risk/service_models.py`, resolve via service defaults in `RiskService.assess`.

- [ ] **Step 4: Write a test confirming the wiring**

```python
def test_monitoring_evaluation_uses_service_default_thresholds_when_omitted() -> None:
    service = create_monitoring_service(
        _stub_observation_source_with_score(score=0.6),  # at the boundary
        event_bus=_stub_event_bus(),
        default_medium_threshold=0.55,  # caller would NOT trip default-default of 0.6
        default_high_threshold=0.85,
    )
    response = service.evaluate(
        MonitoringEvaluationRequest(
            knowledge_base_id="kb-1",
            batch_id="batch-1",
            window_minutes=5,
            min_observations_in_window=1,
            # thresholds omitted — service defaults must apply
        )
    )
    # With service default 0.55, the 0.6 observation triggers an alert.
    assert response.alerts_created == 1
```

- [ ] **Step 5: Run tests pass**

```bash
cd backend && pytest tests/monitoring/ tests/analytics/risk/ -q --no-cov 2>&1 | tail -10
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd backend && git add monitoring/service.py monitoring/service_models.py analytics/risk/service.py analytics/risk/service_models.py tests/monitoring/ tests/analytics/risk/
git commit -m "$(cat <<'EOF'
fix(thresholds): services use DomainConfig-derived defaults when request omits them

MonitoringEvaluationRequest.medium_threshold/high_threshold and
RiskAssessmentRequest.medium_risk_threshold/high_risk_threshold are now
Optional[float]. When the caller omits them, the service uses its
constructor-provided defaults (sourced from DomainConfig in
api/dependencies.py). Pydantic field defaults of 0.6/0.85/0.5/0.8 are
removed so they no longer silently bypass the domain.
EOF
)"
```

---

## Task 9: Final verification

**Files:** none (verification only)

- [ ] **Step 1: Confirm acceptance criteria**

```bash
grep -n "kb-demo\|provider-1\|provider-2\|claim-9" backend/api/routers/analytics.py
```

Expected: no output.

```bash
grep -n "@lru_cache\|_stub_" backend/api/routers/analytics.py
```

Expected: no output.

```bash
grep -n "Depends(get_risk_service)\|Depends(get_timeseries_service)\|Depends(get_gnn_service)" backend/api/routers/analytics.py
```

Expected: 3 matches.

```bash
grep -n "from api.dependencies import" backend/api/routers/analytics.py | grep -E "get_risk_service|get_timeseries_service|get_gnn_service"
```

Expected: 1 match (the consolidated import block lists all three).

- [ ] **Step 2: Full backend test suite + coverage**

```bash
cd backend && pytest --cov 2>&1 | tail -20
```

Expected: all tests pass, coverage ≥ 85%.

- [ ] **Step 3: pyright clean**

```bash
cd backend && pyright . 2>&1 | tail -5
```

Expected: 0 errors.

- [ ] **Step 4: ruff clean on touched files**

```bash
cd backend && ruff check api/routers/analytics.py api/dependencies.py monitoring/ analytics/ config/schema.py
```

Expected: no findings.

- [ ] **Step 5: Manual API smoke (the human runs this)**

```bash
# Boot the dev stack
make dev

# In another shell, hit the endpoints
curl 'http://localhost:8000/analytics/risk-scores?kb_id=empty-kb' | jq
# Expected: {"knowledge_base_id":"empty-kb","items":[],"total":0}

curl 'http://localhost:8000/analytics/gnn/clusters?kb_id=empty-kb' | jq
# Expected: empty cluster list (depends on gnn capability flag)
```

If either endpoint returns hardcoded Medicare-flavored fixtures, the router refactor was incomplete; fix and re-run.

---

## Acceptance Criteria — Sign-off Checklist

- [ ] `MonitoringConfig` has `medium_threshold` and `high_threshold`; `AnalyticsConfig` has `medium_risk_threshold` and `high_risk_threshold`.
- [ ] `MonitoringService`/`RiskService` accept `default_*_threshold` parameters in their factories.
- [ ] `MonitoringEvaluationRequest`/`RiskAssessmentRequest` threshold fields are optional and resolved via the service when omitted.
- [ ] `backend/api/routers/analytics.py` contains no `_stub_*` factories, no `@lru_cache`, no literal `kb-demo`/`provider-1`/`claim-9` strings.
- [ ] `backend/api/dependencies.py` exposes `get_risk_service`, `get_timeseries_service`, `get_gnn_service` and their backing source factories.
- [ ] The three analytics endpoints return empty results when no data is written for the active domain.
- [ ] `pytest --cov` ≥ 85%, `pyright` clean, `ruff check` clean.

## Scope Discipline

- **Do NOT** add Postgres-backed implementations for the analytics sources in this theme. The in-memory adapters with empty-default state are the contract; populating them is a separate effort.
- **Do NOT** wire the `AlertsConfig.thresholds` per-(entity_type, metric_name) dict into evaluation in this theme. That's a richer per-metric threshold model and a separate feature; the severity-tier thresholds added here are the global fallback.
- **Do NOT** change the analytics endpoint URLs or response shapes. Routing + DI is the surface that changes; contract stability is preserved.
- **Do NOT** delete `_gnn_disabled` from the router if any test still imports it. Read `tests/api/` for usage before removing.
- **Do NOT** touch the `routers/analytics.py` `/analytics/overview`, `/analytics/risk-scores/{entity_id}`, `/analytics/timeseries/{entity_id}` endpoints — they consume `ApiState` not the new services. Their migration is tracked in `docs/planning/p3_watch_items_2026-05-12.md` § "Analytics dual-path" and is out of scope for this theme.
