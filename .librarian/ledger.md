# chiliAI Project Librarian Ledger

Schema Version: 1.0
Last Invocation: 2026-05-28T03:28:12Z
Baseline: Refreshed from current working tree on branch `working`; HEAD `dc9ce1645812d4e9706c5f361293a8af15b72892 2026-05-27T20:30:22-04:00 Merge pull request #12 from rhagan9202/contract-alignment-openapi`.

---

## Table 1: Documentation Inventory

| path | type | module/scope | last_verified_timestamp | last_modified_timestamp | responsible_agent |
|------|------|-------------|------------------------|------------------------|-------------------|
| `.github/agents/project_manager.agent.md` | planning | agent-github | 2026-05-28T03:28:12Z | 2026-05-27T20:19:26-04:00 | docs-keeper |
| `.github/agents/requirements_gatherer.agent.md` | planning | agent-github | 2026-05-28T03:28:12Z | 2026-05-27T20:19:26-04:00 | docs-keeper |
| `.github/copilot-instructions.md` | AGENT_Instructions.md | agent-github | 2026-05-28T03:28:12Z | 2026-05-26T18:47:54-04:00 | docs-keeper |
| `.github/instructions/backend.instructions.md` | AGENT_Instructions.md | agent-github | 2026-05-28T03:28:12Z | 2026-05-15T12:04:57-04:00 | docs-keeper |
| `.github/prompts/audit-backend-architecture.prompt.md` | architecture | agent-github | 2026-05-28T03:28:12Z | 2026-05-11T09:42:17-04:00 | docs-keeper |
| `.github/prompts/fix-audit-findings.prompt.md` | planning | agent-github | 2026-05-28T03:28:12Z | 2026-04-12T20:30:41-04:00 | docs-keeper |
| `.github/prompts/plan-humanInTheLoopFeedback.prompt.md` | planning | agent-github | 2026-05-28T03:28:12Z | 2026-05-11T09:42:17-04:00 | docs-keeper |
| `.github/prompts/scaffold-backend-module.prompt.md` | planning | agent-github | 2026-05-28T03:28:12Z | 2026-05-11T09:42:17-04:00 | docs-keeper |
| `.github/skills/refresh-requirements/SKILL.md` | planning | agent-github | 2026-05-28T03:28:12Z | 2026-05-27T20:19:26-04:00 | docs-keeper |
| `.librarian/ledger.md` | other-doc | .librarian | 2026-05-28T03:28:12Z | 2026-05-24T15:02:44-04:00 | docs-keeper |
| `CLAUDE.md` | AGENT_Instructions.md | root | 2026-05-28T03:28:12Z | 2026-05-26T18:47:54-04:00 | docs-keeper |
| `README.md` | README | root | 2026-05-28T03:28:12Z | 2026-05-26T18:47:54-04:00 | docs-keeper |
| `backend/README.md` | README | backend | 2026-05-28T03:28:12Z | 2026-05-26T18:47:54-04:00 | docs-keeper |
| `backend/agent/README.md` | README | backend/agent | 2026-05-28T03:28:12Z | 2026-05-22T11:08:54-04:00 | docs-keeper |
| `backend/analytics/README.md` | README | backend/analytics | 2026-05-28T03:28:12Z | 2026-05-18T09:12:37-04:00 | docs-keeper |
| `backend/analytics/metrics/README.md` | README | backend/analytics | 2026-05-28T03:28:12Z | 2026-05-16T18:51:47-04:00 | docs-keeper |
| `backend/database/README.md` | README | backend/database | 2026-05-28T03:28:12Z | 2026-05-15T16:15:52-04:00 | docs-keeper |
| `backend/embeddings/README.md` | README | backend/embeddings | 2026-05-28T03:28:12Z | 2026-05-21T18:50:35-04:00 | docs-keeper |
| `backend/graph/README.md` | README | backend/graph | 2026-05-28T03:28:12Z | 2026-05-22T11:08:54-04:00 | docs-keeper |
| `backend/ingestion/README.md` | README | backend/ingestion | 2026-05-28T03:28:12Z | 2026-05-22T11:08:54-04:00 | docs-keeper |
| `backend/llm/README.md` | README | backend/llm | 2026-05-28T03:28:12Z | 2026-05-22T11:08:54-04:00 | docs-keeper |
| `backend/records/README.md` | README | backend/records | 2026-05-28T03:28:12Z | 2026-05-22T11:08:54-04:00 | docs-keeper |
| `backend/tests/ingestion/fixtures/policies/policy_001_inpatient_billing.md` | other-doc | backend/tests | 2026-05-28T03:28:12Z | 2026-05-22T10:50:13-04:00 | docs-keeper |
| `backend/tests/ingestion/fixtures/policies/policy_002_provider_exclusion.md` | other-doc | backend/tests | 2026-05-28T03:28:12Z | 2026-05-22T10:50:13-04:00 | docs-keeper |
| `backend/vectorstore/README.md` | README | backend/vectorstore | 2026-05-28T03:28:12Z | 2026-05-22T11:08:54-04:00 | docs-keeper |
| `chili_app/README.md` | README | chili_app | 2026-05-28T03:28:12Z | 2026-05-26T18:47:54-04:00 | docs-keeper |
| `docs/architecture.md` | architecture | docs | 2026-05-28T03:28:12Z | 2026-05-26T18:47:54-04:00 | docs-keeper |
| `docs/backlog/README.md` | README | backlog | 2026-05-28T03:28:12Z | 2026-05-24T22:51:29-04:00 | docs-keeper |
| `docs/backlog/_cicd.md` | planning | backlog | 2026-05-28T03:28:12Z | 2026-05-24T22:51:29-04:00 | docs-keeper |
| `docs/backlog/_infra.md` | planning | backlog | 2026-05-28T03:28:12Z | 2026-05-24T22:51:29-04:00 | docs-keeper |
| `docs/backlog/_multitenancy.md` | planning | backlog | 2026-05-28T03:28:12Z | 2026-05-24T22:51:29-04:00 | docs-keeper |
| `docs/backlog/_observability.md` | planning | backlog | 2026-05-28T03:28:12Z | 2026-05-24T22:51:29-04:00 | docs-keeper |
| `docs/backlog/_plugins.md` | planning | backlog | 2026-05-28T03:28:12Z | 2026-05-24T22:51:29-04:00 | docs-keeper |
| `docs/backlog/_security.md` | planning | backlog | 2026-05-28T03:28:12Z | 2026-05-24T22:51:29-04:00 | docs-keeper |
| `docs/backlog/agent.md` | planning | backlog | 2026-05-28T03:28:12Z | 2026-05-24T22:51:29-04:00 | docs-keeper |
| `docs/backlog/analytics.md` | planning | backlog | 2026-05-28T03:28:12Z | 2026-05-24T22:51:29-04:00 | docs-keeper |
| `docs/backlog/api.md` | planning | backlog | 2026-05-28T03:28:12Z | 2026-05-24T22:51:29-04:00 | docs-keeper |
| `docs/backlog/config.md` | planning | backlog | 2026-05-28T03:28:12Z | 2026-05-24T22:51:29-04:00 | docs-keeper |
| `docs/backlog/database.md` | planning | backlog | 2026-05-28T03:28:12Z | 2026-05-24T22:51:29-04:00 | docs-keeper |
| `docs/backlog/embeddings.md` | planning | backlog | 2026-05-28T03:28:12Z | 2026-05-24T22:51:29-04:00 | docs-keeper |
| `docs/backlog/events.md` | planning | backlog | 2026-05-28T03:28:12Z | 2026-05-24T22:51:29-04:00 | docs-keeper |
| `docs/backlog/frontend.md` | planning | backlog | 2026-05-28T03:28:12Z | 2026-05-24T22:51:29-04:00 | docs-keeper |
| `docs/backlog/graph.md` | planning | backlog | 2026-05-28T03:28:12Z | 2026-05-24T22:51:29-04:00 | docs-keeper |
| `docs/backlog/ingestion.md` | planning | backlog | 2026-05-28T03:28:12Z | 2026-05-24T22:51:29-04:00 | docs-keeper |
| `docs/backlog/knowledgebases.md` | planning | backlog | 2026-05-28T03:28:12Z | 2026-05-24T22:51:29-04:00 | docs-keeper |
| `docs/backlog/llm.md` | planning | backlog | 2026-05-28T03:28:12Z | 2026-05-24T22:51:29-04:00 | docs-keeper |
| `docs/backlog/monitoring.md` | planning | backlog | 2026-05-28T03:28:12Z | 2026-05-24T22:51:29-04:00 | docs-keeper |
| `docs/backlog/rag.md` | planning | backlog | 2026-05-28T03:28:12Z | 2026-05-24T22:51:29-04:00 | docs-keeper |
| `docs/backlog/records.md` | planning | backlog | 2026-05-28T03:28:12Z | 2026-05-24T22:51:29-04:00 | docs-keeper |
| `docs/backlog/shared.md` | planning | backlog | 2026-05-28T03:28:12Z | 2026-05-24T22:51:29-04:00 | docs-keeper |
| `docs/backlog/storage.md` | planning | backlog | 2026-05-28T03:28:12Z | 2026-05-24T22:51:29-04:00 | docs-keeper |
| `docs/backlog/vectorstore.md` | planning | backlog | 2026-05-28T03:28:12Z | 2026-05-24T22:51:29-04:00 | docs-keeper |
| `docs/ledger/README.md` | README | ledger | 2026-05-28T03:28:12Z | 2026-05-22T13:04:54-04:00 | docs-keeper |
| `docs/ledger/config-schema.md` | other-doc | ledger | 2026-05-28T03:28:12Z | 2026-05-22T13:04:54-04:00 | docs-keeper |
| `docs/ledger/event-catalog.md` | other-doc | ledger | 2026-05-28T03:28:12Z | 2026-05-22T13:04:54-04:00 | docs-keeper |
| `docs/ledger/http-routes.md` | other-doc | ledger | 2026-05-28T03:28:12Z | 2026-05-22T13:04:54-04:00 | docs-keeper |
| `docs/ledger/module-map.md` | other-doc | ledger | 2026-05-28T03:28:12Z | 2026-05-22T13:04:54-04:00 | docs-keeper |
| `docs/ledger/protocol-contracts.md` | other-doc | ledger | 2026-05-28T03:28:12Z | 2026-05-22T13:04:54-04:00 | docs-keeper |
| `docs/ledger/tooling-inventory.md` | other-doc | ledger | 2026-05-28T03:28:12Z | 2026-05-22T13:04:54-04:00 | docs-keeper |
| `docs/onboarding.md` | other-doc | docs | 2026-05-28T03:28:12Z | 2026-05-18T15:23:25-04:00 | docs-keeper |
| `docs/project/planning/backlog.md` | planning | project-planning | 2026-05-28T03:28:12Z | 2026-05-27T20:19:26-04:00 | docs-keeper |
| `docs/project/planning/requirements.md` | planning | project-planning | 2026-05-28T03:28:12Z | 2026-05-27T20:19:26-04:00 | docs-keeper |
| `docs/project/planning/sprints/2026-22.md` | planning | project-planning | 2026-05-28T03:28:12Z | 2026-05-27T20:19:26-04:00 | docs-keeper |
| `docs/rendered/system_architecture_diagram_rendered.md` | architecture | docs | 2026-05-28T03:28:12Z | 2026-05-11T09:42:17-04:00 | docs-keeper |
| `docs/security_checklist.md` | other-doc | docs | 2026-05-28T03:28:12Z | 2026-05-12T19:26:51-04:00 | docs-keeper |
| `docs/superpowers/plans/2026-05-08-auth-rbac-enforcement.md` | planning | implementation-planning | 2026-05-28T03:28:12Z | 2026-05-08T08:34:37-04:00 | docs-keeper |
| `docs/superpowers/plans/2026-05-14-backend-persistence-foundation.md` | planning | implementation-planning | 2026-05-28T03:28:12Z | 2026-05-15T00:01:27-04:00 | docs-keeper |
| `docs/superpowers/plans/2026-05-15-records-module-structured-ingestion.md` | planning | implementation-planning | 2026-05-28T03:28:12Z | 2026-05-17T19:50:09-04:00 | docs-keeper |
| `docs/superpowers/plans/2026-05-16-persistence-plan-c-wiring-hardening.md` | planning | implementation-planning | 2026-05-28T03:28:12Z | 2026-05-17T19:50:09-04:00 | docs-keeper |
| `docs/superpowers/plans/2026-05-17-ingestion-studio-ui-ux-implementation.md` | planning | implementation-planning | 2026-05-28T03:28:12Z | 2026-05-16T21:58:38-04:00 | docs-keeper |
| `docs/superpowers/plans/2026-05-19-cms-record-ingestion-config.md` | planning | implementation-planning | 2026-05-28T03:28:12Z | 2026-05-19T19:20:50-04:00 | docs-keeper |
| `docs/superpowers/plans/2026-05-19-embeddings-1-0.md` | planning | implementation-planning | 2026-05-28T03:28:12Z | 2026-05-19T17:36:37-04:00 | docs-keeper |
| `docs/superpowers/plans/2026-05-19-vectorstore-1-0.md` | planning | implementation-planning | 2026-05-28T03:28:12Z | 2026-05-19T14:10:34-04:00 | docs-keeper |
| `docs/superpowers/plans/2026-05-21-dual-graph-contract.md` | planning | implementation-planning | 2026-05-28T03:28:12Z | 2026-05-21T16:59:49-04:00 | docs-keeper |
| `docs/superpowers/plans/2026-05-21-ingestion-prerequisite-vs-error.md` | planning | implementation-planning | 2026-05-28T03:28:12Z | 2026-05-21T13:22:01-04:00 | docs-keeper |
| `docs/superpowers/plans/2026-05-21-kb-contextual-entry-points.md` | planning | implementation-planning | 2026-05-28T03:28:12Z | 2026-05-21T11:57:36-04:00 | docs-keeper |
| `docs/superpowers/plans/2026-05-21-neo4j-graph-indexes.md` | planning | implementation-planning | 2026-05-28T03:28:12Z | 2026-05-21T15:03:01-04:00 | docs-keeper |
| `docs/superpowers/plans/2026-05-22-ingestion-pipeline-e2e-demo.md` | planning | implementation-planning | 2026-05-28T03:28:12Z | 2026-05-22T08:25:14-04:00 | docs-keeper |
| `docs/superpowers/plans/2026-05-24-complete-backlog.md` | planning | implementation-planning | 2026-05-28T03:28:12Z | 2026-05-24T21:20:24-04:00 | docs-keeper |
| `docs/superpowers/plans/2026-05-26-frontend-backend-contract-alignment.md` | planning | implementation-planning | 2026-05-28T03:28:12Z | 2026-05-26T17:09:13-04:00 | docs-keeper |
| `docs/superpowers/plans/2026-05-27-production-readiness-remediation.md` | planning | implementation-planning | 2026-05-28T03:28:12Z | 2026-05-27T10:42:59-04:00 | docs-keeper |
| `docs/superpowers/specs/2026-05-08-auth-rbac-enforcement-design.md` | planning | implementation-planning | 2026-05-28T03:28:12Z | 2026-05-08T08:20:26-04:00 | docs-keeper |
| `docs/superpowers/specs/2026-05-14-backend-persistence-design.md` | planning | implementation-planning | 2026-05-28T03:28:12Z | 2026-05-14T23:42:54-04:00 | docs-keeper |
| `docs/superpowers/specs/2026-05-17-ingestion-studio-ui-ux-design.md` | planning | implementation-planning | 2026-05-28T03:28:12Z | 2026-05-16T21:58:38-04:00 | docs-keeper |
| `docs/superpowers/specs/2026-05-19-embeddings-1-0-design.md` | planning | implementation-planning | 2026-05-28T03:28:12Z | 2026-05-19T17:27:44-04:00 | docs-keeper |
| `docs/superpowers/specs/2026-05-19-vectorstore-1-0-design.md` | planning | implementation-planning | 2026-05-28T03:28:12Z | 2026-05-19T14:03:35-04:00 | docs-keeper |
| `docs/superpowers/specs/2026-05-21-dual-graph-contract-design.md` | planning | implementation-planning | 2026-05-28T03:28:12Z | 2026-05-21T16:59:49-04:00 | docs-keeper |
| `docs/superpowers/specs/2026-05-21-ingestion-prerequisite-vs-error-design.md` | planning | implementation-planning | 2026-05-28T03:28:12Z | 2026-05-21T13:22:01-04:00 | docs-keeper |
| `docs/superpowers/specs/2026-05-21-kb-contextual-entry-points-design.md` | planning | implementation-planning | 2026-05-28T03:28:12Z | 2026-05-21T11:57:36-04:00 | docs-keeper |
| `docs/superpowers/specs/2026-05-21-neo4j-graph-indexes-design.md` | planning | implementation-planning | 2026-05-28T03:28:12Z | 2026-05-21T15:03:01-04:00 | docs-keeper |
| `docs/superpowers/specs/2026-05-22-ingestion-pipeline-e2e-demo-design.md` | planning | implementation-planning | 2026-05-28T03:28:12Z | 2026-05-22T08:12:37-04:00 | docs-keeper |
| `docs/superpowers/specs/2026-05-24-complete-backlog-design.md` | planning | implementation-planning | 2026-05-28T03:28:12Z | 2026-05-24T21:03:40-04:00 | docs-keeper |
| `docs/superpowers/specs/2026-05-26-frontend-backend-contract-alignment-design.md` | planning | implementation-planning | 2026-05-28T03:28:12Z | 2026-05-26T16:59:01-04:00 | docs-keeper |
| `docs/superpowers/specs/2026-05-27-production-readiness-remediation-design.md` | planning | implementation-planning | 2026-05-28T03:28:12Z | 2026-05-27T10:33:17-04:00 | docs-keeper |
| `docs/superpowers/specs/notes/synthetic-policy-corpus.md` | planning | implementation-planning | 2026-05-28T03:28:12Z | 2026-05-22T08:12:37-04:00 | docs-keeper |
| `docs/system_architecture_diagram.md` | architecture | docs | 2026-05-28T03:28:12Z | 2026-05-17T14:14:12-04:00 | docs-keeper |
| `docs/testing/knowledge_base_fixtures/README.md` | README | docs | 2026-05-28T03:28:12Z | 2026-04-27T19:01:28-04:00 | docs-keeper |
| `docs/testing/knowledge_base_fixtures/medicare_fraud/README.md` | README | docs | 2026-05-28T03:28:12Z | 2026-04-27T19:01:28-04:00 | docs-keeper |
| `docs/wiki/CHANGELOG.md` | wiki-topic | cross-cutting | 2026-05-28T03:28:12Z | 2026-05-22T13:21:08-04:00 | wiki-curator |
| `docs/wiki/README.md` | README | cross-cutting | 2026-05-28T03:28:12Z | 2026-05-20T18:54:22-04:00 | docs-keeper |
| `docs/wiki/contracts/api-routes.md` | wiki-topic | cross-cutting | 2026-05-28T03:28:12Z | 2026-05-22T13:21:08-04:00 | wiki-curator |
| `docs/wiki/contracts/domain-config.md` | wiki-topic | cross-cutting | 2026-05-28T03:28:12Z | 2026-05-22T13:21:08-04:00 | wiki-curator |
| `docs/wiki/contracts/events.md` | wiki-topic | cross-cutting | 2026-05-28T03:28:12Z | 2026-05-22T13:04:54-04:00 | wiki-curator |
| `docs/wiki/contracts/shared-types.md` | wiki-topic | cross-cutting | 2026-05-28T03:28:12Z | 2026-05-22T13:04:54-04:00 | wiki-curator |
| `docs/wiki/flows/auth-flow.md` | wiki-topic | cross-cutting | 2026-05-28T03:28:12Z | 2026-05-20T18:54:22-04:00 | wiki-curator |
| `docs/wiki/flows/ingestion-flow.md` | wiki-topic | cross-cutting | 2026-05-28T03:28:12Z | 2026-05-22T13:21:08-04:00 | wiki-curator |
| `docs/wiki/flows/query-flow.md` | wiki-topic | cross-cutting | 2026-05-28T03:28:12Z | 2026-05-20T18:54:22-04:00 | wiki-curator |
| `docs/wiki/flows/records-ingestion-flow.md` | wiki-topic | cross-cutting | 2026-05-28T03:28:12Z | 2026-05-22T13:21:08-04:00 | wiki-curator |
| `docs/wiki/modules/agent.md` | wiki-topic | backend/agent | 2026-05-28T03:28:12Z | 2026-05-22T13:21:08-04:00 | wiki-curator |
| `docs/wiki/modules/analytics.md` | wiki-topic | backend/analytics | 2026-05-28T03:28:12Z | 2026-05-20T18:54:22-04:00 | wiki-curator |
| `docs/wiki/modules/api.md` | wiki-topic | backend/api | 2026-05-28T03:28:12Z | 2026-05-20T18:54:22-04:00 | wiki-curator |
| `docs/wiki/modules/config.md` | wiki-topic | backend/config | 2026-05-28T03:28:12Z | 2026-05-20T18:54:22-04:00 | wiki-curator |
| `docs/wiki/modules/database.md` | wiki-topic | backend/database | 2026-05-28T03:28:12Z | 2026-05-20T18:54:22-04:00 | wiki-curator |
| `docs/wiki/modules/embeddings.md` | wiki-topic | backend/embeddings | 2026-05-28T03:28:12Z | 2026-05-20T18:54:22-04:00 | wiki-curator |
| `docs/wiki/modules/events.md` | wiki-topic | backend/events | 2026-05-28T03:28:12Z | 2026-05-20T18:54:22-04:00 | wiki-curator |
| `docs/wiki/modules/frontend.md` | wiki-topic | chili_app | 2026-05-28T03:28:12Z | 2026-05-20T18:54:22-04:00 | wiki-curator |
| `docs/wiki/modules/graph.md` | wiki-topic | backend/graph | 2026-05-28T03:28:12Z | 2026-05-22T13:21:08-04:00 | wiki-curator |
| `docs/wiki/modules/ingestion.md` | wiki-topic | backend/ingestion | 2026-05-28T03:28:12Z | 2026-05-22T13:21:08-04:00 | wiki-curator |
| `docs/wiki/modules/knowledgebases.md` | wiki-topic | backend/knowledgebases | 2026-05-28T03:28:12Z | 2026-05-28T03:28:12Z | wiki-curator |
| `docs/wiki/modules/llm.md` | wiki-topic | backend/llm | 2026-05-28T03:28:12Z | 2026-05-22T13:04:54-04:00 | wiki-curator |
| `docs/wiki/modules/monitoring.md` | wiki-topic | backend/monitoring | 2026-05-28T03:28:12Z | 2026-05-20T18:54:22-04:00 | wiki-curator |
| `docs/wiki/modules/rag.md` | wiki-topic | backend/rag | 2026-05-28T03:28:12Z | 2026-05-20T18:54:22-04:00 | wiki-curator |
| `docs/wiki/modules/records.md` | wiki-topic | backend/records | 2026-05-28T03:28:12Z | 2026-05-22T13:21:08-04:00 | wiki-curator |
| `docs/wiki/modules/shared.md` | wiki-topic | backend/shared | 2026-05-28T03:28:12Z | 2026-05-22T13:21:08-04:00 | wiki-curator |
| `docs/wiki/modules/storage.md` | wiki-topic | backend/storage | 2026-05-28T03:28:12Z | 2026-05-20T18:54:22-04:00 | wiki-curator |
| `docs/wiki/modules/vectorstore.md` | wiki-topic | backend/vectorstore | 2026-05-28T03:28:12Z | 2026-05-22T13:21:08-04:00 | wiki-curator |
| `infra/README.md` | README | infra | 2026-05-28T03:28:12Z | 2026-04-27T09:54:05-04:00 | docs-keeper |
| `sample_data/README.md` | README | sample_data | 2026-05-28T03:28:12Z | 2026-05-21T20:39:22-04:00 | docs-keeper |

