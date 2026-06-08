# Peer-Group Z-Score → Risk Signals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compute config-driven cross-sectional peer-group z-scores from `raw_records` over configured intervals, persist them as derived `RiskSignal`s, and surface them to the risk-scores endpoint via a new Postgres `RiskSignalSource`.

**Architecture:** A new `backend/analytics/peerstats/` module (protocols + service + in-memory/postgres adapters) computes, per `PeerMetricSpec`, each entity's interval aggregate of a record column, z-scores it against its peer group (entity_type + optional grouping columns) for that interval, and writes derived signals to a new `entity_derived_signals` table. A new best-effort worker stage (triggered inside `handle_records_ingested`) runs the computation, then assesses risk for the deduped set of affected entities. A new `PostgresRiskSignalSource` assembles `RiskProfile`s from the derived signals so the existing risk service — unchanged — scores them.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI, Alembic, TimescaleDB/Postgres (via the psycopg-free `database.ConnectionProvider` protocol), pytest, pyright strict, ruff.

**Spec:** `docs/superpowers/specs/2026-06-08-peer-group-zscore-risk-signals-design.md`

---

## Conventions (read once)

- **Run tests** from the repo root using the host venv: `cd backend && .venv/bin/pytest tests/<path> -v`. (Per project setup the host `backend/.venv` runs pytest/pyright/ruff directly.)
- **Type gate:** `cd backend && .venv/bin/pyright` (bare — it is the real gate; its `tool.pyright.include` covers test dirs too).
- **Lint gate:** `backend/.venv/bin/ruff check --no-cache backend` (ruff's cache dir is not writable in the sandbox).
- **Entity-id convention:** record entity ids are `f"{entity_type}:{raw_id}"` (see `records/mappers/feed_mapper.py:34`). Peerstats MUST produce the same ids so risk profiles join to graph entities.
- **No `Any`, full annotations, coverage ≥85% per package.** Fix every error/warning you surface — do not defer.
- New test files mirror the existing `backend/tests/analytics/<module>/` layout. Create `backend/tests/analytics/peerstats/` with an empty `__init__.py` if absent.

## File Map

**Create:**
- `backend/analytics/peerstats/__init__.py` — public exports
- `backend/analytics/peerstats/models.py` — `PeerAggregate`, `PeerGroupStat`, `DerivedRiskSignal`
- `backend/analytics/peerstats/service_models.py` — `PeerStatsComputeRequest`, `PeerStatsComputeResponse`
- `backend/analytics/peerstats/exceptions.py` — `PeerStatsError`, `PeerStatsConfigurationError`, `PeerStatsSourceError`
- `backend/analytics/peerstats/aggregation.py` — pure helpers: `bucket_start`, `apply_aggregation`, `peer_group_key`, `z_to_signal`
- `backend/analytics/peerstats/protocols.py` — `PeerStatsServiceProtocol`
- `backend/analytics/peerstats/service.py` — `PeerStatsService`, `create_peerstats_service`
- `backend/analytics/peerstats/adapters/__init__.py`
- `backend/analytics/peerstats/adapters/protocols.py` — `RecordColumnSourceProtocol`, `DerivedRiskSignalWriterProtocol`, `ColumnRow`
- `backend/analytics/peerstats/adapters/in_memory.py` — `InMemoryRecordColumnSource`, `InMemoryDerivedRiskSignalWriter`
- `backend/analytics/peerstats/adapters/postgres.py` — `PostgresRecordColumnSource`, `PostgresDerivedRiskSignalWriter`
- `backend/database/migrations/versions/0006_entity_derived_signals.py` — new table
- `backend/analytics/peerstats/README.md`
- `backend/tests/analytics/peerstats/` test modules

**Modify:**
- `backend/config/schema.py` — `CapabilitiesConfig.peer_stats`, new `PeerMetricSpec`/`PeerStatsConfig`, `DomainConfig.peer_stats`
- `backend/config/defaults/medicare_fraud.yaml` — `capabilities.peer_stats: true` + `peer_stats.metrics`
- `backend/analytics/risk/adapters/postgres.py` — add `PostgresRiskSignalSource`
- `backend/api/dependencies.py` — `get_derived_signal_store`, wire `get_risk_signal_source` to Postgres
- `backend/agent/coordinator.py` — peerstats deps, stage, dispatch, `WorkerDependencies` fields
- `backend/README.md`, `docs/architecture.md` — module map + flow

---

## Task 1: Config schema — capability flag + PeerStatsConfig/PeerMetricSpec

**Files:**
- Modify: `backend/config/schema.py` (`CapabilitiesConfig` at line 49; insert new models before `DomainConfig` at line 451; add field in `DomainConfig` after line 476)
- Test: `backend/tests/config/test_peer_stats_config.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/config/test_peer_stats_config.py`:

```python
"""Validation tests for peer-stats domain config."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from config.schema import CapabilitiesConfig, PeerMetricSpec, PeerStatsConfig


def test_peer_metric_spec_defaults() -> None:
    spec = PeerMetricSpec(
        name="weekly_billing",
        record_type="claim_record",
        entity_type="provider",
        entity_id_field="provider_npi",
        value_column="billed_amount",
        aggregation="sum",
        interval="week",
    )
    assert spec.direction == "high"
    assert spec.z_cap == 4.0
    assert spec.weight == 1.0
    assert spec.min_peers == 5
    assert spec.group_by == []
    assert spec.time_column is None


def test_peer_metric_spec_rejects_nonpositive_z_cap() -> None:
    with pytest.raises(ValidationError):
        PeerMetricSpec(
            name="x",
            record_type="r",
            entity_type="e",
            entity_id_field="id",
            value_column="v",
            aggregation="mean",
            interval="day",
            z_cap=0.0,
        )


def test_peer_metric_spec_rejects_min_peers_below_two() -> None:
    with pytest.raises(ValidationError):
        PeerMetricSpec(
            name="x",
            record_type="r",
            entity_type="e",
            entity_id_field="id",
            value_column="v",
            aggregation="mean",
            interval="day",
            min_peers=1,
        )


def test_peer_stats_config_defaults_empty() -> None:
    assert PeerStatsConfig().metrics == []


def test_capabilities_peer_stats_defaults_false() -> None:
    assert CapabilitiesConfig().peer_stats is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/config/test_peer_stats_config.py -v`
Expected: FAIL — `ImportError: cannot import name 'PeerMetricSpec'`.

- [ ] **Step 3: Add the capability flag**

In `backend/config/schema.py`, add to `CapabilitiesConfig` (after line 57 `structured_ingestion: bool = False`):

```python
    peer_stats: bool = False
```

- [ ] **Step 4: Add the new models**

In `backend/config/schema.py`, insert immediately before `class DomainConfig(BaseModel):` (line 451):

```python
class PeerMetricSpec(BaseModel):
    """One cross-sectional peer-group z-score metric derived from a record column."""

    name: str
    record_type: str
    entity_type: str
    entity_id_field: str
    value_column: str
    aggregation: Literal["sum", "mean", "count", "max", "min"]
    interval: Literal["day", "week", "month"]
    time_column: str | None = None
    group_by: list[str] = Field(default_factory=lambda: cast(list[str], []))
    direction: Literal["high", "low", "two_sided"] = "high"
    z_cap: float = Field(default=4.0, gt=0.0)
    weight: float = Field(default=1.0, gt=0.0)
    min_peers: int = Field(default=5, ge=2)
    rationale_template: str = "{name}: z={z:.2f} vs {peer_group} peers"


class PeerStatsConfig(BaseModel):
    """Collection of peer-group z-score metric specs for a domain."""

    metrics: list[PeerMetricSpec] = Field(
        default_factory=lambda: cast(list[PeerMetricSpec], [])
    )
```

(`Literal`, `Field`, `cast`, and `BaseModel` are already imported at the top of this file — verify with `grep -n "^from typing\|^from pydantic\|import cast" backend/config/schema.py`; the existing `policy_rules` field already uses `cast(list[...], [])`.)

- [ ] **Step 5: Wire the field into DomainConfig**

In `backend/config/schema.py`, add after line 476 (`analytics: AnalyticsConfig | None = None`):

```python
    peer_stats: PeerStatsConfig | None = None
```

- [ ] **Step 6: Run tests + gates**

Run: `cd backend && .venv/bin/pytest tests/config/test_peer_stats_config.py -v`
Expected: PASS (5 passed).
Run: `cd backend && .venv/bin/pyright config/schema.py && .venv/bin/ruff check --no-cache config`
Expected: 0 errors.

- [ ] **Step 7: Commit**

```bash
git add backend/config/schema.py backend/tests/config/test_peer_stats_config.py
git commit -m "feat(config): PeerStatsConfig/PeerMetricSpec + peer_stats capability"
```

---

## Task 2: peerstats models + exceptions

**Files:**
- Create: `backend/analytics/peerstats/__init__.py`, `models.py`, `exceptions.py`
- Test: `backend/tests/analytics/peerstats/__init__.py`, `test_models.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/analytics/peerstats/__init__.py` (empty) and `backend/tests/analytics/peerstats/test_models.py`:

```python
"""Tests for peerstats domain models."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from analytics.peerstats.models import DerivedRiskSignal, PeerAggregate


def _now() -> datetime:
    return datetime(2026, 1, 5, tzinfo=timezone.utc)


def test_peer_aggregate_fields() -> None:
    agg = PeerAggregate(
        entity_id="provider:1",
        entity_type="provider",
        peer_group_key="provider",
        interval_start=_now(),
        aggregate_value=12.5,
    )
    assert agg.aggregate_value == 12.5


def test_derived_signal_value_bounds() -> None:
    with pytest.raises(ValidationError):
        DerivedRiskSignal(
            knowledge_base_id="kb1",
            entity_id="provider:1",
            entity_type="provider",
            metric_name="weekly_billing",
            interval_start=_now(),
            peer_group_key="provider",
            aggregate_value=10.0,
            peer_mean=5.0,
            peer_std=2.0,
            z_score=2.5,
            signal_value=1.5,  # out of [0,1]
            weight=1.0,
            rationale="x",
            correlation_id="c1",
        )
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/analytics/peerstats/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'analytics.peerstats'`.

- [ ] **Step 3: Create the exceptions module**

Create `backend/analytics/peerstats/exceptions.py`:

```python
"""Exceptions for the peerstats module."""

from __future__ import annotations


class PeerStatsError(Exception):
    """Base class for peerstats failures."""


class PeerStatsConfigurationError(PeerStatsError):
    """Raised when a peer metric spec is internally inconsistent at runtime."""


class PeerStatsSourceError(PeerStatsError):
    """Raised when loading record column aggregates fails."""
```

- [ ] **Step 4: Create the models module**

Create `backend/analytics/peerstats/models.py`:

```python
"""Internal domain models for cross-sectional peer-group statistics."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PeerAggregate(BaseModel):
    """One entity's aggregate value for one interval bucket and peer group."""

    entity_id: str
    entity_type: str
    peer_group_key: str
    interval_start: datetime
    aggregate_value: float


class PeerGroupStat(BaseModel):
    """Mean/std of a peer group for one interval bucket."""

    peer_group_key: str
    interval_start: datetime
    mean: float
    std: float
    count: int = Field(ge=0)


class DerivedRiskSignal(BaseModel):
    """A peer z-score expressed as a persistable, risk-consumable signal."""

    knowledge_base_id: str
    entity_id: str
    entity_type: str
    metric_name: str
    interval_start: datetime
    peer_group_key: str
    aggregate_value: float
    peer_mean: float
    peer_std: float
    z_score: float
    signal_value: float = Field(ge=0.0, le=1.0)
    weight: float = Field(gt=0.0)
    rationale: str
    correlation_id: str
```

- [ ] **Step 5: Create the package __init__**

Create `backend/analytics/peerstats/__init__.py`:

```python
"""Cross-sectional peer-group z-score analytics."""

from analytics.peerstats.exceptions import (
    PeerStatsConfigurationError,
    PeerStatsError,
    PeerStatsSourceError,
)
from analytics.peerstats.models import (
    DerivedRiskSignal,
    PeerAggregate,
    PeerGroupStat,
)

__all__ = [
    "DerivedRiskSignal",
    "PeerAggregate",
    "PeerGroupStat",
    "PeerStatsConfigurationError",
    "PeerStatsError",
    "PeerStatsSourceError",
]
```

- [ ] **Step 6: Run tests + gates**

Run: `cd backend && .venv/bin/pytest tests/analytics/peerstats/test_models.py -v`
Expected: PASS (2 passed).
Run: `cd backend && .venv/bin/pyright analytics/peerstats && .venv/bin/ruff check --no-cache analytics/peerstats`
Expected: 0 errors.

- [ ] **Step 7: Commit**

```bash
git add backend/analytics/peerstats/__init__.py backend/analytics/peerstats/models.py \
  backend/analytics/peerstats/exceptions.py backend/tests/analytics/peerstats/
git commit -m "feat(peerstats): domain models + exceptions"
```

---

## Task 3: Pure aggregation/statistics helpers

These pure functions hold all the math, so they are unit-testable in isolation and shared by the in-memory adapter and the service.

**Files:**
- Create: `backend/analytics/peerstats/aggregation.py`
- Test: `backend/tests/analytics/peerstats/test_aggregation.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/analytics/peerstats/test_aggregation.py`:

```python
"""Tests for peerstats pure helpers."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from analytics.peerstats.aggregation import (
    apply_aggregation,
    bucket_start,
    peer_group_key,
    z_to_signal,
)


def _dt(y: int, m: int, d: int, h: int = 0) -> datetime:
    return datetime(y, m, d, h, tzinfo=timezone.utc)


def test_bucket_start_day_truncates_time() -> None:
    assert bucket_start(_dt(2026, 1, 5, 14), "day") == _dt(2026, 1, 5)


def test_bucket_start_week_floors_to_monday() -> None:
    # 2026-01-07 is a Wednesday; ISO week starts Monday 2026-01-05.
    assert bucket_start(_dt(2026, 1, 7, 9), "week") == _dt(2026, 1, 5)


def test_bucket_start_month_floors_to_first() -> None:
    assert bucket_start(_dt(2026, 3, 22, 3), "month") == _dt(2026, 3, 1)


@pytest.mark.parametrize(
    ("fn", "expected"),
    [("sum", 6.0), ("mean", 2.0), ("count", 3.0), ("max", 3.0), ("min", 1.0)],
)
def test_apply_aggregation(fn: str, expected: float) -> None:
    assert apply_aggregation([1.0, 2.0, 3.0], fn) == expected


def test_peer_group_key_type_only_when_no_group_cols() -> None:
    assert peer_group_key("provider", []) == "provider"


def test_peer_group_key_includes_group_values() -> None:
    assert peer_group_key("provider", ["cardiology", "TX"]) == "provider|cardiology|TX"


def test_z_to_signal_high_clamps_positive_tail() -> None:
    assert z_to_signal(2.0, direction="high", z_cap=4.0) == 0.5
    assert z_to_signal(-3.0, direction="high", z_cap=4.0) == 0.0
    assert z_to_signal(10.0, direction="high", z_cap=4.0) == 1.0


def test_z_to_signal_low_uses_negative_tail() -> None:
    assert z_to_signal(-2.0, direction="low", z_cap=4.0) == 0.5
    assert z_to_signal(2.0, direction="low", z_cap=4.0) == 0.0


def test_z_to_signal_two_sided_uses_abs() -> None:
    assert z_to_signal(-2.0, direction="two_sided", z_cap=4.0) == 0.5
    assert z_to_signal(2.0, direction="two_sided", z_cap=4.0) == 0.5
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/analytics/peerstats/test_aggregation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'analytics.peerstats.aggregation'`.

- [ ] **Step 3: Implement the helpers**

Create `backend/analytics/peerstats/aggregation.py`:

```python
"""Pure helpers: interval bucketing, aggregation, peer-group keys, z→signal."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from analytics.peerstats.exceptions import PeerStatsConfigurationError

Interval = Literal["day", "week", "month"]
Aggregation = Literal["sum", "mean", "count", "max", "min"]
Direction = Literal["high", "low", "two_sided"]


def bucket_start(observed_at: datetime, interval: Interval) -> datetime:
    """Return the start of the interval bucket containing ``observed_at``."""

    midnight = observed_at.replace(hour=0, minute=0, second=0, microsecond=0)
    if interval == "day":
        return midnight
    if interval == "week":
        return midnight - timedelta(days=midnight.weekday())
    if interval == "month":
        return midnight.replace(day=1)
    raise PeerStatsConfigurationError(f"Unknown interval '{interval}'.")


def apply_aggregation(values: list[float], fn: Aggregation) -> float:
    """Aggregate a non-empty list of numeric values by the named function."""

    if not values:
        raise PeerStatsConfigurationError("Cannot aggregate an empty value list.")
    if fn == "sum":
        return float(sum(values))
    if fn == "mean":
        return float(sum(values) / len(values))
    if fn == "count":
        return float(len(values))
    if fn == "max":
        return float(max(values))
    if fn == "min":
        return float(min(values))
    raise PeerStatsConfigurationError(f"Unknown aggregation '{fn}'.")


def peer_group_key(entity_type: str, group_values: list[str]) -> str:
    """Build a stable cohort key from entity type and grouping-column values."""

    return "|".join([entity_type, *group_values])


def z_to_signal(z_score: float, *, direction: Direction, z_cap: float) -> float:
    """Map a z-score to a [0,1] risk signal value on the risky tail."""

    if direction == "high":
        tail = max(z_score, 0.0)
    elif direction == "low":
        tail = max(-z_score, 0.0)
    else:
        tail = abs(z_score)
    return min(tail / z_cap, 1.0)
```

- [ ] **Step 4: Run tests + gates**

Run: `cd backend && .venv/bin/pytest tests/analytics/peerstats/test_aggregation.py -v`
Expected: PASS (all parametrizations pass).
Run: `cd backend && .venv/bin/pyright analytics/peerstats/aggregation.py && .venv/bin/ruff check --no-cache analytics/peerstats`
Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add backend/analytics/peerstats/aggregation.py backend/tests/analytics/peerstats/test_aggregation.py
git commit -m "feat(peerstats): pure bucketing/aggregation/z-to-signal helpers"
```

---

## Task 4: service_models, protocols, adapter protocols, in-memory adapters

**Files:**
- Create: `backend/analytics/peerstats/service_models.py`, `protocols.py`, `adapters/__init__.py`, `adapters/protocols.py`, `adapters/in_memory.py`
- Test: `backend/tests/analytics/peerstats/test_in_memory_adapters.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/analytics/peerstats/test_in_memory_adapters.py`:

```python
"""Tests for in-memory peerstats adapters."""

from __future__ import annotations

from datetime import datetime, timezone

from analytics.peerstats.adapters.in_memory import (
    InMemoryDerivedRiskSignalWriter,
    InMemoryRecordColumnSource,
)
from analytics.peerstats.adapters.protocols import ColumnRow
from analytics.peerstats.models import DerivedRiskSignal
from config.schema import PeerMetricSpec


def _spec() -> PeerMetricSpec:
    return PeerMetricSpec(
        name="weekly_billing",
        record_type="claim_record",
        entity_type="provider",
        entity_id_field="provider_npi",
        value_column="billed_amount",
        aggregation="sum",
        interval="week",
    )


def test_column_source_aggregates_per_entity_per_interval() -> None:
    source = InMemoryRecordColumnSource()
    monday = datetime(2026, 1, 5, tzinfo=timezone.utc)
    wednesday = datetime(2026, 1, 7, tzinfo=timezone.utc)
    source.add_rows(
        "kb1",
        "claim_record",
        [
            ColumnRow(entity_id="provider:1", entity_type="provider",
                      group_values=[], value=10.0, observed_at=monday),
            ColumnRow(entity_id="provider:1", entity_type="provider",
                      group_values=[], value=5.0, observed_at=wednesday),
            ColumnRow(entity_id="provider:2", entity_type="provider",
                      group_values=[], value=3.0, observed_at=monday),
        ],
    )
    aggregates = source.load_interval_aggregates(
        knowledge_base_id="kb1", spec=_spec(), interval_starts=[monday]
    )
    by_entity = {agg.entity_id: agg.aggregate_value for agg in aggregates}
    assert by_entity == {"provider:1": 15.0, "provider:2": 3.0}
    assert all(agg.peer_group_key == "provider" for agg in aggregates)


def test_writer_round_trips_signals() -> None:
    writer = InMemoryDerivedRiskSignalWriter()
    signal = DerivedRiskSignal(
        knowledge_base_id="kb1", entity_id="provider:1", entity_type="provider",
        metric_name="weekly_billing", interval_start=datetime(2026, 1, 5, tzinfo=timezone.utc),
        peer_group_key="provider", aggregate_value=15.0, peer_mean=9.0, peer_std=6.0,
        z_score=1.0, signal_value=0.25, weight=1.0, rationale="x", correlation_id="c1",
    )
    assert writer.write_signals([signal]) == 1
    latest = writer.latest_signals(knowledge_base_id="kb1", entity_id="provider:1")
    assert latest[0].metric_name == "weekly_billing"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/analytics/peerstats/test_in_memory_adapters.py -v`
Expected: FAIL — `ModuleNotFoundError: analytics.peerstats.adapters`.

- [ ] **Step 3: Create service_models.py**

Create `backend/analytics/peerstats/service_models.py`:

```python
"""Service-boundary models for peerstats compute requests/responses."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from config.schema import PeerMetricSpec


class PeerStatsComputeRequest(BaseModel):
    """A request to compute peer z-scores for one spec over given intervals."""

    knowledge_base_id: str
    spec: PeerMetricSpec
    interval_starts: list[datetime] = Field(default_factory=lambda: [])
    correlation_id: str


class PeerStatsComputeResponse(BaseModel):
    """The outcome of one peerstats compute call."""

    metric_name: str
    signals_written: int = Field(ge=0)
    affected_entity_ids: list[str] = Field(default_factory=lambda: [])
```

- [ ] **Step 4: Create adapter protocols + ColumnRow**

Create `backend/analytics/peerstats/adapters/protocols.py`:

```python
"""Adapter protocols for peerstats record reads and signal writes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable

from analytics.peerstats.models import DerivedRiskSignal, PeerAggregate
from config.schema import PeerMetricSpec


@dataclass(frozen=True, slots=True)
class ColumnRow:
    """One record's contribution to a metric: an entity value at a time."""

    entity_id: str
    entity_type: str
    group_values: list[str] = field(default_factory=lambda: [])
    value: float = 0.0
    observed_at: datetime = datetime.min


@runtime_checkable
class RecordColumnSourceProtocol(Protocol):
    """Load per-entity, per-interval aggregates for a metric spec."""

    def load_interval_aggregates(
        self,
        *,
        knowledge_base_id: str,
        spec: PeerMetricSpec,
        interval_starts: list[datetime],
    ) -> list[PeerAggregate]: ...


@runtime_checkable
class DerivedRiskSignalWriterProtocol(Protocol):
    """Persist derived risk signals idempotently."""

    def write_signals(self, signals: list[DerivedRiskSignal]) -> int: ...
```

- [ ] **Step 5: Create service protocol**

Create `backend/analytics/peerstats/protocols.py`:

```python
"""Service-boundary protocol for peerstats."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from analytics.peerstats.service_models import (
    PeerStatsComputeRequest,
    PeerStatsComputeResponse,
)


@runtime_checkable
class PeerStatsServiceProtocol(Protocol):
    """Compute and persist peer-group z-score signals for a metric spec."""

    def compute(
        self, request: PeerStatsComputeRequest
    ) -> PeerStatsComputeResponse: ...
```

- [ ] **Step 6: Create in-memory adapters**

Create `backend/analytics/peerstats/adapters/__init__.py` (empty) and `backend/analytics/peerstats/adapters/in_memory.py`:

```python
"""In-memory peerstats adapters for tests and local development."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from analytics.peerstats.adapters.protocols import ColumnRow
from analytics.peerstats.aggregation import (
    apply_aggregation,
    bucket_start,
    peer_group_key,
)
from analytics.peerstats.models import DerivedRiskSignal, PeerAggregate
from config.schema import PeerMetricSpec

__all__ = ["InMemoryDerivedRiskSignalWriter", "InMemoryRecordColumnSource"]


class InMemoryRecordColumnSource:
    """Aggregate seeded column rows in Python, mirroring the Postgres adapter."""

    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], list[ColumnRow]] = defaultdict(list)

    def add_rows(
        self, knowledge_base_id: str, record_type: str, rows: list[ColumnRow]
    ) -> None:
        self._rows[(knowledge_base_id, record_type)].extend(rows)

    def load_interval_aggregates(
        self,
        *,
        knowledge_base_id: str,
        spec: PeerMetricSpec,
        interval_starts: list[datetime],
    ) -> list[PeerAggregate]:
        wanted = set(interval_starts)
        buckets: dict[tuple[str, str, str, datetime], list[float]] = defaultdict(list)
        meta: dict[tuple[str, str, str, datetime], tuple[str, str]] = {}
        for row in self._rows.get((knowledge_base_id, spec.record_type), []):
            start = bucket_start(row.observed_at, spec.interval)
            if wanted and start not in wanted:
                continue
            group_key = peer_group_key(row.entity_type, row.group_values)
            key = (row.entity_id, row.entity_type, group_key, start)
            buckets[key].append(row.value)
            meta[key] = (row.entity_type, group_key)
        aggregates: list[PeerAggregate] = []
        for (entity_id, entity_type, group_key, start), values in buckets.items():
            aggregates.append(
                PeerAggregate(
                    entity_id=entity_id,
                    entity_type=entity_type,
                    peer_group_key=group_key,
                    interval_start=start,
                    aggregate_value=apply_aggregation(values, spec.aggregation),
                )
            )
        return aggregates


