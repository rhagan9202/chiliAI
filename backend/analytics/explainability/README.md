# analytics/explainability

Generates and serves **evidence packs** — the `shared.types.EvidencePack` that
explains why an alert fired: a narrative, the selected evidence items, the
alert's subgraph node/edge ids, score snapshot, optional per-feature
attributions and provenance references. Also owns contestable **explanation
reviews** (analyst annotations on parts of a generated pack, kept beside the
immutable pack rather than rewriting it) and the Markdown export renderer.

The narrative and attribution seams, their config switches
(`AnalyticsConfig.narrative_backend`, `AnalyticsConfig.attribution_backend`)
and the export rules are described in
[`../README.md`](../README.md) § Explainability narrative + attribution seams
and § Evidence pack export; this file does not repeat them.

## Layout

| File | Responsibility |
|------|----------------|
| `models.py` | `ExplanationContext` (alert, subgraph, items, scores, lineage), `ExplanationItem`, `ExplanationSubgraph`, `ExplanationLineage`, `ExplanationNarrative`, `NarrativeSection`. |
| `service_models.py` | `ExplainabilityRequest`, `ExplainabilityEvidence`, `ExplainabilityResponse`. |
| `protocols.py` | `ExplainabilityServiceProtocol`, `NarrativeGeneratorProtocol`, `FeatureAttributorProtocol` (both generator protocols must never raise). |
| `service.py` | `ExplainabilityService` (`generate`, `generate_from_context`) and `create_explainability_service`. |
| `repository.py` | `EvidencePackRepository` protocol — KB-scoped `put / get / delete_by_kb`. |
| `provenance.py` | `EvidenceProvenanceRepository` protocol and `EvidencePackProvenanceRepository`, which reads/replaces `EvidencePack.provenance` through an `EvidencePackRepository`. |
| `reviews.py` | Review models (`ExplanationReviewCreate`, `…Record`, `…Target`, `…Query`, `…Page`), `ExplanationReviewRepository` protocol, `InMemoryExplanationReviewRepository`, `ExplanationReviewService`. |
| `export.py` | `render_evidence_markdown`, `humanize_score_name`. |
| `exceptions.py` | `ExplainabilityError` → `…ConfigurationError`, `…InsufficientEvidenceError`, `…SourceError`. |
| `adapters/protocols.py` | `ExplainabilityContextSourceProtocol.load_context`. |
| `adapters/in_memory.py` | `InMemoryExplainabilityContextSource`. |
| `adapters/deterministic.py`, `adapters/llm_narrative.py` | `DeterministicNarrativeGenerator`, `LlmNarrativeGenerator`. |
| `adapters/shap_attribution.py` | `NoopFeatureAttributor`, `ShapRiskAttributor`. |
| `adapters/shap_adapter.py` | `ShapExplainabilityContextSource` (context-source seam; not selected in DI). |
| `adapters/evidence_in_memory.py`, `adapters/evidence_object_store.py` | `InMemoryEvidencePackRepository`, `ObjectStoreEvidencePackRepository`. |
| `adapters/reviews_postgres.py` | `PostgresExplanationReviewRepository`. |

## Contracts and invariants

- `generate_from_context` raises `ExplainabilityInsufficientEvidenceError`
  when the context has no explanation items; otherwise it selects up to
  `max_evidence_items` (default 3), builds the pack with provenance, and
  publishes one `ExplainabilityGeneratedEvent` (`explainability.generated`)
  per call. `generate` first loads the context from the configured context
  source, wrapping failures as `ExplainabilityConfigurationError` /
  `ExplainabilitySourceError`.
- A context's `lineage.playbook_ref` (`playbooks.models.PlaybookRef`) is copied
  into pack metadata — `service.py` imports it from `playbooks/`.
- **Reviews** are one record per `(knowledge_base_id, evidence_pack_id,
  target_type, target_id)`; `record_review` updates the existing record for a
  target rather than adding a second. Target types are `narrative`,
  `narrative_section`, `feature_attribution`, `evidence_item`,
  `provenance_reference`; the states `incomplete`, `misleading`,
  `unsupported`, `rejected` and `regeneration_requested` require at least one
  reason; comments are capped at 1,000 characters.

## How it is reached

- **Worker** — `agent/coordinator.py` builds the service with
  `create_explainability_service` at the Flow B assembly site and persists
  packs through `ObjectStoreEvidencePackRepository`.
- **API** — `api/routers/evidence.py`: `GET /evidence-packs/{id}`,
  `GET …/{id}/provenance`, `GET|POST …/{id}/reviews` (POST requires analyst),
  `GET …/{id}/export`, and the KB-scoped
  `GET /knowledgebases/{knowledge_base_id}/evidence-packs/{id}/provenance`.
  `api/routers/cases.py` and `api/routers/governance.py` also read packs.

## Persistence

- Evidence packs: object storage, key
  `knowledgebases/{kb_id}/evidence/{evidence_pack_id}.json`; `delete_by_kb`
  removes the prefix. Provenance is stored inside the pack.
- Reviews: table `explanation_reviews`
  (`database/migrations/versions/0017_explanation_reviews.py`), unique
  constraint `uq_explanation_reviews_target`.

## Current gaps

- `ExplainabilityContextSourceProtocol` carries a `TODO(production)` for batch
  and graph-depth context loading and a production context-source adapter;
  only the in-memory and (unwired) SHAP context sources exist.

## Tests

`tests/analytics/explainability/` — service, models, both narrative
generators, both SHAP modules, evidence/provenance repositories, reviews
(in-memory and Postgres), export.
