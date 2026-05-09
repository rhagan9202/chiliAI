# Story E10-S11: Kubernetes manifests and Helm chart

## Story
As a platform operator, I want Kubernetes manifests and a Helm chart for deploying chiliAI (API, worker, Redis, ingress), so that the platform can be deployed to any Kubernetes cluster with a single command.

## Acceptance Criteria
1. `infra/k8s/` contains base manifests: Deployment, Service, ConfigMap, Secret, HPA for `chili-api`, `chili-worker`, `chili-app`.
2. `infra/helm/chili/` contains a Helm chart with `values.yaml` for customization: image tags, replica counts, resource limits, external service URIs (Redis, graph DB, vector store), auth config.
3. `helm install chili infra/helm/chili/` deploys a working stack with in-memory adapters and default config.
4. Health probes (`/health`) are configured as liveness and readiness probes.
5. A README in `infra/` documents deployment steps.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | L    | None         |

## Target Files
- `infra/k8s/chili-api-deployment.yaml` — API server deployment
- `infra/k8s/chili-api-service.yaml` — API server service
- `infra/k8s/chili-worker-deployment.yaml` — worker deployment
- `infra/k8s/chili-app-deployment.yaml` — frontend deployment
- `infra/k8s/chili-app-service.yaml` — frontend service
- `infra/k8s/redis-deployment.yaml` — Redis deployment for development
- `infra/k8s/configmap.yaml` — shared ConfigMap
- `infra/k8s/hpa.yaml` — HorizontalPodAutoscaler definitions
- `infra/helm/chili/Chart.yaml` — Helm chart metadata
- `infra/helm/chili/values.yaml` — default configuration values
- `infra/helm/chili/templates/` — Helm templates for all resources
- `infra/README.md` — deployment documentation

## Reference Files to Read First
- `docker-compose.yaml` — existing container definitions and networking
- `docker-compose.dev.yaml` — dev overrides and volume mounts
- `backend/Dockerfile` — backend container build
- `chili_app/Dockerfile` — frontend container build
- `chili_app/nginx.conf` — nginx configuration for frontend serving
- `backend/api/app.py` — health endpoint definition

## Architectural Constraints
- Three-container architecture: `chili-api`, `chili-worker`, `chili-app` (matches `docker-compose.yaml`)
- Health probes: liveness on `/health`, readiness on `/health` with `initialDelaySeconds` appropriate for Python startup
- Resource limits must be set with sensible defaults (CPU, memory) and overridable via Helm values
- Redis is included for development but should be replaceable with an external Redis URI in production
- Helm chart must pass `helm lint` and `helm template` validation
- Ingress resource should support both nginx and traefik ingress controllers via annotation

## What NOT To Do
- Do NOT include production secrets in `values.yaml` — use placeholder references and document the secret creation process
- Do NOT hardcode container image tags — make them configurable in Helm values
- Do NOT deploy a production database (graph DB, vector store) — those are external services configured via URIs
- Do NOT create cluster-level resources (ClusterRole, Namespace) — keep to namespace-scoped resources
- Do NOT use `latest` as the default image tag — use a version placeholder like `0.1.0`
- Do NOT over-engineer the Helm chart with complex conditionals — keep it readable and maintainable

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created
- [ ] `helm lint infra/helm/chili/` passes
- [ ] `helm template chili infra/helm/chili/` renders valid YAML
- [ ] Health probes configured for API and worker
- [ ] Resource limits set with defaults
- [ ] `infra/README.md` documents deployment steps
- [ ] No secrets committed to the repository