class InMemoryDerivedRiskSignalWriter:
    """Store derived signals keyed by (kb, entity, metric, interval)."""

    def __init__(self) -> None:
        self._signals: dict[tuple[str, str, str, datetime], DerivedRiskSignal] = {}

    def write_signals(self, signals: list[DerivedRiskSignal]) -> int:
        for signal in signals:
            key = (
                signal.knowledge_base_id,
                signal.entity_id,
                signal.metric_name,
                signal.interval_start,
            )
            self._signals[key] = signal
        return len(signals)

    def latest_signals(
        self, *, knowledge_base_id: str, entity_id: str
    ) -> list[DerivedRiskSignal]:
        by_metric: dict[str, DerivedRiskSignal] = {}
        for signal in self._signals.values():
            if (
                signal.knowledge_base_id != knowledge_base_id
                or signal.entity_id != entity_id
            ):
                continue
            current = by_metric.get(signal.metric_name)
            if current is None or signal.interval_start >= current.interval_start:
                by_metric[signal.metric_name] = signal
        return list(by_metric.values())
```

- [ ] **Step 7: Run tests + gates**

Run: `cd backend && .venv/bin/pytest tests/analytics/peerstats/test_in_memory_adapters.py -v`
Expected: PASS (2 passed).
Run: `cd backend && .venv/bin/pyright analytics/peerstats && .venv/bin/ruff check --no-cache analytics/peerstats`
Expected: 0 errors.

- [ ] **Step 8: Commit**

```bash
git add backend/analytics/peerstats/service_models.py backend/analytics/peerstats/protocols.py \
  backend/analytics/peerstats/adapters/ backend/tests/analytics/peerstats/test_in_memory_adapters.py
