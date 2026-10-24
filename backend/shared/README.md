# shared

The **shared contracts library** — the third permitted cross-module path (see
[docs/architecture.md](../../docs/architecture.md)). It holds generic platform
types, small cross-cutting protocols, canonical constants, and dependency-light
utilities that every other backend module may import. It must not contain
business logic or domain-specific types: domain entities (providers, claims,
…) exist only in config YAML and flow through the system as generic `Entity`
instances.

## Layout

| File | Responsibility |
|------|----------------|
| `types.py` | Config-definition types (`PropertyType`, `PropertyDefinition`, `EntityDefinition`, `RelationshipDefinition`) and platform types (`Entity`, `Relationship`, `Alert`, `EvidencePack` with `FeatureAttribution` / `EvidenceNarrativeSection` / `EvidenceProvenanceReference`, `KnowledgeBase`, `MonitoringObservation`). `validate_entity` / `validate_relationship` return a list of error strings against config definitions. |
| `protocols.py` | `Configurable`, `ObjectStoreProtocol`, `StoredObject`, `StoredObjectWriteResult` (the object-store contract implemented in [storage/](../storage/README.md)). |
| `exceptions.py` | `ConfigurationError` (unsupported/unavailable backend) and `ConcurrentModificationError` (cross-module marker base for lost optimistic-concurrency races; module-specific subclasses inherit from it). |
| `alerts.py` | `AlertSeverity`, `ACTIVE_ALERT_STATUSES`, `normalize_severity(raw_severity, confidence)`. |
| `environments.py` | `EnvironmentTag` (`local` / `dev` / `staging` / `production`) and `SUPPORTED_ENVIRONMENT_TAGS` — the vocabulary both `CHILI_ENV` and capability manifests' `environment_tags` use. |
| `kb_scope.py` | `resolve_kb_scope(primary_kb_id, domain_config, kb_repository)` — returns `[primary]` or `[primary, reference]` using `DomainConfig.default_reference_kb_id`; a configured but missing reference KB logs a warning and falls back to primary-only. `KnowledgeBaseExistenceCheck` protocol. |
| `provenance.py` | Canonical metadata keys/values for provenance on entities, relationships and vector points (`SOURCE_KIND_KEY`, `SOURCE_FEED_KEY`, `SOURCE_RAW_RECORD_ID_KEY`, `SOURCE_DOCUMENT_ID_KEY`, `SOURCE_CHUNK_ID_KEY`, `SOURCE_ID_KEY`, `EMBEDDING_CHANNEL_KEY`, `SOURCE_KIND_RECORD` / `SOURCE_KIND_DOCUMENT`, `EMBEDDING_CHANNEL_TEXT` / `EMBEDDING_CHANNEL_GRAPH`). |
| `logging.py` | structlog setup: `configure_logging` (idempotent; `LOG_FORMAT=json` selects JSON output, `LOG_LEVEL` sets the level, default `INFO`), `get_logger`, `bind_correlation_id` / `clear_correlation_id` (context-var correlation id injected into every log line). |
| `metrics.py` | Prometheus counters on the default registry: `chili_audit_write_failures_total`, `ingestion_documents_failed_total`, `ingestion_documents_empty_extraction_total`, `ingestion_dedup_suppressed_total`; `log_stage` emits the per-document stage log line. |
| `tracing.py` | OpenTelemetry helpers: `setup_tracing` (exporter endpoint from the argument or `OTEL_EXPORTER_OTLP_ENDPOINT`), `instrument_fastapi_app`, `get_tracer`, `start_pipeline_span`. All OpenTelemetry imports are deferred; without the `[observability]` extra the helpers are no-ops. |
| `validation.py` | Input hygiene helpers: `sanitize_filename` (strips traversal and control characters, prefixes Windows reserved names with `_`, falls back to `"upload"`), `validate_content_type`, `validate_query_length`. |
| `utils.py` | `generate_id`, `utc_now`, `normalize_text`. |

## Contracts and invariants

- **No hardcoded domain types.** `Entity.type` / `Relationship.type` name a
  config-defined `EntityDefinition` / `RelationshipDefinition`; properties are
  validated against config at system boundaries via `validate_entity` /
  `validate_relationship`.
- **Provenance keys are constants.** Every site that stamps, filters or deletes
  by provenance references `shared.provenance` rather than a string literal;
  RAG retrieval filters on `EMBEDDING_CHANNEL_KEY`.
- **Metrics are per process.** Each process serves its own `/metrics` (the API
  via `api/middleware/metrics.py`, the worker via `agent/health.py`); counters
  are per-attempt, so redelivered events can over-count.
- **Dependencies.** Runtime imports are the standard library, `pydantic`,
  `structlog`, `prometheus_client`, plus `config.schema.DomainConfig`
  (imported by `kb_scope.py`). OpenTelemetry is optional.

## How it is reached

Imported directly by every backend module; there are no routes, events, or
handlers here. The package root re-exports the core types plus
`generate_id`, `normalize_text` and `validate_entity`.

## Persistence

None.

## Current gaps

From `TODO(production)` comments:

- `types.py`: `Alert.severity` is a bare `str` (no enum); `Alert.acknowledged`
  is deprecated in favour of `status` but still present; `EvidencePack` has no
  structured timeline or visual-layout fields; `KnowledgeBase` has no owner or
  tags.
- `protocols.py`: no shared `HealthCheckable` / `Lifecycle` / `Measurable`
  protocols.
- `utils.py`: no shared JSON serializer, retry decorator, or text truncation
  helper.
- `exceptions.py`: `cases.exceptions.CaseConcurrentModificationError` does not
  yet inherit from `ConcurrentModificationError`.

## Tests

`tests/shared/` — one file per module (`test_types.py`,
`test_types_relationship_metadata.py`, `test_alerts.py`, `test_kb_scope.py`,
`test_logging.py`, `test_metrics.py`, `test_protocols.py`, `test_tracing.py`,
`test_utils.py`, `test_validation.py`).
