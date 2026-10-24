# governance

**Release readiness, evaluation runs, and baseline approval** for a knowledge
base. `GovernanceEvalService` records candidate-vs-baseline evaluation runs and
admin approve/reject decisions; `GovernanceReportService` builds a read-only
report over existing durable artifacts (published playbook snapshots, workflow
definitions, explanation reviews, eval runs) and derives release blockers from
them. An approved eval run gates playbook publication.

## Layout

| File | Responsibility |
|------|----------------|
| `models.py` | `GovernanceEvalRunCreate` / `GovernanceEvalRun` / `GovernanceEvalRunPage`, `GovernanceMetricInput` / `GovernanceMetricResult`, `GovernanceDriftSummary`, `GovernanceBaselineDecision`, report parts (`GovernanceVersionSummary`, `GovernancePendingApproval`, `GovernanceFeedbackTrend`, `GovernanceReleaseBlocker`), `GovernanceReport` (computed `release_ready`), and the status / kind / severity literals. |
| `repository.py` | `GovernanceEvalRepository` — `save_eval_run`, `update_eval_run`, `get_eval_run`, `list_eval_runs`. |
| `adapters/in_memory.py` / `adapters/postgres.py` | `InMemoryGovernanceEvalRepository`, `PostgresGovernanceEvalRepository`. |
| `service.py` | `GovernanceEvalService`, `GovernanceReportService`, `CHALLENGED_REVIEW_STATES`, and `GovernanceEvalError` / `GovernanceEvalNotFoundError` / `GovernanceEvalApprovalError`. |

## Contracts and invariants

- **Metric pass rule** (`_metric_result`): `delta = candidate - baseline`; a
  `higher`-is-better metric passes when `delta >= -threshold`, a `lower` one
  when `delta <= threshold`. The run's `GovernanceDriftSummary` counts metrics,
  failed metrics, and the max absolute delta.
- **Deterministic run id**:
  `{knowledge_base_id}:{artifact_kind}:{artifact_id}:{artifact_version}:{dataset_id}`.
  Recording the same combination twice raises `ValueError` ("already exists")
  in both adapters. New runs start as `candidate`.
- **Approval**: only a `candidate` run can be approved or rejected; approval is
  refused while any metric failed. `has_approved_eval(kb, artifact_kind,
  artifact_id, artifact_version)` pages through the KB's runs looking for an
  approved decision on exactly that artifact version.
- **Report blockers** (`GovernanceReportService.build_report`):
  `missing_playbook_baseline`, `missing_eval_approval`,
  `pending_workflow_approval` (severity `blocking`) and
  `challenged_explanations` (severity `warning`, from reviews in
  `CHALLENGED_REVIEW_STATES`). `GovernanceReport.release_ready` is true when no
  blocker is `blocking`.
- **Cross-module imports.** `service.py` imports other modules directly rather
  than through the gateway, coordinator, or `shared/`:
  `analytics.explainability.reviews` (`ExplanationReviewService` and its
  query/page/state types), `playbooks.repository.PlaybookRepository`, and
  `workflow_definitions.repository.WorkflowDefinitionRepository`.

## How it is reached

- `api/routers/governance.py`, prefix
  `/knowledgebases/{knowledge_base_id}/governance`:

  | Route | Role |
  |-------|------|
  | `GET /report` | viewer |
  | `GET /eval-runs` | viewer |
  | `POST /eval-runs` | analyst — record a run |
  | `POST /eval-runs/{run_id}/approve` | admin |
  | `POST /eval-runs/{run_id}/reject` | admin |

- `api/routers/playbooks.py` — `POST
  /knowledgebases/{knowledge_base_id}/playbooks/{playbook_id}/publish` calls
  `GovernanceEvalService.has_approved_eval(artifact_kind="playbook", ...)`
  before publishing.
- No worker handler or event involvement.

## Persistence

Table `governance_eval_runs`, created by
`database/migrations/versions/0022_governance_eval_runs.py` (`run_id` primary
key, jsonb metrics / drift summary / approval, indexes
`ix_governance_eval_runs_kb_status` and `ix_governance_eval_runs_artifact`).
`0023_governance_eval_dataset_source_refs.py` adds the
`dataset_source_refs` jsonb column (also added idempotently by `0022`).

`delete_by_kb` is the `governance_evals` step of the KB-delete cascade
(`knowledgebases/cleanup.py`).

## Tests

`tests/governance/` — `test_eval_service.py`, `test_service.py`,
`test_postgres.py`.

See also: [playbooks](../playbooks/README.md),
[workflow_definitions](../workflow_definitions/README.md),
[analytics](../analytics/README.md),
[architecture](../../docs/architecture.md).