git commit -m "feat(peerstats): service models, protocols, in-memory adapters"
```

---

## Task 5: PeerStatsService — the statistical core

**Files:**
- Create: `backend/analytics/peerstats/service.py`
- Modify: `backend/analytics/peerstats/__init__.py` (export service)
- Test: `backend/tests/analytics/peerstats/test_service.py`

The service: loads per-entity aggregates, groups by `(peer_group_key, interval_start)`, computes population mean/std, derives z and signal value per entity, persists signals, and returns the deduped affected entity ids. `min_peers` gates a cohort; `std == 0` yields `z = 0`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/analytics/peerstats/test_service.py`:

```python
"""Tests for PeerStatsService."""

from __future__ import annotations

from datetime import datetime, timezone

from analytics.peerstats.adapters.in_memory import (
    InMemoryDerivedRiskSignalWriter,
    InMemoryRecordColumnSource,
)
from analytics.peerstats.adapters.protocols import ColumnRow
from analytics.peerstats.service import create_peerstats_service
from analytics.peerstats.service_models import PeerStatsComputeRequest
from config.schema import PeerMetricSpec
from events.adapters.in_memory import InMemoryEventBus

MONDAY = datetime(2026, 1, 5, tzinfo=timezone.utc)


def _spec(**overrides: object) -> PeerMetricSpec:
    base: dict[str, object] = dict(
        name="weekly_billing",
        record_type="claim_record",
        entity_type="provider",
        entity_id_field="provider_npi",
        value_column="billed_amount",
        aggregation="sum",
        interval="week",
        min_peers=2,
        z_cap=4.0,
        direction="high",
    )
    base.update(overrides)
    return PeerMetricSpec(**base)  # type: ignore[arg-type]


def _seed(source: InMemoryRecordColumnSource, values: dict[str, float]) -> None:
    rows = [
        ColumnRow(entity_id=eid, entity_type="provider", group_values=[],
                  value=v, observed_at=MONDAY)
        for eid, v in values.items()
    ]
    source.add_rows("kb1", "claim_record", rows)


def _service(
    source: InMemoryRecordColumnSource, writer: InMemoryDerivedRiskSignalWriter
):
    return create_peerstats_service(source, writer=writer, event_bus=InMemoryEventBus())


def test_compute_writes_one_signal_per_entity_with_correct_z() -> None:
    source = InMemoryRecordColumnSource()
    writer = InMemoryDerivedRiskSignalWriter()
    # values [1, 1, 1, 5]: mean=2.0, pop std=sqrt(3)=1.732..., z(5)=1.732
    _seed(source, {"provider:1": 1.0, "provider:2": 1.0, "provider:3": 1.0, "provider:4": 5.0})
    response = _service(source, writer).compute(
        PeerStatsComputeRequest(
            knowledge_base_id="kb1", spec=_spec(), interval_starts=[MONDAY],
            correlation_id="c1",
        )
    )
    assert response.signals_written == 4
    assert set(response.affected_entity_ids) == {f"provider:{i}" for i in range(1, 5)}
    outlier = writer.latest_signals(knowledge_base_id="kb1", entity_id="provider:4")[0]
    assert round(outlier.z_score, 3) == 1.732
    assert round(outlier.signal_value, 4) == round(1.732 / 4.0, 4)


def test_cohort_below_min_peers_is_skipped() -> None:
    source = InMemoryRecordColumnSource()
    writer = InMemoryDerivedRiskSignalWriter()
    _seed(source, {"provider:1": 10.0})  # only 1 peer
    response = _service(source, writer).compute(
        PeerStatsComputeRequest(
            knowledge_base_id="kb1", spec=_spec(min_peers=5),
            interval_starts=[MONDAY], correlation_id="c1",
        )
    )
    assert response.signals_written == 0
    assert response.affected_entity_ids == []


def test_zero_std_yields_zero_z_and_signal() -> None:
    source = InMemoryRecordColumnSource()
    writer = InMemoryDerivedRiskSignalWriter()
    _seed(source, {"provider:1": 4.0, "provider:2": 4.0, "provider:3": 4.0})
    _service(source, writer).compute(
        PeerStatsComputeRequest(
            knowledge_base_id="kb1", spec=_spec(), interval_starts=[MONDAY],
            correlation_id="c1",
        )
    )
    signal = writer.latest_signals(knowledge_base_id="kb1", entity_id="provider:1")[0]
    assert signal.z_score == 0.0
    assert signal.signal_value == 0.0
```

