# scorecards backlog

> **Scope:** Configurable durable scorecard generation (`backend/scorecards/`): template-defined metrics evaluated against ingested record-feed data via bounded formula operators (ratio/sum/mean/weighted_mean/latest), JSON/Markdown export, and persisted runs for dashboard consumption.
> **Story format and rules:** see [design spec §5](../superpowers/specs/2026-05-24-complete-backlog-design.md#5-story-format).

---

## Story scorecards.01: Wire peer-group z-score inputs into scorecard formulas, with a configurable comparison depth

**ID:** scorecards.01
**Status:** planned
**Prerequisites:** []
**Unblocks:** []
**Estimated size:** M

**As a** domain operator building scorecard templates,
**I need** a scorecard metric's `inputs` to be able to reference a configured `peer_stats` z-score metric — including how many trailing intervals ("depth") feed the comparison — instead of only ever reading flat record-feed columns,
**so that** a metric like "spend vs peer average" can cite a traceable cross-sectional peer comparison instead of requiring the peer math to be pre-baked into a feed column with no link back to the `peer_stats` config that produced it.

### Current State
- `ScorecardMetricInputConfig.source` (`backend/config/schema.py:470`) is `Literal["record_feed", "metric", "graph", "document"]`. Only the `"record_feed"` branch is implemented: `_select_input` in `backend/scorecards/evaluation.py:188-253` falls straight into "unsupported source" handling (a missing-input warning) for `"metric"`, `"graph"`, and `"document"`.
- `PeerMetricSpec` / `PeerStatsConfig` (`backend/config/schema.py:707-729`) is a fully separate config section from `ScorecardsConfig` — nothing on `ScorecardMetricInputConfig` references a `PeerMetricSpec.name`, and `DomainConfig`'s cross-reference validation does not check such a reference either (there isn't one to check).
- `backend/analytics/peerstats/` (models.py, aggregation.py, service.py) has no "depth" / lookback-window / trailing-interval concept at all — `PeerMetricSpec.interval` (day/week/month) governs the bucket size, but nothing bounds how many historical buckets a consumer sees.
- Today the only way a scorecard template can reflect a peer comparison is if the numeric z-score is written back into a record feed as a plain column and referenced like any other `record_feed` input — silent and unvalidated against the `peer_stats` config.

### Acceptance Criteria
- [ ] `ScorecardMetricInputConfig` gains a `peer_stats_metric: str | None = None` field referencing a `PeerMetricSpec.name`.
- [ ] `DomainConfig`'s cross-reference validation rejects a scorecard template whose `peer_stats_metric` does not match any configured `PeerStatsConfig.metrics[].name`.
- [ ] A `depth: int = 1` (or similarly named) field bounds how many trailing peer-stat intervals are visible to a `"metric"`-sourced input (default 1 = latest interval only).
- [ ] `_select_input` in `backend/scorecards/evaluation.py` implements the `source="metric"` branch: it resolves the referenced peer metric's most recent `depth` observations for the record's entity and feeds them into the same `_InputSelection` shape record-feed inputs already use, so `ratio`/`sum`/`mean`/`latest`/`weighted_mean` all work unmodified.
- [ ] `ScorecardCitation` for a peer-sourced value cites the `peer_stats` metric name and the interval it was computed for (not just a feed/record id), so peer-derived values remain traceable.
- [ ] Unit tests in `backend/tests/scorecards/test_evaluation.py` cover a metric config end-to-end referencing a peer_stats metric, including a `depth > 1` case and the unknown-metric-name validation rejection.

### Verification
- `pytest backend/tests/scorecards backend/tests/config -q -k peer` green.
- Coverage ≥ 85% on `backend/scorecards/evaluation.py` and the new config validation.
- Manual: configure a `peer_stats_metric` input on an Air Force housing scorecard template, generate a run via `POST /scorecards/runs`, and confirm the metric's citation names the peer_stats metric.

### Code touch points
- `backend/config/schema.py` (modify — `peer_stats_metric` + `depth` on `ScorecardMetricInputConfig`, cross-reference validation)
- `backend/scorecards/evaluation.py` (modify — `source="metric"` branch in `_select_input`)
- `backend/analytics/peerstats/service.py` (modify or extend — depth-bounded historical lookup)
- `backend/tests/scorecards/test_evaluation.py` (modify — peer-sourced metric tests)
- `backend/tests/config/test_schema.py` (modify — cross-reference validation tests)

---

## Story scorecards.02: Add scorecard template versioning so a template edit cannot silently reinterpret past runs

**ID:** scorecards.02
**Status:** planned
**Prerequisites:** []
**Unblocks:** []
**Estimated size:** M

**As a** domain operator evolving scorecard templates,
**I need** each `ScorecardTemplateConfig` to declare a version and each persisted `ScorecardRun` to record which template version produced it,
**so that** renaming a metric's formula or moving a threshold band does not silently reinterpret already-generated historical runs, and a dashboard can distinguish "this old scorecard was measured under different rules" from "this scorecard just failed."

