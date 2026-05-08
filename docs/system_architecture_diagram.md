# chiliAI Detailed System Architecture Diagram

This diagram captures the current runtime shape of chiliAI: a React analyst workbench, a FastAPI gateway, Redis Streams for asynchronous orchestration, a Python worker pipeline, and adapter-backed graph, vector, object-storage, LLM, and embedding integrations.

Rendered SVG output is available at `docs/rendered/system_architecture_diagram_rendered.md`.

```mermaid
flowchart LR
    analyst["Analyst user<br/>Browser"]
    sources["External data sources<br/>Policy docs, claims, provider data,<br/>beneficiary data, medical records"]
    idp["OIDC / OAuth2 identity provider<br/>Future / optional"]

    subgraph deploy["Deployment boundary<br/>Docker Compose or Kubernetes"]
        ingress["Ingress / nginx<br/>TLS termination, /api routing,<br/>static asset delivery"]

        subgraph frontend["chili_app container<br/>React 19 + TypeScript + Vite"]
            shell["App shell + React Router<br/>Dashboard, Knowledge Bases,<br/>Alerts, Investigation, Chat, Config"]
            query["TanStack Query + API client<br/>REST cache, mutation invalidation"]
            wsclient["WebSocket client<br/>Alerts and pipeline status"]
            state["Zustand stores + domain context<br/>Selected KB, selected entity,<br/>UI state, active domain config"]
            graphui["Investigation graph UI<br/>react-force-graph-2d,<br/>entity detail, evidence, timeline"]
        end

        subgraph api["chili-api container<br/>FastAPI gateway"]
            cors["CORS + metrics + tracing middleware<br/>Prometheus metrics, OpenTelemetry hooks"]
            auth["Auth / RBAC middleware<br/>JWT validation paths"]
            routers["REST routers<br/>/config, /knowledgebases,<br/>/alerts, /investigation,<br/>/chat, /analytics"]
            wshub["WebSocket hub<br/>/ws/alerts, /ws/pipeline"]
            di["Dependency injection composition root<br/>Config-cached services and adapters"]
            kbrepo["Knowledge base metadata repository<br/>Current: in-memory"]
        end

        subgraph services["Backend capability services<br/>Interface-first Python packages"]
            config["config<br/>DomainConfig YAML / JSON loader<br/>entity types, relationships,<br/>capabilities, thresholds, adapters"]
            ingestion["ingestion<br/>Parser orchestration, remote fetch,<br/>chunking, extraction, validation"]
            graphsvc["graph<br/>Graph service + repository protocol<br/>entity and relationship CRUD,<br/>neighborhoods, graph metrics"]
            vectorsvc["vectorstore<br/>Vector service + store protocol<br/>embedding records and similarity search"]
            embedsvc["embeddings<br/>Embedder protocol<br/>local / sentence-transformers / OpenAI-ready"]
            llmsvc["llm<br/>LLM client protocol<br/>local / OpenAI / Anthropic-ready"]
            rag["rag<br/>Retrieve, expand graph context,<br/>assemble prompt, generate answer"]
            analytics["analytics<br/>time-series, GNN, risk scoring,<br/>explainability, evidence packs"]
            monitoring["monitoring<br/>Observation source, threshold evaluation,<br/>alert generation"]
            storage["storage<br/>ObjectStore protocol<br/>raw files, parsed docs, chunks,<br/>extractions, validation reports"]
            shared["shared<br/>Entity, Relationship, Alert,<br/>EvidencePack, contracts, utilities"]
        end

        subgraph eventing["Event orchestration"]
            redis["Redis 7 Streams<br/>chili.* streams, consumer groups,<br/>ack, retry, dead-letter publishing"]
        end

        subgraph worker["chili-worker container<br/>agent.coordinator"]
            deps["WorkerDependencies<br/>adapter registries selected by DomainConfig"]
            handlers["Event handlers<br/>documents.parsed, documents.chunked,<br/>entities.extracted, entities.validated,<br/>graph.updated, embeddings.complete,<br/>vectors.indexed, risk.scored"]
            pipeline["Pipeline execution<br/>parse -> chunk -> extract -> validate -><br/>upsert graph -> embed -> index vectors -><br/>analytics -> evidence -> alerts -> kb.ready"]
            health["Worker health server<br/>port 8001 /health"]
        end

        subgraph runtime["Runtime infrastructure"]
            redisdeploy["Bundled Redis<br/>Compose service or K8s StatefulSet"]
            apiworkload["API workload<br/>Compose service or K8s Deployment + HPA"]
            workerworkload["Worker workload<br/>Compose service or K8s Deployment + HPA"]
            appworkload["Frontend workload<br/>Vite dev server or nginx static container"]
            secrets["Secrets and env config<br/>API keys, JWT key, adapter credentials,<br/>CHILI_CONFIG_PATH, REDIS_URL"]
        end
    end

    subgraph stores["Pluggable external persistence and AI providers"]
        graphdb["Graph database<br/>Current dev: Neo4j 5<br/>Target: Neo4j, Memgraph, Neptune"]
        vectordb["Vector store<br/>Current dev: in-memory / Qdrant container available<br/>Target: Qdrant, pgvector, Weaviate"]
        objectstore["Object store<br/>Current dev: local filesystem volume<br/>Target: S3, MinIO, local FS"]
        llmprovider["LLM provider<br/>Current default: local in-memory<br/>Target: OpenAI, Anthropic, Ollama / vLLM"]
        embedprovider["Embedding provider<br/>Current default: local in-memory<br/>Target: OpenAI, sentence-transformers"]
    end

    analyst -->|"HTTPS"| ingress
    ingress -->|"static assets"| shell
    shell --> query
    shell --> state
    shell --> graphui
    shell --> wsclient
    query -->|"REST JSON + uploads"| ingress
    wsclient -->|"WebSocket"| ingress
    ingress -->|"routes /api and /ws"| cors

    sources -->|"file upload, API push,<br/>future polled feeds"| routers
    idp -.->|"JWT / JWKS validation<br/>when auth enabled"| auth

    cors --> auth
    auth --> routers
    auth --> wshub
    routers --> di
    wshub --> di
    di --> config
    di --> kbrepo
    di --> ingestion
    di --> graphsvc
    di --> vectorsvc
    di --> embedsvc
    di --> llmsvc
    di --> rag
    di --> analytics
    di --> monitoring
    di --> storage

    shared -.-> ingestion
    shared -.-> graphsvc
    shared -.-> vectorsvc
    shared -.-> embedsvc
    shared -.-> llmsvc
    shared -.-> rag
    shared -.-> analytics
    shared -.-> monitoring
    shared -.-> storage
    shared -.-> config

    routers -->|"publish kb.create,<br/>documents.uploaded,<br/>claims.received"| redis
    wshub <-->|"push alerts and pipeline status"| redis
    ingestion -->|"publish parse / extraction events"| redis
    graphsvc -->|"publish graph.updated"| redis
    embedsvc -->|"publish embeddings.generated / complete"| redis
    vectorsvc -->|"publish vectors.indexed"| redis
    llmsvc -->|"publish llm.completed"| redis
    analytics -->|"publish risk.scored / analysis events"| redis
    monitoring -->|"publish alerts.created"| redis

    redis -->|"XREADGROUP"| handlers
    handlers --> pipeline
    deps --> handlers
    config --> deps
    pipeline --> ingestion
    pipeline --> graphsvc
    pipeline --> embedsvc
    pipeline --> vectorsvc
    pipeline --> analytics
    pipeline --> monitoring
    pipeline --> storage
    pipeline -->|"XADD downstream events,<br/>ack or dead-letter failures"| redis
    handlers -.-> health

    graphsvc -->|"adapter protocol"| graphdb
    vectorsvc -->|"adapter protocol"| vectordb
    storage -->|"adapter protocol"| objectstore
    llmsvc -->|"adapter protocol"| llmprovider
    embedsvc -->|"adapter protocol"| embedprovider
    rag --> vectorsvc
    rag --> graphsvc
    rag --> llmsvc
    rag --> embedsvc

    redis -.-> redisdeploy
    cors -.-> apiworkload
    handlers -.-> workerworkload
    shell -.-> appworkload
    secrets -.-> di
    secrets -.-> deps
    secrets -.-> redisdeploy
```

