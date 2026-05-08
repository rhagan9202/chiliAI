# chiliAI

A **domain-reconfigurable Graph RAG analytics platform**. Combines knowledge-graph construction, vector-based retrieval-augmented generation, graph neural networks, time-series analysis, anomaly detection, and explainable AI in a loosely coupled, modular system operated through a browser-based analyst workbench.

> For the full architecture and design, see [`docs/architecture.md`](docs/architecture.md).

---

## Goals

- **Flexible, reconfigurable platform** — built around Graph RAG for analytics/exploration, ML, GNN, explainable AI, time-series analysis, and anomaly detection through loosely coupled, interchangeable capability modules in a Python 3.12 backend.
- **Domain reconfigurability** — a single YAML/JSON configuration surface (or UI wizard) retargets the platform to different domains (entity names, relationships, display labels, enabled capabilities). Examples: Medicare fraud detection, food supply chain monitoring, financial crime.
- **Vendor-agnostic** — graph database (Neo4j, Memgraph, Neptune), vector store (pgvector, Qdrant, Weaviate), LLM provider (OpenAI, Anthropic, Ollama/vLLM), and object storage (S3, MinIO, local FS) are all accessed through abstract interface contracts with concrete adapters.

## Starting Exemplar: Medicare Fraud Detection

### Phase 1 — Build the policy knowledge base (batch)

1. Ingest policy documents (PDF, DOCX, HTML, JSON, TXT)
2. Extract entities, relationships, and metadata → build the policy knowledge graph
3. Embed and index extracted text and graph metrics into a vector store for RAG retrieval

The analyst can view a summary of ingested documents, add or remove documents, delete or create knowledge bases, and rebuild the RAG index.

### Phase 2 — Active monitoring (streaming + batch)

4. Ingest structured and unstructured data — claims records, beneficiary information, provider data, medical records
5. Normalize, chunk, and extract entities → create/update the claims knowledge graph
6. Run analytics pipeline — time-series anomaly detection, GNN link prediction and clustering, risk scoring. Results feed back into the knowledge graph (self-reinforcing loop) and forward to the analyst workbench.
7. Surface alerts with evidence/explainability packs (reasoning, subgraph patterns, confidence scores)
8. Analyst explores and queries the graph for investigation
9. Analyst interacts with the knowledge base via LLM-powered conversational RAG

## Repository Structure

```
chiliAI/
├── backend/        # Python 3.12 backend — FastAPI gateway, workers, analytics modules
├── chili_app/      # React 19 + TypeScript + Vite 8 frontend — analyst workbench SPA
├── docs/           # Architecture, design documents, ADRs
├── infra/          # Deployment configuration (Docker Compose, Kubernetes, IaC)
└── .github/        # CI/CD workflows, Copilot instructions
```

## Quick Start

### Docker (Recommended)

```bash
# Development — full stack with hot-reload
cp .env.example .env          # create local config (gitignored)
make dev                       # or: docker compose -f docker-compose.dev.yaml up --build

# Production — built images, nginx, no hot-reload
make prod                      # or: docker compose up --build -d
```

| Service | Dev URL | Prod URL |
|---------|---------|----------|
| Frontend (Vite / nginx) | http://localhost:5173 | http://localhost |
| Backend API | http://localhost:8000 | http://localhost/api/ |
| API health check | http://localhost:8000/health | http://localhost/api/health |
| Neo4j browser | http://localhost:7474 | http://localhost:7474 |
| Qdrant dashboard | http://localhost:6333/dashboard | http://localhost:6333/dashboard |
| MinIO console | http://localhost:9001 | http://localhost:9001 |

See `make help` for all available commands.

### Prerequisites

- Python ≥ 3.12
- Node.js ≥ 20
- Redis 7+ (for event streaming)
- A graph database (Neo4j 5 recommended for local dev)

### Frontend

```bash
cd chili_app
npm install
npm run dev       # Vite dev server on http://localhost:5173
npm run build     # Production build
npm run lint      # ESLint check
```

### Backend

```bash
cd backend
# Create and activate a virtual environment, then:
pip install -e ".[dev]"
uvicorn api.app:create_app --reload --port 8000   # API server
python -m agent.coordinator                         # Pipeline worker
pytest --cov                                        # Run tests with coverage
```

