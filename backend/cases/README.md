# cases

Durable, knowledge-base-scoped **investigation case management** (BL-010).

Cases are promoted from alerts (capturing the originating alert, its evidence
pack, and a timeline snapshot) and persisted across the API and worker
containers. This module replaces the previous in-memory, global `ApiState`
case read model.

## Layout

| File | Responsibility |
|------|----------------|
| `models.py` | `Case` domain model (KB-scoped, with `originating_alert_id`, `evidence_pack_id`, `alert_ids`, `timeline`, `feedback_history`) + `CaseTimelineEvent` and `AnalystFeedback`. |
| `adapters/protocols.py` | `CaseRepository` protocol — `create / get / list / update / delete_by_kb`. |
| `adapters/in_memory.py` | `InMemoryCaseRepository` (dict keyed by `(kb_id, case_id)`) for tests/dev. |
| `adapters/postgres.py` | `PostgresCaseRepository` over `database.ConnectionProvider` (psycopg-free); jsonb `alert_ids`/`timeline`/`feedback_history`; idempotent `create` (`ON CONFLICT DO NOTHING`). |
| `service.py` | `CaseService` — orchestration, durable `add_feedback`, `promote_from_alert` (severity→priority mapping, timeline capture), and `attach_alert` (adds an alert to an existing case; leaves `evidence_pack_id` alone). |
| `exceptions.py` | `CaseError`, `CasePersistenceError`, `CaseNotFoundError`. |

## Contract

`CaseRepository` (all KB-scoped):

```python
def create(self, case: Case) -> Case: ...
def get(self, *, knowledge_base_id: str, case_id: str) -> Case | None: ...
def list(self, *, knowledge_base_id: str, limit: int, offset: int,
         status: str | None = None, priority: str | None = None) -> tuple[list[Case], int]: ...
def update(self, case: Case) -> Case: ...          # raises CaseNotFoundError if absent
def delete_by_kb(self, knowledge_base_id: str) -> int: ...
```

## Persistence

The `cases` table is created by Alembic migration
`database/migrations/versions/0002_cases.py` (`down_revision =
0001_persistence_baseline`), with `PRIMARY KEY (knowledge_base_id, case_id)` and
an `ix_cases_status` index. `0007_case_feedback.py` adds durable
`feedback_history` storage. Backend selection mirrors `records`/`monitoring`:
`get_case_repository` (`api/dependencies.py`) returns the in-memory adapter when
no connection provider is configured, otherwise the Postgres adapter.

## API surface

Routed by `api/routers/cases.py`, all scoped by a required `knowledge_base_id`
query param:

- `GET /cases?knowledge_base_id=` (viewer) — list, with `status`/`priority` filters.
- `GET /cases/{id}?knowledge_base_id=` (viewer) — detail (case + linked alert summaries + evidence pack + entity timeline + durable feedback history).
- `POST /cases?knowledge_base_id=` (analyst) — create.
- `PATCH /cases/{id}?knowledge_base_id=` (analyst) — partial update.
- `POST /cases/promote?knowledge_base_id=` (analyst) — promote an alert into a **new** case.
- `POST /cases/{id}/alerts?knowledge_base_id=` (analyst) — attach an alert to a case that **already exists** (UXA-405). 404 for an unknown case or an alert outside the KB scope; 409 when the case already holds the alert. Appends to `alert_ids` and records an `Alert attached` timeline event; `evidence_pack_id` is deliberately untouched — it records what the case was opened from, and repointing it on every attach would silently rewrite the case's origin. Exclusivity across cases is **not** enforced (promote does not enforce it either; the UI filters already-attached alerts out of the picker).
- `POST /cases/{id}/feedback?knowledge_base_id=` (analyst) — append analyst feedback.

## Durable detail behavior

- **Analyst feedback** is appended through `CaseService.add_feedback` and stored
  on the durable `Case.feedback_history` record.
- **Linked `alerts[]`** on case detail is resolved from `Case.alert_ids` through
  the durable alert feed store (`monitoring.adapters.protocols.AlertFeedStoreProtocol`,
  serving from the `alert_history` table) and filtered to the same knowledge base.
- Analytics `open_cases` now aggregates from the durable case repository and the
  legacy `ApiState` `_seed_cases` store has been removed (**BL-012**, ApiState de-seed).

## Tests

- `tests/cases/test_in_memory_store.py` — repository CRUD, KB isolation, filters, pagination.
- `tests/cases/test_postgres_store.py` — `@pytest.mark.integration` (skipped without `DATABASE_URL`).
- `tests/cases/test_service.py` — service + promote-from-alert.
- `tests/api/test_phase5_stateful_routes.py`, `tests/api/test_read_model_routers.py` — KB-scoped routes + promote flow.