---

## Table 2: Change Manifest

> Source: current working-tree documentation changes on branch `working`.

| path | change_type | last_modified_timestamp | affects_docs |
|------|-------------|------------------------|--------------|
| `.github/agents/project_manager.agent.md` | modified | 2026-05-27T20:19:26-04:00 | `CLAUDE.md`, `.github/copilot-instructions.md`, `docs/project/planning/requirements.md` |
| `.github/agents/requirements_gatherer.agent.md` | modified | 2026-05-27T20:19:26-04:00 | `CLAUDE.md`, `.github/copilot-instructions.md`, `docs/project/planning/requirements.md` |
| `.github/skills/refresh-requirements/SKILL.md` | modified | 2026-05-27T20:19:26-04:00 | `CLAUDE.md`, `.github/copilot-instructions.md`, `docs/project/planning/requirements.md` |
| `backend/ingestion/README.md` | modified | 2026-05-22T11:08:54-04:00 | `README.md`, `docs/architecture.md` |
| `docs/architecture.md` | modified | 2026-05-26T18:47:54-04:00 | `README.md`, `docs/architecture.md` |
| `docs/backlog/README.md` | modified | 2026-05-24T22:51:29-04:00 | `docs/backlog/README.md` |
| `docs/backlog/ingestion.md` | modified | 2026-05-24T22:51:29-04:00 | `docs/backlog/README.md` |
| `docs/ledger/README.md` | modified | 2026-05-22T13:04:54-04:00 | `docs/ledger/README.md` |
| `docs/ledger/http-routes.md` | modified | 2026-05-22T13:04:54-04:00 | `docs/ledger/README.md` |
| `docs/ledger/module-map.md` | modified | 2026-05-22T13:04:54-04:00 | `docs/ledger/README.md` |
| `docs/ledger/protocol-contracts.md` | modified | 2026-05-22T13:04:54-04:00 | `docs/ledger/README.md` |
| `docs/superpowers/plans/2026-05-21-dual-graph-contract.md` | modified | 2026-05-21T16:59:49-04:00 | `docs/backlog/README.md`, `docs/project/planning/backlog.md` |
| `docs/superpowers/plans/2026-05-22-ingestion-pipeline-e2e-demo.md` | modified | 2026-05-22T08:25:14-04:00 | `docs/backlog/README.md`, `docs/project/planning/backlog.md` |
| `docs/superpowers/plans/2026-05-24-complete-backlog.md` | modified | 2026-05-24T21:20:24-04:00 | `docs/backlog/README.md`, `docs/project/planning/backlog.md` |
| `docs/superpowers/specs/2026-05-14-backend-persistence-design.md` | modified | 2026-05-14T23:42:54-04:00 | `docs/backlog/README.md`, `docs/project/planning/backlog.md` |
| `docs/superpowers/specs/2026-05-21-dual-graph-contract-design.md` | modified | 2026-05-21T16:59:49-04:00 | `docs/backlog/README.md`, `docs/project/planning/backlog.md` |
| `docs/superpowers/specs/2026-05-24-complete-backlog-design.md` | modified | 2026-05-24T21:03:40-04:00 | `docs/backlog/README.md`, `docs/project/planning/backlog.md` |
| `docs/wiki/CHANGELOG.md` | modified | 2026-05-22T13:21:08-04:00 | `docs/wiki/README.md`, `docs/wiki/CHANGELOG.md` |
| `docs/wiki/README.md` | modified | 2026-05-20T18:54:22-04:00 | `docs/wiki/README.md`, `docs/wiki/CHANGELOG.md` |
| `docs/wiki/contracts/api-routes.md` | modified | 2026-05-22T13:21:08-04:00 | `docs/wiki/README.md`, `docs/wiki/CHANGELOG.md` |
| `docs/wiki/contracts/domain-config.md` | modified | 2026-05-22T13:21:08-04:00 | `docs/wiki/README.md`, `docs/wiki/CHANGELOG.md` |
| `docs/wiki/contracts/events.md` | modified | 2026-05-22T13:04:54-04:00 | `docs/wiki/README.md`, `docs/wiki/CHANGELOG.md` |
| `docs/wiki/contracts/shared-types.md` | modified | 2026-05-22T13:04:54-04:00 | `docs/wiki/README.md`, `docs/wiki/CHANGELOG.md` |
| `docs/wiki/flows/query-flow.md` | modified | 2026-05-20T18:54:22-04:00 | `docs/wiki/README.md`, `docs/wiki/CHANGELOG.md` |
| `docs/wiki/modules/agent.md` | modified | 2026-05-22T13:21:08-04:00 | `docs/wiki/README.md`, `docs/wiki/CHANGELOG.md` |
| `docs/wiki/modules/analytics.md` | modified | 2026-05-20T18:54:22-04:00 | `docs/wiki/README.md`, `docs/wiki/CHANGELOG.md` |
| `docs/wiki/modules/api.md` | modified | 2026-05-20T18:54:22-04:00 | `docs/wiki/README.md`, `docs/wiki/CHANGELOG.md` |
| `docs/wiki/modules/embeddings.md` | modified | 2026-05-20T18:54:22-04:00 | `docs/wiki/README.md`, `docs/wiki/CHANGELOG.md` |
| `docs/wiki/modules/events.md` | modified | 2026-05-20T18:54:22-04:00 | `docs/wiki/README.md`, `docs/wiki/CHANGELOG.md` |
| `docs/wiki/modules/frontend.md` | modified | 2026-05-20T18:54:22-04:00 | `docs/wiki/README.md`, `docs/wiki/CHANGELOG.md` |
| `docs/wiki/modules/ingestion.md` | modified | 2026-05-22T13:21:08-04:00 | `docs/wiki/README.md`, `docs/wiki/CHANGELOG.md` |
| `docs/wiki/modules/knowledgebases.md` | added | 2026-05-28T03:28:12Z | `docs/wiki/README.md`, `docs/wiki/CHANGELOG.md` |
| `docs/wiki/modules/monitoring.md` | modified | 2026-05-20T18:54:22-04:00 | `docs/wiki/README.md`, `docs/wiki/CHANGELOG.md` |
| `docs/wiki/modules/rag.md` | modified | 2026-05-20T18:54:22-04:00 | `docs/wiki/README.md`, `docs/wiki/CHANGELOG.md` |
| `docs/wiki/modules/records.md` | modified | 2026-05-22T13:21:08-04:00 | `docs/wiki/README.md`, `docs/wiki/CHANGELOG.md` |
| `docs/wiki/modules/shared.md` | modified | 2026-05-22T13:21:08-04:00 | `docs/wiki/README.md`, `docs/wiki/CHANGELOG.md` |
| `docs/wiki/modules/vectorstore.md` | modified | 2026-05-22T13:21:08-04:00 | `docs/wiki/README.md`, `docs/wiki/CHANGELOG.md` |