(Confirm the in-memory event bus import path with `grep -rn "class InMemoryEventBus" backend/events`; adjust the import if it differs.)

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/analytics/peerstats/test_service.py -v`
Expected: FAIL — `ModuleNotFoundError: analytics.peerstats.service`.

- [ ] **Step 3: Implement the service**

Create `backend/analytics/peerstats/service.py`:

```python
"""Compute cross-sectional peer-group z-scores and persist them as signals."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from statistics import fmean, pstdev

from analytics.peerstats.adapters.protocols import (
    DerivedRiskSignalWriterProtocol,
    RecordColumnSourceProtocol,
)
from analytics.peerstats.aggregation import z_to_signal
from analytics.peerstats.exceptions import PeerStatsSourceError
from analytics.peerstats.models import DerivedRiskSignal, PeerAggregate
from analytics.peerstats.service_models import (
    PeerStatsComputeRequest,
    PeerStatsComputeResponse,
)
from events.protocols import EventBus


class PeerStatsService:
    """Orchestrate aggregate → peer mean/std → z → signal persistence."""

    def __init__(
        self,
        column_source: RecordColumnSourceProtocol,
        *,
        writer: DerivedRiskSignalWriterProtocol,
        event_bus: EventBus,
    ) -> None:
        self._column_source = column_source
        self._writer = writer
        self._event_bus = event_bus

    def compute(
        self, request: PeerStatsComputeRequest
    ) -> PeerStatsComputeResponse:
        spec = request.spec
        try:
            aggregates = self._column_source.load_interval_aggregates(
                knowledge_base_id=request.knowledge_base_id,
                spec=spec,
                interval_starts=request.interval_starts,
            )
        except PeerStatsSourceError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            raise PeerStatsSourceError("Failed to load interval aggregates.") from exc

        groups: dict[tuple[str, datetime], list[PeerAggregate]] = defaultdict(list)
        for aggregate in aggregates:
            groups[(aggregate.peer_group_key, aggregate.interval_start)].append(
                aggregate
            )

        signals: list[DerivedRiskSignal] = []
        affected: set[str] = set()
        for (group_key, interval_start), members in groups.items():
            if len(members) < spec.min_peers:
                continue
            values = [member.aggregate_value for member in members]
            mean = fmean(values)
            std = pstdev(values)
            for member in members:
                z_score = 0.0 if std == 0.0 else (member.aggregate_value - mean) / std
                signal_value = z_to_signal(
                    z_score, direction=spec.direction, z_cap=spec.z_cap
                )
                rationale = spec.rationale_template.format(
                    name=spec.name, z=z_score, peer_group=group_key
                )
                signals.append(
                    DerivedRiskSignal(
                        knowledge_base_id=request.knowledge_base_id,
                        entity_id=member.entity_id,
                        entity_type=member.entity_type,
                        metric_name=spec.name,
                        interval_start=interval_start,
                        peer_group_key=group_key,
                        aggregate_value=member.aggregate_value,
                        peer_mean=mean,
                        peer_std=std,
                        z_score=z_score,
                        signal_value=signal_value,
                        weight=spec.weight,
                        rationale=rationale,
                        correlation_id=request.correlation_id,
                    )
                )
                affected.add(member.entity_id)

        written = self._writer.write_signals(signals)
        self._event_bus.publish(
            "analytics.peerstats.computed",
            {
                "knowledge_base_id": request.knowledge_base_id,
                "metric_name": spec.name,
                "signals_written": written,
                "correlation_id": request.correlation_id,
            },
        )
        return PeerStatsComputeResponse(
            metric_name=spec.name,
            signals_written=written,
            affected_entity_ids=sorted(affected),
        )


def create_peerstats_service(
    column_source: RecordColumnSourceProtocol,
    *,
    writer: DerivedRiskSignalWriterProtocol,
    event_bus: EventBus,
) -> PeerStatsService:
    """Construct a :class:`PeerStatsService`."""

    return PeerStatsService(column_source, writer=writer, event_bus=event_bus)
```

**Before finalizing:** verify the event-bus publish signature with `grep -n "def publish" backend/events/protocols.py`. If `publish` takes a typed event object rather than `(topic, payload)`, match the existing call style used by `analytics/risk/service.py` (look at how `RiskScoredEvent` is published) and adjust the `self._event_bus.publish(...)` call accordingly. The event is observability-only; keep it consistent with sibling modules.

- [ ] **Step 4: Export the service**

Append to `backend/analytics/peerstats/__init__.py` `__all__` and imports:

```python
from analytics.peerstats.service import PeerStatsService, create_peerstats_service
```

and add `"PeerStatsService"`, `"create_peerstats_service"` to `__all__`.

- [ ] **Step 5: Run tests + gates**

Run: `cd backend && .venv/bin/pytest tests/analytics/peerstats/test_service.py -v`
Expected: PASS (3 passed).
Run: `cd backend && .venv/bin/pyright analytics/peerstats && .venv/bin/ruff check --no-cache analytics/peerstats`
Expected: 0 errors.

- [ ] **Step 6: Commit**

```bash
git add backend/analytics/peerstats/service.py backend/analytics/peerstats/__init__.py \
  backend/tests/analytics/peerstats/test_service.py
git commit -m "feat(peerstats): PeerStatsService statistical core (peer z-scores)"
```

---

## Task 6: Alembic migration — entity_derived_signals

**Files:**
- Create: `backend/database/migrations/versions/0006_entity_derived_signals.py`
- Test: `backend/tests/database/test_migration_0006.py` (mirror existing migration tests if present; otherwise this asserts the revision chain)

- [ ] **Step 1: Write the failing test**

First confirm how migrations are tested: `grep -rln "down_revision\|alembic" backend/tests/database 2>/dev/null`. If a migration-chain test exists, extend it. Otherwise create `backend/tests/database/test_migration_0006.py`:

```python
"""Assert the 0006 migration links to the current head and defines the table."""

from __future__ import annotations

import importlib


def test_revision_chain() -> None:
    module = importlib.import_module(
        "database.migrations.versions.0006_entity_derived_signals"
    )
    assert module.revision == "0006_entity_derived_signals"
    assert module.down_revision == "0005_conversations"


def test_upgrade_sql_creates_table() -> None:
    import inspect

    module = importlib.import_module(
        "database.migrations.versions.0006_entity_derived_signals"
    )
    source = inspect.getsource(module.upgrade)
    assert "CREATE TABLE entity_derived_signals" in source
    assert "PRIMARY KEY (knowledge_base_id, entity_id, metric_name, interval_start)" in source
```

(If `0006_...` is not importable as a dotted name because it starts with a digit, use `importlib.import_module("database.migrations.versions")` + file read, or follow the exact pattern the existing migration tests use. Adjust to match repo convention found in step 1's grep.)

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/database/test_migration_0006.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the migration**

Create `backend/database/migrations/versions/0006_entity_derived_signals.py` (mirrors `0001_persistence_baseline.py` style):

```python
"""Derived peer-group z-score risk signals.