> **Current state**: Both frontend and backend are early-stage scaffolds. See [`docs/architecture.md` §14.3](docs/architecture.md#143-current-state-vs-target) for current state vs. target.

## Key Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Event transport | Redis Streams | Lightweight, supports consumer groups for worker scaling |
| Cross-module interaction | FastAPI gateway / agent coordinator / shared contracts library only | Enforces loose coupling — see [`docs/architecture.md` §2.2](docs/architecture.md#22-loose-coupling-and-narrow-module-boundaries) |
| Type checking | `pyright --strict` (backend), TypeScript strict (frontend) | Catches errors early; enforces explicit domain types |
| Test coverage | pytest ≥ 85% for backend packages | Quality gate — missing tests = incomplete work |
| Deployment | Docker containers on Kubernetes or Docker Compose | Hybrid cloud + on-premises support |

## Documentation

| Document | Purpose |
|----------|---------|
| [`docs/architecture.md`](docs/architecture.md) | Full high-level architecture and design (source of truth) |
| [`backend/README.md`](backend/README.md) | Backend setup, module overview, development commands |
| [`chili_app/README.md`](chili_app/README.md) | Frontend setup, page structure, development commands |

---

## Upstream Accelerator Reference

# Crushing Fraud XAI Accelerator (v0.1)

A reusable, domain-pack-based accelerator for detecting anomalous patterns and potential fraud/waste/abuse schemes across healthcare claims, enrollment and entities, while keeping humans centric in the process (triage support; not automated enforcement).  
This repo is structured to be lifecycle-ready: Frame → Detect/Explain → Validate → Operate, with evaluation gates, monitoring, and a pause/discontinue mechanism.

---

## Why this exists

- **Enable Repeatable Productization**: To shift from one-off AI pilots to repeatable, productized AI solutions across HHS
- **Optimize for Cross-Domain Repeatability**: To ensure consistency and efficiency by standardizing:
  - Potential "indicator" and what it must output (scores, reason codes, evidence bundle pointers) 
  - How humans validate and improve it (investigator review + structured feedback + evaluation gates).
  - How it stays safe and stable (monitoring, drift checks, incident response, and governed change control).
- **Ensure Governance and Compliance**: To provide procurement and governance-ready artifacts by default, aligning with federal AI governance expectations (e.g., risk classification, test/validation plans, post-deployment monitoring, data rights required in OMB M-25-21 and M-25-22), as well as agency-wide guidance (HHS AI strategy, CMS AI Playbook)
- **Future-Ready Design**: To be easily adaptable for future advancements, allowing components to translate into Agent Skills to automate certain or most steps over time

---

## What this repo contains

### Core Kit (reusable across domains)

Core Kit components are meant to be used together; templates are just the “forms” that record decisions made while using docs/eval/monitoring/UI.

- `core/docs/` (build/run + contracts + governance)
  - Overview, roles/RACI, delivery playbook, indicator contract, explainability spec, evaluation harness guidance, monitoring/ops guidance, governance/change control, security/privacy, reference architectures, release/versioning.
- `core/templates/` (C01–C09 “decision artifacts”)
  - Use-case canvas, indicator builder, high-impact screening, model card, data provenance, eval plan/acceptance, go-live checklist, weekly ops review, change request.
- `core/eval/` (evaluation assets)
  - Test set format, scoring rubric, explanation quality rubric, evaluation report template.
- `core/monitoring/` (operate safely)
  - Telemetry contract, dashboards spec, drift checks, incident runbook, pause/discontinue policy.
- `core/ui/` (human-in-the-loop workflow spec)
  - Screen specs, fields dictionary, navigation flow, and (optional) API contract for integrations.

### Domain packs (use-case specific)

Each folder under `domain-packs/` is a deployable module that defines:
- `schema.md`: Domain entity, relationship, and event model.
- `feature_dictionary.md`: Canonical feature families + windows + drift monitoring set.
- `evidence_bundle_spec.md`: What must be shown to investigators + completeness rules.
- `indicators.md`: Indicator library (reason codes, thresholds/logic, next steps).
- `eval_dataset_spec.md`: Sampling + labeling instructions tailored to the domain.
- `README.md`: How to run this domain pack and what it’s for.

v0.1 domain packs:
- `domain-packs/medicare_ffs_claims/`
- `domain-packs/marketplace_agent_broker_enrollment/`
- `domain-packs/medicaid_dental_vision_claims/`
- `domain-packs/dmepos_suppliers_risks/`

### Code starters (implementation scaffolding)

Optional templates and skeletons to accelerate technical implementation. These are not prescriptive and can be adapted to your stack and cloud provider.

- `code-starters/notebooks/` (exploratory and prototyping)
  - Feature building, indicator scoring, and explanation generation notebooks ready to customize per domain pack.
- `code-starters/pipelines/` (production orchestration)
  - Pipeline skeleton for scheduling and monitoring batch scoring jobs.
- `code-starters/iac/` (infrastructure as code)
  - Terraform skeleton for deploying compute, storage, and monitoring resources on cloud platforms.

---

## How to use the components (end-to-end)

### 1) Frame (SME + ops alignment)
**Use**:
- `core/docs/00_overview.md` + `core/docs/01_roles-raci.md` to align responsibilities, scope, and guardrails.
- `core/ui/fields_dictionary.md` + `core/ui/screens_spec.md` to ensure the workflow captures evidence, feedback, approvals, and audit fields.

**Record**:
- `core/templates/C01_use-case-canvas.md` (decision supported, downstream action, harms, guardrails, success criteria).

**Output**:
- A configured use-case instance (usecaseid/usecaseversion) pointing at one domain pack.

### 2) Configure indicators (domain pack → indicator contract)
**Use**:
- `core/docs/03_indicator-contract.md` to implement every indicator with the same output fields (score, reason codes, evidence pointers, next steps, monitoring hooks).
- `core/docs/04_explainability-spec.md` to ensure local/temporal/network explanations are evidence-linked and usable.
- `domain-packs/<pack>/indicators.md` + `domain-packs/<pack>/feature_dictionary.md` + `domain-packs/<pack>/evidence_bundle_spec.md` to implement scoring + evidence assembly per indicator.

**Record**:
- `core/templates/C02_indicator-builder.md` for each indicator promoted beyond "draft."

**Output**:
- A scoring job that produces (a) queues and (b) evidence bundles consistent with the contract.

### 3) Validate (evaluation gates + investigator labeling)
**Use**:
- `core/eval/` assets to build the test set, run evaluation, and standardize results (Precision@K proxy, explanation usefulness, evidence adequacy, stability).
- `domain-packs/<pack>/eval_dataset_spec.md` for domain-specific sampling and labeling guidance.

**Record**:
- `core/templates/C06_eval-plan-acceptance.md` (thresholds + acceptance gates) and `core/templates/C04_model-card-xai.md` (limitations + intended use).
- If needed: `core/templates/C03_high-impact-ai-screen.md` (triage-only vs consequential scope + added controls).

**Output**:
- A signed evaluation decision: approve/pilot/pause/revise, with an eval report and change requests for any modifications.

### 4) Go-live (ops + safety readiness)
**Use**:
- `core/monitoring/telemetry_contract.md` + `core/monitoring/dashboards_spec.md` to instrument throughput, quality, drift, evidence missingness, and governance activity.
- `core/monitoring/drift_checks.md` + `core/monitoring/incident_runbook.md` for response procedures when data shifts or quality drops.
- `core/monitoring/pause_discontinue_policy.md` to stop indicators safely when performance is not appropriate.

**Record**:
- `core/templates/C07_go-live-checklist.md` and schedule `core/templates/C08_weekly-ops-review.md`.

**Output**:
- A production pilot with monitoring, weekly review cadence, and change control enforced.

### 5) Operate (monitor → tune → govern)
**Use**:
- Dashboards + drift checks weekly; treat investigator feedback as the primary signal for precision proxy and explanation usefulness.
- `core/templates/C09_change-request.md` for any change to thresholds, peer groups, evidence requirements, features, or models (with rollback plan + validation).

**Output**:
- A governed iteration loop that improves top-K usefulness without silently changing behavior.

---

## Definition of Done (v0.1)

A use case is “live” only when:
- Data provenance is documented and approved (`core/templates/C05_data-provenance.md`).
- Each approved indicator has reason codes, evidence requirements, and next steps documented (`core/templates/C02_indicator-builder.md`) and implemented per the contract.
- Evaluation gates are met and signed (`core/templates/C06_eval-plan-acceptance.md`) including explanation usefulness and evidence adequacy.
- Monitoring dashboards and drift checks are running (`core/monitoring/`) and weekly ops review is scheduled (`core/templates/C08_weekly-ops-review.md`).
- Change control + pause/discontinue path is usable (`core/templates/C09_change-request.md` + `core/monitoring/pause_discontinue_policy.md`).

---

## Quick start (10 business days)

Follow `core/docs/02_delivery-playbook.md` to run one domain pack end-to-end with 3–5 indicators first, then scale indicator coverage after feedback is flowing.

---

## Data handling note

This repo is intended for deployment in client-controlled environments. Do not commit PHI/PII or sensitive datasets; use synthetic or de-identified examples only.
