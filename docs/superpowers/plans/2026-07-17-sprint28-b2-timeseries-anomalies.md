# Sprint 2026-28 B2 — Ingest-Triggered Timeseries Anomaly Detection: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run self-history anomaly detection on per-entity record-aggregate
series as an ingest pipeline stage after peerstats, persist anomaly points to
a new `timeseries_anomalies` table, feed anomaly severities into
`entity_derived_signals` (joining peerstats z-scores in the risk profile),
and serve the real series + persisted anomalies from
`GET /analytics/timeseries/{entity_id}` with an unchanged response contract.

**Architecture:** Spec `docs/superpowers/specs/2026-07-17-sprint28-b2-timeseries-anomalies-design.md`
(read it first — especially §2 owner rulings and the 2026-07-17 amendments).
Series come from `raw_records` interval aggregates via the peerstats
`RecordColumnSourceProtocol` (NOT the `observations` hypertable — superseded
ruling). Detection reuses the existing `TimeseriesService` strategies. The
stage is best-effort (never breaks ingest) and shares one risk-assess pass
with peerstats.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, Alembic, TimescaleDB/Postgres,
pytest; no new dependencies.

## Global Constraints

- pyright strict 0 errors (bare `pyright` from `backend/`, venv:
  `backend/.venv/bin/pyright`); tests are in scope — no `Any`, no private
  imports into included test dirs.
- `backend/.venv/bin/ruff check --no-cache .` clean.
- Coverage ≥ 85% per package (`make test` from repo root — it targets
  `chili_test`, NEVER export `DATABASE_URL=…/chili` yourself).
- Postgres-touching tests: `@pytest.mark.integration` (module-level
  `pytestmark`), skip when `DATABASE_URL` unset.
- After the migration: `make migrate-snapshot` regenerates
  `backend/database/migrations/snapshots/head.sql`; commit the snapshot with
  the migration (CI gate BL-042).
- `EntityTimeseriesResponse` / route signatures must NOT change — verify
  no OpenAPI drift with the contract-regen commands (Task 8).
- Commit after every task; message style `feat(analytics): … (B2)` matching
  recent history; end every commit body with the Claude Code co-author line
  used in this repo.
- All work on branch `feat/sprint-2026-28-b2-timeseries-anomalies`.

---

### Task 1: Config schema — `TimeseriesMetricSpec` + `TimeseriesAnalyticsConfig`

**Files:**
- Modify: `backend/config/schema.py` (new models near `PeerMetricSpec`
  ~line 713; new `DomainConfig` field after `peer_stats` ~line 770;
  cross-reference validation inside `DomainConfig._validate_cross_references`
  which starts ~line 787)
- Test: `backend/tests/config/` — find the file testing `PeerStatsConfig` /
  cross-reference validation (grep `peer_stats` under `backend/tests/config/`)
  and add tests beside the analogous ones.

**Interfaces:**
- Produces: `TimeseriesMetricSpec` (fields: `name: str`, `record_type: str`,
  `entity_type: str`, `entity_id_field: str`, `value_column: str`,
  `aggregation: Literal["sum","mean","count","max","min"]`,
  `interval: Literal["day","week","month"]`, `time_column: str | None`,
  `detection_strategy: Literal["z_score","stl_decomposition","isolation_forest"]`,
  `baseline_window: int`, `min_history: int`, `z_threshold: float`,
  `z_cap: float`, `signal_weight: float`);
  `TimeseriesAnalyticsConfig` (`metrics: list[TimeseriesMetricSpec]`);
  `DomainConfig.timeseries: TimeseriesAnalyticsConfig | None = None`.
  Every later task consumes these exact names.

- [ ] **Step 1: Write the failing tests**

```python
def test_timeseries_metric_spec_rejects_min_history_at_or_below_baseline() -> None:
    with pytest.raises(ValidationError):
        TimeseriesMetricSpec(
            name="m",
            record_type="claim_record",
            entity_type="provider",
            entity_id_field="npi",
            value_column="amount",
            aggregation="sum",
            interval="week",
            baseline_window=5,
            min_history=5,
        )


def test_domain_config_rejects_timeseries_spec_with_unknown_record_type() -> None:
    config = _build_minimal_config()  # reuse the module's existing minimal-config helper
    payload = config.model_dump()
    payload["timeseries"] = {
        "metrics": [
            {
                "name": "m",
                "record_type": "no_such_type",
                "entity_type": "provider",
                "entity_id_field": "npi",
                "value_column": "amount",
                "aggregation": "sum",
                "interval": "week",
            }
        ]
    }
    with pytest.raises(ValidationError, match="no_such_type"):
        DomainConfig.model_validate(payload)


def test_domain_config_rejects_timeseries_value_column_missing_from_schema() -> None:
    # Build a config whose records feed has record_type "claim_record" and a
    # record_schema WITHOUT "not_a_column"; expect a ValidationError naming it.
    ...


def test_domain_config_accepts_valid_timeseries_spec() -> None:
    # Same feed; spec references real schema fields; model validates clean and
    # config.timeseries.metrics[0].detection_strategy == "z_score" (default).
    ...
```

Fill the `...` bodies following the file's existing fixture helpers (there
are cross-reference tests for feed observations to copy the setup from).

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/bin/pytest tests/config/ -k timeseries -v` (from `backend/`)
Expected: FAIL — `TimeseriesMetricSpec` not defined.

- [ ] **Step 3: Implement**

In `backend/config/schema.py`, directly below `PeerStatsConfig`:

```python
class TimeseriesMetricSpec(BaseModel):
    """One self-history anomaly-detection series derived from a record column.

    The aggregate identity (record_type … time_column) mirrors
    ``PeerMetricSpec`` so the peerstats record-column SQL can serve both:
    peerstats compares an entity to its peers cross-sectionally; a
    timeseries spec compares an entity to its own interval history.
    """

    name: str
    record_type: str
    entity_type: str
    entity_id_field: str
    value_column: str
    aggregation: Literal["sum", "mean", "count", "max", "min"]
    interval: Literal["day", "week", "month"]
    time_column: str | None = None
    detection_strategy: Literal[
        "z_score", "stl_decomposition", "isolation_forest"
    ] = "z_score"
    baseline_window: int = Field(default=5, gt=1)
    min_history: int = Field(default=6, gt=2)
    z_threshold: float = Field(default=2.0, gt=0.0)
    z_cap: float = Field(default=4.0, gt=0.0)
    signal_weight: float = Field(default=1.0, gt=0.0)

    @model_validator(mode="after")
    def _validate_history_requirements(self) -> TimeseriesMetricSpec:
        if self.min_history <= self.baseline_window:
            raise ValueError(
                "TimeseriesMetricSpec min_history must exceed baseline_window."
            )
        return self


class TimeseriesAnalyticsConfig(BaseModel):
    """Collection of self-history anomaly series specs for a domain."""

    metrics: list[TimeseriesMetricSpec] = Field(
        default_factory=lambda: cast(list[TimeseriesMetricSpec], [])
    )
```

(Match `PeerStatsConfig`'s exact `default_factory` idiom — copy whichever
form that class uses so pyright stays clean.)

Add to `DomainConfig` immediately after `peer_stats`:

```python
    timeseries: TimeseriesAnalyticsConfig | None = None