Creates the entity_derived_signals table consumed by PostgresRiskSignalSource.

Revision ID: 0006_entity_derived_signals
Revises: 0005_conversations
Create Date: 2026-06-08
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006_entity_derived_signals"
down_revision: str | None = "0005_conversations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE entity_derived_signals (
            knowledge_base_id text             NOT NULL,
            entity_id         text             NOT NULL,
            entity_type       text             NOT NULL,
            metric_name       text             NOT NULL,
            interval_start    timestamptz      NOT NULL,
            peer_group_key    text             NOT NULL,
            aggregate_value   double precision NOT NULL,
            peer_mean         double precision NOT NULL,
            peer_std          double precision NOT NULL,
            z_score           double precision NOT NULL,
            signal_value      double precision NOT NULL,
            weight            double precision NOT NULL,
            rationale         text             NOT NULL,
            correlation_id    text             NOT NULL,
            computed_at       timestamptz      NOT NULL DEFAULT now(),
            PRIMARY KEY (knowledge_base_id, entity_id, metric_name, interval_start)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_entity_derived_signals_latest "
        "ON entity_derived_signals "
        "(knowledge_base_id, entity_id, metric_name, computed_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS entity_derived_signals")
```

- [ ] **Step 4: Run tests + gate; apply migration against the dev DB**

Run: `cd backend && .venv/bin/pytest tests/database/test_migration_0006.py -v`
Expected: PASS.
If the dev stack is up (`make dev`), apply and verify: `make api-shell` then `alembic upgrade head`, and confirm `\d entity_derived_signals`. Otherwise note that CI/dev will apply it on next boot.
Run: `cd backend && .venv/bin/ruff check --no-cache database/migrations`
Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add backend/database/migrations/versions/0006_entity_derived_signals.py backend/tests/database/test_migration_0006.py
git commit -m "feat(db): entity_derived_signals migration (0006)"
```

---

## Task 7: Postgres peerstats adapters

The Postgres column source aggregates `raw_records` JSONB in SQL: cast `(payload->>value_column)::numeric`, bucket with `date_trunc`, build the entity id as `entity_type || ':' || (payload->>entity_id_field)`, and group by entity + bucket + group key. The writer upserts derived signals.

**Files:**
- Modify: `backend/analytics/peerstats/adapters/postgres.py` (create)
- Test: `backend/tests/analytics/peerstats/test_postgres_adapters.py` (marked `integration`)

- [ ] **Step 1: Write the failing integration test**

Create `backend/tests/analytics/peerstats/test_postgres_adapters.py`:

```python
"""Integration tests for Postgres peerstats adapters (require a live DB)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_module_imports_without_psycopg() -> None:
    # The adapter must import unconditionally (psycopg-free, like sibling adapters).
    from analytics.peerstats.adapters.postgres import (  # noqa: F401
        PostgresDerivedRiskSignalWriter,
        PostgresRecordColumnSource,
    )
```

(Full round-trip integration tests against a live Postgres belong with the other `@pytest.mark.integration` DB tests; model them on `backend/tests/analytics/timeseries` Postgres tests if present. The import test above guarantees the unconditional-import rule and gives non-integration coverage of the module surface.)

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/analytics/peerstats/test_postgres_adapters.py -v`
Expected: FAIL — `ModuleNotFoundError: analytics.peerstats.adapters.postgres`.

- [ ] **Step 3: Implement the Postgres adapters**

Create `backend/analytics/peerstats/adapters/postgres.py`:

```python
"""Postgres-backed peerstats adapters.

``PostgresRecordColumnSource`` aggregates the ``raw_records`` JSONB payload in
SQL; ``PostgresDerivedRiskSignalWriter`` upserts ``entity_derived_signals``.
Both depend only on the psycopg-free ``database.ConnectionProvider`` protocol.
"""

from __future__ import annotations

from datetime import datetime
from typing import cast

from analytics.peerstats.exceptions import PeerStatsSourceError
from analytics.peerstats.models import DerivedRiskSignal, PeerAggregate
from config.schema import PeerMetricSpec
from database.protocols import ConnectionProvider, Row

_AGG_FN_SQL: dict[str, str] = {
    "sum": "sum(val)",
    "mean": "avg(val)",
    "count": "count(*)",
    "max": "max(val)",
    "min": "min(val)",
}

_UPSERT_SQL = """
    INSERT INTO entity_derived_signals (
        knowledge_base_id, entity_id, entity_type, metric_name, interval_start,
        peer_group_key, aggregate_value, peer_mean, peer_std, z_score,
        signal_value, weight, rationale, correlation_id
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (knowledge_base_id, entity_id, metric_name, interval_start)
    DO UPDATE SET
        peer_group_key = EXCLUDED.peer_group_key,
        aggregate_value = EXCLUDED.aggregate_value,
        peer_mean = EXCLUDED.peer_mean,
        peer_std = EXCLUDED.peer_std,
        z_score = EXCLUDED.z_score,
        signal_value = EXCLUDED.signal_value,
        weight = EXCLUDED.weight,
        rationale = EXCLUDED.rationale,
        correlation_id = EXCLUDED.correlation_id,
        computed_at = now()
"""


def _build_agg_sql(spec: PeerMetricSpec) -> str:
    agg_expr = _AGG_FN_SQL[spec.aggregation]
    time_expr = (
        "ingested_at"
        if spec.time_column is None
        else f"(payload->>%(time_col)s)::timestamptz"
    )
    # Grouping-column values are appended to the peer-group key in order.
    group_exprs = "".join(
        f" || '|' || coalesce(payload->>%(g{i})s, '')"
        for i in range(len(spec.group_by))
    )
    return f"""
        SELECT
            %(entity_type)s || ':' || (payload->>%(id_field)s) AS entity_id,
            %(entity_type)s AS entity_type,
            %(entity_type)s{group_exprs} AS peer_group_key,
            date_trunc(%(interval)s, {time_expr}) AS interval_start,
            {agg_expr} AS aggregate_value
        FROM (
            SELECT payload, ingested_at,
                   (payload->>%(value_col)s)::numeric AS val
            FROM raw_records
            WHERE knowledge_base_id = %(kb)s
              AND record_type = %(record_type)s
              AND payload ? %(value_col)s
              AND payload ? %(id_field)s
        ) AS rows
        GROUP BY entity_id, entity_type, peer_group_key, interval_start
    """


class PostgresRecordColumnSource:
    """Aggregate raw_records JSONB columns per entity per interval in SQL."""

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def load_interval_aggregates(
        self,
        *,
        knowledge_base_id: str,
        spec: PeerMetricSpec,
        interval_starts: list[datetime],
    ) -> list[PeerAggregate]:
        params: dict[str, object] = {
            "kb": knowledge_base_id,
            "record_type": spec.record_type,
            "entity_type": spec.entity_type,
            "id_field": spec.entity_id_field,
            "value_col": spec.value_column,
            "interval": spec.interval,
        }
        if spec.time_column is not None:
            params["time_col"] = spec.time_column
        for i, col in enumerate(spec.group_by):
            params[f"g{i}"] = col
        try:
            with self._provider.connection() as conn:
                rows = conn.execute(_build_agg_sql(spec), params).fetchall()
        except Exception as exc:
            raise PeerStatsSourceError(
                "Failed to aggregate record columns."
            ) from exc
        wanted = set(interval_starts)
        aggregates: list[PeerAggregate] = []
        for row in rows:
            interval_start = cast(datetime, row[3])
            if wanted and interval_start not in wanted:
                continue
            aggregates.append(
                PeerAggregate(
                    entity_id=str(row[0]),
                    entity_type=str(row[1]),
                    peer_group_key=str(row[2]),
                    interval_start=interval_start,
                    aggregate_value=float(cast(float, row[4])),
                )
            )
        return aggregates


class PostgresDerivedRiskSignalWriter:
    """Upsert derived risk signals into entity_derived_signals."""

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def write_signals(self, signals: list[DerivedRiskSignal]) -> int:
        if not signals:
            return 0
        try:
            with self._provider.connection() as conn:
                for signal in signals:
                    conn.execute(_UPSERT_SQL, _signal_params(signal))
                conn.commit()
        except Exception as exc:
            raise PeerStatsSourceError(
                "Failed to write derived risk signals."
            ) from exc
        return len(signals)


def _signal_params(signal: DerivedRiskSignal) -> tuple[object, ...]:
    return (
        signal.knowledge_base_id,
        signal.entity_id,
        signal.entity_type,
        signal.metric_name,
        signal.interval_start,
        signal.peer_group_key,
        signal.aggregate_value,
        signal.peer_mean,
        signal.peer_std,
        signal.z_score,
        signal.signal_value,
        signal.weight,
        signal.rationale,
        signal.correlation_id,
    )


def _row_unused(_: Row) -> None:  # pragma: no cover - keeps Row import meaningful
    return None


