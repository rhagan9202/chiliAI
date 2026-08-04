# SAFE-CMS PI 4 Playbooks and Workflow Runway ADR

> Scope: `SAFE-CMS-013` through `SAFE-CMS-016`
> Source plan: `docs/superpowers/plans/2026-07-30-cms-fraud-ai-safe-agile-20-sprint-surge.md`
> Formalized: 2026-08-04
> Branch context at formalization: `safe-cms-013-playbooks`

## 1. Decision

PI 4 starts with versioned fraud playbooks as domain-pack-authored definitions that can be published into durable
database snapshots. The shared platform owns validation, publication state, historical references, export/import,
and generic UI/API rendering. CMS-specific typology labels, evidence checklists, RAG prompts, policy refs, and
decision guidance remain in the Medicare domain pack.

The workflow builder in `SAFE-CMS-014` consumes playbook workflow templates but is not a runtime dependency for
`SAFE-CMS-013`. Playbooks may declare workflow step templates now; execution semantics remain data-only until the
workflow definition engine exists.

## 2. Context

The current surge foundation has these usable primitives:

- `DomainConfig.typologies` and `FeatureCatalogConfig` with validated feature/typology references.
- `FraudTypologyConfig.playbook_ids`, currently unvalidated because no playbook catalog exists.
- Alert generation metadata on `shared.types.Alert` and `monitoring.models.AlertHistoryRecord`.
- Evidence provenance metadata on `shared.types.EvidenceProvenanceReference`.
- Case rows in `cases.models.Case`, currently without a first-class playbook version snapshot.
- KB domain stamping on `KnowledgeBase.domain_name`.
- OpenAPI/codegen discipline for frontend contracts.

## 3. Rulings

1. **Source of truth:** Domain packs are the authoring source for seed playbooks. The database stores published
   immutable snapshots by `domain_name`, `playbook_id`, and `version`.
2. **Publication states:** Playbooks use `draft`, `published`, and `retired`. Only `published` snapshots attach to
   alerts, evidence, and cases.
3. **Historical meaning:** Alerts, evidence packs, and cases store `playbook_id` and `playbook_version` at creation
   or promotion time. A later published version never mutates those historical references.
4. **KB scope:** Management APIs are routed under `/knowledgebases/{knowledge_base_id}/playbooks` to reuse existing
   KB entitlement checks. The published record itself is domain-scoped using the KB's `domain_name`; legacy KBs
   with no domain stamp use the active `DomainConfig.domain.name`.
5. **Workflow boundary:** `SAFE-CMS-013` persists workflow template refs and step metadata, but does not execute
   them. `SAFE-CMS-014` turns these templates into executable workflow definitions.
6. **Export/import:** Exported playbooks are JSON domain-pack artifacts with schema version, domain name, playbook
   definitions, and references. Import validates the artifact before publication.
7. **No CMS literals in shared code:** Shared models use playbook, typology, feature, evidence requirement,
   prompt ref, policy ref, and workflow template terms. CMS wording lives in default YAML and tests.

## 4. Data Model

### 4.1 Domain Config

Add optional `playbooks` to `DomainConfig`:

- `version`: catalog version string.
- `items`: list of playbook definitions.

Each playbook definition includes:

- `id`, `version`, `title`, `summary`, `status`.
- `typology_ids`, `feature_ids`, `policy_rule_ids`.
- `evidence_requirements`: stable IDs, labels, descriptions, required flag, source types.
- `workflow_steps`: stable IDs, labels, capability refs, input refs, output refs, approval flags.
- `rag_prompts`: stable IDs, model ref, prompt version, system prompt, user prompt.
- `decision_guidance`: ordered analyst-facing guidance strings.
- `export_tags`: domain-pack artifact tags.

Validation rules:

- Catalog playbook IDs are unique.
- `(playbook_id, version)` pairs are unique.
- Playbook typology refs exist in `DomainConfig.typologies`.
- Playbook feature refs exist in `DomainConfig.feature_catalog.features`.
- Playbook policy refs exist in loaded `policy_rules` using the `pack.rule` format.
- Typology `playbook_ids` must reference declared playbooks.

### 4.2 Database

Add `fraud_playbook_snapshots`:

| Column | Purpose |
|--------|---------|
| `domain_name` | Domain pack name such as `medicare_fraud`. |
| `playbook_id` | Stable playbook ID. |
| `version` | Immutable published version. |
| `status` | `draft`, `published`, or `retired`. |
| `definition` | Validated playbook definition JSON. |
| `source` | `domain_config`, `api_import`, or `api_publish`. |
| `published_by` | Authenticated actor user ID. |
| `published_at` | Publication timestamp. |
| `created_at` | Insert timestamp. |
| `updated_at` | Last state-change timestamp. |

Primary key: `(domain_name, playbook_id, version)`.

Add `playbook_refs` JSONB fields where historical meaning must persist:

- `alert_history.generation_metadata.playbook_ref` remains metadata-backed in the first slice.
- `evidence_pack.provenance[*].metadata.playbook_ref` remains provenance-backed in the first slice.
- `cases.playbook_ref` should become a typed JSONB column in the cases persistence adapter because cases are the
  long-lived review artifact.

## 5. API Surface

Routes:

- `GET /knowledgebases/{knowledge_base_id}/playbooks`
- `GET /knowledgebases/{knowledge_base_id}/playbooks/{playbook_id}/versions/{version}`
- `POST /knowledgebases/{knowledge_base_id}/playbooks/{playbook_id}/publish`
- `POST /knowledgebases/{knowledge_base_id}/playbooks/import`
- `GET /knowledgebases/{knowledge_base_id}/playbooks/export`

RBAC:

- Viewer: list, detail, export.
- Analyst: none beyond read in this sprint.
- Admin: publish and import.

All endpoints return 404 for KBs outside the authenticated user's entitlement list.

## 6. Frontend Surface

Start with small reusable surfaces:

- `PlaybookBadge` for alert, cockpit, and case surfaces.
- `PlaybookDetailPanel` for title, version, status, typologies, required evidence, workflow steps, prompts, and
  decision guidance.
- `PlaybookManagerPage` only if no existing admin/config surface can host list/publish/import/export controls.

The first user-facing placements:

- Alert detail or queue row: badge for the playbook that generated or guided the alert.
- Investigation cockpit/case dossier: badge and compact detail for selected case/alert playbook ref.
- Management surface: list config-authored and DB-published versions, publish seed, export JSON.

## 7. Verification Gates

- Domain schema tests for valid playbooks, duplicate IDs, unknown refs, non-CMS omission, and CMS seeds.
- Playbook service tests for publish immutability, status transitions, and export/import round-trip.
- Migration replay and repository tests for `fraud_playbook_snapshots`.
- API tests for KB scoping, RBAC, list/detail/publish/import/export.
- OpenAPI export and frontend codegen after contract changes.
- Frontend tests for badge/detail rendering, management actions, and redaction-safe prompt display.
- Historical snapshot tests proving a new playbook version does not rewrite existing case meaning.

## 8. Open Questions Resolved By This ADR

- **Static config or database?** Both: config-authored seed plus DB-published immutable snapshots.
- **Domain-scoped or KB-scoped records?** Published snapshots are domain-scoped; API access is KB-scoped.
- **Workflow execution in SAFE-CMS-013?** No. Store workflow templates only.
- **Where do CMS strings live?** In domain packs and tests, not in shared services.
- **Can historical cases change when playbooks update?** No. Cases store playbook ID/version snapshots.
