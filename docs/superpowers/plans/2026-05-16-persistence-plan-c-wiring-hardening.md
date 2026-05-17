# Backend Persistence — Plan C: Per-Consumer Adapters, Write-Back & Finalization

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the backend persistence initiative — add the read-side Postgres adapters and the `analytics/metrics/` package, then wire worker handlers so graph metrics, risk scores, and alerts persist durably and loop back into the graph.

**Architecture:** Plan A delivered `database/` and the six-table baseline migration; Plan B delivered `records/` and Flow 1. Plan C adds the remaining per-consumer Postgres adapters (each beside its in-memory sibling, selected by `config.database.backend`) and three worker handlers: Flow 2 persists graph metrics on `GraphUpdatedEvent` (throttled per-KB to avoid recompute storms), Flow 3 persists risk assessments on `RiskScoredEvent`, Flow 4 persists alerts on `AlertsCreatedEvent`. Flows 3/4 also write an entity-property snapshot back onto the graph entity.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, psycopg 3 (sync, via the `database.ConnectionProvider` protocol), Redis Streams events, pytest.

---

## Scope & Design Decisions

This is **Plan C of three**. It depends on Plan A (`database/` module, `0001_persistence_baseline` migration creating all six tables) and Plan B (`records/`, `monitoring/adapters/postgres.py::PostgresObservationStore`, `monitoring/adapters/protocols.py::ObservationWriter`, `GraphService.upsert_records_graph`, `handle_records_ingested`) — both already implemented on branch `db-development-infra`. **Plan C adds no migration**; the `entity_metric_history`, `entity_metrics_current`, `risk_score_history`, and `alert_history` tables already exist and are currently unused.

**Reference spec:** `docs/superpowers/specs/2026-05-14-backend-persistence-design.md` (§5.3 per-consumer adapters, §6.3–6.6 schema, §8 Flows 2/3/4).

Decisions confirmed with the user during planning (deviations from the literal spec, approved):

- **D-C1 — Risk Postgres adapter scope.** `risk_score_history` stores risk *outputs*; `RiskSignalSourceProtocol.load_profile` needs input *signals* (graph-derived, deferred per design §1). The Postgres risk adapter therefore is **not** a full `RiskSignalSourceProtocol`. Plan C delivers a narrow `RiskHistoryWriter` (Flow 3) plus a `load_historical_score` read on the same store. `load_profile`/`list_ranked_entries` stay in-memory (`list_ranked_entries` is additionally blocked: `risk_score_history` has no `entity_type` column).
- **D-C2 — Graph write-back & throttling.** Flows 3/4 write back to the graph **only as an entity-property snapshot** (`update_entity_properties`, which publishes no event). The durable history lives in the SQL `risk_score_history`/`alert_history` tables; D7's separate graph *history nodes* are deferred (they duplicate the SQL tables and add graph churn). Flow 2's metric recompute is **throttled per-KB** (`MetricsRecomputeThrottle`) so a burst of `GraphUpdatedEvent`s cannot thrash the system with recomputation. Because entity-property writes publish no event, the feedback loop (analytics → graph properties → future metrics/queries) cannot re-trigger recompute.
- **D-C3 — `upsert_records_graph`, never `upsert_task`, for any records/analytics-originated graph write.** `upsert_task` requires document-pipeline artifacts and publishes a `GraphUpdatedEvent` that would re-enter the analytics pipeline in a loop. Plan C's graph writes use `update_entity_properties` only.
- **D-C4 — Event reference enrichment.** Flows 3/4 run in the worker from event payloads, but `RiskScoredReference`/`AlertCreatedReference` carry summaries, not the full data the history tables need. Plan C adds fields to those reference sub-models (with defaults, so decoding stays backward-compatible) and updates their builders. No new event *types*; the codec registry is untouched.
- **D-C5 — API scope.** Plan C wires Postgres adapters into the worker composition root and adds a Postgres branch to `api/dependencies.py::get_monitoring_source`. The `api/state.py` deterministic risk/timeseries demo stubs are a pre-existing seam and are **out of scope**.

---

## Conventions

- All commands run from `backend/` unless stated otherwise.
- The host venv is the fast path: `.venv/bin/pytest`, `.venv/bin/pyright`, `.venv/bin/ruff` from `backend/`.
- Unit tests: `.venv/bin/pytest -m "not integration"`. Integration tests: `.venv/bin/pytest -m integration` against a running TimescaleDB with `alembic upgrade head` applied; they skip when `DATABASE_URL` is unset.
- New Postgres adapters depend only on the psycopg-free `database.ConnectionProvider` protocol — they import no psycopg. A connection is used as `with provider.connection() as conn:`, then `conn.execute(sql, params).fetchall()/.fetchone()` and `conn.commit()`. `Row` is a positional `tuple[object, ...]`; jsonb columns are written with an explicit `%s::jsonb` cast over `json.dumps(...)`.
- New integration-test files set module-level `pytestmark = pytest.mark.integration`, declare a local `database_url` skip-gate fixture (copy from `tests/monitoring/test_postgres_observation_store.py`), and clean up rows in a `try/finally` ending with `provider.close()`.
- New code must pass `pyright --strict` and `ruff check .`. No `Any`, full annotations, no error suppression.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `backend/config/schema.py` | New `AnalyticsConfig`; `DomainConfig.analytics` + post-validator default |
| `backend/analytics/metrics/__init__.py` | Public exports for the new metrics package |
| `backend/analytics/metrics/models.py` | `EntityMetricSample`, `EntityMetricValue`, graph-scope constants |
| `backend/analytics/metrics/exceptions.py` | `MetricsError` / `MetricsRepositoryError` |
| `backend/analytics/metrics/throttle.py` | `MetricsRecomputeThrottle` (per-KB recompute rate limiter) |
| `backend/analytics/metrics/adapters/{__init__,protocols,in_memory,postgres}.py` | `EntityMetricRepository` protocol + in-memory + Postgres adapters |
| `backend/monitoring/adapters/postgres.py` | Add `PostgresObservationSource` (read) + `PostgresAlertHistoryStore` (alert log) |
| `backend/monitoring/adapters/protocols.py` | New `AlertHistoryWriter` protocol |
| `backend/monitoring/adapters/in_memory.py` | New `InMemoryAlertHistoryWriter` |
| `backend/monitoring/models.py` | New `AlertHistoryRecord` model |
| `backend/analytics/timeseries/adapters/postgres.py` | New `PostgresTimeSeriesHistorySource` (read) |
| `backend/analytics/risk/adapters/postgres.py` | New `PostgresRiskHistoryStore` (writer + history read) |
| `backend/analytics/risk/adapters/protocols.py` | New `RiskHistoryWriter` protocol |
| `backend/analytics/risk/adapters/in_memory.py` | New `InMemoryRiskHistoryWriter` |
| `backend/analytics/risk/models.py` | New `RiskAssessmentRecord` model |
| `backend/analytics/risk/exceptions.py` | New `RiskHistoryError` |
| `backend/events/types.py` | `RiskFactorReference`; new fields on `RiskScoredReference` + `AlertCreatedReference` |
| `backend/analytics/risk/service.py` | Populate `RiskScoredReference.factors` |
| `backend/monitoring/service.py` | Populate the new `AlertCreatedReference` fields |
| `backend/agent/coordinator.py` | Flows 2/3/4 handlers, `build_*`, `WorkerDependencies`, dispatch/consume wiring |
| `backend/api/dependencies.py` | Postgres branch in `get_monitoring_source` |
| `backend/config/defaults/medicare_fraud_dev.yaml` | Example `analytics` section |
| `backend/pyproject.toml` | pyright `include` additions |
| READMEs, `docs/architecture.md`, `.github/copilot-instructions.md` | Docs |
| `backend/tests/...` | Unit + integration tests |

---

## Phase 1 — Configuration

### Task 1: `AnalyticsConfig` and `DomainConfig.analytics`

**Files:**
- Modify: `backend/config/schema.py`
- Modify: `backend/config/defaults/medicare_fraud_dev.yaml`
- Test: `backend/tests/config/test_schema.py` (or the nearest existing config test module)

- [ ] **Step 1: Write the failing test**

Add to the config schema test module:

```python
def test_analytics_config_defaults() -> None:
    from config.schema import AnalyticsConfig

    config = AnalyticsConfig()
    assert config.metrics_recompute_min_interval_seconds == 300


def test_domain_config_defaults_analytics_section(tmp_path: Path) -> None:
    """A config that omits `analytics` gets the default AnalyticsConfig."""
    from config.loader import load_config

    # Use the bundled medicare config, which omits the analytics section.
    config = load_config(
        Path(__file__).resolve().parents[2]
        / "config" / "defaults" / "medicare_fraud.yaml"
    )
    assert config.analytics is not None
    assert config.analytics.metrics_recompute_min_interval_seconds == 300
```

