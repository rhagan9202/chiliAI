# chiliAI Project Librarian Ledger

Schema Version: 1.0
Last Invocation: 2026-05-22T00:00:00Z
Baseline: First-run initialization anchored to merge commit `acae4ac` (feature/ingestion-pipeline-e2e-demo merged into prod, 2026-05-22).

---

## Table 1: Documentation Inventory

| path | type | module/scope | last_verified_timestamp | last_modified_timestamp | responsible_agent |
|------|------|-------------|------------------------|------------------------|-------------------|
| `README.md` | README | root | 2026-05-22T00:00:00Z | 2026-05-22 | docs-keeper |
| `CLAUDE.md` | AGENT_Instructions.md | root | 2026-05-22T00:00:00Z | 2026-05-22 | docs-keeper |
| `.github/copilot-instructions.md` | AGENT_Instructions.md | root | 2026-05-22T00:00:00Z | 2026-05-22 | docs-keeper |
| `backend/README.md` | README | backend | 2026-05-22T00:00:00Z | 2026-05-22 | docs-keeper |
| `backend/agent/README.md` | README | backend/agent | 2026-05-22T00:00:00Z | 2026-05-22 | docs-keeper |
| `backend/analytics/README.md` | README | backend/analytics | 2026-05-22T00:00:00Z | 2026-05-22 | docs-keeper |
| `backend/analytics/metrics/README.md` | README | backend/analytics/metrics | 2026-05-22T00:00:00Z | 2026-05-22 | docs-keeper |
| `backend/database/README.md` | README | backend/database | 2026-05-22T00:00:00Z | 2026-05-22 | docs-keeper |
| `backend/embeddings/README.md` | README | backend/embeddings | 2026-05-22T00:00:00Z | 2026-05-22 | docs-keeper |
| `backend/graph/README.md` | README | backend/graph | 2026-05-22T00:00:00Z | 2026-05-22 | docs-keeper |
| `backend/ingestion/README.md` | README | backend/ingestion | 2026-05-22T00:00:00Z | 2026-05-22 | docs-keeper |
| `backend/llm/README.md` | README | backend/llm | 2026-05-22T00:00:00Z | 2026-05-22 | docs-keeper |
| `backend/records/README.md` | README | backend/records | 2026-05-22T00:00:00Z | 2026-05-22 | docs-keeper |
| `backend/vectorstore/README.md` | README | backend/vectorstore | 2026-05-22T00:00:00Z | 2026-05-22 | docs-keeper |
| `chili_app/README.md` | README | chili_app | 2026-05-22T00:00:00Z | 2026-05-22 | docs-keeper |
| `infra/README.md` | README | infra | 2026-05-22T00:00:00Z | 2026-05-22 | docs-keeper |
| `sample_data/README.md` | README | sample_data | 2026-05-22T00:00:00Z | 2026-05-22 | docs-keeper |
| `docs/architecture.md` | architecture | cross-cutting | 2026-05-22T00:00:00Z | 2026-05-22 | both |
| `docs/onboarding.md` | other-doc | cross-cutting | 2026-05-22T00:00:00Z | unknown | docs-keeper |
| `docs/security_checklist.md` | other-doc | cross-cutting | 2026-05-22T00:00:00Z | unknown | docs-keeper |
| `docs/archive/todos_and_stubs_audit_2026-05-05.md` | other-doc | cross-cutting | 2026-05-24T00:00:00Z | 2026-05-05 | docs-keeper |
| `docs/system_architecture_diagram.md` | architecture | cross-cutting | 2026-05-22T00:00:00Z | unknown | both |
| `docs/wiki/README.md` | wiki-topic | cross-cutting | 2026-05-22T00:00:00Z | 2026-05-20 | wiki-curator |
| `docs/wiki/CHANGELOG.md` | wiki-topic | cross-cutting | 2026-05-22T00:00:00Z | 2026-05-20 | wiki-curator |
| `docs/wiki/modules/api.md` | wiki-topic | backend/api | 2026-05-22T00:00:00Z | 2026-05-20 | wiki-curator |
| `docs/wiki/modules/agent.md` | wiki-topic | backend/agent | 2026-05-22T00:00:00Z | 2026-05-20 | wiki-curator |
| `docs/wiki/modules/ingestion.md` | wiki-topic | backend/ingestion | 2026-05-22T00:00:00Z | 2026-05-20 | wiki-curator |
| `docs/wiki/modules/graph.md` | wiki-topic | backend/graph | 2026-05-22T00:00:00Z | 2026-05-20 | wiki-curator |
| `docs/wiki/modules/vectorstore.md` | wiki-topic | backend/vectorstore | 2026-05-22T00:00:00Z | 2026-05-20 | wiki-curator |
| `docs/wiki/modules/embeddings.md` | wiki-topic | backend/embeddings | 2026-05-22T00:00:00Z | 2026-05-20 | wiki-curator |
| `docs/wiki/modules/rag.md` | wiki-topic | backend/rag | 2026-05-22T00:00:00Z | 2026-05-20 | wiki-curator |
| `docs/wiki/modules/llm.md` | wiki-topic | backend/llm | 2026-05-22T00:00:00Z | 2026-05-20 | wiki-curator |
| `docs/wiki/modules/analytics.md` | wiki-topic | backend/analytics | 2026-05-22T00:00:00Z | 2026-05-20 | wiki-curator |
| `docs/wiki/modules/monitoring.md` | wiki-topic | backend/monitoring | 2026-05-22T00:00:00Z | 2026-05-20 | wiki-curator |
| `docs/wiki/modules/records.md` | wiki-topic | backend/records | 2026-05-22T00:00:00Z | 2026-05-20 | wiki-curator |
| `docs/wiki/modules/database.md` | wiki-topic | backend/database | 2026-05-22T00:00:00Z | 2026-05-20 | wiki-curator |
| `docs/wiki/modules/events.md` | wiki-topic | backend/events | 2026-05-22T00:00:00Z | 2026-05-20 | wiki-curator |
| `docs/wiki/modules/storage.md` | wiki-topic | backend/storage | 2026-05-22T00:00:00Z | 2026-05-20 | wiki-curator |
| `docs/wiki/modules/config.md` | wiki-topic | backend/config | 2026-05-22T00:00:00Z | 2026-05-20 | wiki-curator |
| `docs/wiki/modules/shared.md` | wiki-topic | backend/shared | 2026-05-22T00:00:00Z | 2026-05-20 | wiki-curator |
| `docs/wiki/modules/frontend.md` | wiki-topic | chili_app | 2026-05-22T00:00:00Z | 2026-05-20 | wiki-curator |
| `docs/wiki/contracts/shared-types.md` | wiki-topic | backend/shared | 2026-05-22T00:00:00Z | 2026-05-20 | wiki-curator |
| `docs/wiki/contracts/api-routes.md` | wiki-topic | backend/api | 2026-05-22T00:00:00Z | 2026-05-20 | wiki-curator |
| `docs/wiki/contracts/events.md` | wiki-topic | backend/events | 2026-05-22T00:00:00Z | 2026-05-20 | wiki-curator |
| `docs/wiki/contracts/domain-config.md` | wiki-topic | backend/config | 2026-05-22T00:00:00Z | 2026-05-20 | wiki-curator |
| `docs/wiki/flows/ingestion-flow.md` | wiki-topic | backend/ingestion | 2026-05-22T00:00:00Z | 2026-05-20 | wiki-curator |
| `docs/wiki/flows/records-ingestion-flow.md` | wiki-topic | backend/records | 2026-05-22T00:00:00Z | 2026-05-20 | wiki-curator |
| `docs/wiki/flows/query-flow.md` | wiki-topic | backend/rag | 2026-05-22T00:00:00Z | 2026-05-20 | wiki-curator |
| `docs/wiki/flows/auth-flow.md` | wiki-topic | backend/api | 2026-05-22T00:00:00Z | 2026-05-20 | wiki-curator |
| `docs/superpowers/specs/notes/synthetic-policy-corpus.md` | other-doc | backend/ingestion | 2026-05-22T00:00:00Z | 2026-05-22 | docs-keeper |
| `docs/superpowers/specs/2026-05-22-ingestion-pipeline-e2e-demo-design.md` | other-doc | cross-cutting | 2026-05-22T00:00:00Z | 2026-05-22 | docs-keeper |
| `docs/superpowers/plans/2026-05-22-ingestion-pipeline-e2e-demo.md` | other-doc | cross-cutting | 2026-05-22T00:00:00Z | 2026-05-22 | docs-keeper |
| `docs/testing/knowledge_base_fixtures/README.md` | README | docs/testing | 2026-05-22T00:00:00Z | unknown | docs-keeper |
| `docs/testing/knowledge_base_fixtures/medicare_fraud/README.md` | README | docs/testing | 2026-05-22T00:00:00Z | unknown | docs-keeper |
| `docs/archive/README.md` | other-doc | archive | 2026-05-22T00:00:00Z | unknown | none |
| `docs/archive/codebase_audit_2026-04-27.md` | other-doc | archive | 2026-05-22T00:00:00Z | 2026-04-27 | none |
| `docs/archive/project_status_report.md` | other-doc | archive | 2026-05-22T00:00:00Z | unknown | none |

