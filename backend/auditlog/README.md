# auditlog

Append-only **audit ledger** for material actions (who did what, to which
resource, with before/after summaries). Writers across the API gateway and the
worker call `AuditLogService.record`; admins read the ledger through
`GET /audit/events`. A failed audit write never fails the action being
audited — the failure is counted, buffered, and surfaced via
`GET /audit/status`.

## Layout

| File | Responsibility |
|------|----------------|
| `models.py` | `AuditEventCreate` (write input), `AuditEvent` (stored row), `AuditEventQuery` (read filters, `limit` 1–500), `AuditEventPage`, `AuditWriteFailure`, the `AuditOutcome` literal (`success` / `failure`), and the `PLATFORM_TENANT_ID` constant. |
| `protocols.py` | `AuditLogRepository` — `append(event)` and `list(query)` only. There is no update or delete. |
| `service.py` | `AuditLogService` — builds the event (`generate_id`, `utc_now` default), appends it, and isolates failures. |
| `adapters/in_memory.py` | `InMemoryAuditLogRepository` for tests/dev. |
| `adapters/postgres.py` | `PostgresAuditLogRepository` over `database.ConnectionProvider`; parameterised filter builder (`action_prefix` is a `LIKE 'prefix%'` match), newest-first paging with a `count(*)` total. |
| `exceptions.py` | `AuditLogError`, `AuditLogPersistenceError`. |

## Contracts and invariants

- **Append-only.** The repository protocol exposes no mutation besides
  `append`, and nothing in this module edits or deletes rows.
- **Non-blocking writes.** `AuditLogService.record` catches any repository
  exception, increments `chili_audit_write_failures_total{action,error_class}`
  (`shared/metrics.py`), keeps the last `max_failure_buffer` (default 100)
  `AuditWriteFailure`s in process memory, and returns `None` instead of
  raising. On success it returns the stored `AuditEvent`. The failure buffer is
  per-process and is not persisted.
- **Single tenant.** There is no tenancy implementation; writers pass
  `PLATFORM_TENANT_ID` (`"platform"`) and scope by `knowledge_base_id`.
  `AuditEventQuery.tenant_id` is optional so a KB-only query returns the full
  timeline regardless of the tenant value historical rows carry.

## How it is reached

- **Writers (API):** `api/routers/` — `cases`, `alerts`, `evidence`, `auth`,
  `knowledgebases`, `workflows`, `events`, `config` — obtain the service from
  `get_audit_log_service` (`api/dependencies.py`), which memoises one
  `AuditLogService` per app (Postgres when a connection provider exists,
  otherwise in-memory).
- **Writers (modules):** `capabilities/service.py`,
  `workflow_definitions/service.py`, and the identity-link repository
  (`analytics/identity_resolution/repository.py`, steward decisions) record
  events when handed a service. In the worker, `agent/coordinator.py`
  (`build_audit_log_service`) builds one and passes it to the workflow
  executor deps.
- **Readers:** `api/routers/audit.py` (prefix `/audit`, `admin` role):
  `GET /audit/events` (filters `tenant_id`, `knowledge_base_id`,
  `actor_user_id`, `action_prefix`, `resource_type`, `resource_id`, `outcome`,
  `from`, `to`, `limit`, `offset`) and `GET /audit/status` (failed-write count
  plus recent failures).

## Persistence

Table `audit_log`, created by `database/migrations/versions/0016_audit_log.py`:
`event_id` primary key, jsonb `actor_roles` / `before` / `after` / `metadata`,
`ck_audit_log_outcome` check constraint, and indexes
`ix_audit_log_tenant_occurred_at`, `ix_audit_log_kb_occurred_at`,
`ix_audit_log_actor_occurred_at` (all `occurred_at DESC`).

## Current gaps

- Append-only is enforced by the code surface only; the migration adds no
  database-level guard (trigger or revoked privileges) against `UPDATE` /
  `DELETE`.
- The write-failure buffer behind `GET /audit/status` lives in each process's
  memory, so the API's status does not reflect worker-side failures (those are
  visible only through the metric).

## Tests

`tests/auditlog/test_service.py`, `tests/auditlog/test_postgres_store.py`
(`@pytest.mark.integration`).

See also: [architecture](../../docs/architecture.md),
[module map](../../docs/ledger/module-map.md).