__all__ = [
    "PostgresDerivedRiskSignalWriter",
    "PostgresRecordColumnSource",
]
```

**Note on parametrization:** the existing `database.protocols.ConnectionProvider.connection().execute` is used elsewhere with positional `%s` params (see `records/adapters/postgres.py`). Confirm whether `execute` supports named (`%(name)s` + dict) parameters with the configured driver via `grep -n "def execute" backend/database/protocols.py` and the psycopg adapter. If only positional params are supported, refactor `_build_agg_sql` to emit `%s` placeholders and pass a positional tuple in the correct order instead of a dict. Do not ship until this is verified against the real adapter. Remove the `_row_unused` shim if `Row` ends up referenced elsewhere.

- [ ] **Step 4: Run tests + gates**

Run: `cd backend && .venv/bin/pytest tests/analytics/peerstats/test_postgres_adapters.py -v`
Expected: PASS (import test passes; integration round-trips run only with `-m integration` against a live DB).
Run: `cd backend && .venv/bin/pyright analytics/peerstats && .venv/bin/ruff check --no-cache analytics/peerstats`
Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add backend/analytics/peerstats/adapters/postgres.py backend/tests/analytics/peerstats/test_postgres_adapters.py
git commit -m "feat(peerstats): Postgres record-column source + derived-signal writer"
```

---

## Task 8: PostgresRiskSignalSource — derived signals → RiskProfile

**Files:**
- Modify: `backend/analytics/risk/adapters/postgres.py` (add class alongside `PostgresRiskHistoryStore`)
- Test: `backend/tests/analytics/risk/test_postgres_signal_source.py`

The source implements the existing `RiskSignalSourceProtocol`: `load_profile` reads the latest `entity_derived_signals` row per metric → `RiskProfile`; `list_ranked_entries` and `load_historical_score` read `risk_score_history` (reuse the existing query shape).

- [ ] **Step 1: Write the failing test (logic + import surface, non-integration)**

Create `backend/tests/analytics/risk/test_postgres_signal_source.py`:

```python
"""Tests for PostgresRiskSignalSource using a fake connection provider."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from analytics.risk.adapters.postgres import PostgresRiskSignalSource


class _FakeCursor:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._rows[0] if self._rows else None


class _FakeConn:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows

    def __enter__(self) -> "_FakeConn":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, _sql: str, _params: object) -> _FakeCursor:
        return _FakeCursor(self._rows)

    def commit(self) -> None:
        return None


class _FakeProvider:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows

    def connection(self) -> _FakeConn:
        return _FakeConn(self._rows)


def test_load_profile_builds_signals_from_rows() -> None:
    now = datetime(2026, 1, 5, tzinfo=timezone.utc)
    # rows: (metric_name, signal_value, weight, rationale)
    rows = [
        ("weekly_billing", 0.4, 1.5, "weekly_billing: z=1.60 vs provider peers"),
        ("weekly_claim_count", 0.2, 1.0, "weekly_claim_count: z=0.80 vs provider peers"),
    ]
    source = PostgresRiskSignalSource(_FakeProvider(rows))  # type: ignore[arg-type]
    profile = source.load_profile(knowledge_base_id="kb1", entity_id="provider:1")
    assert {s.signal_name for s in profile.signals} == {
        "weekly_billing", "weekly_claim_count"
    }
    billing = next(s for s in profile.signals if s.signal_name == "weekly_billing")
    assert billing.value == 0.4
    assert billing.weight == 1.5


def test_load_profile_raises_when_no_signals() -> None:
    source = PostgresRiskSignalSource(_FakeProvider([]))  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        source.load_profile(knowledge_base_id="kb1", entity_id="provider:404")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/analytics/risk/test_postgres_signal_source.py -v`
Expected: FAIL — `ImportError: cannot import name 'PostgresRiskSignalSource'`.

- [ ] **Step 3: Implement PostgresRiskSignalSource**

In `backend/analytics/risk/adapters/postgres.py`, add imports at top (alongside existing):

```python
from analytics.risk.models import RankedRiskEntry, RiskProfile, RiskSignal
```

(Keep the existing `from analytics.risk.models import RiskAssessmentRecord, RiskFactor` import; merge into one line or add as needed.)

Add these SQL constants after `_LATEST_SCORE_SQL`:

```python
_LATEST_SIGNALS_SQL = """
    SELECT DISTINCT ON (metric_name)
        metric_name, signal_value, weight, rationale
    FROM entity_derived_signals
    WHERE knowledge_base_id = %s AND entity_id = %s
    ORDER BY metric_name, computed_at DESC
"""

_RANKED_SQL = """
    SELECT DISTINCT ON (entity_id)
        entity_id, overall_score, risk_level
    FROM risk_score_history
    WHERE knowledge_base_id = %s
    ORDER BY entity_id, assessed_at DESC
"""
```

Add the class:

```python
class PostgresRiskSignalSource:
    """A ``RiskSignalSourceProtocol`` backed by ``entity_derived_signals``.

    ``load_profile`` assembles a profile from the latest derived signal per
    metric; ranking and historical lookups read ``risk_score_history``.
    """

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def load_profile(
        self, *, knowledge_base_id: str, entity_id: str
    ) -> RiskProfile:
        try:
            with self._provider.connection() as conn:
                rows = conn.execute(
                    _LATEST_SIGNALS_SQL, (knowledge_base_id, entity_id)
                ).fetchall()
        except Exception as exc:
            raise RiskSourceError("Failed to load derived risk signals.") from exc
        signals = [
            RiskSignal(
                signal_name=str(row[0]),
                value=float(cast(float, row[1])),
                weight=float(cast(float, row[2])),
                rationale=None if row[3] is None else str(row[3]),
            )
            for row in rows
        ]
        if not signals:
            raise ValueError(
                "No derived risk signals registered for "
                f"knowledge_base_id='{knowledge_base_id}', entity_id='{entity_id}'."
            )
        return RiskProfile(
            knowledge_base_id=knowledge_base_id,
            entity_id=entity_id,
            signals=signals,
        )

    def list_ranked_entries(
        self,
        *,
        knowledge_base_id: str,
        entity_type: str | None,
        limit: int,
    ) -> list[RankedRiskEntry]:
        try:
            with self._provider.connection() as conn:
                rows = conn.execute(_RANKED_SQL, (knowledge_base_id,)).fetchall()
        except Exception as exc:
            raise RiskSourceError("Failed to load ranked risk entries.") from exc
        entries = [
            RankedRiskEntry(
                knowledge_base_id=knowledge_base_id,
                entity_id=str(row[0]),
                entity_type=_entity_type_of(str(row[0])),
                overall_score=float(cast(float, row[1])),
                risk_level=str(row[2]),
            )
            for row in rows
        ]
        if entity_type is not None:
            entries = [e for e in entries if e.entity_type == entity_type]
        entries.sort(key=lambda entry: entry.overall_score, reverse=True)
        return entries[:limit]

    def load_historical_score(
        self, *, knowledge_base_id: str, entity_id: str
    ) -> float | None:
        try:
            with self._provider.connection() as conn:
                row = conn.execute(
                    _LATEST_SCORE_SQL, (knowledge_base_id, entity_id)
                ).fetchone()
        except Exception as exc:
            raise RiskSourceError("Failed to load historical risk score.") from exc
        if row is None:
            return None
        return float(cast(float, row[0]))


def _entity_type_of(entity_id: str) -> str:
    """Derive entity type from the ``type:raw_id`` id convention."""

    return entity_id.split(":", 1)[0] if ":" in entity_id else entity_id
```

Add `RiskSourceError` to the imports at the top: `from analytics.risk.exceptions import RiskHistoryError, RiskSourceError`. Add `"PostgresRiskSignalSource"` to `__all__`.

- [ ] **Step 4: Run tests + gates**

Run: `cd backend && .venv/bin/pytest tests/analytics/risk/test_postgres_signal_source.py -v`
Expected: PASS (2 passed).
Run: `cd backend && .venv/bin/pyright analytics/risk && .venv/bin/ruff check --no-cache analytics/risk`
Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add backend/analytics/risk/adapters/postgres.py backend/tests/analytics/risk/test_postgres_signal_source.py
git commit -m "feat(risk): PostgresRiskSignalSource assembling profiles from derived signals"
```

---

## Task 9: API dependency wiring — Postgres risk signal source

**Files:**
- Modify: `backend/api/dependencies.py` (risk section around lines 1027-1042; imports)
- Test: `backend/tests/api/test_risk_signal_source_wiring.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/api/test_risk_signal_source_wiring.py`:

```python
"""Verify get_risk_signal_source selects the backend by configured database."""

from __future__ import annotations

from analytics.risk.adapters.in_memory import InMemoryRiskSignalSource
from api import dependencies