```

Append inside `DomainConfig._validate_cross_references` (after the feed
loop, before errors are raised — mirror the structure used for
`feed.observations` checks):

```python
        if self.timeseries is not None and self.timeseries.metrics:
            feeds = list(self.records.feeds) if self.records is not None else []
            feeds_by_record_type: dict[str, list[RecordFeedConfig]] = {}
            for feed in feeds:
                feeds_by_record_type.setdefault(feed.record_type, []).append(feed)
            for spec in self.timeseries.metrics:
                matching = feeds_by_record_type.get(spec.record_type, [])
                if not matching:
                    errors.append(
                        f"Timeseries metric '{spec.name}' references record_type "
                        f"'{spec.record_type}' not declared by any records feed."
                    )
                    continue
                for feed in matching:
                    schema_fields = feed.record_schema
                    label = (
                        f"Timeseries metric '{spec.name}' on records feed "
                        f"'{feed.name}'"
                    )
                    if spec.entity_id_field not in schema_fields:
                        errors.append(
                            f"{label}: entity_id_field '{spec.entity_id_field}' "
                            f"is not in record_schema."
                        )
                    value_def = schema_fields.get(spec.value_column)
                    if value_def is None:
                        errors.append(
                            f"{label}: value_column '{spec.value_column}' is not "
                            f"in record_schema."
                        )
                    elif value_def.type.value not in ("integer", "decimal"):
                        errors.append(
                            f"{label}: value_column '{spec.value_column}' must be "
                            f"numeric (integer or decimal), got "
                            f"'{value_def.type.value}'."
                        )
                    if spec.time_column is not None:
                        time_def = schema_fields.get(spec.time_column)
                        if time_def is None:
                            errors.append(
                                f"{label}: time_column '{spec.time_column}' is "
                                f"not in record_schema."
                            )
                        elif time_def.type.value not in ("date", "datetime"):
                            errors.append(
                                f"{label}: time_column '{spec.time_column}' must "
                                f"be a date or datetime field, got "
                                f"'{time_def.type.value}'."
                            )
```

Adapt local variable names (`errors`, the property-definition `.type.value`
access) to exactly what the surrounding validator uses — read it first.

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest tests/config/ -v` (from `backend/`)
Expected: PASS (all — including pre-existing config tests).

- [ ] **Step 5: Commit**

```bash
git add backend/config/schema.py backend/tests/config/
git commit -m "feat(config): TimeseriesMetricSpec + TimeseriesAnalyticsConfig with cross-reference validation (B2)"
```

---

### Task 2: `timeseries_anomalies` persistence — model, protocol, adapters, migration

**Files:**
- Modify: `backend/analytics/timeseries/models.py` (add `TimeseriesAnomalyRecord`)
- Modify: `backend/analytics/timeseries/adapters/protocols.py` (add `TimeseriesAnomalyStoreProtocol`)
- Modify: `backend/analytics/timeseries/adapters/in_memory.py` (add `InMemoryTimeseriesAnomalyStore`)
- Modify: `backend/analytics/timeseries/adapters/postgres.py` (add `PostgresTimeseriesAnomalyStore`)
- Create: `backend/database/migrations/versions/0011_timeseries_anomalies.py`
- Test: `backend/tests/analytics/timeseries/test_anomaly_store.py` (new),
  `backend/tests/analytics/timeseries/test_anomaly_store_postgres.py` (new, integration)

**Interfaces:**
- Consumes: `TimeseriesMetricSpec` naming only indirectly (strategy string).
- Produces:
  - `TimeseriesAnomalyRecord(knowledge_base_id: str, entity_id: str,
    metric_name: str, observed_at: datetime, observed_value: float,
    expected_value: float, z_score: float (ge=0), severity: float (0..1),
    detection_strategy: str, correlation_id: str)`
  - `TimeseriesAnomalyStoreProtocol` with
    `write_anomalies(records: list[TimeseriesAnomalyRecord]) -> int`,
    `load_anomalies(*, knowledge_base_id: str, entity_id: str,
    metric_name: str) -> list[TimeseriesAnomalyRecord]`,
    `delete_by_kb(knowledge_base_id: str) -> int`
  - `InMemoryTimeseriesAnomalyStore`, `PostgresTimeseriesAnomalyStore(provider)`
  - Table `timeseries_anomalies`, PK `(knowledge_base_id, entity_id,
    metric_name, observed_at)`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/analytics/timeseries/test_anomaly_store.py`:

```python
"""In-memory timeseries anomaly store behavior."""

from __future__ import annotations

from datetime import UTC, datetime

from analytics.timeseries.adapters.in_memory import InMemoryTimeseriesAnomalyStore
from analytics.timeseries.models import TimeseriesAnomalyRecord


def _record(observed_at: datetime, *, severity: float = 0.8) -> TimeseriesAnomalyRecord:
    return TimeseriesAnomalyRecord(
        knowledge_base_id="kb-1",
        entity_id="provider:1",
        metric_name="weekly_billing_self",
        observed_at=observed_at,
        observed_value=900.0,
        expected_value=100.0,
        z_score=3.2,
        severity=severity,
        detection_strategy="z_score",
        correlation_id="corr-1",
    )


def test_write_then_load_returns_ordered_anomalies() -> None:
    store = InMemoryTimeseriesAnomalyStore()
    later = _record(datetime(2026, 2, 1, tzinfo=UTC))
    earlier = _record(datetime(2026, 1, 1, tzinfo=UTC))
    assert store.write_anomalies([later, earlier]) == 2
    loaded = store.load_anomalies(
        knowledge_base_id="kb-1", entity_id="provider:1", metric_name="weekly_billing_self"
    )
    assert [r.observed_at for r in loaded] == [earlier.observed_at, later.observed_at]


def test_write_upserts_on_conflict_key() -> None:
    store = InMemoryTimeseriesAnomalyStore()
    when = datetime(2026, 1, 1, tzinfo=UTC)
    store.write_anomalies([_record(when, severity=0.5)])
    store.write_anomalies([_record(when, severity=0.9)])
    loaded = store.load_anomalies(
        knowledge_base_id="kb-1", entity_id="provider:1", metric_name="weekly_billing_self"
    )
    assert len(loaded) == 1
    assert loaded[0].severity == 0.9


def test_delete_by_kb_scopes_to_one_kb() -> None:
    store = InMemoryTimeseriesAnomalyStore()
    store.write_anomalies([_record(datetime(2026, 1, 1, tzinfo=UTC))])
    other = _record(datetime(2026, 1, 1, tzinfo=UTC)).model_copy(
        update={"knowledge_base_id": "kb-2"}
    )
    store.write_anomalies([other])
    assert store.delete_by_kb("kb-1") == 1
    assert store.load_anomalies(
        knowledge_base_id="kb-2", entity_id="provider:1", metric_name="weekly_billing_self"
    )
```

`backend/tests/analytics/timeseries/test_anomaly_store_postgres.py` — mirror
`test_postgres_history_source.py`'s pattern exactly (module-level
`pytestmark = pytest.mark.integration`, `database_url` fixture that
`pytest.skip`s when `DATABASE_URL` unset, provider via
`create_connection_provider(DatabaseConfig(backend="postgres"))`). One test:
write two records (distinct `observed_at`) + one conflicting rewrite with a
new severity, load and assert order + upserted severity, then
`delete_by_kb` and assert `load_anomalies` returns `[]`. Use a unique
`knowledge_base_id` (e.g. `f"kb-anomaly-test-{uuid4()}"`) and delete in a
`finally` block.

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/bin/pytest tests/analytics/timeseries/test_anomaly_store.py -v`
Expected: FAIL — imports don't exist.

- [ ] **Step 3: Implement models + protocol + adapters**

`models.py` (below `AnomalyPoint`):

```python
class TimeseriesAnomalyRecord(BaseModel):
    """A persisted anomalous interval bucket for one entity series."""

    knowledge_base_id: str
    entity_id: str
    metric_name: str
    observed_at: datetime
    observed_value: float
    expected_value: float
    z_score: float = Field(ge=0.0)
    severity: float = Field(ge=0.0, le=1.0)
    detection_strategy: str
    correlation_id: str
```

Add it to `__all__`.

`adapters/protocols.py`:

```python
@runtime_checkable
class TimeseriesAnomalyStoreProtocol(Protocol):
    """Persist and read detected series anomalies idempotently."""

    def write_anomalies(self, records: list[TimeseriesAnomalyRecord]) -> int:
        """Upsert each record on its (kb, entity, metric, observed_at) key."""
        ...

    def load_anomalies(
        self, *, knowledge_base_id: str, entity_id: str, metric_name: str
    ) -> list[TimeseriesAnomalyRecord]:
        """Return the entity metric's anomalies ordered by observed_at."""
        ...

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        """Delete all anomalies for a knowledge base; return rows removed."""
        ...
```

`adapters/in_memory.py`:

```python
class InMemoryTimeseriesAnomalyStore:
    """Dict-backed anomaly store keyed like the Postgres PK."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str, str, datetime], TimeseriesAnomalyRecord] = {}

    def write_anomalies(self, records: list[TimeseriesAnomalyRecord]) -> int:
        for record in records:
            key = (
                record.knowledge_base_id,
                record.entity_id,
                record.metric_name,
                record.observed_at,
            )
            self._records[key] = record
        return len(records)

    def load_anomalies(
        self, *, knowledge_base_id: str, entity_id: str, metric_name: str
    ) -> list[TimeseriesAnomalyRecord]:
        matches = [
            record
            for record in self._records.values()
            if record.knowledge_base_id == knowledge_base_id
            and record.entity_id == entity_id
            and record.metric_name == metric_name
        ]
        return sorted(matches, key=lambda record: record.observed_at)

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        keys = [key for key in self._records if key[0] == knowledge_base_id]
        for key in keys:
            del self._records[key]
        return len(keys)
```

`adapters/postgres.py` — add below the history source (reuse the module's
`ConnectionProvider`/`Row` imports and error style):

```python
_ANOMALY_UPSERT_SQL = """
    INSERT INTO timeseries_anomalies (
        knowledge_base_id, entity_id, metric_name, observed_at,
        observed_value, expected_value, z_score, severity,
        detection_strategy, correlation_id
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (knowledge_base_id, entity_id, metric_name, observed_at)
    DO UPDATE SET
        observed_value = EXCLUDED.observed_value,
        expected_value = EXCLUDED.expected_value,
        z_score = EXCLUDED.z_score,
        severity = EXCLUDED.severity,
        detection_strategy = EXCLUDED.detection_strategy,
        correlation_id = EXCLUDED.correlation_id,
        detected_at = now()
"""

_ANOMALY_SELECT_SQL = """
    SELECT observed_at, observed_value, expected_value, z_score, severity,
           detection_strategy, correlation_id
    FROM timeseries_anomalies
    WHERE knowledge_base_id = %s AND entity_id = %s AND metric_name = %s
    ORDER BY observed_at
"""

_ANOMALY_DELETE_BY_KB_SQL = (
    "DELETE FROM timeseries_anomalies WHERE knowledge_base_id = %s"
)


class PostgresTimeseriesAnomalyStore:
    """A ``TimeseriesAnomalyStoreProtocol`` backed by ``timeseries_anomalies``."""

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def write_anomalies(self, records: list[TimeseriesAnomalyRecord]) -> int:
        if not records:
            return 0
        try:
            with self._provider.connection() as conn:
                for record in records:
                    conn.execute(
                        _ANOMALY_UPSERT_SQL,
                        (
                            record.knowledge_base_id,
                            record.entity_id,
                            record.metric_name,
                            record.observed_at,
                            record.observed_value,
                            record.expected_value,
                            record.z_score,
                            record.severity,
                            record.detection_strategy,
                            record.correlation_id,
                        ),
                    )
                conn.commit()
        except Exception as exc:
            raise TimeseriesSourceError("Failed to write timeseries anomalies.") from exc
        return len(records)

    def load_anomalies(
        self, *, knowledge_base_id: str, entity_id: str, metric_name: str
    ) -> list[TimeseriesAnomalyRecord]:
        try:
            with self._provider.connection() as conn:
                rows = conn.execute(
                    _ANOMALY_SELECT_SQL, (knowledge_base_id, entity_id, metric_name)
                ).fetchall()
        except Exception as exc:
            raise TimeseriesSourceError("Failed to load timeseries anomalies.") from exc
        return [
            TimeseriesAnomalyRecord(
                knowledge_base_id=knowledge_base_id,
                entity_id=entity_id,
                metric_name=metric_name,
                observed_at=cast(datetime, row[0]),
                observed_value=float(cast(float, row[1])),
                expected_value=float(cast(float, row[2])),
                z_score=float(cast(float, row[3])),
                severity=float(cast(float, row[4])),
                detection_strategy=cast(str, row[5]),
                correlation_id=cast(str, row[6]),
            )
            for row in rows
        ]

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        try:
            with self._provider.connection() as conn:
                cursor = conn.execute(_ANOMALY_DELETE_BY_KB_SQL, (knowledge_base_id,))
                conn.commit()
                return cursor.rowcount
        except Exception as exc:
            raise TimeseriesSourceError("Failed to delete timeseries anomalies.") from exc
```

Update each file's `__all__`.

- [ ] **Step 4: Write the migration**

`backend/database/migrations/versions/0011_timeseries_anomalies.py` — copy
`0006_entity_derived_signals.py`'s structure exactly:

```python
"""Persisted timeseries anomaly points (BL-047, sprint 2026-28 B2).

Creates the timeseries_anomalies table written by the worker's timeseries
stage and read by the analytics entity-timeseries route.

Revision ID: 0011_timeseries_anomalies
Revises: 0010_event_dlq
Create Date: 2026-07-17
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0011_timeseries_anomalies"
down_revision: str | None = "0010_event_dlq"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE timeseries_anomalies (
            knowledge_base_id  text             NOT NULL,
            entity_id          text             NOT NULL,
            metric_name        text             NOT NULL,
            observed_at        timestamptz      NOT NULL,
            observed_value     double precision NOT NULL,
            expected_value     double precision NOT NULL,
            z_score            double precision NOT NULL,
            severity           double precision NOT NULL,
            detection_strategy text             NOT NULL,
            correlation_id     text             NOT NULL,
            detected_at        timestamptz      NOT NULL DEFAULT now(),
            PRIMARY KEY (knowledge_base_id, entity_id, metric_name, observed_at)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS timeseries_anomalies")
```

