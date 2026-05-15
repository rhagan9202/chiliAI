# Telemetry Contract (v0.1)

## Purpose
Defines the minimum telemetry events and fields required to monitor, audit, and debug the Program Integrity XAI Accelerator end to end:
- Data pipelines
- Scoring runs
- UI and workflow interactions
- Monitoring and governance actions

Aligns with Core fields dictionary and monitoring dashboards.

---

## 1. Envelope (common to all events)

All telemetry entries MUST include:

- `event_id` (string, unique)
- `event_timestamp` (timestamp, UTC)
- `event_type` (string)
- `tenant_id` (string)
- `program_id` (string)
- `env` (string): `dev|test|prod`
- `source_system` (string): e.g., `data_pipeline`, `scoring_service`, `ui_web`, `governance_service`.
- `trace_id` (string, optional): for request/flow correlation.
- `core_version` (string)
- `domain_pack_id` (string)
- `domain_pack_version` (string)
- `use_case_id` (string)
- `use_case_version` (string)

---

## 2. Data pipeline events

### 2.1 `data_batch_ingested`
Fields:
- `event_type`: `data_batch_ingested`
- `pipeline_id` (string)
- `source_name` (string)
- `batch_id` (string)
- `record_count` (integer)
- `start_time` (timestamp)
- `end_time` (timestamp)
- `freshness_lag_hours` (number)
- `status` (string): `success|warning|error`
- `warning_codes` (array<string>, optional)
- `error_code` (string, optional)
- `error_message` (string, optional)

### 2.2 `data_quality_check_completed`
Fields:
- `event_type`: `data_quality_check_completed`
- `pipeline_id` (string)
- `check_id` (string)
- `check_type` (string): `freshness|missingness|volume|schema|custom`
- `target_resource` (string): table or view name
- `status` (string): `pass|fail|warn`
- `metrics` (object): key/value pairs (e.g., missingness_rate, volume_z_score)
- `details_uri` (string, optional)

---

## 3. Scoring and indicator events

### 3.1 `scoring_run_started`
Fields:
- `event_type`: `scoring_run_started`
- `scoring_run_id` (string)
- `indicator_ids` (array<string>)
- `scheduled_trigger` (string): e.g., `cron`, `manual`, `event`
- `expected_entities` (integer, optional)

### 3.2 `scoring_run_completed`
Fields:
- `event_type`: `scoring_run_completed`
- `scoring_run_id` (string)
- `indicator_ids` (array<string>)
- `start_time` (timestamp)
- `end_time` (timestamp)
- `entities_scored` (integer)
- `items_queued` (integer)
- `status` (string): `success|warning|error`
- `error_code` (string, optional)
- `error_message` (string, optional)
- `perf_metrics` (object, optional): e.g., `{p95_latency_ms, mean_latency_ms}`

### 3.3 `indicator_output_stats`
Fields:
- `event_type`: `indicator_output_stats`
- `scoring_run_id` (string)
- `indicator_id` (string)
- `indicator_version` (string)
- `entities_scored` (integer)
- `score_distribution` (object): summary (mean, std, quantiles)
- `severity_distribution` (object): counts per band
- `missing_evidence_count` (integer)
- `evidence_insufficient_count` (integer)

---

## 4. UI and workflow events

### 4.1 `ui_view_queue`
Fields:
- `event_type`: `ui_view_queue`
- `actor_id` (string)
- `actor_role` (string)
- `queue_id` (string)
- `filter_state` (object): severity, indicators, etc.

### 4.2 `ui_open_case`
Fields:
- `event_type`: `ui_open_case`
- `actor_id` (string)
- `actor_role` (string)
- `case_id` (string)
- `entity_id` (string)
- `indicator_ids` (array<string>)

### 4.3 `ui_view_evidence_bundle`
Fields:
- `event_type`: `ui_view_evidence_bundle`
- `actor_id` (string)
- `actor_role` (string)
- `case_id` (string)
- `evidence_bundle_id` (string)
- `indicator_ids` (array<string>)
- `view_duration_ms` (number, optional)

### 4.4 `ui_export_evidence`
Fields:
- `event_type`: `ui_export_evidence`
- `actor_id` (string)
- `actor_role` (string)
- `case_id` (string)
- `evidence_bundle_id` (string)
- `export_format` (string)
- `export_size_bytes` (integer)

### 4.5 `ui_submit_feedback`
Fields:
- `event_type`: `ui_submit_feedback`
- `actor_id` (string)
- `actor_role` (string)
- `case_id` (string)
- `indicator_ids` (array<string>)
- `feedback_id` (string)
- `feedback_label` (string)
- `reason_tags` (array<string>)
- `explanation_usefulness` (integer)
- `evidence_adequacy` (integer)

### 4.6 `ui_change_case_status`
Fields:
- `event_type`: `ui_change_case_status`
- `actor_id` (string)
- `actor_role` (string)
- `case_id` (string)
- `old_status` (string)
- `new_status` (string)
- `status_reason` (string, optional)

---

## 5. Monitoring & drift events

### 5.1 `monitoring_drift_check_completed`
Fields:
- `event_type`: `monitoring_drift_check_completed`
- `indicator_id` (string)
- `indicator_version` (string)
- `drift_check_id` (string)
- `drift_check_type` (string): `data|output|performance|stability`
- `status` (string): `pass|warn|fail`
- `metrics` (object): includes PSI, KS, precision_at_k, stability_at_k, etc.
- `details_uri` (string, optional)

### 5.2 `monitoring_alert_raised`
Fields:
- `event_type`: `monitoring_alert_raised`
- `alert_id` (string)
- `alert_type` (string): `data_drift|output_drift|performance_drop|infra|security`
- `severity` (string): `info|warning|critical`
- `indicator_ids` (array<string>, optional)
- `scoring_run_id` (string, optional)
- `summary` (string)
- `details_uri` (string, optional)

---

## 6. Governance & safety events

### 6.1 `governance_change_request_created`
Fields:
- `event_type`: `governance_change_request_created`
- `change_request_id` (string)
- `requested_by` (string)
- `change_type` (array<string>)
- `affected_indicator_ids` (array<string>)

### 6.2 `governance_change_request_decision`
Fields:
- `event_type`: `governance_change_request_decision`
- `change_request_id` (string)
- `approver_id` (string)
- `approver_role` (string)
- `decision` (string): `approved|rejected|needs_revision`
- `comments` (string, optional)

### 6.3 `safety_control_action`
Fields:
- `event_type`: `safety_control_action`
- `control_action_id` (string)
- `action_type` (string): `pause_indicator|resume_indicator|retire_indicator|pause_use_case|resume_use_case`
- `target_type` (string): `indicator|use_case`
- `target_id` (string)
- `issued_by` (string)
- `effective_at` (timestamp)
- `reason` (string)

---

## 7. Security & audit events

### 7.1 `security_access_event`
Fields:
- `event_type`: `security_access_event`
- `actor_id` (string)
- `actor_role` (string)
- `object_type` (string): `case|evidence_bundle|indicator|config|export`
- `object_id` (string)
- `action` (string): `view|update|delete|export`
- `result` (string): `success|denied|error`
- `ip_address` (string, optional)
- `user_agent` (string, optional)
- `error_code` (string, optional)

---

## 8. Implementation considerations

- Telemetry should be:
  - Asynchronous where possible (non-blocking).
  - Sampled only when safe; governance and security events should not be sampled.
- Sensitive payloads:
  - Avoid embedding raw PII/PHI in telemetry; use IDs and classification tags.
- Retention:
  - Align with data retention and audit policies for healthcare programs.