(Import `Path` from `pathlib` at the top of the test file if not already present.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/config/test_schema.py -k analytics -v`
Expected: FAIL with `ImportError` / `AttributeError` on `AnalyticsConfig`.

- [ ] **Step 3: Add `AnalyticsConfig`**

In `backend/config/schema.py`, immediately after the `MonitoringConfig` class (ends line 174), insert:

```python
class AnalyticsConfig(BaseModel):
    """Configuration for analytics persistence and recompute behaviour."""

    metrics_recompute_min_interval_seconds: int = Field(default=300, gt=0)
```

- [ ] **Step 4: Add the field and default to `DomainConfig`**

In `DomainConfig`, after the `validation: ValidationConfig | None = None` line (line 350), add:

```python
    analytics: AnalyticsConfig | None = None
```

In `_validate_cross_references`, after the `if self.records is None:` block (lines 391-392), add:

```python
        if self.analytics is None:
            self.analytics = AnalyticsConfig()
```

In `__all__`, add `"AnalyticsConfig"` (keep alphabetical ordering — insert before `"AuthConfig"`).

- [ ] **Step 5: Add an example `analytics` section to the dev config**

In `backend/config/defaults/medicare_fraud_dev.yaml`, after the `database:` block, add:

```yaml
analytics:
  metrics_recompute_min_interval_seconds: 300
```

- [ ] **Step 6: Run tests, pyright, ruff**

Run: `.venv/bin/pytest tests/config/ -v && .venv/bin/pyright && .venv/bin/ruff check config/`
Expected: PASS, clean.

- [ ] **Step 7: Commit**

```bash
git add config/schema.py config/defaults/medicare_fraud_dev.yaml tests/config/
git commit -m "feat(config): add AnalyticsConfig for metric-recompute throttling"
```

---

## Phase 2 — `analytics/metrics/` package

### Task 2: Metrics models and exceptions

**Files:**
- Create: `backend/analytics/metrics/__init__.py` (empty placeholder for now — completed in Task 5)
- Create: `backend/analytics/metrics/models.py`
- Create: `backend/analytics/metrics/exceptions.py`
- Test: `backend/tests/analytics/metrics/__init__.py` (empty), `backend/tests/analytics/metrics/test_models.py`

- [ ] **Step 1: Create the empty package markers**

Create `backend/analytics/metrics/__init__.py` containing only:

```python
"""Entity-metric persistence package (graph metrics over time + current snapshot)."""
```

Create `backend/tests/analytics/metrics/__init__.py` as an empty file.

- [ ] **Step 2: Write the failing test**

Create `backend/tests/analytics/metrics/test_models.py`:

```python
"""Tests for the analytics metrics models."""

from __future__ import annotations

from datetime import datetime, timezone

from analytics.metrics.models import (
    GRAPH_SCOPE_ENTITY_ID,
    METRIC_AVG_DEGREE,
    METRIC_ENTITY_COUNT,
    METRIC_RELATIONSHIP_COUNT,
    EntityMetricSample,
    EntityMetricValue,
)


def test_graph_scope_constants() -> None:
    assert GRAPH_SCOPE_ENTITY_ID == "__graph__"
    assert METRIC_ENTITY_COUNT == "entity_count"
    assert METRIC_RELATIONSHIP_COUNT == "relationship_count"
    assert METRIC_AVG_DEGREE == "avg_degree"


def test_entity_metric_sample_defaults_observed_at() -> None:
    sample = EntityMetricSample(
        knowledge_base_id="kb-1",
        entity_id=GRAPH_SCOPE_ENTITY_ID,
        metric_name=METRIC_ENTITY_COUNT,
        value=12.0,
        correlation_id="corr-1",
    )
    assert sample.observed_at.tzinfo is not None


def test_entity_metric_value_round_trips() -> None:
    value = EntityMetricValue(
        knowledge_base_id="kb-1",
        entity_id="claim:c1",
        metric_name=METRIC_AVG_DEGREE,
        value=2.5,
        updated_at=datetime(2026, 5, 16, tzinfo=timezone.utc),
    )
    assert value.value == 2.5
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/pytest tests/analytics/metrics/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: analytics.metrics.models`.

- [ ] **Step 4: Create `models.py`**

Create `backend/analytics/metrics/models.py`:

```python
"""Internal models for entity-metric persistence."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from shared.utils import utc_now

GRAPH_SCOPE_ENTITY_ID = "__graph__"
"""Sentinel entity id for graph-wide (KB-level) metrics that have no single owner."""

METRIC_ENTITY_COUNT = "entity_count"
METRIC_RELATIONSHIP_COUNT = "relationship_count"
METRIC_AVG_DEGREE = "avg_degree"


class EntityMetricSample(BaseModel):
    """One metric value for one entity (or graph scope) at a point in time."""

    knowledge_base_id: str
    entity_id: str
    metric_name: str
    value: float
    observed_at: datetime = Field(default_factory=utc_now)
    correlation_id: str


class EntityMetricValue(BaseModel):
    """The latest value of one metric for one entity (current snapshot)."""

    knowledge_base_id: str
    entity_id: str
    metric_name: str
    value: float
    updated_at: datetime


__all__ = [
    "GRAPH_SCOPE_ENTITY_ID",
    "METRIC_AVG_DEGREE",
    "METRIC_ENTITY_COUNT",
    "METRIC_RELATIONSHIP_COUNT",
    "EntityMetricSample",
    "EntityMetricValue",
]
```

- [ ] **Step 5: Create `exceptions.py`**

Create `backend/analytics/metrics/exceptions.py`:

```python
"""Exception hierarchy for the analytics metrics package."""

from __future__ import annotations


class MetricsError(Exception):
    """Base exception for analytics metrics failures."""


class MetricsRepositoryError(MetricsError):
    """Raised when the entity-metric repository cannot read or write metrics."""


__all__ = [
    "MetricsError",
    "MetricsRepositoryError",
]
```

- [ ] **Step 6: Run test, pyright, ruff**

Run: `.venv/bin/pytest tests/analytics/metrics/test_models.py -v && .venv/bin/pyright && .venv/bin/ruff check analytics/metrics/`
Expected: PASS, clean. (pyright will not yet check `analytics/metrics` strictly — that include entry is added in Task 5; ruff still runs.)

- [ ] **Step 7: Commit**

```bash
git add analytics/metrics/__init__.py analytics/metrics/models.py analytics/metrics/exceptions.py tests/analytics/metrics/
git commit -m "feat(metrics): add entity-metric models and exceptions"
```

---

### Task 3: `EntityMetricRepository` protocol and in-memory adapter

**Files:**
- Create: `backend/analytics/metrics/adapters/__init__.py`
- Create: `backend/analytics/metrics/adapters/protocols.py`
- Create: `backend/analytics/metrics/adapters/in_memory.py`
- Test: `backend/tests/analytics/metrics/test_in_memory_repository.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/analytics/metrics/test_in_memory_repository.py`:

```python
"""Tests for the in-memory entity-metric repository."""

from __future__ import annotations

from analytics.metrics.adapters.in_memory import InMemoryEntityMetricRepository
from analytics.metrics.adapters.protocols import EntityMetricRepository
from analytics.metrics.models import EntityMetricSample


def _sample(metric: str, value: float, *, correlation_id: str = "corr-1") -> EntityMetricSample:
    return EntityMetricSample(
        knowledge_base_id="kb-1",
        entity_id="__graph__",
        metric_name=metric,
        value=value,
        correlation_id=correlation_id,
    )


def test_repository_satisfies_protocol() -> None:
    repo: EntityMetricRepository = InMemoryEntityMetricRepository()
    assert repo.record_metrics([]) == 0


def test_record_metrics_appends_history_and_upserts_current() -> None:
    repo = InMemoryEntityMetricRepository()
    written = repo.record_metrics([_sample("entity_count", 5.0)])
    assert written == 1

    current = repo.load_current_metrics(knowledge_base_id="kb-1", entity_id="__graph__")
    assert len(current) == 1
    assert current[0].value == 5.0


def test_record_metrics_current_reflects_latest_value() -> None:
    repo = InMemoryEntityMetricRepository()
    repo.record_metrics([_sample("entity_count", 5.0)])
    repo.record_metrics([_sample("entity_count", 9.0)])

    current = repo.load_current_metrics(knowledge_base_id="kb-1", entity_id="__graph__")
    assert [c.value for c in current] == [9.0]


def test_load_current_metrics_unknown_entity_returns_empty() -> None:
    repo = InMemoryEntityMetricRepository()
    assert repo.load_current_metrics(knowledge_base_id="kb-x", entity_id="e-x") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/analytics/metrics/test_in_memory_repository.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create `adapters/__init__.py` and `adapters/protocols.py`**

Create `backend/analytics/metrics/adapters/__init__.py`:

```python
"""Entity-metric repository adapters."""
```

Create `backend/analytics/metrics/adapters/protocols.py`:

```python
"""Adapter-level protocol for entity-metric persistence."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from analytics.metrics.models import EntityMetricSample, EntityMetricValue


@runtime_checkable
class EntityMetricRepository(Protocol):
    """Persist graph metrics over time and expose the current snapshot."""

    def record_metrics(self, samples: list[EntityMetricSample]) -> int:
        """Append samples to history and upsert the current snapshot.

        Returns the count of newly inserted history rows. Idempotent: a sample
        with the same (knowledge_base_id, entity_id, metric_name, observed_at)
        is not double-counted.
        """
        ...

    def load_current_metrics(
        self, *, knowledge_base_id: str, entity_id: str
    ) -> list[EntityMetricValue]:
        """Return the latest value of every metric for one entity."""
        ...


__all__ = [
    "EntityMetricRepository",
]
```

- [ ] **Step 4: Create `adapters/in_memory.py`**

Create `backend/analytics/metrics/adapters/in_memory.py`:

```python
"""In-memory entity-metric repository for tests and local development."""

from __future__ import annotations

from analytics.metrics.models import EntityMetricSample, EntityMetricValue

__all__ = ["InMemoryEntityMetricRepository"]


class InMemoryEntityMetricRepository:
    """A dict-backed ``EntityMetricRepository``."""

    def __init__(self) -> None:
        self._history: list[EntityMetricSample] = []
        self._current: dict[tuple[str, str, str], EntityMetricValue] = {}

    def record_metrics(self, samples: list[EntityMetricSample]) -> int:
        written = 0
        for sample in samples:
            history_key = (
                sample.knowledge_base_id,
                sample.entity_id,
                sample.metric_name,
                sample.observed_at,
            )
            if any(
                (s.knowledge_base_id, s.entity_id, s.metric_name, s.observed_at)
                == history_key
                for s in self._history
            ):
                continue
            self._history.append(sample)
            written += 1
            self._current[
                (sample.knowledge_base_id, sample.entity_id, sample.metric_name)
            ] = EntityMetricValue(
                knowledge_base_id=sample.knowledge_base_id,
                entity_id=sample.entity_id,
                metric_name=sample.metric_name,
                value=sample.value,
                updated_at=sample.observed_at,
            )
        return written

    def load_current_metrics(
        self, *, knowledge_base_id: str, entity_id: str
    ) -> list[EntityMetricValue]:
        matches = [
            value
            for (kb, ent, _metric), value in self._current.items()
            if kb == knowledge_base_id and ent == entity_id
        ]
        return sorted(matches, key=lambda value: value.metric_name)
```

- [ ] **Step 5: Run test, ruff**

Run: `.venv/bin/pytest tests/analytics/metrics/test_in_memory_repository.py -v && .venv/bin/ruff check analytics/metrics/`
Expected: PASS, clean.

- [ ] **Step 6: Commit**

```bash
git add analytics/metrics/adapters/ tests/analytics/metrics/test_in_memory_repository.py
git commit -m "feat(metrics): add EntityMetricRepository protocol and in-memory adapter"
```

---

### Task 4: `PostgresEntityMetricRepository`

**Files:**
- Create: `backend/analytics/metrics/adapters/postgres.py`
- Test: `backend/tests/analytics/metrics/test_postgres_repository.py`

- [ ] **Step 1: Write the failing integration test**

Create `backend/tests/analytics/metrics/test_postgres_repository.py`:

```python
"""Integration tests for the Postgres entity-metric repository."""

from __future__ import annotations

import os

import pytest

from analytics.metrics.adapters.postgres import PostgresEntityMetricRepository
from analytics.metrics.models import EntityMetricSample
from config.schema import DatabaseConfig
from database.runtime import create_connection_provider

pytestmark = pytest.mark.integration


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set; skipping metrics integration test.")
    return url


def _sample(metric: str, value: float) -> EntityMetricSample:
    return EntityMetricSample(
        knowledge_base_id="kb-metrics-test",
        entity_id="__graph__",
        metric_name=metric,
        value=value,
        correlation_id="corr-metrics-1",
    )


def test_record_metrics_round_trip_and_idempotent(database_url: str) -> None:
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    repo = PostgresEntityMetricRepository(provider)
    try:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM entity_metric_history "
                "WHERE knowledge_base_id = 'kb-metrics-test'"
            )
            conn.execute(
                "DELETE FROM entity_metrics_current "
                "WHERE knowledge_base_id = 'kb-metrics-test'"
            )
            conn.commit()

        assert repo.record_metrics([]) == 0

        sample = _sample("entity_count", 5.0)
        assert repo.record_metrics([sample]) == 1
        # Same observed_at -> idempotent, no new history row.
        assert repo.record_metrics([sample]) == 0

        current = repo.load_current_metrics(
            knowledge_base_id="kb-metrics-test", entity_id="__graph__"
        )
        assert [(c.metric_name, c.value) for c in current] == [("entity_count", 5.0)]
    finally:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM entity_metric_history "
                "WHERE knowledge_base_id = 'kb-metrics-test'"
            )
            conn.execute(
                "DELETE FROM entity_metrics_current "
                "WHERE knowledge_base_id = 'kb-metrics-test'"
            )
            conn.commit()
        provider.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/analytics/metrics/test_postgres_repository.py -m integration -v`
Expected: FAIL with `ModuleNotFoundError` (or SKIP if `DATABASE_URL` is unset — set it and run against the dev Timescale container to see the real failure).

- [ ] **Step 3: Create `adapters/postgres.py`**

Create `backend/analytics/metrics/adapters/postgres.py`:

```python
"""Postgres-backed entity-metric repository.

Depends only on the psycopg-free ``database.ConnectionProvider`` protocol.
Writes the time-series ``entity_metric_history`` hypertable and upserts the
``entity_metrics_current`` snapshot table in a single transaction.
"""

from __future__ import annotations

from datetime import datetime
from typing import cast

from analytics.metrics.exceptions import MetricsRepositoryError
from analytics.metrics.models import EntityMetricSample, EntityMetricValue
from database.protocols import ConnectionProvider, Row

_HISTORY_INSERT_SQL = """
    INSERT INTO entity_metric_history (
        knowledge_base_id, entity_id, metric_name, value, observed_at, correlation_id
    ) VALUES (%s, %s, %s, %s, %s, %s)
    ON CONFLICT (knowledge_base_id, entity_id, metric_name, observed_at) DO NOTHING
"""

_CURRENT_UPSERT_SQL = """
    INSERT INTO entity_metrics_current (
        knowledge_base_id, entity_id, metric_name, value, updated_at
    ) VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT (knowledge_base_id, entity_id, metric_name)
    DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at
"""

_CURRENT_SELECT_SQL = """
    SELECT knowledge_base_id, entity_id, metric_name, value, updated_at
    FROM entity_metrics_current
    WHERE knowledge_base_id = %s AND entity_id = %s
    ORDER BY metric_name
"""


class PostgresEntityMetricRepository:
    """An ``EntityMetricRepository`` backed by the two metric tables."""

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def record_metrics(self, samples: list[EntityMetricSample]) -> int:
        if not samples:
            return 0
        written = 0
        try:
            with self._provider.connection() as conn:
                for sample in samples:
                    cursor = conn.execute(
                        _HISTORY_INSERT_SQL,
                        (
                            sample.knowledge_base_id,
                            sample.entity_id,
                            sample.metric_name,
                            sample.value,
                            sample.observed_at,
                            sample.correlation_id,
                        ),
                    )
                    written += cursor.rowcount
                    conn.execute(
                        _CURRENT_UPSERT_SQL,
                        (
                            sample.knowledge_base_id,
                            sample.entity_id,
                            sample.metric_name,
                            sample.value,
                            sample.observed_at,
                        ),
                    )
                conn.commit()
        except Exception as exc:
            raise MetricsRepositoryError("Failed to record entity metrics.") from exc
        return written

    def load_current_metrics(
        self, *, knowledge_base_id: str, entity_id: str
    ) -> list[EntityMetricValue]:
        try:
            with self._provider.connection() as conn:
                rows = conn.execute(
                    _CURRENT_SELECT_SQL, (knowledge_base_id, entity_id)
                ).fetchall()
        except Exception as exc:
            raise MetricsRepositoryError("Failed to load current metrics.") from exc
        return [_row_to_value(row) for row in rows]


def _row_to_value(row: Row) -> EntityMetricValue:
    return EntityMetricValue(
        knowledge_base_id=str(row[0]),
        entity_id=str(row[1]),
        metric_name=str(row[2]),
        value=float(cast(float, row[3])),
        updated_at=cast(datetime, row[4]),
    )


__all__ = [
    "PostgresEntityMetricRepository",
]
```

- [ ] **Step 4: Run the integration test against the dev database**

Ensure the dev stack is up (`make dev`) and the migration applied, then run with `DATABASE_URL` pointing at the Timescale container:

Run: `.venv/bin/pytest tests/analytics/metrics/test_postgres_repository.py -m integration -v`
Expected: PASS.

- [ ] **Step 5: Run ruff**

Run: `.venv/bin/ruff check analytics/metrics/`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add analytics/metrics/adapters/postgres.py tests/analytics/metrics/test_postgres_repository.py
git commit -m "feat(metrics): add Postgres entity-metric repository"
```

---

### Task 5: `MetricsRecomputeThrottle` and package exports

**Files:**
- Create: `backend/analytics/metrics/throttle.py`
- Modify: `backend/analytics/metrics/__init__.py`
- Modify: `backend/pyproject.toml`
- Test: `backend/tests/analytics/metrics/test_throttle.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/analytics/metrics/test_throttle.py`:

```python
"""Tests for the per-KB metrics recompute throttle."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from analytics.metrics.throttle import MetricsRecomputeThrottle


def test_first_recompute_is_allowed() -> None:
    throttle = MetricsRecomputeThrottle(min_interval_seconds=300)
    now = datetime(2026, 5, 16, 12, 0, 0, tzinfo=timezone.utc)
    assert throttle.should_recompute("kb-1", now=now) is True


def test_recompute_within_interval_is_rejected() -> None:
    throttle = MetricsRecomputeThrottle(min_interval_seconds=300)
    start = datetime(2026, 5, 16, 12, 0, 0, tzinfo=timezone.utc)
    assert throttle.should_recompute("kb-1", now=start) is True
    assert (
        throttle.should_recompute("kb-1", now=start + timedelta(seconds=120))
        is False
    )


def test_recompute_after_interval_is_allowed_again() -> None:
    throttle = MetricsRecomputeThrottle(min_interval_seconds=300)
    start = datetime(2026, 5, 16, 12, 0, 0, tzinfo=timezone.utc)
    assert throttle.should_recompute("kb-1", now=start) is True
    assert (
        throttle.should_recompute("kb-1", now=start + timedelta(seconds=301))
        is True
    )


def test_throttle_is_per_knowledge_base() -> None:
    throttle = MetricsRecomputeThrottle(min_interval_seconds=300)
    now = datetime(2026, 5, 16, 12, 0, 0, tzinfo=timezone.utc)
    assert throttle.should_recompute("kb-1", now=now) is True
    assert throttle.should_recompute("kb-2", now=now) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/analytics/metrics/test_throttle.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create `throttle.py`**

Create `backend/analytics/metrics/throttle.py`:

```python
"""Per-knowledge-base rate limiter for graph-metric recomputation.

A burst of ``GraphUpdatedEvent``s would otherwise trigger a metric
recompute per event. The throttle records the last recompute time per KB and
rejects further recomputes until ``min_interval_seconds`` has elapsed, so the
graph-metrics feedback loop cannot thrash the system.
"""

from __future__ import annotations

from datetime import datetime, timedelta

__all__ = ["MetricsRecomputeThrottle"]


class MetricsRecomputeThrottle:
    """Allow at most one metric recompute per KB per ``min_interval_seconds``."""

    def __init__(self, *, min_interval_seconds: int) -> None:
        if min_interval_seconds <= 0:
            raise ValueError("min_interval_seconds must be greater than 0.")
        self._min_interval = timedelta(seconds=min_interval_seconds)
        self._last_recompute: dict[str, datetime] = {}

    def should_recompute(self, knowledge_base_id: str, *, now: datetime) -> bool:
        """Return True and record ``now`` when a recompute is permitted."""

        previous = self._last_recompute.get(knowledge_base_id)
        if previous is not None and (now - previous) < self._min_interval:
            return False
        self._last_recompute[knowledge_base_id] = now
        return True