---

## Table 2: Change Manifest (Since Merge Commit acae4ac — feature/ingestion-pipeline-e2e-demo)

> Changes introduced by the feature/ingestion-pipeline-e2e-demo branch merge. Source: `git log --since` comparison against the prior prod tip (commit before `acae4ac`).

| path | change_type | last_modified_timestamp | affects_docs |
|------|-------------|------------------------|--------------|
| `backend/shared/provenance.py` | added | 2026-05-22 | `docs/architecture.md`, `docs/wiki/modules/shared.md`, `docs/wiki/contracts/shared-types.md`, `backend/graph/README.md`, `backend/vectorstore/README.md` |
| `backend/llm/adapters/ollama_adapter.py` | added | 2026-05-22 | `backend/llm/README.md`, `docs/wiki/modules/llm.md` |
| `backend/llm/adapters/fallback.py` | added | 2026-05-22 | `backend/llm/README.md`, `docs/wiki/modules/llm.md` |
| `backend/llm/factory.py` | added | 2026-05-22 | `backend/llm/README.md`, `docs/wiki/modules/llm.md` |
| `backend/ingestion/extractor.py` | modified | 2026-05-22 | `backend/ingestion/README.md`, `docs/wiki/modules/ingestion.md`, `docs/architecture.md` |
| `backend/config/schema.py` | modified | 2026-05-22 | `docs/architecture.md`, `docs/wiki/contracts/domain-config.md`, `CLAUDE.md` |
| `backend/config/defaults/medicare_fraud_cms_desynpuf.yaml` | modified | 2026-05-22 | `docs/architecture.md`, `docs/wiki/contracts/domain-config.md`, `backend/records/README.md` |
| `backend/api/routers/knowledgebases.py` | modified | 2026-05-22 | `docs/architecture.md`, `docs/wiki/contracts/api-routes.md`, `docs/wiki/modules/api.md` |
| `backend/api/routers/records.py` | modified | 2026-05-22 | `docs/wiki/contracts/api-routes.md`, `docs/wiki/modules/api.md`, `backend/records/README.md` |
| `backend/graph/protocols.py` | modified | 2026-05-22 | `backend/graph/README.md`, `docs/wiki/modules/graph.md` |
| `backend/graph/service.py` | modified | 2026-05-22 | `backend/graph/README.md`, `docs/wiki/modules/graph.md` |
| `backend/graph/adapters/in_memory.py` | modified | 2026-05-22 | `backend/graph/README.md`, `docs/wiki/modules/graph.md` |
| `backend/graph/adapters/neo4j_adapter.py` | modified | 2026-05-22 | `backend/graph/README.md`, `docs/wiki/modules/graph.md` |
| `backend/vectorstore/protocols.py` | modified | 2026-05-22 | `backend/vectorstore/README.md`, `docs/wiki/modules/vectorstore.md` |
| `backend/vectorstore/service.py` | modified | 2026-05-22 | `backend/vectorstore/README.md`, `docs/wiki/modules/vectorstore.md` |
| `backend/vectorstore/adapters/in_memory.py` | modified | 2026-05-22 | `backend/vectorstore/README.md`, `docs/wiki/modules/vectorstore.md` |
| `backend/vectorstore/adapters/qdrant_adapter.py` | modified | 2026-05-22 | `backend/vectorstore/README.md`, `docs/wiki/modules/vectorstore.md` |
| `backend/records/adapters/in_memory.py` | modified | 2026-05-22 | `backend/records/README.md`, `docs/wiki/modules/records.md` |
| `backend/records/adapters/postgres.py` | modified | 2026-05-22 | `backend/records/README.md`, `docs/wiki/modules/records.md` |
| `backend/agent/coordinator.py` | modified | 2026-05-22 | `backend/agent/README.md`, `docs/wiki/modules/agent.md`, `docs/architecture.md` |
| `backend/events/types.py` | modified | 2026-05-22 | `docs/wiki/contracts/events.md`, `docs/architecture.md` |
| `backend/shared/types.py` | modified | 2026-05-22 | `docs/wiki/contracts/shared-types.md`, `docs/architecture.md` |
| `backend/shared/tracing.py` | modified | 2026-05-22 | `docs/wiki/modules/shared.md` |
| `backend/shared/logging.py` | modified | 2026-05-22 | `docs/wiki/modules/shared.md` |
| `tools/sample_data/build_tennessee_subset.py` | added | 2026-05-22 | `sample_data/README.md`, `docs/architecture.md` |
| `scripts/demo_ingest_tn_subset.sh` | added | 2026-05-22 | `README.md`, `docs/architecture.md` |
| `backend/tests/ingestion/fixtures/` | added | 2026-05-22 | `backend/ingestion/README.md` |