Then run: `make migrate-snapshot` (from repo root, dev stack's Postgres up)
and confirm `head.sql` gained the table.

- [ ] **Step 5: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest tests/analytics/timeseries/ -v` (integration
test needs the dev stack Postgres up + migrations applied to `chili_test`;
`make test` handles env, or apply via
`DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/alembic upgrade head`
from `backend/`).
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/analytics/timeseries backend/database/migrations backend/tests/analytics/timeseries
git commit -m "feat(analytics): timeseries anomaly store (protocol, adapters, 0011 migration) (B2)"
```

---

### Task 3: Record-aggregate series source

**Files:**
- Create: `backend/analytics/timeseries/adapters/record_aggregates.py`
- Test: `backend/tests/analytics/timeseries/test_record_aggregates.py` (new)

**Interfaces:**
- Consumes: `RecordColumnSourceProtocol.load_interval_aggregates(*,
  knowledge_base_id: str, spec: PeerMetricSpec, interval_starts:
  list[datetime]) -> list[PeerAggregate]` (from
  `analytics.peerstats.adapters.protocols`); `PeerAggregate` has
  `entity_id/entity_type/peer_group_key/interval_start/aggregate_value`.
  `TimeseriesMetricSpec` from Task 1.
- Produces:
  - `to_peer_spec(spec: TimeseriesMetricSpec) -> PeerMetricSpec`
  - `load_entity_series_map(column_source: RecordColumnSourceProtocol, *,
    knowledge_base_id: str, spec: TimeseriesMetricSpec) ->
    dict[str, TimeSeriesSeries]`
  - `RecordAggregateTimeSeriesSource(column_source, *, specs:
    list[TimeseriesMetricSpec])` implementing
    `TimeSeriesHistorySourceProtocol`, plus `metric_names() -> list[str]`
    (config order).

- [ ] **Step 1: Write the failing tests**

```python
"""Record-aggregate series source over the peerstats column protocol."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from analytics.peerstats.models import PeerAggregate
from analytics.timeseries.adapters.record_aggregates import (
    RecordAggregateTimeSeriesSource,
    load_entity_series_map,
)
from config.schema import PeerMetricSpec, TimeseriesMetricSpec


class _FakeColumnSource:
    """Protocol double returning canned aggregates; records the spec used."""

    def __init__(self, aggregates: list[PeerAggregate]) -> None:
        self._aggregates = aggregates
        self.last_spec: PeerMetricSpec | None = None

    def load_interval_aggregates(
        self,
        *,
        knowledge_base_id: str,
        spec: PeerMetricSpec,
        interval_starts: list[datetime],
    ) -> list[PeerAggregate]:
        self.last_spec = spec
        return self._aggregates


def _spec() -> TimeseriesMetricSpec:
    return TimeseriesMetricSpec(
        name="weekly_billing_self",
        record_type="claim_record",
        entity_type="provider",
        entity_id_field="npi",
        value_column="amount",
        aggregation="sum",
        interval="week",
        time_column="service_date",
    )


def _aggregate(entity_id: str, day: int, value: float) -> PeerAggregate:
    return PeerAggregate(
        entity_id=entity_id,
        entity_type="provider",
        peer_group_key="provider",
        interval_start=datetime(2026, 1, day, tzinfo=UTC),
        aggregate_value=value,
    )


def test_series_map_groups_and_orders_per_entity() -> None:
    source = _FakeColumnSource(
        [
            _aggregate("provider:1", 8, 200.0),
            _aggregate("provider:1", 1, 100.0),
            _aggregate("provider:2", 1, 50.0),
        ]
    )
    series_map = load_entity_series_map(source, knowledge_base_id="kb-1", spec=_spec())
    assert set(series_map) == {"provider:1", "provider:2"}
    values = [obs.value for obs in series_map["provider:1"].observations]
    assert values == [100.0, 200.0]
    assert series_map["provider:1"].metric_name == "weekly_billing_self"
    assert source.last_spec is not None
    assert source.last_spec.value_column == "amount"
    assert source.last_spec.time_column == "service_date"


def test_load_series_returns_one_entity_and_raises_when_absent() -> None:
    source = RecordAggregateTimeSeriesSource(
        _FakeColumnSource([_aggregate("provider:1", 1, 100.0)]), specs=[_spec()]
    )
    series = source.load_series(
        knowledge_base_id="kb-1", entity_id="provider:1", metric_name="weekly_billing_self"
    )
    assert series.observations[0].value == 100.0
    with pytest.raises(ValueError):
        source.load_series(
            knowledge_base_id="kb-1", entity_id="provider:9", metric_name="weekly_billing_self"
        )
    with pytest.raises(ValueError):
        source.load_series(
            knowledge_base_id="kb-1", entity_id="provider:1", metric_name="unknown"
        )


def test_metric_names_preserve_config_order_and_range_is_empty() -> None:
    source = RecordAggregateTimeSeriesSource(_FakeColumnSource([]), specs=[_spec()])
    assert source.metric_names() == ["weekly_billing_self"]
    assert (
        source.load_metric_range(
            knowledge_base_id="kb-1",
            metric_name="weekly_billing_self",
            start=datetime(2026, 1, 1, tzinfo=UTC),
            end=datetime(2026, 2, 1, tzinfo=UTC),
        )
        == []
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/bin/pytest tests/analytics/timeseries/test_record_aggregates.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

`backend/analytics/timeseries/adapters/record_aggregates.py`:

```python
"""Per-entity time series derived from raw_records interval aggregates.

Reuses the peerstats record-column aggregation SQL through
``RecordColumnSourceProtocol`` — a deliberate intra-``analytics`` dependency
(both are submodules of the one analytics module; duplicating the JSONB
aggregation here would violate DRY). Peerstats reads these aggregates
cross-sectionally; this source reads them longitudinally per entity.
"""

from __future__ import annotations

from datetime import datetime

from analytics.peerstats.adapters.protocols import RecordColumnSourceProtocol
from analytics.timeseries.models import TimeSeriesObservation, TimeSeriesSeries
from config.schema import PeerMetricSpec, TimeseriesMetricSpec


def to_peer_spec(spec: TimeseriesMetricSpec) -> PeerMetricSpec:
    """Express a timeseries spec as the aggregate identity peerstats loads."""

    return PeerMetricSpec(
        name=spec.name,
        record_type=spec.record_type,
        entity_type=spec.entity_type,
        entity_id_field=spec.entity_id_field,
        value_column=spec.value_column,
        aggregation=spec.aggregation,
        interval=spec.interval,
        time_column=spec.time_column,
    )


def load_entity_series_map(
    column_source: RecordColumnSourceProtocol,
    *,
    knowledge_base_id: str,
    spec: TimeseriesMetricSpec,
) -> dict[str, TimeSeriesSeries]:
    """One aggregate query, grouped into ordered per-entity series."""

    aggregates = column_source.load_interval_aggregates(
        knowledge_base_id=knowledge_base_id,
        spec=to_peer_spec(spec),
        interval_starts=[],
    )
    observations_by_entity: dict[str, list[TimeSeriesObservation]] = {}
    for aggregate in aggregates:
        observations_by_entity.setdefault(aggregate.entity_id, []).append(
            TimeSeriesObservation(
                observed_at=aggregate.interval_start,
                value=aggregate.aggregate_value,
            )
        )
    series_map: dict[str, TimeSeriesSeries] = {}
    for entity_id, observations in observations_by_entity.items():
        observations.sort(key=lambda observation: observation.observed_at)
        series_map[entity_id] = TimeSeriesSeries(
            knowledge_base_id=knowledge_base_id,
            entity_id=entity_id,
            metric_name=spec.name,
            observations=observations,
        )
    return series_map


class RecordAggregateTimeSeriesSource:
    """A ``TimeSeriesHistorySourceProtocol`` over raw_records aggregates."""

    def __init__(
        self,
        column_source: RecordColumnSourceProtocol,
        *,
        specs: list[TimeseriesMetricSpec],
    ) -> None:
        self._column_source = column_source
        self._specs_by_name: dict[str, TimeseriesMetricSpec] = {
            spec.name: spec for spec in specs
        }

    def metric_names(self) -> list[str]:
        """Configured series names in declaration order."""

        return list(self._specs_by_name)

    def load_series(
        self,
        *,
        knowledge_base_id: str,
        entity_id: str,
        metric_name: str,
    ) -> TimeSeriesSeries:
        spec = self._specs_by_name.get(metric_name)
        if spec is None:
            raise ValueError(f"No timeseries metric spec named '{metric_name}'.")
        series_map = load_entity_series_map(
            self._column_source, knowledge_base_id=knowledge_base_id, spec=spec
        )
        series = series_map.get(entity_id)
        if series is None:
            raise ValueError(
                "No time series registered for "
                f"knowledge_base_id='{knowledge_base_id}', "
                f"entity_id='{entity_id}', metric_name='{metric_name}'."
            )
        return series

    def load_metric_range(
        self,
        *,
        knowledge_base_id: str,
        metric_name: str,
        start: datetime,
        end: datetime,
    ) -> list[TimeSeriesObservation]:
        # Per-entity source; graph-scope metric ranges are
        # entity_metric_history's job (PostgresTimeSeriesHistorySource).
        return []


__all__ = [
    "RecordAggregateTimeSeriesSource",
    "load_entity_series_map",
    "to_peer_spec",
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest tests/analytics/timeseries/ -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/analytics/timeseries/adapters/record_aggregates.py backend/tests/analytics/timeseries/test_record_aggregates.py
git commit -m "feat(analytics): record-aggregate per-entity timeseries source (B2)"
```

---

### Task 4: Worker pipeline stage

**Files:**
- Modify: `backend/agent/coordinator.py` —
  - new factory `build_timeseries_anomaly_store` beside
    `build_observation_writer` (~line 690)
  - new `run_timeseries_stage` beside `run_peerstats_stage` (~line 2653)
  - restructure the peerstats/risk block in `handle_records_ingested`
    (~lines 2845-2872)
  - `WorkerDependencies` fields (~line 363) + `build_worker_dependencies`
    (~line 1076) + the handler's parameter plumbing / dispatch call site
- Test: `backend/tests/agent/` — find the file testing
  `run_peerstats_stage` / `handle_records_ingested` (grep
  `run_peerstats_stage` under `backend/tests/`) and add stage tests beside it.

**Interfaces:**
- Consumes: Task 1 config models; Task 2 store
  (`TimeseriesAnomalyStoreProtocol`, `TimeseriesAnomalyRecord`,
  `InMemoryTimeseriesAnomalyStore`, `PostgresTimeseriesAnomalyStore`);
  Task 3 `load_entity_series_map`; existing `InMemoryTimeSeriesHistorySource`,
  `create_timeseries_service`, `TimeseriesAnalysisRequest`,
  `TimeseriesInsufficientHistoryError`, `TimeseriesConfigurationError`;
  peerstats `z_to_signal(z, *, direction, z_cap)`, `DerivedRiskSignal`,
  `DerivedRiskSignalWriterProtocol`, `RecordColumnSourceProtocol`,
  `build_record_column_source`, `build_derived_signal_writer`.
- Produces: `run_timeseries_stage(...) -> list[str]` (sorted affected entity
  ids); `build_timeseries_anomaly_store(provider) ->
  TimeseriesAnomalyStoreProtocol`; `WorkerDependencies` gains
  `record_column_source: RecordColumnSourceProtocol`,
  `timeseries_anomaly_store: TimeseriesAnomalyStoreProtocol`,
  `timeseries_config: TimeseriesAnalyticsConfig`,
  `timeseries_enabled: bool`. Task 5 consumes
  `timeseries_anomaly_store` for the cascade.

- [ ] **Step 1: Write the failing tests**

Model them on the existing peerstats-stage tests in the same file (reuse its
fixtures/builders). Core cases:

```python
def test_timeseries_stage_persists_anomalies_and_signals_and_returns_affected() -> None:
    """A spiking series yields an anomaly row, a prefixed derived signal, and the entity id."""
    column_source = _FakeColumnSource(  # same double as Task 3's tests; 7 weekly buckets,
        _weekly_aggregates("provider:1", [100.0, 110.0, 90.0, 105.0, 95.0, 100.0, 900.0])
    )
    anomaly_store = InMemoryTimeseriesAnomalyStore()
    signal_writer = InMemoryDerivedRiskSignalWriter()
    affected = run_timeseries_stage(
        column_source=column_source,
        anomaly_store=anomaly_store,
        signal_writer=signal_writer,
        event_bus=InMemoryEventBus(),
        timeseries_config=TimeseriesAnalyticsConfig(metrics=[_stage_spec()]),
        knowledge_base_id="kb-1",
        record_type="claim_record",
        correlation_id="corr-1",
    )
    assert affected == ["provider:1"]
    stored = anomaly_store.load_anomalies(
        knowledge_base_id="kb-1", entity_id="provider:1", metric_name=_stage_spec().name
    )
    assert stored and stored[-1].observed_value == 900.0
    written = signal_writer.written  # adapt to the in-memory writer's actual accessor
    assert written[-1].metric_name == f"timeseries_anomaly:{_stage_spec().name}"
    assert 0.0 <= written[-1].signal_value <= 1.0


def test_timeseries_stage_skips_specs_for_other_record_types() -> None:
    """record_type mismatch -> no queries, no writes, empty affected."""


def test_timeseries_stage_short_history_is_a_controlled_skip() -> None:
    """3 buckets with min_history=6 -> no anomalies, no signals, no exception."""


def test_timeseries_stage_clamps_infinite_z_scores() -> None:
    """Flat baseline then a jump produces z=inf; stored z_score and severity are finite."""
```

(Write the two stub bodies fully — same arrange/act shape as the first
test. Check `InMemoryDerivedRiskSignalWriter`'s real accessor for written
signals — read `backend/analytics/peerstats/adapters/in_memory.py` — and
adjust `written` accordingly. `_stage_spec()` = Task 3's `_spec()` with
`baseline_window=3, min_history=5`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/bin/pytest tests/agent/ -k timeseries_stage -v`
Expected: FAIL — `run_timeseries_stage` not defined.

- [ ] **Step 3: Implement**

Factory (below `build_observation_writer`):

```python
def build_timeseries_anomaly_store(
    provider: ConnectionProvider | None,
) -> TimeseriesAnomalyStoreProtocol:
    """Select the timeseries anomaly store: Postgres when a provider exists."""

    if provider is None:
        return InMemoryTimeseriesAnomalyStore()
    return PostgresTimeseriesAnomalyStore(provider)
```

Stage (below `run_peerstats_stage`; module constant near the other module
constants):

```python
_TIMESERIES_Z_CLAMP = 1.0e6  # flat-baseline jumps yield z=inf; keep stored floats JSON-safe


def run_timeseries_stage(
    *,
    column_source: RecordColumnSourceProtocol,
    anomaly_store: TimeseriesAnomalyStoreProtocol,
    signal_writer: DerivedRiskSignalWriterProtocol,
    event_bus: EventBus,
    timeseries_config: TimeseriesAnalyticsConfig,
    knowledge_base_id: str,
    record_type: str,
    correlation_id: str,
) -> list[str]:
    """Detect self-history anomalies for every spec matching this feed.

    One aggregate query per spec (not per entity); detection runs over a
    batch-local in-memory source. Insufficient history and missing optional
    detection dependencies are controlled skips. Returns the sorted entity
    ids that received an anomaly-derived risk signal so the caller assesses
    each once alongside peerstats-affected ids.
    """

    affected: set[str] = set()
    for spec in timeseries_config.metrics:
        if spec.record_type != record_type:
            continue
        series_map = load_entity_series_map(
            column_source, knowledge_base_id=knowledge_base_id, spec=spec
        )
        if not series_map:
            logger.info(
                "Timeseries stage found no series for metric=%s kb=%s",
                spec.name,
                knowledge_base_id,
            )
            continue
        service = create_timeseries_service(
            InMemoryTimeSeriesHistorySource(series=list(series_map.values())),
            event_bus=event_bus,
        )
        anomaly_records: list[TimeseriesAnomalyRecord] = []
        signals: list[DerivedRiskSignal] = []
        for entity_id in sorted(series_map):
            try:
                response = service.analyze(
                    TimeseriesAnalysisRequest(
                        knowledge_base_id=knowledge_base_id,
                        entity_id=entity_id,
                        metric_name=spec.name,
                        baseline_window=spec.baseline_window,
                        min_history=spec.min_history,
                        z_threshold=spec.z_threshold,
                        detection_strategy=spec.detection_strategy,
                    )
                )
            except TimeseriesInsufficientHistoryError:
                continue  # controlled skip: this entity lacks buckets, others may not
            except TimeseriesConfigurationError as exc:
                logger.info(
                    "Timeseries stage skipped metric=%s: %s", spec.name, exc
                )
                break  # configuration problems (e.g. missing extra) repeat per entity
            if not response.anomalies:
                continue
            for anomaly in response.anomalies:
                bounded_z = min(anomaly.z_score, _TIMESERIES_Z_CLAMP)
                anomaly_records.append(
                    TimeseriesAnomalyRecord(
                        knowledge_base_id=knowledge_base_id,
                        entity_id=entity_id,
                        metric_name=spec.name,
                        observed_at=anomaly.observed_at,
                        observed_value=anomaly.observed_value,
                        expected_value=anomaly.expected_value,
                        z_score=bounded_z,
                        severity=z_to_signal(
                            bounded_z, direction="high", z_cap=spec.z_cap
                        ),
                        detection_strategy=spec.detection_strategy,
                        correlation_id=correlation_id,
                    )
                )
            latest = max(response.anomalies, key=lambda anomaly: anomaly.observed_at)
            latest_z = min(latest.z_score, _TIMESERIES_Z_CLAMP)
            signals.append(
                DerivedRiskSignal(
                    knowledge_base_id=knowledge_base_id,
                    entity_id=entity_id,
                    entity_type=spec.entity_type,
                    metric_name=f"timeseries_anomaly:{spec.name}",
                    interval_start=latest.observed_at,
                    peer_group_key="__self_history__",
                    aggregate_value=latest.observed_value,
                    peer_mean=latest.expected_value,
                    peer_std=(latest.deviation / latest_z if latest_z > 0.0 else 0.0),
                    z_score=latest_z,
                    signal_value=z_to_signal(
                        latest_z, direction="high", z_cap=spec.z_cap
                    ),
                    weight=spec.signal_weight,
                    rationale=(
                        f"{spec.name}: self-history anomaly z={latest_z:.2f} "
                        f"({spec.detection_strategy}, {len(response.anomalies)} "
                        f"anomalous {spec.interval} buckets)"
                    ),
                    correlation_id=correlation_id,
                )
            )
            affected.add(entity_id)
        if anomaly_records:
            anomaly_store.write_anomalies(anomaly_records)
        if signals:
            signal_writer.write_signals(signals)
    return sorted(affected)
```

Imports to add at the top of `coordinator.py` (merge into existing import
blocks): `TimeseriesAnalyticsConfig` (config.schema — extend the existing
config import), `load_entity_series_map`
(`analytics.timeseries.adapters.record_aggregates`),
`InMemoryTimeSeriesHistorySource` (`analytics.timeseries.adapters.in_memory`),
`InMemoryTimeseriesAnomalyStore` (same module),
`PostgresTimeseriesAnomalyStore` (`analytics.timeseries.adapters.postgres`),
`TimeseriesAnomalyStoreProtocol` (`analytics.timeseries.adapters.protocols`),
`TimeseriesAnomalyRecord` (`analytics.timeseries.models`),
`create_timeseries_service` (`analytics.timeseries.service`),
`TimeseriesAnalysisRequest` (`analytics.timeseries.service_models`),
`TimeseriesConfigurationError`, `TimeseriesInsufficientHistoryError`
(`analytics.timeseries.exceptions`), `z_to_signal`
(`analytics.peerstats.aggregation`), `DerivedRiskSignal`
(`analytics.peerstats.models`) — some may already be imported; check.

Restructure `handle_records_ingested` (replace lines ~2845-2872 — the
peerstats `if`/`try` block — keeping the cancellation probe above it
untouched):

```python
    affected: set[str] = set()
    if (
        peer_stats_enabled
        and peerstats_service is not None
        and peer_stats_config is not None
        and peer_stats_config.metrics
    ):
        try:
            affected.update(
                run_peerstats_stage(
                    peerstats_service=peerstats_service,
                    peer_stats_config=peer_stats_config,
                    knowledge_base_id=event.knowledge_base_id,
                    record_type=feed.record_type,
                    correlation_id=event.correlation_id,
                )
            )
        except Exception:  # noqa: BLE001 - best-effort: never break ingest
            logger.exception(
                "Peerstats stage failed for kb=%s correlation=%s",
                event.knowledge_base_id,
                event.correlation_id,
            )
    if (
        timeseries_enabled
        and timeseries_config is not None
        and timeseries_config.metrics
    ):
        try:
            affected.update(
                run_timeseries_stage(
                    column_source=record_column_source,
                    anomaly_store=timeseries_anomaly_store,
                    signal_writer=derived_signal_store,
                    event_bus=event_bus,
                    timeseries_config=timeseries_config,
                    knowledge_base_id=event.knowledge_base_id,
                    record_type=feed.record_type,
                    correlation_id=event.correlation_id,
                )
            )
        except Exception:  # noqa: BLE001 - best-effort: never break ingest
            logger.exception(
                "Timeseries stage failed for kb=%s correlation=%s",
                event.knowledge_base_id,
                event.correlation_id,
            )
    if risk_service is not None and affected:
        try:
            assess_entities(
                risk_service=risk_service,
                knowledge_base_id=event.knowledge_base_id,
                entity_ids=sorted(affected),
                correlation_id=event.correlation_id,
            )
        except Exception:  # noqa: BLE001 - best-effort: never break ingest
            logger.exception(
                "Risk assess stage failed for kb=%s correlation=%s",
                event.knowledge_base_id,
                event.correlation_id,
            )
    return len(records)
```

Behavioral note (document in the commit message): previously a peerstats
infra failure also skipped risk assessment; now each stage is independently
best-effort and risk assessment runs for whichever stage produced signals.
`assess_entities` keeps its own semantics (expected per-entity conditions
swallowed inside; infra errors reach the new wrapper and are logged).

Then thread the new values:
1. Read `handle_records_ingested`'s signature; add parameters
   `timeseries_enabled: bool`, `timeseries_config: TimeseriesAnalyticsConfig | None`,
   `record_column_source: RecordColumnSourceProtocol`,
   `timeseries_anomaly_store: TimeseriesAnomalyStoreProtocol` (and
   `derived_signal_store` / `event_bus` if not already parameters), matching
   the style of the peerstats params.
2. `WorkerDependencies`: add fields
   `record_column_source: RecordColumnSourceProtocol`,
   `timeseries_anomaly_store: TimeseriesAnomalyStoreProtocol`,
   `timeseries_config: TimeseriesAnalyticsConfig`,
   `timeseries_enabled: bool`.
3. `build_worker_dependencies` (near the peerstats block ~line 1093):

```python
    timeseries_config = config.timeseries or TimeseriesAnalyticsConfig()
    record_column_source = build_record_column_source(connection_provider)
    timeseries_anomaly_store = build_timeseries_anomaly_store(connection_provider)
```

   and pass all four in the `WorkerDependencies(...)` construction
   (`timeseries_enabled=config.capabilities.timeseries`).
4. Update the `_dispatch_event` call site for `RecordsIngestedEvent` to pass
   the new arguments from deps (mirror how `peer_stats_config` flows).

(In-memory caveat: with `provider=None` the stage's
`InMemoryRecordColumnSource` is a different instance from the peerstats
service's internal one, so the stage sees no data — acceptable: every real
deployment runs Postgres, and unit tests inject the column source
directly.)

- [ ] **Step 4: Run tests + full agent suite**

Run: `backend/.venv/bin/pytest tests/agent/ -v`
Expected: PASS (new stage tests + all pre-existing handler tests — the
`WorkerDependencies` constructor change will break existing builders; update
those test fixtures with the new fields using in-memory implementations).

- [ ] **Step 5: Commit**

```bash
git add backend/agent backend/tests/agent
git commit -m "feat(agent): ingest-triggered timeseries anomaly stage after peerstats (B2)"
```

---

### Task 5: KB-delete cascade membership

**Files:**
- Modify: `backend/knowledgebases/cleanup.py` (structural purger protocol
  ~line 46, `KbDeletionStores` field ~line 58, step list ~line 100)
- Modify: `build_kb_deletion_stores` (find its definition — grep
  `def build_kb_deletion_stores` in `backend/`) and BOTH call sites
  (worker: `coordinator.py` ~1097; API: grep `build_kb_deletion_stores`
  in `backend/api/`)
- Test: the existing cleanup tests (grep `kb_deletion_steps` under
  `backend/tests/`) — extend.

**Interfaces:**
- Consumes: Task 2's store instances (worker already has
  `timeseries_anomaly_store` from Task 4; API side builds one in Task 6 —
  for this task, construct it inline at the API call site with
  `build_timeseries_anomaly_store`-equivalent logic or the Task 6 DI
  accessor if implementing in order).
- Produces: cascade step `"timeseries_anomalies"`; `KbDeletionStores`
  requires `timeseries_anomaly_store: TimeseriesAnomalyPurger`.

- [ ] **Step 1: Write the failing test**

In the cleanup test file, extend the step-order/coverage test (there will be
an existing assertion listing step names) to include
`"timeseries_anomalies"` positioned directly after `"derived_signals"`, and
add:

```python
def test_kb_delete_purges_timeseries_anomalies() -> None:
    # Build KbDeletionStores exactly as the file's existing fixture does,
    # passing an InMemoryTimeseriesAnomalyStore seeded with one kb-1 record;
    # run the cascade for kb-1; assert load_anomalies(...) returns [].
    ...
```

- [ ] **Step 2: Run to verify it fails**

Run: `backend/.venv/bin/pytest tests/ -k kb_deletion -v` (from `backend/`)
Expected: FAIL — `KbDeletionStores` has no such field.

- [ ] **Step 3: Implement**

`cleanup.py` — protocol beside `GnnClusterPurger` (same structural
rationale):

```python
class TimeseriesAnomalyPurger(Protocol):
    """The slice of the timeseries anomaly store the cascade needs.

    Structural (like ``GnnClusterPurger``) so this module keeps its
    no-cross-module-imports rule; ``PostgresTimeseriesAnomalyStore`` and
    ``InMemoryTimeseriesAnomalyStore`` satisfy it without registration.
    """

    def delete_by_kb(self, knowledge_base_id: str) -> int: ...
```

`KbDeletionStores`: add required field
`timeseries_anomaly_store: TimeseriesAnomalyPurger` next to
`gnn_cluster_store`.

Step list — insert directly after the `"derived_signals"` entry:

```python
        ("timeseries_anomalies", lambda: stores.timeseries_anomaly_store.delete_by_kb(kb)),
```

`build_kb_deletion_stores`: add a
`timeseries_anomaly_store: TimeseriesAnomalyPurger` parameter passed through
to the dataclass. Worker call site passes the instance built in Task 4; API
call site passes its DI-built store (Task 6's `get_timeseries_anomaly_store()`
— if executing tasks in order, create that accessor now exactly as specified
in Task 6 and have Task 6 reuse it).

- [ ] **Step 4: Run to verify pass**

Run: `backend/.venv/bin/pytest tests/ -k "kb_deletion or cleanup" -v`
Expected: PASS (update any other fixture constructing `KbDeletionStores`).

- [ ] **Step 5: Commit**

```bash
git add backend/knowledgebases backend/agent backend/api backend/tests
git commit -m "feat(knowledgebases): timeseries anomalies join the KB-delete cascade (B2)"
```

---

### Task 6: API — real entity route, Postgres metric-range wiring (analytics.07)

**Files:**
- Modify: `backend/api/dependencies.py` (`get_timeseries_history_source`
  ~1267, `get_timeseries_payload` ~898, new accessors, `_LRU_CACHE_SINGLETONS`
  registry ~1710-1751)
- Modify: `backend/api/state.py` (delete `get_timeseries`,
  `_build_timeseries_series`, `_timeseries_source`, `_timeseries_service`
  + now-unused imports)
- Test: `backend/tests/api/test_analytics_router.py`

**Interfaces:**
- Consumes: Task 2 store + Task 3 source; existing
  `PostgresTimeSeriesHistorySource`, `InMemoryTimeSeriesHistorySource`,
  `EntityTimeseriesResponse` / `EntityTimeseriesPointResponse`
  (`api/contracts.py:370-386`), the `get_risk_signal_source` DI-switch
  pattern (`dependencies.py:1246-1252`), and the app's domain-config
  accessor (grep `def get_domain_config` in `dependencies.py` — use
  whatever accessor the file provides).
- Produces: `get_timeseries_anomaly_store()`, `get_entity_series_source()`,
  `get_record_column_source()` (reuse if one already exists — grep first),
  rewritten `get_timeseries_payload`. Route signatures and response models
  unchanged.

- [ ] **Step 1: Write the failing tests**

In `test_analytics_router.py` (follow its existing `client` fixture +
`dependency_overrides` style):

```python
def test_entity_timeseries_serves_series_with_persisted_anomalies() -> None:
    """Override get_entity_series_source with a RecordAggregateTimeSeriesSource over
    a fake column source (3 weekly buckets for provider:1) and
    get_timeseries_anomaly_store with an in-memory store holding an anomaly at
    bucket 3's observed_at. GET /analytics/timeseries/provider:1?kb_id=kb-1
    -> 200; metric_name == the spec name; 3 points; exactly the third point
    has is_anomaly true."""


def test_entity_timeseries_unavailable_when_no_spec_has_data() -> None:
    """Sources return no data -> 200 with availability_status == "unavailable",
    empty points, and a non-null unavailable_reason."""
```

Write both bodies fully using Task 3's `_FakeColumnSource` shape inline.
Delete/replace the old tests that monkeypatched `ApiState._timeseries_source`
(they test the seeded path being removed).

- [ ] **Step 2: Run to verify fail**

Run: `backend/.venv/bin/pytest tests/api/test_analytics_router.py -v`
Expected: new tests FAIL (accessors missing).

- [ ] **Step 3: Implement**

`dependencies.py` — replace `get_timeseries_history_source` (mirroring
`get_risk_signal_source`):

```python
@lru_cache(maxsize=1)
def get_timeseries_history_source() -> TimeSeriesHistorySourceProtocol:
    """Return the graph-scope timeseries source: Postgres when a DB is configured."""
    provider = get_connection_provider()
    if provider is None:
        return InMemoryTimeSeriesHistorySource()
    return PostgresTimeSeriesHistorySource(provider)
```

New accessors (same section; register all new `@lru_cache` functions in
`_LRU_CACHE_SINGLETONS`):

```python
@lru_cache(maxsize=1)
def get_timeseries_anomaly_store() -> TimeseriesAnomalyStoreProtocol:
    """Return the timeseries anomaly store selected by the database backend."""
    provider = get_connection_provider()
    if provider is None:
        return InMemoryTimeseriesAnomalyStore()
    return PostgresTimeseriesAnomalyStore(provider)


@lru_cache(maxsize=1)
def get_record_column_source() -> RecordColumnSourceProtocol:
    """Return the record-aggregate column source selected by the database backend."""
    provider = get_connection_provider()
    if provider is None:
        return InMemoryRecordColumnSource()
    return PostgresRecordColumnSource(provider)


@lru_cache(maxsize=1)
def get_entity_series_source() -> RecordAggregateTimeSeriesSource:
    """Return the per-entity record-aggregate series source."""
    config = get_domain_config()  # use the file's actual config accessor
    specs = list(config.timeseries.metrics) if config.timeseries is not None else []
    return RecordAggregateTimeSeriesSource(get_record_column_source(), specs=specs)
```

(If a record-column-source accessor already exists under another name,
reuse it instead of adding one.)

Rewrite `get_timeseries_payload`:

```python
def get_timeseries_payload(
    entity_id: str = Path(..., description="Entity identifier."),
    kb_id: str = Query(..., min_length=1, description="Knowledge base identifier."),
    source: RecordAggregateTimeSeriesSource = Depends(get_entity_series_source),
    anomaly_store: TimeseriesAnomalyStoreProtocol = Depends(get_timeseries_anomaly_store),
) -> EntityTimeseriesResponse:
    """Return a KB-scoped entity timeseries built from record aggregates."""
    metric_names = source.metric_names()
    for metric_name in metric_names:
        try:
            series = source.load_series(
                knowledge_base_id=kb_id, entity_id=entity_id, metric_name=metric_name
            )
        except ValueError:
            continue  # this spec has no data for the entity; try the next
        anomalies = anomaly_store.load_anomalies(
            knowledge_base_id=kb_id, entity_id=entity_id, metric_name=metric_name
        )
        anomaly_timestamps = {record.observed_at for record in anomalies}
        return EntityTimeseriesResponse(
            entity_id=entity_id,
            metric_name=metric_name,
            points=[
                EntityTimeseriesPointResponse(
                    timestamp=observation.observed_at,
                    value=observation.value,
                    label=observation.observed_at.strftime("%b %d"),
                    is_anomaly=observation.observed_at in anomaly_timestamps,
                )
                for observation in series.observations
            ],
            availability_status="available",
            unavailable_reason=None,
        )
    return EntityTimeseriesResponse(
        entity_id=entity_id,
        metric_name=metric_names[0] if metric_names else "timeseries",
        points=[],
        availability_status="unavailable",
        unavailable_reason="No time series is configured or populated for this entity.",
    )
```

(Infra failures — `TimeseriesSourceError` — deliberately propagate to a 500;
only "no data" `ValueError` falls through to the next spec.)

`state.py`: delete the seeded members and `get_timeseries`; remove imports
that become unused. If Task 5 needed the API cascade store, it now uses
`get_timeseries_anomaly_store()`.

- [ ] **Step 4: Run to verify pass + no contract drift**

Run: `backend/.venv/bin/pytest tests/api/ -v`
Expected: PASS.

From repo root:
```bash
PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json
cd chili_app && npm run codegen:api && cd ..
git diff --stat chili_app/
```
Expected: empty diff (contract unchanged). If anything changed, the route
shape drifted — fix the backend, do not commit frontend churn.

- [ ] **Step 5: Commit**

```bash
git add backend/api backend/tests/api
git commit -m "feat(api): entity timeseries route serves record aggregates + persisted anomalies; Postgres metric-range source via DI (B2, analytics.07)"
```

---

### Task 7: Domain pack config — CMS + housing

**Files:**
- Modify: `backend/config/defaults/medicare_fraud_cms_desynpuf.yaml`
  (capabilities ~line 136; new top-level `peer_stats:` and `timeseries:`
  blocks — place them where `medicare_fraud.yaml` places `peer_stats`)
- Modify: `backend/config/defaults/department_air_force_housing.yaml`
  (capabilities ~line 152-158; new `timeseries:` block)
- Test: the config-defaults loading tests (grep `defaults` under
  `backend/tests/config/`).

**Interfaces:**
- Consumes: Task 1 schema. Field names come from the feeds:
  carrier feeds (`record_type: carrier_claim_record`) key providers on
  `PRF_PHYSN_NPI_1` with payments in `LINE_NCH_PMT_AMT_1`; inpatient
  (`inpatient_claim_record`) keys on `AT_PHYSN_NPI` with `CLM_PMT_AMT`;
  claim dates are `CLM_FROM_DT` (type `date`). Housing `bah_rates` feed:
  `record_type: bah_rate`, `market_id`, `affordability_index` (decimal,
  0-100), `snapshot_date` (date).

- [ ] **Step 1: Write the failing test**

Add to the defaults-loading test file:

```python
def test_cms_pack_declares_peerstats_and_timeseries() -> None:
    config = _load_default("medicare_fraud_cms_desynpuf")  # use the file's existing loader helper
    assert config.capabilities.peer_stats is True
    assert config.peer_stats is not None and len(config.peer_stats.metrics) == 2
    assert config.timeseries is not None
    names = [spec.name for spec in config.timeseries.metrics]
    assert names == ["weekly_carrier_billing_self", "monthly_inpatient_billing_self"]


def test_housing_pack_declares_timeseries() -> None:
    config = _load_default("department_air_force_housing")
    assert config.capabilities.timeseries is True
    assert config.timeseries is not None
    assert config.timeseries.metrics[0].name == "monthly_affordability_trend"
```

- [ ] **Step 2: Run to verify fail**, then **Step 3: Implement**

CMS — set `peer_stats: true` inside `capabilities:` and add top-level:

```yaml
peer_stats:
  metrics:
    - name: weekly_carrier_billing
      record_type: carrier_claim_record
      entity_type: provider
      entity_id_field: PRF_PHYSN_NPI_1
      value_column: LINE_NCH_PMT_AMT_1
      aggregation: sum
      interval: week
      time_column: CLM_FROM_DT
      direction: high
      z_cap: 4.0
      weight: 1.5
      min_peers: 5
    - name: monthly_inpatient_billing
      record_type: inpatient_claim_record
      entity_type: provider
      entity_id_field: AT_PHYSN_NPI
      value_column: CLM_PMT_AMT
      aggregation: sum
      interval: month
      time_column: CLM_FROM_DT
      direction: high
      z_cap: 4.0
      weight: 1.5
      min_peers: 5

timeseries:
  metrics:
    - name: weekly_carrier_billing_self
      record_type: carrier_claim_record
      entity_type: provider
      entity_id_field: PRF_PHYSN_NPI_1
      value_column: LINE_NCH_PMT_AMT_1
      aggregation: sum
      interval: week
      time_column: CLM_FROM_DT
      detection_strategy: z_score
      baseline_window: 4
      min_history: 6
      z_threshold: 2.5
      z_cap: 4.0
      signal_weight: 1.0
    - name: monthly_inpatient_billing_self
      record_type: inpatient_claim_record
      entity_type: provider
      entity_id_field: AT_PHYSN_NPI
      value_column: CLM_PMT_AMT
      aggregation: sum
      interval: month
      time_column: CLM_FROM_DT
      detection_strategy: z_score
      baseline_window: 3
      min_history: 5
      z_threshold: 2.5
      z_cap: 4.0
      signal_weight: 1.0
```

Housing — ensure `timeseries: true` under `capabilities:` and add:

```yaml
timeseries:
  metrics:
    - name: monthly_affordability_trend
      record_type: bah_rate
      entity_type: allowance_market_snapshot
      entity_id_field: market_id
      value_column: affordability_index
      aggregation: mean
      interval: month
      time_column: snapshot_date
      detection_strategy: z_score
      baseline_window: 3
      min_history: 5
      z_threshold: 2.0
      z_cap: 4.0
      signal_weight: 0.8
```

- [ ] **Step 4: Run to verify pass**

Run: `backend/.venv/bin/pytest tests/config/ -v`
Expected: PASS (cross-reference validation proves the field references).

- [ ] **Step 5: Commit**

```bash
git add backend/config/defaults backend/tests/config
git commit -m "feat(config): CMS peerstats + timeseries metric packs; housing timeseries block (B2)"
```

---

### Task 8: Full gates, docs, backlog

**Files:**
- Modify: `backend/analytics/README.md` (series-source contract: per-entity
  ← raw_records aggregates; graph-scope ← entity_metric_history;
  observations = monitoring-only; anomaly store + cascade membership),
  `backend/README.md` (pipeline stage list), `backend/agent/README.md` if it
  describes Flow 1 stages, `docs/architecture.md` (analytics flow section),
  `docs/backlog/analytics.md` (analytics.06 superseded w/ spec §2 rationale;
  analytics.07 done; note the delivered pipeline slice), the
  `docs/backlog/README.md` rollup (regenerate per its stated convention),
  `docs/project/planning/backlog.md` (BL-047 row → done),
  `docs/project/planning/sprints/2026-28.md` (B2 status).
- Also re-check `.github/copilot-instructions.md` + CLAUDE.md for
  contradictions per repo rules.

- [ ] **Step 1: Run every gate**

```bash
make test                                   # from repo root; ≥85% per package
cd backend && .venv/bin/pyright && .venv/bin/ruff check --no-cache . && cd ..
```
Expected: all green, coverage ≥ 85%. Fix anything red before proceeding —
including pre-existing failures you surface.

- [ ] **Step 2: Update the docs listed above** (each claim must match the
  code as built — cite the new module paths, the stage's controlled-skip
  semantics, and the `timeseries_anomaly:` signal-name prefix).

- [ ] **Step 3: Commit**

```bash
git add backend/README.md backend/analytics backend/agent docs
git commit -m "docs(analytics,agent,backlog): timeseries anomaly stage — series contract, cascade, story reconciliation (B2)"
```

---

### Task 9: Live verification — RESERVED FOR THE CONTROLLER

Against `make dev` (api + worker restarted onto this branch — remember:
volume-mount deploys need an explicit `docker compose restart`, up alone is
a no-op), `medicare_fraud_cms_desynpuf` pack:

- [ ] Run `make demo-tn-subset` (1% sample) and wait for ingest completion.
- [ ] Worker logs show the timeseries stage running (no unexpected
  "found no series" for carrier/inpatient metrics; no stage exceptions).
- [ ] `docker exec chiliai-postgres-1 psql -U chili -d chili -c "SELECT metric_name, count(*) FROM timeseries_anomalies GROUP BY metric_name"` returns rows.
- [ ] `... -c "SELECT metric_name, count(*) FROM entity_derived_signals WHERE metric_name LIKE 'timeseries_anomaly:%' GROUP BY metric_name"` returns rows, alongside the peerstats metrics (`weekly_carrier_billing`, `monthly_inpatient_billing`).
- [ ] A risk profile carries both signal families (pick an entity id from the
  previous query; check `risk_score_history` / risk factors via the API).
- [ ] `GET /analytics/timeseries/<entity_id>?kb_id=<kb>` returns real points
  with ≥1 `is_anomaly: true`; the workbench chart renders the anomaly chips
  in the browser.
- [ ] Housing spot-check: `make dev-domain DOMAIN=department_air_force_housing`
  + `make seed-housing`; the workbench chart on a market snapshot entity is
  either populated (if seeded history suffices) or an honest "unavailable" —
  never an error.
- [ ] Delete a scratch KB; `timeseries_anomalies` rows for it are gone
  (cascade step).

---

## Self-review notes (already applied)

- Spec coverage: §3.1 config (T1), §3.2 record-aggregate source (T3),
  §3.3 stage + shared risk pass (T4), §3.4 table/store/cascade (T2+T5),
  §3.5 API + unchanged contract (T6), §3.6 packs (T7), §4 error handling
  (T4's skip/except structure, T6's ValueError-vs-SourceError split),
  §6 gates/live (T8+T9), §7 backlog (T8).
- Type consistency: `TimeseriesAnomalyStoreProtocol` method names match
  across T2 (definition), T4 (stage + factory), T5 (purger mirror), T6 (DI);
  `load_entity_series_map` keyword signature identical in T3 and T4;
  `TimeseriesMetricSpec` field names identical in T1, T3, T4, T7.
- Known simplification: `RecordAggregateTimeSeriesSource.load_series` loads
  the full per-spec aggregate set to serve one entity (matches the existing
  peerstats SQL's no-predicate design). Fine at demo scale; note as a
  follow-up in the analytics backlog if T9 shows latency.