```

- [ ] **Step 4: Complete `analytics/metrics/__init__.py`**

Replace the contents of `backend/analytics/metrics/__init__.py` with:

```python
"""Entity-metric persistence package (graph metrics over time + current snapshot)."""

from __future__ import annotations

from analytics.metrics.adapters.in_memory import InMemoryEntityMetricRepository
from analytics.metrics.adapters.postgres import PostgresEntityMetricRepository
from analytics.metrics.adapters.protocols import EntityMetricRepository
from analytics.metrics.exceptions import MetricsError, MetricsRepositoryError
from analytics.metrics.models import (
    GRAPH_SCOPE_ENTITY_ID,
    METRIC_AVG_DEGREE,
    METRIC_ENTITY_COUNT,
    METRIC_RELATIONSHIP_COUNT,
    EntityMetricSample,
    EntityMetricValue,
)
from analytics.metrics.throttle import MetricsRecomputeThrottle

__all__ = [
    "GRAPH_SCOPE_ENTITY_ID",
    "METRIC_AVG_DEGREE",
    "METRIC_ENTITY_COUNT",
    "METRIC_RELATIONSHIP_COUNT",
    "EntityMetricRepository",
    "EntityMetricSample",
    "EntityMetricValue",
    "InMemoryEntityMetricRepository",
    "MetricsError",
    "MetricsRecomputeThrottle",
    "MetricsRepositoryError",
    "PostgresEntityMetricRepository",
]
```

- [ ] **Step 5: Add `analytics/metrics` to pyright `include`**

In `backend/pyproject.toml`, in `[tool.pyright].include`, insert `"analytics/metrics"` immediately after the `"analytics/gnn"` line:

```toml
    "analytics/gnn",
    "analytics/metrics",
    "analytics/timeseries",
```

Then insert `"tests/analytics/metrics"` immediately after `"tests/analytics/gnn"`:

```toml
    "tests/analytics/gnn",
    "tests/analytics/metrics",
    "tests/analytics/timeseries",
```

- [ ] **Step 6: Run tests, pyright, ruff**

Run: `.venv/bin/pytest tests/analytics/metrics/ -v && .venv/bin/pyright && .venv/bin/ruff check analytics/metrics/`
Expected: PASS, clean.

- [ ] **Step 7: Commit**

```bash
git add analytics/metrics/ tests/analytics/metrics/test_throttle.py pyproject.toml
git commit -m "feat(metrics): add recompute throttle and finalize metrics package"
```

---

## Phase 3 — Monitoring read-side and alert history

### Task 6: `PostgresObservationSource` (read side)

**Files:**
- Modify: `backend/monitoring/adapters/postgres.py`
- Modify: `backend/monitoring/adapters/__init__.py`, `backend/monitoring/__init__.py`
- Test: `backend/tests/monitoring/test_postgres_observation_source.py`

- [ ] **Step 1: Write the failing integration test**

Create `backend/tests/monitoring/test_postgres_observation_source.py`:

```python
"""Integration tests for the Postgres observation source (read side)."""

from __future__ import annotations

import os

import pytest

from config.schema import DatabaseConfig
from database.runtime import create_connection_provider
from monitoring.adapters.postgres import PostgresObservationSource, PostgresObservationStore
from monitoring.models import MonitoringBatch, MonitoringObservation

pytestmark = pytest.mark.integration


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set; skipping observation source test.")
    return url


def _batch() -> MonitoringBatch:
    return MonitoringBatch(
        knowledge_base_id="kb-obs-src-test",
        batch_id="corr-obs-src-1",
        observations=[
            MonitoringObservation(
                entity_id="claim:c1",
                entity_type="claim",
                metric_name="claim_anomaly",
                score=0.8,
                rationale="integration test",
            )
        ],
    )


def test_load_batch_round_trip(database_url: str) -> None:
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    writer = PostgresObservationStore(provider)
    source = PostgresObservationSource(provider)
    try:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM observations WHERE knowledge_base_id = 'kb-obs-src-test'"
            )
            conn.commit()

        writer.write_observations(_batch(), correlation_id="corr-obs-src-1")
        loaded = source.load_batch(
            knowledge_base_id="kb-obs-src-test", batch_id="corr-obs-src-1"
        )
        assert loaded.knowledge_base_id == "kb-obs-src-test"
        assert loaded.observations[0].metric_name == "claim_anomaly"
        assert loaded.observations[0].score == 0.8
    finally:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM observations WHERE knowledge_base_id = 'kb-obs-src-test'"
            )
            conn.commit()
        provider.close()


def test_load_batch_unknown_raises_value_error(database_url: str) -> None:
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    source = PostgresObservationSource(provider)
    try:
        with pytest.raises(ValueError, match="No monitoring batch"):
            source.load_batch(knowledge_base_id="kb-missing", batch_id="corr-missing")
    finally:
        provider.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/monitoring/test_postgres_observation_source.py -m integration -v`
Expected: FAIL — `ImportError: cannot import name 'PostgresObservationSource'`.

- [ ] **Step 3: Add `PostgresObservationSource` to `monitoring/adapters/postgres.py`**

In `backend/monitoring/adapters/postgres.py`, add the import of `MonitoringObservation` and the new `Row`/`datetime` imports at the top (alongside the existing imports):

```python
from __future__ import annotations

from datetime import datetime
from typing import cast

from database.protocols import ConnectionProvider, Row
from monitoring.exceptions import MonitoringSourceError
from monitoring.models import MonitoringBatch, MonitoringObservation
```

After the existing `_INSERT_SQL` constant, add:

```python
_SELECT_BATCH_SQL = """
    SELECT entity_id, entity_type, metric_name, score, observed_at,
           rationale, evidence_pack_id
    FROM observations
    WHERE knowledge_base_id = %s AND batch_id = %s
    ORDER BY observed_at, entity_id, metric_name
"""
```

After the `PostgresObservationStore` class (before the module `__all__`), add:

```python
class PostgresObservationSource:
    """An ``ObservationSourceProtocol`` backed by the ``observations`` table.

    ``load_batch`` resolves the run by ``batch_id`` (the ingest correlation
    id), using the existing ``ix_observations_batch`` index.
    """

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def load_batch(self, *, knowledge_base_id: str, batch_id: str) -> MonitoringBatch:
        try:
            with self._provider.connection() as conn:
                rows = conn.execute(
                    _SELECT_BATCH_SQL, (knowledge_base_id, batch_id)
                ).fetchall()
        except Exception as exc:
            raise MonitoringSourceError("Failed to load monitoring batch.") from exc
        if not rows:
            raise ValueError(
                f"No monitoring batch registered for "
                f"knowledge_base_id='{knowledge_base_id}' and batch_id='{batch_id}'."
            )
        return MonitoringBatch(
            knowledge_base_id=knowledge_base_id,
            batch_id=batch_id,
            observations=[_row_to_observation(row) for row in rows],
        )


def _row_to_observation(row: Row) -> MonitoringObservation:
    return MonitoringObservation(
        entity_id=str(row[0]),
        entity_type=str(row[1]),
        metric_name=str(row[2]),
        score=float(cast(float, row[3])),
        observed_at=cast(datetime, row[4]),
        rationale=str(row[5]),
        evidence_pack_id=None if row[6] is None else str(row[6]),
    )
```

Update the module `__all__` to:

```python
__all__ = [
    "PostgresObservationSource",
    "PostgresObservationStore",
]
```

- [ ] **Step 4: Export the new adapter**

In `backend/monitoring/adapters/__init__.py`, add `PostgresObservationSource` and `PostgresObservationStore` to the imports and `__all__` (this fixes the pre-existing gap where `PostgresObservationStore` was not exported). In `backend/monitoring/__init__.py`, add both to the imports from `monitoring.adapters.postgres` and to `__all__`, keeping alphabetical ordering.

- [ ] **Step 5: Run the integration test, pyright, ruff**

Run: `.venv/bin/pytest tests/monitoring/test_postgres_observation_source.py -m integration -v && .venv/bin/pyright && .venv/bin/ruff check monitoring/`
Expected: PASS, clean.

- [ ] **Step 6: Add the test file to pyright include**

In `backend/pyproject.toml`, in `[tool.pyright].include`, insert `"tests/monitoring/test_postgres_observation_source.py"` immediately after `"tests/monitoring/test_postgres_observation_store.py"`.

Run: `.venv/bin/pyright`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add monitoring/adapters/postgres.py monitoring/adapters/__init__.py monitoring/__init__.py pyproject.toml tests/monitoring/test_postgres_observation_source.py
git commit -m "feat(monitoring): add Postgres observation source (read side)"
```

---

### Task 7: `AlertHistoryWriter` protocol, `AlertHistoryRecord` model, in-memory adapter

**Files:**
- Modify: `backend/monitoring/models.py`
- Modify: `backend/monitoring/adapters/protocols.py`
- Modify: `backend/monitoring/adapters/in_memory.py`
- Test: `backend/tests/monitoring/test_alert_history_writer.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/monitoring/test_alert_history_writer.py`:

```python
"""Tests for the in-memory alert-history writer."""

from __future__ import annotations

from datetime import datetime, timezone

from monitoring.adapters.in_memory import InMemoryAlertHistoryWriter
from monitoring.adapters.protocols import AlertHistoryWriter
from monitoring.models import AlertHistoryRecord


def _record(alert_id: str, *, entity_id: str = "claim:c1") -> AlertHistoryRecord:
    return AlertHistoryRecord(
        knowledge_base_id="kb-1",
        alert_id=alert_id,
        entity_id=entity_id,
        entity_type="claim",
        severity="high",
        status="open",
        title="Anomalous claim",
        reasoning="score exceeded threshold",
        metric_name="claim_anomaly",
        created_at=datetime(2026, 5, 16, tzinfo=timezone.utc),
    )


def test_writer_satisfies_protocol() -> None:
    writer: AlertHistoryWriter = InMemoryAlertHistoryWriter()
    assert writer.write_alerts([]) == 0


def test_write_alerts_is_idempotent_per_alert_id() -> None:
    writer = InMemoryAlertHistoryWriter()
    assert writer.write_alerts([_record("a-1")]) == 1
    assert writer.write_alerts([_record("a-1")]) == 0


def test_count_open_alerts_filters_by_entity_and_status() -> None:
    writer = InMemoryAlertHistoryWriter()
    writer.write_alerts([_record("a-1"), _record("a-2")])
    assert writer.count_open_alerts(knowledge_base_id="kb-1", entity_id="claim:c1") == 2
    assert (
        writer.count_open_alerts(knowledge_base_id="kb-1", entity_id="claim:other") == 0
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/monitoring/test_alert_history_writer.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Add `AlertHistoryRecord` to `monitoring/models.py`**

In `backend/monitoring/models.py`, after the `AlertGroup` class, add:

```python
class AlertHistoryRecord(BaseModel):
    """A row destined for the analytics-facing ``alert_history`` log."""

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

Add `"AlertHistoryRecord"` to the module `__all__` (alphabetical — after `"AlertGroup"`).

- [ ] **Step 4: Add the `AlertHistoryWriter` protocol**

In `backend/monitoring/adapters/protocols.py`, add the import `from monitoring.models import AlertHistoryRecord, MonitoringBatch` (extend the existing `MonitoringBatch` import). After the `ObservationWriter` protocol, add:

```python
@runtime_checkable
class AlertHistoryWriter(Protocol):
    """Persist alerts to the analytics-facing ``alert_history`` log."""

    def write_alerts(self, records: list[AlertHistoryRecord]) -> int:
        """Persist alert rows idempotently; return the count of newly written rows."""
        ...

    def count_open_alerts(
        self, *, knowledge_base_id: str, entity_id: str
    ) -> int:
        """Return how many ``open`` alerts the log holds for one entity."""
        ...
```

Add `"AlertHistoryWriter"` to the module `__all__` (alphabetical — first).

- [ ] **Step 5: Add `InMemoryAlertHistoryWriter`**

In `backend/monitoring/adapters/in_memory.py`, add `AlertHistoryRecord` to the `from monitoring.models import ...` line, add `"InMemoryAlertHistoryWriter"` to `__all__`, and append the class:

```python
class InMemoryAlertHistoryWriter:
    """An ``AlertHistoryWriter`` that records alert rows in memory."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], AlertHistoryRecord] = {}

    def write_alerts(self, records: list[AlertHistoryRecord]) -> int:
        written = 0
        for record in records:
            key = (record.knowledge_base_id, record.alert_id)
            if key in self._records:
                continue
            self._records[key] = record
            written += 1
        return written

    def count_open_alerts(
        self, *, knowledge_base_id: str, entity_id: str
    ) -> int:
        return sum(
            1
            for record in self._records.values()
            if record.knowledge_base_id == knowledge_base_id
            and record.entity_id == entity_id
            and record.status == "open"
        )
```

- [ ] **Step 6: Run test, pyright, ruff**

Run: `.venv/bin/pytest tests/monitoring/test_alert_history_writer.py -v && .venv/bin/pyright && .venv/bin/ruff check monitoring/`
Expected: PASS, clean.

- [ ] **Step 7: Add the test file to pyright include and commit**

In `backend/pyproject.toml`, insert `"tests/monitoring/test_alert_history_writer.py"` immediately after `"tests/monitoring/test_observation_writer.py"` in the pyright `include` list.

```bash
git add monitoring/ tests/monitoring/test_alert_history_writer.py pyproject.toml
git commit -m "feat(monitoring): add AlertHistoryWriter protocol and in-memory adapter"
```

---

### Task 8: `PostgresAlertHistoryStore`

**Files:**
- Modify: `backend/monitoring/adapters/postgres.py`
- Modify: `backend/monitoring/adapters/__init__.py`, `backend/monitoring/__init__.py`
- Test: `backend/tests/monitoring/test_postgres_alert_history.py`

- [ ] **Step 1: Write the failing integration test**

Create `backend/tests/monitoring/test_postgres_alert_history.py`:

```python
"""Integration tests for the Postgres alert-history store."""

from __future__ import annotations

import os

import pytest

from config.schema import DatabaseConfig
from database.runtime import create_connection_provider
from monitoring.adapters.postgres import PostgresAlertHistoryStore
from monitoring.models import AlertHistoryRecord

pytestmark = pytest.mark.integration


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set; skipping alert-history test.")
    return url


def _record(alert_id: str) -> AlertHistoryRecord:
    return AlertHistoryRecord(
        knowledge_base_id="kb-alert-test",
        alert_id=alert_id,
        entity_id="claim:c1",
        entity_type="claim",
        severity="high",
        status="open",
        title="Anomalous claim",
        reasoning="score exceeded threshold",
        metric_name="claim_anomaly",
    )


def test_write_and_count_round_trip(database_url: str) -> None:
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    store = PostgresAlertHistoryStore(provider)
    try:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM alert_history WHERE knowledge_base_id = 'kb-alert-test'"
            )
            conn.commit()

        assert store.write_alerts([]) == 0
        assert store.write_alerts([_record("a-1"), _record("a-2")]) == 2
        # Idempotent on (knowledge_base_id, alert_id).
        assert store.write_alerts([_record("a-1")]) == 0
        assert (
            store.count_open_alerts(
                knowledge_base_id="kb-alert-test", entity_id="claim:c1"
            )
            == 2
        )
    finally:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM alert_history WHERE knowledge_base_id = 'kb-alert-test'"
            )
            conn.commit()
        provider.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/monitoring/test_postgres_alert_history.py -m integration -v`