### Current State
- `ScorecardTemplateConfig` (`backend/config/schema.py:665-676`) has no version field: `id`, `name`, `category`, `scope`, `period`, `sections`, `export_formats` only.
- `ScorecardRun` (`backend/scorecards/models.py:71-92`) stores `template_id` and `template_name` but nothing identifying which version/content of the template graded it.
- `ScorecardService._source_snapshot_hash` (`backend/scorecards/service.py:188-212`) fingerprints the request plus the evaluated records only — it deliberately excludes the template definition, so two runs generated before and after a template threshold edit hash identically (and therefore look idempotent) even though grading now differs for the same underlying data.
- No test in `backend/tests/scorecards/` asserts that editing a template's thresholds or formula is reflected anywhere in a persisted run's identity.

### Acceptance Criteria
- [ ] `ScorecardTemplateConfig.version: str = "1.0"` added in `backend/config/schema.py`.
- [ ] `ScorecardRun` gains a `template_version: str` field, stamped from the resolved template at generate time (`backend/scorecards/service.py`).
- [ ] `_source_snapshot_hash` folds the template version (or a content hash of its grading-relevant fields — formulas + thresholds) into the hash, so a template edit changes the resulting run id/hash even over unchanged source data.
- [ ] Alembic migration adds a `template_version` column to the durable scorecard-runs table (`backend/database/migrations/versions/0008_scorecards.py` baseline).
- [ ] `PostgresScorecardRunRepository` / `InMemoryScorecardRunRepository` (`backend/scorecards/adapters/`) persist and round-trip `template_version`.
- [ ] Unit test in `backend/tests/scorecards/test_service.py` asserts `template_version` is stamped on a generated run, and that editing a template's thresholds changes `source_snapshot_hash` for identical input records.

### Verification
- `pytest backend/tests/scorecards -q -k version` green.
- Coverage ≥ 85% on `backend/scorecards/service.py` and the new migration.
- Manual: bump a template's threshold in a domain pack, regenerate a scorecard for the same KB/scope/period over unchanged data, and confirm the new run's `template_version` and `id` differ from the prior run.

### Code touch points
- `backend/config/schema.py` (modify — `version` on `ScorecardTemplateConfig`)
- `backend/scorecards/models.py` (modify — `template_version` on `ScorecardRun`)
- `backend/scorecards/service.py` (modify — stamp version, fold into snapshot hash)
- `backend/database/migrations/versions/0011_scorecard_template_version.py` (new)
- `backend/scorecards/adapters/in_memory.py` (modify — preserve field)
- `backend/scorecards/adapters/postgres.py` (modify — column in SQL + row mapping)
- `backend/tests/scorecards/test_service.py` (modify — version-stamp + hash-change tests)
- `backend/tests/scorecards/test_postgres_store.py` (modify — round-trip test)

---

## Story scorecards.03: Emit scorecard generation observability metrics and structured logs

**ID:** scorecards.03
**Status:** planned
**Prerequisites:** []
**Unblocks:** []
**Estimated size:** M

**As a** platform/worker operator running scorecard generation,
**I need** per-template Prometheus counters and structured log lines for every scorecard generation, mirroring the records.06 precedent,
**so that** I can answer "how many scorecard runs were generated in the last hour", "which templates are failing or landing incomplete most often", and "how long does generation take" without grepping raw API logs.

### Current State
- `grep -rn "logger\|Counter\|Histogram" backend/scorecards/ backend/api/routers/scorecards.py` returns no hits anywhere in the scorecards module or its router — zero logging, zero metrics.
- `ScorecardService.generate` (`backend/scorecards/service.py:83-113`) emits nothing on success or failure. A run landing with metrics at `health="incomplete"` or `completeness="formula_error"` (`backend/scorecards/evaluation.py`) is visible only by fetching that run's sections through the API — there is no aggregate signal.
- `backend/records/metrics.py` (added by records.06) and `backend/monitoring/metrics.py` are the existing per-stage precedent this story should mirror (architecture §11.2).

### Acceptance Criteria
- [ ] New module `backend/scorecards/metrics.py` defines: `scorecard_runs_generated_total{template_id,overall_health}` (Counter), `scorecard_generation_duration_seconds{template_id}` (Histogram), `scorecard_metrics_incomplete_total{template_id,completeness}` (Counter).
- [ ] `ScorecardService.generate` (`backend/scorecards/service.py`) emits a structured log line at INFO on generation start (`template_id`, `knowledge_base_id`, `scope_type`, `scope_id`) and on completion (`overall_health`, `duration_ms`, incomplete-metric count), and increments the counters/histogram above.
- [ ] 404 error paths in `backend/api/routers/scorecards.py` emit a structured log line with a correlation id for traceability.
- [ ] Test in `backend/tests/scorecards/test_metrics.py` (new) asserts the counters and histogram move on a successful generate and on a generate that produces incomplete metrics.
- [ ] `backend/scorecards/README.md` (new) "Observability" section enumerates the metrics and lists Grafana panel suggestions.

### Verification
- `pytest backend/tests/scorecards -q -k metrics` green.
- Coverage ≥ 85% on `backend/scorecards/metrics.py` and `service.py`.
- Manual: `curl http://localhost:8000/metrics | grep scorecard_` shows the new metric names after generating a scorecard run via `POST /scorecards/runs`.

### Code touch points
- `backend/scorecards/metrics.py` (new)
- `backend/scorecards/service.py` (modify — instrument `generate`)
- `backend/api/routers/scorecards.py` (modify — instrument error paths)
- `backend/scorecards/README.md` (new — observability section)
- `backend/tests/scorecards/test_metrics.py` (new)