## Primary Request Paths

```mermaid
sequenceDiagram
    autonumber
    actor Analyst
    participant UI as React workbench
    participant API as FastAPI routers
    participant OBJ as Object store
    participant Redis as Redis Streams
    participant Worker as agent.coordinator
    participant Graph as Graph service / DB
    participant Embed as Embeddings service
    participant Vector as Vector service / DB
    participant Analytics as Analytics + monitoring

    Analyst->>UI: Create knowledge base and upload documents
    UI->>API: POST /knowledgebases and POST /knowledgebases/{id}/documents
    API->>OBJ: Persist raw source files
    API->>Redis: XADD kb.create and documents.uploaded
    API-->>UI: 202 Accepted with ingestion status
    Redis-->>Worker: XREADGROUP documents.uploaded
    Worker->>OBJ: Load raw documents
    Worker->>Worker: Parse, chunk, extract entities, validate
    Worker->>Graph: Upsert entities and relationships
    Worker->>Embed: Generate embeddings
    Worker->>Vector: Index embedding records
    Worker->>Analytics: Score risk, derive evidence, evaluate alerts
    Worker->>Redis: XADD graph.updated, vectors.indexed, alerts.created, kb.ready
    Redis-->>API: Alert and pipeline events
    API-->>UI: WebSocket update
```