Expected: FAIL — `ImportError: cannot import name 'PostgresAlertHistoryStore'`.

- [ ] **Step 3: Add `PostgresAlertHistoryStore` to `monitoring/adapters/postgres.py`**

Extend the `monitoring.models` import to include `AlertHistoryRecord`. After `_SELECT_BATCH_SQL`, add:

```python
_ALERT_INSERT_SQL = """
    INSERT INTO alert_history (
        knowledge_base_id, alert_id, entity_id, entity_type, severity, status,
        title, reasoning, metric_name, evidence_pack_id, created_at, updated_at
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (knowledge_base_id, alert_id) DO NOTHING
"""

_ALERT_COUNT_OPEN_SQL = """
    SELECT count(*) FROM alert_history
    WHERE knowledge_base_id = %s AND entity_id = %s AND status = 'open'
"""
```

After the `PostgresObservationSource` class and `_row_to_observation`, add:

```python
class PostgresAlertHistoryStore:
    """An ``AlertHistoryWriter`` backed by the ``alert_history`` table."""

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def write_alerts(self, records: list[AlertHistoryRecord]) -> int:
        if not records:
            return 0
        written = 0
        try:
            with self._provider.connection() as conn:
                for record in records:
                    cursor = conn.execute(
                        _ALERT_INSERT_SQL,
                        (
                            record.knowledge_base_id,
                            record.alert_id,
                            record.entity_id,
                            record.entity_type,
                            record.severity,
                            record.status,
                            record.title,
                            record.reasoning,
                            record.metric_name,
                            record.evidence_pack_id,
                            record.created_at,
                            record.updated_at,
                        ),
                    )
                    written += cursor.rowcount
                conn.commit()
        except Exception as exc:
            raise MonitoringSourceError("Failed to write alert history.") from exc
        return written

    def count_open_alerts(
        self, *, knowledge_base_id: str, entity_id: str
    ) -> int:
        try:
            with self._provider.connection() as conn:
                row = conn.execute(
                    _ALERT_COUNT_OPEN_SQL, (knowledge_base_id, entity_id)
                ).fetchone()
        except Exception as exc:
            raise MonitoringSourceError("Failed to count open alerts.") from exc
        return 0 if row is None else int(cast(int, row[0]))
```

Update the module `__all__` to include `"PostgresAlertHistoryStore"` (alphabetical).

- [ ] **Step 4: Export the new adapter**

Add `PostgresAlertHistoryStore` to `monitoring/adapters/__init__.py` and `monitoring/__init__.py` imports and `__all__`.

- [ ] **Step 5: Run the integration test, pyright, ruff**

Run: `.venv/bin/pytest tests/monitoring/test_postgres_alert_history.py -m integration -v && .venv/bin/pyright && .venv/bin/ruff check monitoring/`
Expected: PASS, clean.

- [ ] **Step 6: Add the test to pyright include and commit**

Insert `"tests/monitoring/test_postgres_alert_history.py"` into the pyright `include` list (after `test_postgres_alert_history` belongs alphabetically near the other `tests/monitoring` entries).

```bash
git add monitoring/ pyproject.toml tests/monitoring/test_postgres_alert_history.py
git commit -m "feat(monitoring): add Postgres alert-history store"
```

---

## Phase 4 — Time-series read-side adapter

### Task 9: `PostgresTimeSeriesHistorySource`

**Files:**
- Create: `backend/analytics/timeseries/adapters/postgres.py`
- Modify: `backend/analytics/timeseries/adapters/__init__.py`, `backend/analytics/timeseries/__init__.py`
- Test: `backend/tests/analytics/timeseries/test_postgres_history_source.py`

- [ ] **Step 1: Write the failing integration test**

Create `backend/tests/analytics/timeseries/test_postgres_history_source.py`:

```python
"""Integration tests for the Postgres time-series history source."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from analytics.metrics.adapters.postgres import PostgresEntityMetricRepository
from analytics.metrics.models import EntityMetricSample
from analytics.timeseries.adapters.postgres import PostgresTimeSeriesHistorySource
from config.schema import DatabaseConfig
from database.runtime import create_connection_provider

pytestmark = pytest.mark.integration


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set; skipping timeseries source test.")
    return url


def test_load_series_and_metric_range(database_url: str) -> None:
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    repo = PostgresEntityMetricRepository(provider)
    source = PostgresTimeSeriesHistorySource(provider)
    base = datetime(2026, 5, 16, 12, 0, 0, tzinfo=timezone.utc)
    try:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM entity_metric_history "
                "WHERE knowledge_base_id = 'kb-ts-test'"
            )
            conn.execute(
                "DELETE FROM entity_metrics_current "
                "WHERE knowledge_base_id = 'kb-ts-test'"
            )
            conn.commit()

        repo.record_metrics(
            [
                EntityMetricSample(
                    knowledge_base_id="kb-ts-test",
                    entity_id="__graph__",
                    metric_name="entity_count",
                    value=float(index),
                    observed_at=base + timedelta(minutes=index),
                    correlation_id=f"corr-{index}",
                )
                for index in range(3)
            ]
        )

        series = source.load_series(
            knowledge_base_id="kb-ts-test",
            entity_id="__graph__",
            metric_name="entity_count",
        )
        assert [obs.value for obs in series.observations] == [0.0, 1.0, 2.0]

        window = source.load_metric_range(
            knowledge_base_id="kb-ts-test",
            metric_name="entity_count",
            start=base,
            end=base + timedelta(minutes=1),
        )
        assert [obs.value for obs in window] == [0.0, 1.0]
    finally:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM entity_metric_history "
                "WHERE knowledge_base_id = 'kb-ts-test'"
            )
            conn.execute(
                "DELETE FROM entity_metrics_current "
                "WHERE knowledge_base_id = 'kb-ts-test'"
            )
            conn.commit()
        provider.close()


def test_load_series_unknown_raises_value_error(database_url: str) -> None:
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    source = PostgresTimeSeriesHistorySource(provider)
    try:
        with pytest.raises(ValueError, match="No time series"):
            source.load_series(
                knowledge_base_id="kb-missing",
                entity_id="e-missing",
                metric_name="entity_count",
            )
    finally:
        provider.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/analytics/timeseries/test_postgres_history_source.py -m integration -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create `analytics/timeseries/adapters/postgres.py`**

```python
"""Postgres-backed time-series history source.

Reads the ``entity_metric_history`` hypertable that Flow 2 populates with
graph metrics over time. Depends only on the psycopg-free
``database.ConnectionProvider`` protocol.
"""

from __future__ import annotations

from datetime import datetime
from typing import cast

from analytics.timeseries.exceptions import TimeseriesSourceError
from analytics.timeseries.models import TimeSeriesObservation, TimeSeriesSeries
from database.protocols import ConnectionProvider, Row

_SERIES_SQL = """
    SELECT observed_at, value
    FROM entity_metric_history
    WHERE knowledge_base_id = %s AND entity_id = %s AND metric_name = %s
    ORDER BY observed_at
"""

_RANGE_SQL = """
    SELECT observed_at, value
    FROM entity_metric_history
    WHERE knowledge_base_id = %s AND metric_name = %s
      AND observed_at >= %s AND observed_at <= %s
    ORDER BY observed_at
"""


class PostgresTimeSeriesHistorySource:
    """A ``TimeSeriesHistorySourceProtocol`` backed by ``entity_metric_history``."""

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def load_series(
        self,
        *,
        knowledge_base_id: str,
        entity_id: str,
        metric_name: str,
    ) -> TimeSeriesSeries:
        try:
            with self._provider.connection() as conn:
                rows = conn.execute(
                    _SERIES_SQL, (knowledge_base_id, entity_id, metric_name)
                ).fetchall()
        except Exception as exc:
            raise TimeseriesSourceError("Failed to load time-series history.") from exc
        if not rows:
            raise ValueError(
                "No time series registered for "
                f"knowledge_base_id='{knowledge_base_id}', "
                f"entity_id='{entity_id}', metric_name='{metric_name}'."
            )
        return TimeSeriesSeries(
            knowledge_base_id=knowledge_base_id,
            entity_id=entity_id,
            metric_name=metric_name,
            observations=[_row_to_observation(row) for row in rows],
        )

    def load_metric_range(
        self,
        *,
        knowledge_base_id: str,
        metric_name: str,
        start: datetime,
        end: datetime,
    ) -> list[TimeSeriesObservation]:
        try:
            with self._provider.connection() as conn:
                rows = conn.execute(
                    _RANGE_SQL, (knowledge_base_id, metric_name, start, end)
                ).fetchall()
        except Exception as exc:
            raise TimeseriesSourceError("Failed to load metric range.") from exc
        return [_row_to_observation(row) for row in rows]


def _row_to_observation(row: Row) -> TimeSeriesObservation:
    return TimeSeriesObservation(
        observed_at=cast(datetime, row[0]),
        value=float(cast(float, row[1])),
    )


__all__ = [
    "PostgresTimeSeriesHistorySource",
]
```

- [ ] **Step 4: Export the adapter**

Add `PostgresTimeSeriesHistorySource` to `backend/analytics/timeseries/adapters/__init__.py` and `backend/analytics/timeseries/__init__.py` imports and `__all__` (alphabetical).

- [ ] **Step 5: Run the integration test, pyright, ruff**

Run: `.venv/bin/pytest tests/analytics/timeseries/test_postgres_history_source.py -m integration -v && .venv/bin/pyright && .venv/bin/ruff check analytics/timeseries/`
Expected: PASS, clean. (`analytics/timeseries` and `tests/analytics/timeseries` are already in the pyright `include` list, so no `pyproject.toml` change is needed here.)

- [ ] **Step 6: Commit**

```bash
git add analytics/timeseries/ tests/analytics/timeseries/test_postgres_history_source.py
git commit -m "feat(timeseries): add Postgres time-series history source"
```

---

## Phase 5 — Risk history writer and store

### Task 10: `RiskHistoryWriter` protocol, `RiskAssessmentRecord`, in-memory adapter

**Files:**
- Modify: `backend/analytics/risk/models.py`
- Modify: `backend/analytics/risk/exceptions.py`
- Modify: `backend/analytics/risk/adapters/protocols.py`
- Modify: `backend/analytics/risk/adapters/in_memory.py`
- Modify: `backend/pyproject.toml`
- Test: `backend/tests/analytics/risk/test_history_writer.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/analytics/risk/test_history_writer.py`:

```python
"""Tests for the in-memory risk-history writer."""

from __future__ import annotations

from datetime import datetime, timezone

from analytics.risk.adapters.in_memory import InMemoryRiskHistoryWriter
from analytics.risk.adapters.protocols import RiskHistoryWriter
from analytics.risk.models import RiskAssessmentRecord, RiskFactor


def _record(request_id: str, *, score: float, entity_id: str = "claim:c1") -> RiskAssessmentRecord:
    return RiskAssessmentRecord(
        knowledge_base_id="kb-1",
        entity_id=entity_id,
        request_id=request_id,
        overall_score=score,
        risk_level="high",
        factors=[
            RiskFactor(
                factor_name="anomaly",
                raw_value=0.9,
                weight=1.0,
                contribution=0.9,
            )
        ],
        assessed_at=datetime(2026, 5, 16, tzinfo=timezone.utc),
    )


def test_writer_satisfies_protocol() -> None:
    writer: RiskHistoryWriter = InMemoryRiskHistoryWriter()
    assert writer.load_historical_score(knowledge_base_id="kb-x", entity_id="e-x") is None


def test_write_assessment_is_idempotent_per_request_id() -> None:
    writer = InMemoryRiskHistoryWriter()
    assert writer.write_assessment(_record("req-1", score=0.7)) is True
    assert writer.write_assessment(_record("req-1", score=0.7)) is False