def test_in_memory_when_no_provider(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    dependencies.get_risk_signal_source.cache_clear()
    monkeypatch.setattr(dependencies, "get_connection_provider", lambda: None)
    source = dependencies.get_risk_signal_source()
    assert isinstance(source, InMemoryRiskSignalSource)
    dependencies.get_risk_signal_source.cache_clear()
```

- [ ] **Step 2: Run to verify it fails or check current behavior**

Run: `cd backend && .venv/bin/pytest tests/api/test_risk_signal_source_wiring.py -v`
Expected: PASS already for the in-memory branch (current code always returns in-memory). This test pins existing behavior so the refactor in Step 3 keeps the no-DB fallback. Proceed to add the Postgres branch.

- [ ] **Step 3: Wire the Postgres source**

In `backend/api/dependencies.py`, add the import near the other risk adapter imports (find with `grep -n "InMemoryRiskSignalSource" backend/api/dependencies.py`):

```python
from analytics.risk.adapters.postgres import PostgresRiskSignalSource
```

Replace the body of `get_risk_signal_source` (lines 1027-1030) with:

```python
@lru_cache(maxsize=1)
def get_risk_signal_source() -> RiskSignalSourceProtocol:
    """Return the risk signal source: Postgres-derived signals when a DB is configured."""
    provider = get_connection_provider()
    if provider is None:
        return InMemoryRiskSignalSource()
    return PostgresRiskSignalSource(provider)
```

- [ ] **Step 4: Run tests + gates**

Run: `cd backend && .venv/bin/pytest tests/api/test_risk_signal_source_wiring.py -v`
Expected: PASS.
Run: `cd backend && .venv/bin/pyright api/dependencies.py && .venv/bin/ruff check --no-cache api`
Expected: 0 errors.
Run the broader API suite to catch regressions: `cd backend && .venv/bin/pytest tests/api -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/api/dependencies.py backend/tests/api/test_risk_signal_source_wiring.py
git commit -m "feat(api): select PostgresRiskSignalSource when a database is configured"
```

---

## Task 10: Worker stage — compute peerstats on ingest, batch+dedup assess

**Files:**
- Modify: `backend/agent/coordinator.py` — `WorkerDependencies` (line 265), `build_risk_signal_source` (line 479), `build_worker_dependencies` (reorder + new deps), `handle_records_ingested` (line 1790), dispatch (line 2568+); new helpers `build_record_column_source`, `build_derived_signal_writer`, `build_peerstats_service`, `_run_peerstats_stage`, `assess_entities`
- Test: `backend/tests/agent/test_peerstats_stage.py`

This is the integration task. Work in small steps.

- [ ] **Step 1: Write the failing test (stage in isolation)**

Create `backend/tests/agent/test_peerstats_stage.py`:

```python
"""Test the peerstats worker stage end-to-end with in-memory adapters."""

from __future__ import annotations

from datetime import datetime, timezone

from analytics.peerstats.adapters.in_memory import (
    InMemoryDerivedRiskSignalWriter,
    InMemoryRecordColumnSource,
)
from analytics.peerstats.adapters.protocols import ColumnRow
from analytics.peerstats.service import create_peerstats_service
from agent.coordinator import run_peerstats_stage
from config.schema import PeerMetricSpec, PeerStatsConfig
from events.adapters.in_memory import InMemoryEventBus

MONDAY = datetime(2026, 1, 5, tzinfo=timezone.utc)


def _spec(name: str, value_column: str) -> PeerMetricSpec:
    return PeerMetricSpec(
        name=name, record_type="claim_record", entity_type="provider",
        entity_id_field="provider_npi", value_column=value_column,
        aggregation="sum", interval="week", min_peers=2,
    )


def test_run_peerstats_stage_returns_deduped_affected_entities() -> None:
    source = InMemoryRecordColumnSource()
    rows = [
        ColumnRow(entity_id="provider:1", entity_type="provider", group_values=[],
                  value=10.0, observed_at=MONDAY),
        ColumnRow(entity_id="provider:2", entity_type="provider", group_values=[],
                  value=2.0, observed_at=MONDAY),
    ]
    source.add_rows("kb1", "claim_record", rows)
    writer = InMemoryDerivedRiskSignalWriter()
    service = create_peerstats_service(source, writer=writer, event_bus=InMemoryEventBus())
    config = PeerStatsConfig(metrics=[_spec("m1", "billed_amount"), _spec("m2", "billed_amount")])

    affected = run_peerstats_stage(
        peerstats_service=service,
        peer_stats_config=config,
        knowledge_base_id="kb1",
        record_type="claim_record",
        interval_starts=[MONDAY],
        correlation_id="c1",
    )
    # provider:1 and provider:2 each touched by two specs → deduped to two ids.
    assert affected == ["provider:1", "provider:2"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/agent/test_peerstats_stage.py -v`
Expected: FAIL — `ImportError: cannot import name 'run_peerstats_stage'`.

- [ ] **Step 3: Add the stage helper to coordinator**

In `backend/agent/coordinator.py`, add imports near the other analytics imports (after the risk import at line 89):

```python
from analytics.peerstats.adapters.in_memory import (
    InMemoryDerivedRiskSignalWriter,
    InMemoryRecordColumnSource,
)
from analytics.peerstats.adapters.postgres import (
    PostgresDerivedRiskSignalWriter,
    PostgresRecordColumnSource,
)
from analytics.peerstats.adapters.protocols import (
    DerivedRiskSignalWriterProtocol,
    RecordColumnSourceProtocol,
)
from analytics.peerstats.service import PeerStatsService, create_peerstats_service
from analytics.peerstats.service_models import PeerStatsComputeRequest
from analytics.peerstats.aggregation import bucket_start
from config.schema import PeerStatsConfig
```

Add the pure stage function (place it near `handle_records_ingested`, before line 1790):

```python
def run_peerstats_stage(
    *,
    peerstats_service: PeerStatsService,
    peer_stats_config: PeerStatsConfig,
    knowledge_base_id: str,
    record_type: str,
    interval_starts: list[datetime],
    correlation_id: str,
) -> list[str]:
    """Compute peer z-scores for every spec matching this feed's record type.

    Returns the deduped, sorted list of entity ids that received signals so the
    caller can assess each affected entity exactly once.
    """

    affected: set[str] = set()
    for spec in peer_stats_config.metrics:
        if spec.record_type != record_type:
            continue
        response = peerstats_service.compute(
            PeerStatsComputeRequest(
                knowledge_base_id=knowledge_base_id,
                spec=spec,
                interval_starts=interval_starts,
                correlation_id=correlation_id,
            )
        )
        affected.update(response.affected_entity_ids)
    return sorted(affected)
```

- [ ] **Step 4: Run the stage test**

Run: `cd backend && .venv/bin/pytest tests/agent/test_peerstats_stage.py -v`
Expected: PASS.

- [ ] **Step 5: Add the assess helper + builders + WorkerDependencies fields**

Add the assess helper near `run_peerstats_stage`:

```python
def assess_entities(
    *,
    risk_service: RiskService,
    knowledge_base_id: str,
    entity_ids: list[str],
) -> int:
    """Assess each entity once; tolerate entities with insufficient signals.

    Each successful assess publishes one RiskScoredEvent (existing Flow 3),
    which the risk-history handler persists to risk_score_history.
    """

    assessed = 0
    for entity_id in entity_ids:
        try:
            risk_service.assess(
                RiskAssessmentRequest(
                    knowledge_base_id=knowledge_base_id, entity_id=entity_id
                )
            )
            assessed += 1
        except RiskError as exc:  # insufficient signals / config / source
            logger.info(
                "Skipping risk assess for entity=%s: %s", entity_id, exc
            )
    return assessed
```

Add `from analytics.risk.exceptions import RiskError` to the risk imports.

Add the builder functions next to `build_risk_signal_source` (line 479). **Modify `build_risk_signal_source` to take the provider** so the worker matches the API wiring:

```python
def build_risk_signal_source(
    provider: ConnectionProvider | None,
) -> RiskSignalSourceProtocol:
    """Return the risk signal source: Postgres-derived when a provider exists."""

    if provider is None:
        return InMemoryRiskSignalSource()
    return PostgresRiskSignalSource(provider)


def build_record_column_source(
    provider: ConnectionProvider | None,
) -> RecordColumnSourceProtocol:
    """Return the peerstats record column source."""

    if provider is None:
        return InMemoryRecordColumnSource()
    return PostgresRecordColumnSource(provider)


def build_derived_signal_writer(
    provider: ConnectionProvider | None,
) -> DerivedRiskSignalWriterProtocol:
    """Return the peerstats derived-signal writer."""

    if provider is None:
        return InMemoryDerivedRiskSignalWriter()
    return PostgresDerivedRiskSignalWriter(provider)


def build_peerstats_service(
    provider: ConnectionProvider | None, *, event_bus: EventBus
) -> PeerStatsService:
    """Assemble the peerstats service from the configured database backend."""

    return create_peerstats_service(
        build_record_column_source(provider),
        writer=build_derived_signal_writer(provider),
        event_bus=event_bus,
    )
```

Add `from analytics.risk.adapters.postgres import PostgresRiskSignalSource` to imports.

Add fields to `WorkerDependencies` (after line 280 `risk_service: RiskService`):

```python
    peerstats_service: PeerStatsService
    peer_stats_config: PeerStatsConfig
```

- [ ] **Step 6: Reorder + wire deps in build_worker_dependencies**

In `build_worker_dependencies`, move the `connection_provider = build_connection_provider(config)` line (currently line 755) to **before** the `risk_service = create_risk_service(...)` block (line 747), then change the risk source call to pass the provider:

```python
    connection_provider = build_connection_provider(config)
    risk_service = create_risk_service(
        build_risk_signal_source(connection_provider),
        event_bus=event_bus,
    )
```

(Delete the now-duplicate `connection_provider = build_connection_provider(config)` at old line 755.)

After `records_config = config.records or RecordsConfig()` (line 790), add:

```python
    peer_stats_config = config.peer_stats or PeerStatsConfig()
    peerstats_service = build_peerstats_service(
        connection_provider, event_bus=event_bus
    )
```

Add to the `return WorkerDependencies(...)` call (after `risk_service=risk_service,` at line 804):

```python
        peerstats_service=peerstats_service,
        peer_stats_config=peer_stats_config,
```

- [ ] **Step 7: Invoke the stage from handle_records_ingested**

Add two parameters to `handle_records_ingested` (line 1790) signature, after `metrics_throttle` (line 1801):

```python
    peerstats_service: PeerStatsService | None = None,
    peer_stats_config: PeerStatsConfig | None = None,
    risk_service: RiskService | None = None,
    peer_stats_enabled: bool = False,
```

Before `return len(records)` (line 1896), insert the best-effort stage:

```python
    if (
        peer_stats_enabled
        and peerstats_service is not None
        and peer_stats_config is not None
        and peer_stats_config.metrics
    ):
        try:
            interval_starts = sorted(
                {
                    bucket_start(record.ingested_at, spec.interval)
                    for spec in peer_stats_config.metrics
                    if spec.record_type == feed.record_type
                    for record in records
                }
            )
            affected = run_peerstats_stage(
                peerstats_service=peerstats_service,
                peer_stats_config=peer_stats_config,
                knowledge_base_id=event.knowledge_base_id,
                record_type=feed.record_type,
                interval_starts=interval_starts,
                correlation_id=event.correlation_id,
            )
            if risk_service is not None and affected:
                assess_entities(
                    risk_service=risk_service,
                    knowledge_base_id=event.knowledge_base_id,
                    entity_ids=affected,
                )
        except Exception:  # best-effort: never break ingest
            logger.exception(
                "Peerstats stage failed for kb=%s correlation=%s",
                event.knowledge_base_id,
                event.correlation_id,
            )
```

(`feed.record_type` is the feed's record type — confirm the attribute name with `grep -n "record_type" backend/config/schema.py` in `RecordFeedConfig`; it is `record_type`.)

- [ ] **Step 8: Pass deps at the dispatch site**

In `_dispatch_event` (the `isinstance(event, RecordsIngestedEvent)` branch near line 2568), find the `return handle_records_ingested(...)` call and add the new keyword arguments, reading from `deps`/locals already in scope (the dispatch block destructures dependencies — match its existing style):

```python
        return handle_records_ingested(
            event,
            records_config=records_config,
            raw_record_store=raw_record_store,
            graph_service=graph_service,
            observation_writer=observation_writer,
            # ... existing kwargs ...
            peerstats_service=peerstats_service,
            peer_stats_config=peer_stats_config,
            risk_service=risk_service,
            peer_stats_enabled=config.capabilities.peer_stats,
        )
```

Read lines 2560-2600 first to see exactly which locals are in scope (e.g. whether it uses `deps.risk_service` or a destructured `risk_service`, and how `config` is named there). Wire `peerstats_service`, `peer_stats_config`, `risk_service` from the same source the surrounding kwargs use; gate with `config.capabilities.peer_stats`. There may be a second call site around line 2772/2914 (other dispatch paths) — update each `handle_records_ingested(...)` call consistently. Find them all: `grep -n "handle_records_ingested(" backend/agent/coordinator.py`.

- [ ] **Step 9: Run the full agent + analytics suites**

Run: `cd backend && .venv/bin/pytest tests/agent tests/analytics -q`
Expected: PASS (fix any signature mismatches surfaced at call sites).
Run: `cd backend && .venv/bin/pyright agent/coordinator.py && .venv/bin/ruff check --no-cache agent`
Expected: 0 errors.

- [ ] **Step 10: Commit**

```bash
git add backend/agent/coordinator.py backend/tests/agent/test_peerstats_stage.py
git commit -m "feat(worker): peerstats stage on ingest + batched/deduped risk assess"
```

---

## Task 11: Medicare default config + docs + full gate

**Files:**
- Modify: `backend/config/defaults/medicare_fraud.yaml`
- Create: `backend/analytics/peerstats/README.md`
- Modify: `backend/README.md`, `docs/architecture.md`
- Modify: `backend/pyproject.toml` (`[tool.pyright]` include) if peerstats isn't covered

- [ ] **Step 1: Add peer_stats to the medicare config**

In `backend/config/defaults/medicare_fraud.yaml`, set `capabilities.peer_stats: true` (under the existing `capabilities:` block) and add a top-level section. The `claims_feed` already defines `record_type: claim_record`, `id_field: claim_id`, columns `provider_npi`, `billed_amount`, `service_date` (verify by reading the `records:` block):

```yaml
peer_stats:
  metrics:
    - name: weekly_provider_billing
      record_type: claim_record
      entity_type: provider
      entity_id_field: provider_npi
      value_column: billed_amount
      aggregation: sum
      interval: week
      time_column: service_date
      direction: high
      z_cap: 4.0
      weight: 1.6
      min_peers: 5
    - name: weekly_provider_claim_count
      record_type: claim_record
      entity_type: provider
      entity_id_field: provider_npi
      value_column: billed_amount
      aggregation: count
      interval: week
      time_column: service_date
      direction: high
      z_cap: 4.0
      weight: 1.0
      min_peers: 5
```

(Two specs satisfy the risk service's ≥2-signal floor for providers.)

- [ ] **Step 2: Validate the config loads**

Run: `cd backend && .venv/bin/pytest tests/config -q` and a quick load check:
`cd backend && CHILI_CONFIG_PATH=config/defaults/medicare_fraud.yaml .venv/bin/python -c "from config.loader import load_domain_config; c=load_domain_config(); print(len((c.peer_stats.metrics if c.peer_stats else [])))"`
Expected: prints `2`. (Confirm the loader function name with `grep -n "def load" backend/config/loader.py`.)

- [ ] **Step 3: Write the module README**

Create `backend/analytics/peerstats/README.md`:

```markdown
# peerstats

Cross-sectional peer-group z-score analytics.

For each `PeerMetricSpec` in `DomainConfig.peer_stats`, this module aggregates a
record column per entity over a config interval (`day`/`week`/`month`), z-scores
each entity's interval aggregate against its peer group (`entity_type` + optional
`group_by` columns) for that interval, and writes a `DerivedRiskSignal` per entity
to `entity_derived_signals`. `PostgresRiskSignalSource` (in `analytics/risk`) reads
those signals so the risk service scores them — the risk module is unchanged.

## Flow
1. Worker `RecordsIngestedEvent` handler calls `run_peerstats_stage` (best-effort).
2. `PeerStatsService.compute` loads aggregates (`RecordColumnSourceProtocol`),
   computes peer mean/std (population) and z, maps z → `[0,1]` signal value via
   `direction` + `z_cap`, and persists via `DerivedRiskSignalWriterProtocol`.
3. The worker assesses the deduped set of affected entities once each.

## Adapters
- In-memory (`adapters/in_memory.py`) — tests/dev.
- Postgres (`adapters/postgres.py`) — aggregates `raw_records` JSONB in SQL,
  upserts `entity_derived_signals`.

## Edge cases
Cohort `< min_peers` → no signal; `std == 0` → `z = 0`; missing/non-numeric column
value → record skipped; group membership computed per interval.
```

- [ ] **Step 4: Update backend README + architecture**

In `backend/README.md`, add `analytics/peerstats/` to the module map and a Current State line noting the records → peer z-scores → risk signals path and the `peer_stats` capability flag.

In `docs/architecture.md`, add the peerstats stage to the worker flow description (Flow 1 now also computes peer z-scores and assesses affected entities) and note the new `entity_derived_signals` table and `PostgresRiskSignalSource`.

- [ ] **Step 5: Ensure pyright covers peerstats**

Check `grep -n "include" backend/pyproject.toml` under `[tool.pyright]`. If `analytics/peerstats` is not already covered by an existing glob, add `"analytics/peerstats"` (and the test path if test dirs are explicitly listed) to the include list.

- [ ] **Step 6: Full gate**

Run from `backend/`:
```bash
.venv/bin/pyright
.venv/bin/ruff check --no-cache .
.venv/bin/pytest --cov -q
```
Expected: pyright 0 errors; ruff clean; pytest green with coverage ≥85% per package (add tests if peerstats or the new risk/postgres lines fall below — e.g. cover `list_ranked_entries`, `load_historical_score`, and the `assess_entities` skip path).

- [ ] **Step 7: Regenerate OpenAPI to confirm no contract drift**

The risk/timeseries response contracts are unchanged, but verify no drift:
```bash
PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json
cd chili_app && npm run codegen:api
git diff --stat chili_app/src/lib/api/schema.ts
```
Expected: no change to `schema.ts` (no frontend-consumed model changed). If `chili_app/openapi.json` changed only by formatting, revert it.

- [ ] **Step 8: Commit**

```bash
git add backend/config/defaults/medicare_fraud.yaml backend/analytics/peerstats/README.md \
  backend/README.md docs/architecture.md backend/pyproject.toml
git commit -m "docs+config(peerstats): medicare specs, README, architecture, pyright include"
```

---

## Self-Review (completed by plan author)

**Spec coverage:**
- Step 1 of design (config params/columns) → Task 1 + Task 11.
- Step 2 (read columns from records DB) → Task 7 `PostgresRecordColumnSource` (raw_records JSONB).
- Step 3 (timeseries of aggregates over config intervals) → Task 3 `bucket_start`/`apply_aggregation` + Task 7 SQL.
- Step 4 (z-scores vs peer groups per interval) → Task 5 `PeerStatsService`.
- Step 5 (feed risk) → Task 8 `PostgresRiskSignalSource` + Task 9 wiring + Task 10 assess loop.
- Batching+dedup of assess → Task 10 `run_peerstats_stage` (deduped affected set) + `assess_entities`.
- Persistence table → Task 6. Edge cases → Task 5 tests. Docs → Task 11.

**Type consistency:** `load_interval_aggregates`, `write_signals`, `compute`, `run_peerstats_stage`, `assess_entities`, `build_peerstats_service`, `PostgresRiskSignalSource.load_profile` names are used identically across tasks. `DerivedRiskSignal`/`PeerAggregate`/`ColumnRow`/`PeerMetricSpec`/`PeerStatsConfig` field names match between definition (Tasks 1-4) and use (Tasks 5-10).

**Verification flags (must confirm against real code during execution):** event-bus `publish` signature (Task 5), `ConnectionProvider.execute` named-vs-positional params (Task 7), `RecordFeedConfig.record_type` attribute (Task 10), all `handle_records_ingested` call sites (Task 10), config loader function name (Task 11). Each is called out inline at its task.