```mermaid
sequenceDiagram
    autonumber
    actor Analyst
    participant UI as RAG chat / investigation UI
    participant API as FastAPI chat + investigation routers
    participant RAG as RAG service
    participant Embed as Embeddings service
    participant Vector as Vector store
    participant Graph as Graph service / DB
    participant LLM as LLM provider adapter

    Analyst->>UI: Ask a domain question or inspect an entity
    UI->>API: POST /chat or GET /investigation/*
    API->>RAG: Build answer request
    RAG->>Embed: Embed query
    RAG->>Vector: Similarity search
    RAG->>Graph: Expand matching entities and neighborhoods
    RAG->>LLM: Generate answer with citations and graph context
    LLM-->>RAG: Answer payload
    RAG-->>API: Response with evidence and citations
    API-->>UI: Render answer, graph context, entity detail
```

## Deployment Mapping

| Layer | Local development | Production / cluster path |
| --- | --- | --- |
| Frontend | `chili_app` Vite dev server on `:5173` | `chili-app` nginx container behind Ingress |
| API | `uvicorn api.app:create_app --reload` on `:8000` | `chili-api` Deployment + Service + optional HPA |
| Worker | `python -m agent.coordinator` | `chili-worker` Deployment + Service + optional HPA |
| Events | Redis Compose service | Redis StatefulSet or managed Redis |
| Graph | Neo4j Compose service in dev config | External Neo4j, Memgraph, or Neptune |
| Vector | In-memory by default; Qdrant container available | External Qdrant, pgvector, or Weaviate |
| Object storage | Local filesystem volume | S3, MinIO, or local filesystem volume |
| Secrets | `.env` and environment variables | Kubernetes Secret referenced by workloads |

## Architectural Notes

- The API is the synchronous gateway for frontend-driven workflows; it should validate requests, wire dependencies, publish events, and delegate business behavior to capability services.
- Redis Streams decouple interactive requests from longer-running ingestion, graph, embedding, analytics, and alerting work. Workers consume with consumer groups and publish downstream events.
- Adapter protocols isolate vendor-specific graph, vector, LLM, embedding, and object-store code from business logic.
- `DomainConfig` is the main reconfiguration surface. It controls entity and relationship definitions, enabled capabilities, thresholds, and adapter selections.
- `shared` is the leaf contract package. Backend modules should exchange stable shared types instead of importing each other's internals.