def test_load_historical_score_returns_latest() -> None:
    writer = InMemoryRiskHistoryWriter()
    writer.write_assessment(
        _record("req-1", score=0.4)
    )
    later = _record("req-2", score=0.8)
    later = later.model_copy(
        update={"assessed_at": datetime(2026, 5, 17, tzinfo=timezone.utc)}
    )
    writer.write_assessment(later)
    assert (
        writer.load_historical_score(knowledge_base_id="kb-1", entity_id="claim:c1")
        == 0.8
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/analytics/risk/test_history_writer.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Add `RiskAssessmentRecord` to `analytics/risk/models.py`**

After the `RankedRiskEntry` class, add (the file already imports `datetime`? — it does not; add `from datetime import datetime` to the imports and `from shared.utils import utc_now`):

```python
class RiskAssessmentRecord(BaseModel):
    """A row destined for the analytics-facing ``risk_score_history`` log."""

    knowledge_base_id: str
    entity_id: str
    request_id: str
    overall_score: float = Field(ge=0.0, le=1.0)
    risk_level: str
    factors: list[RiskFactor] = Field(default_factory=list)
    assessed_at: datetime = Field(default_factory=utc_now)
```

Add `"RiskAssessmentRecord"` to the module `__all__` (alphabetical — before `"RiskFactor"`).

- [ ] **Step 4: Add `RiskHistoryError`**

In `backend/analytics/risk/exceptions.py`, after `RiskSourceError`, add:

```python
class RiskHistoryError(RiskError):
    """Raised when the risk-history store cannot read or write assessments."""
```

Add `"RiskHistoryError"` to `__all__` (alphabetical — after `"RiskError"`).

- [ ] **Step 5: Add the `RiskHistoryWriter` protocol**

In `backend/analytics/risk/adapters/protocols.py`, extend the model import to `from analytics.risk.models import RankedRiskEntry, RiskAssessmentRecord, RiskProfile` and append:

```python
@runtime_checkable
class RiskHistoryWriter(Protocol):
    """Persist risk assessments to the ``risk_score_history`` log.

    The Postgres implementation also exposes a latest-score read so Flow 3
    closes its own loop; full ``RiskSignalSourceProtocol`` backing is out of
    scope (signals are graph-derived — see design §1).
    """

    def write_assessment(self, record: RiskAssessmentRecord) -> bool:
        """Persist one assessment idempotently; return True if a row was written."""
        ...

    def load_historical_score(
        self, *, knowledge_base_id: str, entity_id: str
    ) -> float | None:
        """Return the most recent overall risk score for one entity, if any."""
        ...
```

Add `"RiskHistoryWriter"` to `__all__` (alphabetical — first).

- [ ] **Step 6: Add `InMemoryRiskHistoryWriter`**

In `backend/analytics/risk/adapters/in_memory.py`, extend the model import to include `RiskAssessmentRecord`, add `"InMemoryRiskHistoryWriter"` to `__all__`, and append:

```python
class InMemoryRiskHistoryWriter:
    """A ``RiskHistoryWriter`` that records assessments in memory."""

    def __init__(self) -> None:
        self._records: dict[str, RiskAssessmentRecord] = {}

    def write_assessment(self, record: RiskAssessmentRecord) -> bool:
        if record.request_id in self._records:
            return False
        self._records[record.request_id] = record
        return True

    def load_historical_score(
        self, *, knowledge_base_id: str, entity_id: str
    ) -> float | None:
        matches = [
            record
            for record in self._records.values()
            if record.knowledge_base_id == knowledge_base_id
            and record.entity_id == entity_id
        ]
        if not matches:
            return None
        latest = max(matches, key=lambda record: record.assessed_at)
        return latest.overall_score
```

- [ ] **Step 7: Add `analytics/risk` to pyright include**

In `backend/pyproject.toml`, in `[tool.pyright].include`, insert `"analytics/risk"` immediately after `"analytics/metrics"`, and `"tests/analytics/risk"` immediately after `"tests/analytics/metrics"`.

- [ ] **Step 8: Run tests, pyright, ruff**

Run: `.venv/bin/pytest tests/analytics/risk/ -v && .venv/bin/pyright && .venv/bin/ruff check analytics/risk/`
Expected: PASS, clean. If pyright surfaces strict errors in pre-existing `analytics/risk` files, fix each one properly (CLAUDE.md forbids suppression) before committing.

- [ ] **Step 9: Commit**

```bash
git add analytics/risk/ tests/analytics/risk/test_history_writer.py pyproject.toml
git commit -m "feat(risk): add RiskHistoryWriter protocol and in-memory adapter"
```

---

### Task 11: `PostgresRiskHistoryStore`

**Files:**
- Create: `backend/analytics/risk/adapters/postgres.py`
- Modify: `backend/analytics/risk/adapters/__init__.py`, `backend/analytics/risk/__init__.py`
- Test: `backend/tests/analytics/risk/test_postgres_history_store.py`

- [ ] **Step 1: Write the failing integration test**

Create `backend/tests/analytics/risk/test_postgres_history_store.py`:

```python
"""Integration tests for the Postgres risk-history store."""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from analytics.risk.adapters.postgres import PostgresRiskHistoryStore
from analytics.risk.models import RiskAssessmentRecord, RiskFactor
from config.schema import DatabaseConfig
from database.runtime import create_connection_provider

pytestmark = pytest.mark.integration


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set; skipping risk-history test.")
    return url


def _record(request_id: str, *, score: float, assessed_at: datetime) -> RiskAssessmentRecord:
    return RiskAssessmentRecord(
        knowledge_base_id="kb-risk-test",
        entity_id="claim:c1",
        request_id=request_id,
        overall_score=score,
        risk_level="high",
        factors=[
            RiskFactor(
                factor_name="anomaly",
                raw_value=0.9,
                weight=1.0,
                contribution=score,
                rationale="integration test",
            )
        ],
        assessed_at=assessed_at,
    )


def test_write_and_load_latest_score(database_url: str) -> None:
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    store = PostgresRiskHistoryStore(provider)
    try:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM risk_score_history "
                "WHERE knowledge_base_id = 'kb-risk-test'"
            )
            conn.commit()

        first = _record(
            "req-risk-1", score=0.4,
            assessed_at=datetime(2026, 5, 16, tzinfo=timezone.utc),
        )
        second = _record(
            "req-risk-2", score=0.8,
            assessed_at=datetime(2026, 5, 17, tzinfo=timezone.utc),
        )
        assert store.write_assessment(first) is True
        # Idempotent on request_id.
        assert store.write_assessment(first) is False
        assert store.write_assessment(second) is True

        assert (
            store.load_historical_score(
                knowledge_base_id="kb-risk-test", entity_id="claim:c1"
            )
            == 0.8
        )
        assert (
            store.load_historical_score(
                knowledge_base_id="kb-risk-test", entity_id="claim:absent"
            )
            is None
        )
    finally:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM risk_score_history "
                "WHERE knowledge_base_id = 'kb-risk-test'"
            )
            conn.commit()
        provider.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/analytics/risk/test_postgres_history_store.py -m integration -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create `analytics/risk/adapters/postgres.py`**

```python
"""Postgres-backed risk-history store.

Writes the ``risk_score_history`` table and exposes the latest score per
entity. Depends only on the psycopg-free ``database.ConnectionProvider``
protocol. The ``factors`` jsonb column is written via an explicit ``::jsonb``
cast over serialized JSON.
"""

from __future__ import annotations

import json

from analytics.risk.exceptions import RiskHistoryError
from analytics.risk.models import RiskAssessmentRecord, RiskFactor
from database.protocols import ConnectionProvider

_INSERT_SQL = """
    INSERT INTO risk_score_history (
        knowledge_base_id, entity_id, request_id, overall_score,
        risk_level, factors, assessed_at
    ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)
    ON CONFLICT (request_id) DO NOTHING
"""

_LATEST_SCORE_SQL = """
    SELECT overall_score
    FROM risk_score_history
    WHERE knowledge_base_id = %s AND entity_id = %s
    ORDER BY assessed_at DESC
    LIMIT 1
"""


def _factor_to_dict(factor: RiskFactor) -> dict[str, object]:
    return {
        "factor_name": factor.factor_name,
        "raw_value": factor.raw_value,
        "weight": factor.weight,
        "contribution": factor.contribution,
        "rationale": factor.rationale,
    }


class PostgresRiskHistoryStore:
    """A ``RiskHistoryWriter`` backed by the ``risk_score_history`` table."""

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def write_assessment(self, record: RiskAssessmentRecord) -> bool:
        factors_json = json.dumps(
            [_factor_to_dict(factor) for factor in record.factors], default=str
        )
        try:
            with self._provider.connection() as conn:
                cursor = conn.execute(
                    _INSERT_SQL,
                    (
                        record.knowledge_base_id,
                        record.entity_id,
                        record.request_id,
                        record.overall_score,
                        record.risk_level,
                        factors_json,
                        record.assessed_at,
                    ),
                )
                written = cursor.rowcount
                conn.commit()
        except Exception as exc:
            raise RiskHistoryError("Failed to write risk assessment.") from exc
        return written > 0

    def load_historical_score(
        self, *, knowledge_base_id: str, entity_id: str
    ) -> float | None:
        try:
            with self._provider.connection() as conn:
                row = conn.execute(
                    _LATEST_SCORE_SQL, (knowledge_base_id, entity_id)
                ).fetchone()
        except Exception as exc:
            raise RiskHistoryError("Failed to load historical risk score.") from exc
        if row is None:
            return None
        return float(row[0])  # type: ignore[arg-type]
```

Note: replace the `# type: ignore` line above with a clean cast — `from typing import cast` and `return float(cast(float, row[0]))` — to satisfy `pyright --strict` and the no-suppression rule. (The `cast` is the correct form; the `type: ignore` shown is a placeholder reminder only — do not leave it in.)

Final form of that import/return:

```python
from typing import cast
...
        if row is None:
            return None
        return float(cast(float, row[0]))
```

Add the module `__all__`:

```python
__all__ = [
    "PostgresRiskHistoryStore",
]
```

- [ ] **Step 4: Export the adapter**

Add `PostgresRiskHistoryStore` to `backend/analytics/risk/adapters/__init__.py` and `backend/analytics/risk/__init__.py` imports and `__all__` (alphabetical).

- [ ] **Step 5: Run the integration test, pyright, ruff**

Run: `.venv/bin/pytest tests/analytics/risk/test_postgres_history_store.py -m integration -v && .venv/bin/pyright && .venv/bin/ruff check analytics/risk/`
Expected: PASS, clean.

- [ ] **Step 6: Commit**

```bash
git add analytics/risk/ tests/analytics/risk/test_postgres_history_store.py
git commit -m "feat(risk): add Postgres risk-history store"
```

---

## Phase 6 — Event reference enrichment

### Task 12: `RiskScoredReference.factors`

**Files:**
- Modify: `backend/events/types.py`
- Modify: `backend/analytics/risk/service.py`
- Test: `backend/tests/events/test_types.py`, `backend/tests/analytics/risk/test_service.py`

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/events/test_types.py`:

```python
def test_risk_scored_reference_carries_factors() -> None:
    from events.types import RiskFactorReference, RiskScoredReference

    reference = RiskScoredReference(
        knowledge_base_id="kb-1",
        request_id="req-1",
        entity_id="claim:c1",
        overall_score=0.8,
        risk_level="high",
        factor_count=1,
        factors=[
            RiskFactorReference(
                factor_name="anomaly",
                raw_value=0.9,
                weight=1.0,
                contribution=0.8,
            )
        ],
    )
    assert reference.factors[0].factor_name == "anomaly"


def test_risk_scored_reference_factors_default_empty() -> None:
    from events.types import RiskScoredReference

    reference = RiskScoredReference(
        knowledge_base_id="kb-1",
        request_id="req-1",
        entity_id="claim:c1",
        overall_score=0.8,
        risk_level="high",
        factor_count=0,
    )
    assert reference.factors == []
```

Add to `backend/tests/analytics/risk/test_service.py` (a profile with ≥2 signals is required by `RiskProfile`; reuse the module's existing profile-builder helper if present, otherwise build inline):

```python
def test_assess_publishes_factors_on_risk_scored_event() -> None:
    from analytics.risk.adapters.in_memory import InMemoryRiskSignalSource
    from analytics.risk.models import RiskProfile, RiskSignal
    from analytics.risk.service import create_risk_service
    from analytics.risk.service_models import RiskAssessmentRequest
    from events.adapters.in_memory import InMemoryEventBus
    from events.types import RiskScoredEvent

    profile = RiskProfile(
        knowledge_base_id="kb-1",
        entity_id="claim:c1",
        signals=[
            RiskSignal(signal_name="anomaly", value=0.9, weight=1.0),
            RiskSignal(signal_name="volume", value=0.4, weight=1.0),
        ],
    )
    event_bus = InMemoryEventBus()
    service = create_risk_service(
        InMemoryRiskSignalSource(profiles=[profile]), event_bus=event_bus
    )
    service.assess(
        RiskAssessmentRequest(knowledge_base_id="kb-1", entity_id="claim:c1")
    )
    published = [e for e in event_bus.published_events if isinstance(e, RiskScoredEvent)]
    assert len(published) == 1
    assert len(published[0].assessments[0].factors) == 2
```

(If `InMemoryEventBus.published_events` is named differently, use the attribute the existing risk service tests already assert on.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/events/test_types.py -k risk_scored_reference tests/analytics/risk/test_service.py -k factors -v`
Expected: FAIL — `ImportError` on `RiskFactorReference` / missing `factors`.

- [ ] **Step 3: Add `RiskFactorReference` and the `factors` field**

In `backend/events/types.py`, immediately before the `RiskScoredReference` class, add:

```python
class RiskFactorReference(BaseModel):
    """A single weighted risk factor carried on a RiskScoredReference."""

    factor_name: str
    raw_value: float = Field(ge=0.0, le=1.0)
    weight: float = Field(gt=0.0)
    contribution: float = Field(ge=0.0, le=1.0)
    rationale: str | None = None
```

In `RiskScoredReference`, after the `factor_count` field, add:

```python
    factors: list[RiskFactorReference] = Field(
        default_factory=lambda: list[RiskFactorReference]()
    )
```

Add `"RiskFactorReference"` to the module `__all__` (alphabetical).

- [ ] **Step 4: Populate `factors` in `RiskService.assess`**

In `backend/analytics/risk/service.py`, extend the `events.types` import to include `RiskFactorReference`. In `assess()`, change the `RiskScoredReference(...)` construction inside the `RiskScoredEvent` publish so it adds:

```python
                        factors=[
                            RiskFactorReference(
                                factor_name=factor.factor_name,
                                raw_value=factor.raw_value,
                                weight=factor.weight,
                                contribution=factor.contribution,
                                rationale=factor.rationale,
                            )
                            for factor in response.factors
                        ],
```

(`response.factors` is a `list[RiskFactorScore]`, which has exactly these five fields.)

- [ ] **Step 5: Run tests, pyright, ruff**

Run: `.venv/bin/pytest tests/events/ tests/analytics/risk/ -v && .venv/bin/pyright && .venv/bin/ruff check events/ analytics/risk/`
Expected: PASS, clean.

- [ ] **Step 6: Commit**

```bash
git add events/types.py analytics/risk/service.py tests/events/test_types.py tests/analytics/risk/test_service.py
git commit -m "feat(events): carry risk factors on RiskScoredReference"
```

---

### Task 13: `AlertCreatedReference` enrichment

**Files:**
- Modify: `backend/events/types.py`
- Modify: `backend/monitoring/service.py`
- Modify: `backend/agent/coordinator.py` (`_run_explainability_stage`)
- Test: `backend/tests/events/test_types.py`, `backend/tests/monitoring/test_service.py`

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/events/test_types.py`:

```python
def test_alert_created_reference_new_fields_default() -> None:
    from events.types import AlertCreatedReference

    reference = AlertCreatedReference(
        knowledge_base_id="kb-1",
        alert_id="a-1",
        entity_id="claim:c1",
        severity="high",
    )
    assert reference.entity_type == ""
    assert reference.status == "open"
    assert reference.title == ""
    assert reference.reasoning == ""
    assert reference.metric_name == ""
```

Add to `backend/tests/monitoring/test_service.py` a test asserting that, after `evaluate()` produces alerts, the published `AlertsCreatedEvent`'s references carry the alert's `entity_type`, `title`, `reasoning`, `status`, and the candidate's `metric_name`. Model it on the existing monitoring-service test that already asserts an `AlertsCreatedEvent` is published — extend that test (or add a sibling) to check `reference.metric_name` and `reference.title` are non-empty.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/events/test_types.py -k alert_created_reference tests/monitoring/test_service.py -v`
Expected: FAIL — missing fields on `AlertCreatedReference`.

- [ ] **Step 3: Add the new fields to `AlertCreatedReference`**

In `backend/events/types.py`, in the `AlertCreatedReference` class, after the `evidence_pack_id` field, add:

```python
    entity_type: str = ""
    status: str = "open"
    title: str = ""
    reasoning: str = ""
    metric_name: str = ""
```

- [ ] **Step 4: Populate the fields in `MonitoringService.evaluate`**

In `backend/monitoring/service.py`, in `evaluate()`, the `AlertsCreatedEvent` publish currently builds one `AlertCreatedReference` per `alert`. Replace that comprehension so it zips the parallel `deduped` (candidates) and `alerts` lists and populates the new fields:

```python
        if alerts:
            self._event_bus.publish(
                AlertsCreatedEvent(
                    alerts=[
                        AlertCreatedReference(
                            knowledge_base_id=request.knowledge_base_id,
                            alert_id=alert.id,
                            entity_id=alert.entity_id,
                            severity=alert.severity,
                            evidence_pack_id=alert.evidence_pack_id,
                            entity_type=alert.entity_type,
                            status=alert.status,
                            title=alert.title,
                            reasoning=alert.reasoning,
                            metric_name=candidate.metric_name,
                        )
                        for candidate, alert in zip(deduped, alerts, strict=True)
                    ]
                )
            )
```

(`deduped` is the `list[AlertCandidate]` and `alerts` is `[_to_alert(candidate, ...) for candidate in deduped]`, so the two lists are positionally aligned; `strict=True` enforces that.)

- [ ] **Step 5: Populate the fields in the Flow B explainability builder**

In `backend/agent/coordinator.py`, `_run_explainability_stage` builds an `AlertCreatedReference`. Update its return so it also passes a synthesized `title` and `reasoning` (entity_type / metric_name stay at their defaults — Flow B does not resolve them):

```python
    return AlertCreatedReference(
        knowledge_base_id=knowledge_base_id,
        alert_id=response.alert_id,
        entity_id=entity_id,
        severity=risk_response.risk_level,
        evidence_pack_id=response.evidence_pack.id,
        status="open",
        title=f"{risk_response.risk_level.title()} risk: {entity_id}",
        reasoning=response.evidence_pack.reasoning,
    )
```

(`EvidencePack` has a `reasoning` field — confirmed in `shared/types.py`.)

- [ ] **Step 6: Run tests, pyright, ruff**

Run: `.venv/bin/pytest tests/events/ tests/monitoring/ tests/agent/ -v && .venv/bin/pyright && .venv/bin/ruff check events/ monitoring/ agent/`
Expected: PASS, clean.

- [ ] **Step 7: Commit**

```bash
git add events/types.py monitoring/service.py agent/coordinator.py tests/
git commit -m "feat(events): enrich AlertCreatedReference for the alert-history log"
```

---

## Phase 7 — Worker handlers and wiring

> All edits in this phase are to `backend/agent/coordinator.py`. The file is the worker composition root; verbatim anchors for every edit are given.

### Task 14: New imports, `WorkerDependencies` fields, and `build_*` selectors

**Files:**
- Modify: `backend/agent/coordinator.py`

- [ ] **Step 1: Add the new imports**

Extend the `config.schema` import block to include `AnalyticsConfig` (insert alphabetically before `DatabaseConfig`).

After the existing `from analytics.risk... import ...` block, add:

```python
from analytics.metrics.adapters.in_memory import InMemoryEntityMetricRepository
from analytics.metrics.adapters.postgres import PostgresEntityMetricRepository
from analytics.metrics.adapters.protocols import EntityMetricRepository
from analytics.metrics.models import (
    GRAPH_SCOPE_ENTITY_ID,
    METRIC_AVG_DEGREE,
    METRIC_ENTITY_COUNT,
    METRIC_RELATIONSHIP_COUNT,
    EntityMetricSample,
)
from analytics.metrics.throttle import MetricsRecomputeThrottle
from analytics.risk.adapters.in_memory import InMemoryRiskHistoryWriter
from analytics.risk.adapters.postgres import PostgresRiskHistoryStore
from analytics.risk.adapters.protocols import RiskHistoryWriter
from analytics.risk.models import RiskAssessmentRecord, RiskFactor
```

(`InMemoryRiskSignalSource` / `RiskSignalSourceProtocol` are already imported by Plan B — leave those import lines unchanged.)

Extend the `monitoring.adapters.in_memory` import to add `InMemoryAlertHistoryWriter`; extend `monitoring.adapters.postgres` to add `PostgresAlertHistoryStore` and `PostgresObservationSource`; extend `monitoring.adapters.protocols` to add `AlertHistoryWriter`; extend `monitoring.models` to add `AlertHistoryRecord`. The resulting blocks read:

```python
from monitoring.adapters.in_memory import (
    InMemoryAlertHistoryWriter,
    InMemoryObservationSource,
    InMemoryObservationWriter,
)
from monitoring.adapters.postgres import (
    PostgresAlertHistoryStore,
    PostgresObservationSource,
    PostgresObservationStore,
)
from monitoring.adapters.protocols import (
    AlertHistoryWriter,
    ObservationSourceProtocol,
    ObservationWriter,
)
from monitoring.exceptions import MonitoringError
from monitoring.models import AlertHistoryRecord, MonitoringBatch
```

- [ ] **Step 2: Add the new `__all__` entries**

In the module `__all__`, add (preserving the existing alphabetical order): `"build_alert_history_writer"`, `"build_entity_metric_repository"`, `"build_risk_history_writer"`, `"handle_alerts_created_for_graph"`, `"handle_risk_scored_for_graph"`.

- [ ] **Step 3: Add the new `WorkerDependencies` fields**

In the `WorkerDependencies` dataclass, after the `observation_writer: ObservationWriter` line, add:

```python
    entity_metric_repository: EntityMetricRepository
    metrics_throttle: MetricsRecomputeThrottle
    risk_history_writer: RiskHistoryWriter
    alert_history_writer: AlertHistoryWriter
```

- [ ] **Step 4: Rewrite `build_monitoring_observation_source` to select Postgres**

Replace the existing `build_monitoring_observation_source` function:

```python
def build_monitoring_observation_source(
    _config: DomainConfig,
) -> ObservationSourceProtocol:
    """Return the configured monitoring observation source adapter."""

    return InMemoryObservationSource()
```

with:

```python
def build_monitoring_observation_source(
    provider: ConnectionProvider | None,
) -> ObservationSourceProtocol:
    """Select a monitoring observation source: Postgres when a provider exists."""

    if provider is None:
        return InMemoryObservationSource()
    return PostgresObservationSource(provider)
```

- [ ] **Step 5: Add the three new `build_*` selectors**

Immediately after `build_observation_writer` (ends with `return PostgresObservationStore(provider)`), add:

```python
def build_entity_metric_repository(
    provider: ConnectionProvider | None,
) -> EntityMetricRepository:
    """Select an entity-metric repository: Postgres when a provider exists."""

    if provider is None:
        return InMemoryEntityMetricRepository()
    return PostgresEntityMetricRepository(provider)


def build_risk_history_writer(
    provider: ConnectionProvider | None,
) -> RiskHistoryWriter:
    """Select a risk-history writer: Postgres when a provider exists."""

    if provider is None:
        return InMemoryRiskHistoryWriter()
    return PostgresRiskHistoryStore(provider)


def build_alert_history_writer(
    provider: ConnectionProvider | None,
) -> AlertHistoryWriter:
    """Select an alert-history writer: Postgres when a provider exists."""

    if provider is None:
        return InMemoryAlertHistoryWriter()
    return PostgresAlertHistoryStore(provider)
```

- [ ] **Step 6: Run pyright and ruff**

Run: `.venv/bin/pyright && .venv/bin/ruff check agent/`
Expected: clean. (`build_worker_dependencies` will not yet construct the new `WorkerDependencies` fields — that is Task 15; pyright flags the missing arguments. To keep this task independently green, do Steps 1–6 and Task 15's Step 1 in one commit, or accept that pyright is red until Task 15. **Recommended:** treat Tasks 14 + 15 as a single commit boundary — implement both, then run checks once.)

- [ ] **Step 7: Proceed to Task 15 before committing**

Do not commit yet; Task 15 completes the composition root so the module type-checks.

---

### Task 15: Assemble the new dependencies in `build_worker_dependencies`

**Files:**
- Modify: `backend/agent/coordinator.py`

- [ ] **Step 1: Reorder and extend the dependency assembly**

In `build_worker_dependencies`, the current block reads:

```python
    monitoring_config = config.monitoring
    monitoring_service = create_monitoring_service(
        build_monitoring_observation_source(config),
        event_bus=event_bus,
        dedup_window_seconds=(
            monitoring_config.dedup_window_seconds
            if monitoring_config is not None
            else 3600
        ),
        max_alerts_per_evaluation=(
            monitoring_config.max_alerts_per_evaluation
            if monitoring_config is not None
            else 100
        ),
        grouping_window_seconds=(
            monitoring_config.grouping_window_seconds
            if monitoring_config is not None
            else 300
        ),
    )
    connection_provider = build_connection_provider(config)
    raw_record_store = build_raw_record_store(connection_provider)
    observation_writer = build_observation_writer(connection_provider)
    records_config = config.records or RecordsConfig()
```

Replace it with (the `connection_provider` is built first so the monitoring source can use it):

```python
    connection_provider = build_connection_provider(config)
    monitoring_config = config.monitoring
    monitoring_service = create_monitoring_service(
        build_monitoring_observation_source(connection_provider),
        event_bus=event_bus,
        dedup_window_seconds=(
            monitoring_config.dedup_window_seconds
            if monitoring_config is not None
            else 3600
        ),
        max_alerts_per_evaluation=(
            monitoring_config.max_alerts_per_evaluation
            if monitoring_config is not None
            else 100
        ),
        grouping_window_seconds=(
            monitoring_config.grouping_window_seconds
            if monitoring_config is not None
            else 300
        ),
    )
    raw_record_store = build_raw_record_store(connection_provider)
    observation_writer = build_observation_writer(connection_provider)
    entity_metric_repository = build_entity_metric_repository(connection_provider)
    risk_history_writer = build_risk_history_writer(connection_provider)
    alert_history_writer = build_alert_history_writer(connection_provider)
    analytics_config = config.analytics or AnalyticsConfig()
    metrics_throttle = MetricsRecomputeThrottle(
        min_interval_seconds=analytics_config.metrics_recompute_min_interval_seconds
    )
    records_config = config.records or RecordsConfig()
```

- [ ] **Step 2: Pass the new fields into the `WorkerDependencies(...)` constructor**

In the `return WorkerDependencies(...)` call, after `observation_writer=observation_writer,`, add:

```python
        entity_metric_repository=entity_metric_repository,
        metrics_throttle=metrics_throttle,
        risk_history_writer=risk_history_writer,
        alert_history_writer=alert_history_writer,
```

- [ ] **Step 3: Run pyright, ruff, and the existing worker suite**

Run: `.venv/bin/pyright && .venv/bin/ruff check agent/ && .venv/bin/pytest tests/agent/ -m "not integration" -v`
Expected: clean, all existing worker tests still PASS.

- [ ] **Step 4: Commit Tasks 14 + 15 together**

```bash
git add agent/coordinator.py
git commit -m "feat(worker): wire Plan C adapter selectors into WorkerDependencies"
```

---

### Task 16: Thread the four new dependencies through dispatch and the consume loop

**Files:**
- Modify: `backend/agent/coordinator.py`

This task is plumbing only — it adds the four parameters everywhere they must flow, all defaulting to `None`, and adds `alerts.created` to the consumed event types. No behavior changes yet; the existing worker suite must stay green.

- [ ] **Step 1: Extend `handle_event`**

In `handle_event`'s signature, after `observation_writer: ObservationWriter | None = None,`, add:

```python
    entity_metric_repository: EntityMetricRepository | None = None,
    metrics_throttle: MetricsRecomputeThrottle | None = None,
    risk_history_writer: RiskHistoryWriter | None = None,
    alert_history_writer: AlertHistoryWriter | None = None,
```

In the `_dispatch_event(...)` call inside `handle_event`, after `observation_writer=observation_writer,`, add:

```python
            entity_metric_repository=entity_metric_repository,
            metrics_throttle=metrics_throttle,
            risk_history_writer=risk_history_writer,
            alert_history_writer=alert_history_writer,
```

- [ ] **Step 2: Extend `_dispatch_event`**

In `_dispatch_event`'s signature, after `observation_writer: ObservationWriter | None,`, add:

```python
    entity_metric_repository: EntityMetricRepository | None,
    metrics_throttle: MetricsRecomputeThrottle | None,
    risk_history_writer: RiskHistoryWriter | None,
    alert_history_writer: AlertHistoryWriter | None,
```

- [ ] **Step 3: Extend `drain_ingestion_events`**

In `drain_ingestion_events`'s signature, after `observation_writer: ObservationWriter | None = None,`, add the same four `... | None = None` parameters as in Step 1.

In the nested `_run_handler` closure's `handle_event(...)` call, after `observation_writer=observation_writer,`, add the four `...=...,` pass-throughs.

In the `event_types` list, add `"alerts.created"` after `"records.ingested"`.

- [ ] **Step 4: Extend the `run_worker` call site**

In `run_worker`, the `drain_ingestion_events(...)` call passes `observation_writer=deps.observation_writer,`. After it, add:

```python
                entity_metric_repository=deps.entity_metric_repository,
                metrics_throttle=deps.metrics_throttle,
                risk_history_writer=deps.risk_history_writer,
                alert_history_writer=deps.alert_history_writer,
```

- [ ] **Step 5: Run pyright, ruff, worker suite**

Run: `.venv/bin/pyright && .venv/bin/ruff check agent/ && .venv/bin/pytest tests/agent/ -m "not integration" -v`
Expected: clean, all PASS (no behavior change yet).

- [ ] **Step 6: Commit**

```bash
git add agent/coordinator.py
git commit -m "refactor(worker): thread Plan C dependencies through dispatch and drain loop"
```

---

### Task 17: Flow 2 — persist graph metrics on `GraphUpdatedEvent`

**Files:**
- Modify: `backend/agent/coordinator.py`
- Test: `backend/tests/agent/test_graph_metrics_flow.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/agent/test_graph_metrics_flow.py`:

```python
"""Tests for Flow 2 — graph-metric persistence."""

from __future__ import annotations

from datetime import datetime, timezone

from agent.coordinator import _persist_graph_metrics_for_event
from analytics.metrics.adapters.in_memory import InMemoryEntityMetricRepository
from analytics.metrics.throttle import MetricsRecomputeThrottle
from events.adapters.in_memory import InMemoryEventBus
from events.types import GraphUpdatedDocumentReference, GraphUpdatedEvent
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.service import create_graph_service
from shared.types import Entity
from storage.adapters.in_memory import InMemoryObjectStore


def _graph_service_with_entities(count: int) -> object:
    service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=InMemoryObjectStore(),
        event_bus=InMemoryEventBus(),
    )
    service.upsert_records_graph(
        "kb-1",
        [
            Entity(id=f"claim:{index}", type="claim", properties={})
            for index in range(count)
        ],
        [],
    )
    return service


def _event() -> GraphUpdatedEvent:
    return GraphUpdatedEvent(
        correlation_id="corr-metrics",
        documents=[
            GraphUpdatedDocumentReference(
                knowledge_base_id="kb-1",
                source_document_id="src-1",
                parsed_document_id="parsed-1",
                extraction_result_id="extract-1",
                validation_report_id="valid-1",
                upserted_entity_count=3,
                upserted_relationship_count=0,
            )
        ],
    )


def test_flow2_persists_graph_metrics() -> None:
    service = _graph_service_with_entities(3)
    repo = InMemoryEntityMetricRepository()
    throttle = MetricsRecomputeThrottle(min_interval_seconds=300)

    _persist_graph_metrics_for_event(
        event=_event(),
        graph_service=service,  # type: ignore[arg-type]
        entity_metric_repository=repo,
        metrics_throttle=throttle,
    )

    current = repo.load_current_metrics(
        knowledge_base_id="kb-1", entity_id="__graph__"
    )
    by_metric = {value.metric_name: value.value for value in current}
    assert by_metric["entity_count"] == 3.0
    assert "relationship_count" in by_metric
    assert "avg_degree" in by_metric


def test_flow2_is_throttled_per_kb() -> None:
    service = _graph_service_with_entities(3)
    repo = InMemoryEntityMetricRepository()
    throttle = MetricsRecomputeThrottle(min_interval_seconds=300)

    _persist_graph_metrics_for_event(
        event=_event(),
        graph_service=service,  # type: ignore[arg-type]
        entity_metric_repository=repo,
        metrics_throttle=throttle,
    )
    # A second event within the interval is throttled — no new history rows.
    _persist_graph_metrics_for_event(
        event=_event(),
        graph_service=service,  # type: ignore[arg-type]
        entity_metric_repository=repo,
        metrics_throttle=throttle,
    )
    current = repo.load_current_metrics(
        knowledge_base_id="kb-1", entity_id="__graph__"
    )
    assert len(current) == 3  # one row per metric, not six
```

Note: the `# type: ignore[arg-type]` markers above are a placeholder shorthand for the test author — replace them by typing the helper `_graph_service_with_entities` as `-> GraphService` (import `GraphService` from `graph.service`) so no suppression is needed. `tests/agent` is pyright-strict.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/agent/test_graph_metrics_flow.py -v`
Expected: FAIL — `ImportError: cannot import name '_persist_graph_metrics_for_event'`.

- [ ] **Step 3: Add the `_persist_graph_metrics_for_event` helper**

In `backend/agent/coordinator.py`, immediately before `_write_analytics_properties_to_graph`, add:

```python
def _persist_graph_metrics_for_event(
    *,
    event: GraphUpdatedEvent,
    graph_service: GraphService,
    entity_metric_repository: EntityMetricRepository | None,
    metrics_throttle: MetricsRecomputeThrottle | None,
) -> None:
    """Flow 2 — persist graph metrics per KB, throttled to avoid recompute storms.

    Best-effort: a failure here is logged but never aborts Flow B. The throttle
    drops recomputes that arrive within the configured per-KB interval so a
    burst of graph updates cannot thrash the system.
    """

    if entity_metric_repository is None or metrics_throttle is None:
        return
    now = __datetime__.now(tz=__timezone__.utc)
    seen: set[str] = set()
    for document in event.documents:
        knowledge_base_id = document.knowledge_base_id
        if knowledge_base_id in seen:
            continue
        seen.add(knowledge_base_id)
        if not metrics_throttle.should_recompute(knowledge_base_id, now=now):
            logger.debug(
                "Skipping throttled graph-metric recompute for kb=%s",
                knowledge_base_id,
            )
            continue
        try:
            metrics = graph_service.compute_metrics(knowledge_base_id)
            entity_metric_repository.record_metrics(
                [
                    EntityMetricSample(
                        knowledge_base_id=knowledge_base_id,
                        entity_id=GRAPH_SCOPE_ENTITY_ID,
                        metric_name=METRIC_ENTITY_COUNT,
                        value=float(metrics.entity_count),
                        observed_at=now,
                        correlation_id=event.correlation_id,
                    ),
                    EntityMetricSample(
                        knowledge_base_id=knowledge_base_id,
                        entity_id=GRAPH_SCOPE_ENTITY_ID,
                        metric_name=METRIC_RELATIONSHIP_COUNT,
                        value=float(metrics.relationship_count),
                        observed_at=now,
                        correlation_id=event.correlation_id,
                    ),
                    EntityMetricSample(
                        knowledge_base_id=knowledge_base_id,
                        entity_id=GRAPH_SCOPE_ENTITY_ID,
                        metric_name=METRIC_AVG_DEGREE,
                        value=metrics.avg_degree,
                        observed_at=now,
                        correlation_id=event.correlation_id,
                    ),
                ]
            )
        except Exception as exc:  # noqa: BLE001 - metrics must not block Flow B
            logger.warning(
                "Failed to persist graph metrics for kb=%s: %s",
                knowledge_base_id,
                exc,
            )
```

- [ ] **Step 4: Call the helper from `handle_graph_updated_for_analytics`**

Add two keyword-only parameters to `handle_graph_updated_for_analytics`, after `object_store: ObjectStore | None = None,`:

```python
    entity_metric_repository: EntityMetricRepository | None = None,
    metrics_throttle: MetricsRecomputeThrottle | None = None,
```

In the body, immediately before the closing `if alerts:` block, add:

```python
    _persist_graph_metrics_for_event(
        event=event,
        graph_service=graph_service,
        entity_metric_repository=entity_metric_repository,
        metrics_throttle=metrics_throttle,
    )
```

- [ ] **Step 5: Pass the new args from `_dispatch_event`**

In `_dispatch_event`, the `GraphUpdatedEvent` branch calls `handle_graph_updated_for_analytics(...)`. Add to that call, after `object_store=object_store,`:

```python
                    entity_metric_repository=entity_metric_repository,
                    metrics_throttle=metrics_throttle,
```

- [ ] **Step 6: Run tests, pyright, ruff**

Run: `.venv/bin/pytest tests/agent/ -m "not integration" -v && .venv/bin/pyright && .venv/bin/ruff check agent/`
Expected: PASS, clean.

- [ ] **Step 7: Commit**

```bash
git add agent/coordinator.py tests/agent/test_graph_metrics_flow.py
git commit -m "feat(worker): Flow 2 — persist throttled graph metrics on graph.updated"
```

---

### Task 18: Flow 3 — persist risk assessments on `RiskScoredEvent`

**Files:**
- Modify: `backend/agent/coordinator.py`
- Test: `backend/tests/agent/test_risk_scored_graph_flow.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/agent/test_risk_scored_graph_flow.py`:

```python
"""Tests for Flow 3 — risk write-back."""

from __future__ import annotations

from agent.coordinator import handle_risk_scored_for_graph
from analytics.risk.adapters.in_memory import InMemoryRiskHistoryWriter
from events.adapters.in_memory import InMemoryEventBus
from events.types import RiskFactorReference, RiskScoredEvent, RiskScoredReference
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.service import GraphService, create_graph_service
from shared.types import Entity
from storage.adapters.in_memory import InMemoryObjectStore


def _graph_service_with_entity() -> GraphService:
    service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=InMemoryObjectStore(),
        event_bus=InMemoryEventBus(),
    )
    service.upsert_records_graph(
        "kb-1", [Entity(id="claim:c1", type="claim", properties={})], []
    )
    return service


def _event() -> RiskScoredEvent:
    return RiskScoredEvent(
        correlation_id="corr-risk",
        assessments=[
            RiskScoredReference(
                knowledge_base_id="kb-1",
                request_id="req-1",
                entity_id="claim:c1",
                overall_score=0.82,
                risk_level="high",
                factor_count=1,
                factors=[
                    RiskFactorReference(
                        factor_name="anomaly",
                        raw_value=0.9,
                        weight=1.0,
                        contribution=0.82,
                    )
                ],
            )
        ],
    )


def test_flow3_persists_history_and_snapshots_graph() -> None:
    writer = InMemoryRiskHistoryWriter()
    service = _graph_service_with_entity()

    processed = handle_risk_scored_for_graph(
        _event(), risk_history_writer=writer, graph_service=service
    )

    assert processed == 1
    assert (
        writer.load_historical_score(knowledge_base_id="kb-1", entity_id="claim:c1")
        == 0.82
    )
    entity = service.get_entity("kb-1", "claim:c1")
    assert entity is not None
    assert entity.properties["risk_score"] == 0.82
    assert entity.properties["risk_level"] == "high"
    assert "risk_assessed_at" in entity.properties


def test_flow3_is_idempotent_on_replay() -> None:
    writer = InMemoryRiskHistoryWriter()
    service = _graph_service_with_entity()
    event = _event()

    handle_risk_scored_for_graph(
        event, risk_history_writer=writer, graph_service=service
    )
    # Replay (retry/DLQ) writes no second history row.
    handle_risk_scored_for_graph(
        event, risk_history_writer=writer, graph_service=service
    )
    assert (
        writer.load_historical_score(knowledge_base_id="kb-1", entity_id="claim:c1")
        == 0.82
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/agent/test_risk_scored_graph_flow.py -v`
Expected: FAIL — `ImportError: cannot import name 'handle_risk_scored_for_graph'`.

- [ ] **Step 3: Add the `handle_risk_scored_for_graph` handler**

In `backend/agent/coordinator.py`, immediately after the existing `handle_risk_scored` function, add:

```python
def handle_risk_scored_for_graph(
    event: RiskScoredEvent,
    *,
    risk_history_writer: RiskHistoryWriter,
    graph_service: GraphService,
) -> int:
    """Flow 3 — persist risk assessments and snapshot risk onto the graph entity.

    Idempotent: ``risk_score_history`` is keyed by request_id and
    ``update_entity_properties`` is a property merge, so the worker's retry/DLQ
    wrapper can safely re-run this handler. The graph write publishes no event,
    so it cannot re-trigger the analytics pipeline.
    """

    assessed_at = __datetime__.now(tz=__timezone__.utc)
    processed = 0
    for assessment in event.assessments:
        record = RiskAssessmentRecord(
            knowledge_base_id=assessment.knowledge_base_id,
            entity_id=assessment.entity_id,
            request_id=assessment.request_id,
            overall_score=assessment.overall_score,
            risk_level=assessment.risk_level,
            factors=[
                RiskFactor(
                    factor_name=factor.factor_name,
                    raw_value=factor.raw_value,
                    weight=factor.weight,
                    contribution=factor.contribution,
                    rationale=factor.rationale,
                )
                for factor in assessment.factors
            ],
            assessed_at=assessed_at,
        )
        risk_history_writer.write_assessment(record)
        try:
            graph_service.update_entity_properties(
                assessment.knowledge_base_id,
                assessment.entity_id,
                {
                    "risk_score": float(assessment.overall_score),
                    "risk_level": assessment.risk_level,
                    "risk_assessed_at": assessed_at.isoformat(),
                },
            )
        except Exception as exc:  # noqa: BLE001 - graph backend may be unavailable
            logger.warning(
                "Failed to snapshot risk to graph kb=%s entity=%s: %s",
                assessment.knowledge_base_id,
                assessment.entity_id,
                exc,
            )
        processed += 1
    return processed
```

- [ ] **Step 4: Extend the `RiskScoredEvent` dispatch branch**

In `_dispatch_event`, replace the existing `RiskScoredEvent` branch:

```python
    if isinstance(event, RiskScoredEvent):
        if monitoring_service is None:
            return 0
        try:
            return handle_risk_scored(
                event,
                monitoring_service=monitoring_service,
                event_bus=event_bus,
            )
        except Exception as exc:  # noqa: BLE001 - monitoring must not abort pipeline
            logger.warning(
                "Monitoring stream consumer raised; continuing. error=%s",
                exc,
            )
            return 0
```

with:

```python
    if isinstance(event, RiskScoredEvent):
        processed = 0
        if monitoring_service is not None:
            try:
                processed = handle_risk_scored(
                    event,
                    monitoring_service=monitoring_service,
                    event_bus=event_bus,
                )
            except Exception as exc:  # noqa: BLE001 - monitoring must not abort pipeline
                logger.warning(
                    "Monitoring stream consumer raised; continuing. error=%s",
                    exc,
                )
        if risk_history_writer is not None:
            try:
                handle_risk_scored_for_graph(
                    event,
                    risk_history_writer=risk_history_writer,
                    graph_service=graph_service,
                )
            except Exception as exc:  # noqa: BLE001 - write-back must not abort pipeline
                logger.warning(
                    "Risk graph write-back raised; continuing. error=%s",
                    exc,
                )
        return processed
```

- [ ] **Step 5: Run tests, pyright, ruff**

Run: `.venv/bin/pytest tests/agent/ -m "not integration" -v && .venv/bin/pyright && .venv/bin/ruff check agent/`
Expected: PASS, clean.

- [ ] **Step 6: Commit**

```bash
git add agent/coordinator.py tests/agent/test_risk_scored_graph_flow.py
git commit -m "feat(worker): Flow 3 — persist risk history and snapshot to the graph"
```

---

### Task 19: Flow 4 — persist alerts on `AlertsCreatedEvent`

**Files:**
- Modify: `backend/agent/coordinator.py`
- Test: `backend/tests/agent/test_alerts_created_graph_flow.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/agent/test_alerts_created_graph_flow.py`:

```python
"""Tests for Flow 4 — alert write-back."""

from __future__ import annotations

from agent.coordinator import handle_alerts_created_for_graph
from events.adapters.in_memory import InMemoryEventBus
from events.types import AlertCreatedReference, AlertsCreatedEvent
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.service import GraphService, create_graph_service
from monitoring.adapters.in_memory import InMemoryAlertHistoryWriter
from shared.types import Entity
from storage.adapters.in_memory import InMemoryObjectStore


def _graph_service_with_entity() -> GraphService:
    service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=InMemoryObjectStore(),
        event_bus=InMemoryEventBus(),
    )
    service.upsert_records_graph(
        "kb-1", [Entity(id="claim:c1", type="claim", properties={})], []
    )
    return service


def _reference(alert_id: str) -> AlertCreatedReference:
    return AlertCreatedReference(
        knowledge_base_id="kb-1",
        alert_id=alert_id,
        entity_id="claim:c1",
        severity="high",
        entity_type="claim",
        status="open",
        title="Anomalous claim",
        reasoning="score exceeded threshold",
        metric_name="claim_anomaly",
    )


def _event() -> AlertsCreatedEvent:
    return AlertsCreatedEvent(
        correlation_id="corr-alert",
        alerts=[_reference("a-1"), _reference("a-2")],
    )


def test_flow4_persists_history_and_snapshots_graph() -> None:
    writer = InMemoryAlertHistoryWriter()
    service = _graph_service_with_entity()

    processed = handle_alerts_created_for_graph(
        _event(), alert_history_writer=writer, graph_service=service
    )

    assert processed == 2
    assert (
        writer.count_open_alerts(knowledge_base_id="kb-1", entity_id="claim:c1") == 2
    )
    entity = service.get_entity("kb-1", "claim:c1")
    assert entity is not None
    assert entity.properties["active_alert_count"] == 2
    assert entity.properties["last_alert_severity"] == "high"
    assert "last_alert_at" in entity.properties


def test_flow4_is_idempotent_on_replay() -> None:
    writer = InMemoryAlertHistoryWriter()
    service = _graph_service_with_entity()
    event = _event()

    handle_alerts_created_for_graph(
        event, alert_history_writer=writer, graph_service=service
    )
    handle_alerts_created_for_graph(
        event, alert_history_writer=writer, graph_service=service
    )
    # Count is derived, not incremented — replay leaves it at 2.
    entity = service.get_entity("kb-1", "claim:c1")
    assert entity is not None
    assert entity.properties["active_alert_count"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/agent/test_alerts_created_graph_flow.py -v`
Expected: FAIL — `ImportError: cannot import name 'handle_alerts_created_for_graph'`.

- [ ] **Step 3: Add the `handle_alerts_created_for_graph` handler**

In `backend/agent/coordinator.py`, immediately after `handle_risk_scored_for_graph`, add:

```python
def handle_alerts_created_for_graph(
    event: AlertsCreatedEvent,
    *,
    alert_history_writer: AlertHistoryWriter,
    graph_service: GraphService,
) -> int:
    """Flow 4 — persist alerts to the alert-history log and snapshot onto the graph.

    Idempotent: ``alert_history`` is keyed by alert_id; the entity's
    ``active_alert_count`` is derived from a count of open alerts (never blindly
    incremented), so retry/DLQ replay is safe. The graph write publishes no
    event, so it cannot re-trigger the analytics pipeline.
    """

    created_at = __datetime__.now(tz=__timezone__.utc)
    records: list[AlertHistoryRecord] = []
    severity_by_entity: dict[tuple[str, str], str] = {}
    for alert in event.alerts:
        records.append(
            AlertHistoryRecord(
                knowledge_base_id=alert.knowledge_base_id,
                alert_id=alert.alert_id,
                entity_id=alert.entity_id,
                entity_type=alert.entity_type,
                severity=alert.severity,
                status=alert.status,
                title=alert.title,
                reasoning=alert.reasoning,
                metric_name=alert.metric_name,
                evidence_pack_id=alert.evidence_pack_id,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        severity_by_entity[(alert.knowledge_base_id, alert.entity_id)] = alert.severity

    alert_history_writer.write_alerts(records)

    for (knowledge_base_id, entity_id), severity in severity_by_entity.items():
        try:
            open_count = alert_history_writer.count_open_alerts(
                knowledge_base_id=knowledge_base_id, entity_id=entity_id
            )
            graph_service.update_entity_properties(
                knowledge_base_id,
                entity_id,
                {
                    "active_alert_count": open_count,
                    "last_alert_at": created_at.isoformat(),
                    "last_alert_severity": severity,
                },
            )
        except Exception as exc:  # noqa: BLE001 - graph backend may be unavailable
            logger.warning(
                "Failed to snapshot alerts to graph kb=%s entity=%s: %s",
                knowledge_base_id,
                entity_id,
                exc,
            )
    return len(records)
```

- [ ] **Step 4: Add the `AlertsCreatedEvent` dispatch branch**

In `_dispatch_event`, immediately after the `RiskScoredEvent` branch and before the `RecordsIngestedEvent` branch, add:

```python
    if isinstance(event, AlertsCreatedEvent):
        if alert_history_writer is None:
            return 0
        try:
            return handle_alerts_created_for_graph(
                event,
                alert_history_writer=alert_history_writer,
                graph_service=graph_service,
            )
        except Exception as exc:  # noqa: BLE001 - write-back must not abort pipeline
            logger.warning(
                "Alert graph write-back raised; continuing. error=%s",
                exc,
            )
            return 0
```

(`"alerts.created"` was already added to the `event_types` consume list in Task 16 Step 3 — verify it is present.)

- [ ] **Step 5: Run the full worker suite, pyright, ruff**

Run: `.venv/bin/pytest tests/agent/ -m "not integration" -v && .venv/bin/pyright && .venv/bin/ruff check agent/`
Expected: PASS, clean.

- [ ] **Step 6: Commit**

```bash
git add agent/coordinator.py tests/agent/test_alerts_created_graph_flow.py
git commit -m "feat(worker): Flow 4 — persist alert history and snapshot to the graph"
```

---

## Phase 8 — API composition root

### Task 20: Postgres branch in `get_monitoring_source`

**Files:**
- Modify: `backend/api/dependencies.py`
- Test: `backend/tests/api/test_monitoring_source_selection.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/api/test_monitoring_source_selection.py`:

```python
"""Tests for config-driven monitoring observation-source selection."""

from __future__ import annotations

from api.dependencies import get_connection_provider, get_monitoring_source
from monitoring.adapters.in_memory import InMemoryObservationSource


def test_in_memory_backend_selects_in_memory_source() -> None:
    """The default test config uses database.backend=in_memory."""
    get_connection_provider.cache_clear()
    get_monitoring_source.cache_clear()
    try:
        source = get_monitoring_source()
        assert isinstance(source, InMemoryObservationSource)
    finally:
        get_connection_provider.cache_clear()
        get_monitoring_source.cache_clear()
```

- [ ] **Step 2: Run test to verify it fails or passes-by-accident**

Run: `.venv/bin/pytest tests/api/test_monitoring_source_selection.py -v`
Expected: PASS (the current `get_monitoring_source` already returns `InMemoryObservationSource`). This test pins the in-memory behaviour so the Postgres branch added next does not regress it.

- [ ] **Step 3: Add the Postgres branch**

In `backend/api/dependencies.py`, add `PostgresObservationSource` to the `from monitoring.adapters.postgres import ...` line if one exists, otherwise add `from monitoring.adapters.postgres import PostgresObservationSource` alongside the other monitoring imports.

Replace the existing provider:

```python
@lru_cache(maxsize=1)
def get_monitoring_source() -> ObservationSourceProtocol:
    """Return the monitoring observation source selected by config."""
    return InMemoryObservationSource()
```

with:

```python
@lru_cache(maxsize=1)
def get_monitoring_source() -> ObservationSourceProtocol:
    """Return the monitoring observation source selected by the database backend."""
    provider = get_connection_provider()
    if provider is None:
        return InMemoryObservationSource()
    return PostgresObservationSource(provider)
```

- [ ] **Step 4: Run tests, pyright, ruff**

Run: `.venv/bin/pytest tests/api/test_monitoring_source_selection.py tests/api/ -m "not integration" -v && .venv/bin/pyright && .venv/bin/ruff check api/dependencies.py`
Expected: PASS, clean.

- [ ] **Step 5: Add the test to pyright include**

In `backend/pyproject.toml`, insert `"tests/api/test_monitoring_source_selection.py"` into the `[tool.pyright].include` list, alphabetically among the other `tests/api/` entries.

Run: `.venv/bin/pyright`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add api/dependencies.py tests/api/test_monitoring_source_selection.py pyproject.toml
git commit -m "feat(api): select Postgres observation source when database backend is postgres"
```

---

## Phase 9 — Documentation and final verification

### Task 21: Documentation

**Files:**
- Create: `backend/analytics/metrics/README.md`
- Modify: `backend/README.md`, `docs/architecture.md`, `.github/copilot-instructions.md`, `CLAUDE.md`
- Modify: nearest `README.md` / `AGENT.md` / `AGENT_Instructions.md` under `backend/analytics/` and `backend/monitoring/` if present

- [ ] **Step 1: Create `backend/analytics/metrics/README.md`**

```markdown
# analytics/metrics

Entity-metric persistence. A small read/write package — no service, no events —
keyed to the two metric tables created by the persistence baseline migration:

- `entity_metric_history` (TimescaleDB hypertable) — graph metrics over time.
- `entity_metrics_current` — the latest value per entity metric.

## Components

- `EntityMetricRepository` (`adapters/protocols.py`) — `record_metrics` (append
  history + upsert current) and `load_current_metrics` (snapshot read).
- `InMemoryEntityMetricRepository` / `PostgresEntityMetricRepository` — config-
  selected siblings; the Postgres adapter depends only on
  `database.ConnectionProvider`.
- `MetricsRecomputeThrottle` (`throttle.py`) — per-knowledge-base rate limiter.
  Flow 2 (`agent.coordinator.handle_graph_updated_for_analytics`) consults it so
  a burst of `GraphUpdatedEvent`s cannot trigger a metric-recompute storm.
- Graph-scope metrics use the sentinel `entity_id = "__graph__"` with metric
  names `entity_count`, `relationship_count`, `avg_degree`.

## Adapter selection

`config.database.backend`: `in_memory` (default, used by tests) → in-memory
adapter; `postgres` → `PostgresEntityMetricRepository`. Selection happens in the
worker composition root (`agent/coordinator.py::build_entity_metric_repository`).
```

- [ ] **Step 2: Update `backend/README.md`**

In the module map / "Current State" section, add `analytics/metrics/` (entity-metric persistence) and note the three new worker flows:
- Flow 2 — graph metrics persisted to `entity_metric_history` / `entity_metrics_current` on `GraphUpdatedEvent`, throttled per KB.
- Flow 3 — risk assessments persisted to `risk_score_history` and snapshotted onto graph entities on `RiskScoredEvent`.
- Flow 4 — alerts persisted to `alert_history` and snapshotted onto graph entities on `AlertsCreatedEvent`.

In the Environment Variables / configuration section, document the new optional `analytics` config section (`metrics_recompute_min_interval_seconds`, default 300).

- [ ] **Step 3: Update `docs/architecture.md`**

In the module decomposition, add `analytics/metrics/`. In the data-flow section, document Flows 2/3/4 and the per-consumer Postgres adapters (`monitoring`, `analytics/timeseries`, `analytics/risk`, `analytics/metrics`) as the now-implemented read/write side of the persistence backbone. Note design deviations D-C1 and D-C2 from this plan (risk adapter is writer + history-read only; Flows 3/4 write an entity-property snapshot to the graph, not separate history nodes; Flow 2 recompute is throttled).

- [ ] **Step 4: Update `.github/copilot-instructions.md` and `CLAUDE.md`**

In `CLAUDE.md`'s "Backend Module Map", change `analytics/{timeseries,gnn,risk,explainability}/` to `analytics/{timeseries,gnn,risk,explainability,metrics}/`. Make the equivalent edit in `.github/copilot-instructions.md` to keep the two consistent.

- [ ] **Step 5: Update nearest module instruction files**

Per `CLAUDE.md`'s turn-completion rule, search up from `backend/analytics/metrics/`, `backend/monitoring/`, `backend/analytics/risk/`, and `backend/analytics/timeseries/` for `README.md` / `AGENT.md` / `AGENT_Instructions.md` and update any that describe adapter inventories so they list the new Postgres adapters.

- [ ] **Step 6: Commit**

```bash
git add analytics/metrics/README.md backend/README.md ../docs/architecture.md ../.github/copilot-instructions.md ../CLAUDE.md
# plus any module instruction files updated in Step 5
git commit -m "docs: document Plan C persistence adapters, flows, and metrics module"
```

(Adjust the relative paths above to match the repo root from `backend/`.)

---

### Task 22: Full verification

**Files:** none — verification only.

- [ ] **Step 1: Type-check the whole hardened surface**

Run: `cd backend && .venv/bin/pyright`
Expected: `0 errors`. Fix any error properly — no `Any`, no suppression (CLAUDE.md).

- [ ] **Step 2: Lint**

Run: `.venv/bin/ruff check .`
Expected: clean (import-order findings excepted per CLAUDE.md).

- [ ] **Step 3: Run the full unit suite**

Run: `.venv/bin/pytest -m "not integration"`
Expected: all PASS — no regressions against the pre-Plan-C baseline.

- [ ] **Step 4: Run the integration suite against the dev database**

Ensure `make dev` is up and `alembic upgrade head` has been applied to the Timescale container, then with `DATABASE_URL` exported:

Run: `.venv/bin/pytest -m integration`
Expected: all PASS (none skipped — the new Postgres adapter tests for metrics, observations, alert history, timeseries, and risk history all execute).

- [ ] **Step 5: Confirm coverage gates**

Run: `.venv/bin/pytest --cov` (a run that includes the integration suite against a live DB, so the Postgres adapters count toward coverage — mirroring Plan A/B gating).
Expected: per-package coverage ≥ 85% for `analytics/metrics`, `analytics/risk`, `analytics/timeseries`, `monitoring`, and `agent`. Add unit tests for any uncovered branch until the gate is green.

- [ ] **Step 6: Smoke-test the worker end to end**

With the dev stack running, ingest a structured-records CSV feed (Flow 1) and confirm in the Timescale container that, after the worker processes the resulting events:
- `observations` has rows for the batch (Plan B);
- `entity_metric_history` / `entity_metrics_current` gain graph-metric rows (Flow 2);
- `risk_score_history` gains rows and the graph entities carry `risk_score` / `risk_level` properties (Flow 3);
- `alert_history` gains rows and alerted entities carry `active_alert_count` (Flow 4).

Inspect with `make api-shell` or a `psql` session against the Timescale service.

- [ ] **Step 7: Final commit (if Steps 1–5 required any fixes)**

```bash
git add -A
git commit -m "test: close Plan C coverage gaps and finalize verification"
```

---

## Self-Review (plan author's check against the spec)

- **Spec coverage** — Every Plan C deliverable maps to a task: monitoring read-side `ObservationSourceProtocol` (T6); monitoring alert-history writer (T7–T8); `analytics/timeseries` Postgres read adapter (T9); `analytics/risk` writer + history read (T10–T11); `analytics/metrics/` package (T2–T5); Flow 2 / 3 / 4 worker handlers (T17 / T18 / T19); config additions (T1); API wiring (T20); docs (T21).
- **Approved deviations** — D-C1 (risk adapter scoped to writer + `load_historical_score`; no `load_profile`/`list_ranked_entries` — `risk_score_history` has no `entity_type` column and no signals), D-C2 (entity-property snapshot + SQL history, no graph history nodes; Flow 2 throttled per the user's anti-thrash directive), and D-C3/D-C4/D-C5 are recorded in the Scope section and re-stated in the docs task.
- **Type consistency** — Method and model names are consistent across tasks (`record_metrics`/`load_current_metrics`, `write_alerts`/`count_open_alerts`, `write_assessment`/`load_historical_score`, `load_series`/`load_metric_range`, `EntityMetricSample`/`EntityMetricValue`, `AlertHistoryRecord`, `RiskAssessmentRecord`, `RiskFactorReference`, `build_entity_metric_repository`/`build_risk_history_writer`/`build_alert_history_writer`).
- **Known shorthand** — Tasks 11 and 17 show a `# type: ignore` token *only* as an inline reminder, each immediately followed by the exact suppression-free replacement (a `cast`, or typing a test helper `-> GraphService`). The engineer must use the replacement; no `type: ignore` survives into committed code.


