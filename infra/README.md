# chiliAI Kubernetes Deployment

This directory ships a complete Kubernetes deployment for chiliAI:

- `k8s/` — flat Kubernetes manifests for `kubectl apply -f`-style deployment.
- `helm/chili/` — a Helm chart (`apiVersion: v2`) wrapping the same resources
  with values-driven overrides.

The chart deploys three application workloads (`chili-api`, `chili-worker`,
`chili-app`) plus an in-cluster Redis StatefulSet for Redis Streams. Heavy
infrastructure (Neo4j, Qdrant, MinIO/S3) is **external** — point the chart at
your existing services via `values.yaml`.

## Prerequisites

- A Kubernetes cluster (≥ v1.27) with an ingress controller installed
  (nginx-ingress or traefik) and a default StorageClass for the Redis PVC.
- `kubectl` ≥ v1.27 configured against the target cluster.
- `helm` ≥ v3.13 (only required for the Helm path).
- Container images for `chili-api`, `chili-worker`, `chili-app` published to a
  registry the cluster can pull from. The defaults reference
  `ghcr.io/chiliai/chili-{api,worker,app}:0.1.0` — override via
  `values.yaml -> image.<component>.repository|tag`.

## Quick start (Helm, in-memory adapters, no TLS)

The default `values.yaml` runs with the chart's bundled Redis, in-memory
domain config, and `auth.enabled: false`. Suitable for dev/CI smoke tests.

```bash
# 1. Provision the secrets object (required even with empty values).
kubectl create secret generic chili-secrets \
    --from-literal=NEO4J_PASSWORD=changeme \
    --from-literal=MINIO_ACCESS_KEY=minioadmin \
    --from-literal=MINIO_SECRET_KEY=minioadmin \
    --from-literal=JWT_SIGNING_KEY="$(openssl rand -base64 32)"

# 2. Install the chart.
helm install chili infra/helm/chili/

# 3. Verify pods come up healthy.
kubectl get pods -l app.kubernetes.io/name=chili
```

## Production deployment

1. Edit `infra/helm/chili/values-prod.yaml`:
   - Set image tags to the version you intend to deploy (avoid `latest`).
   - Point `redis.uri`, `neo4j.uri`, `qdrant.uri`, `minio.endpoint` at your
     managed/external services.
   - Configure `auth.enabled: true`, `auth.issuerUrl`, `auth.audience`.
   - Configure `tls.enabled: true`, `tls.secretName`, `tls.hosts`.
2. Provision the `chili-secrets` Secret with real values (see
   [Secrets management](#secrets-management)).
3. Provision the TLS Secret (see [TLS / HTTPS](#tls--https)).
4. Install:
   ```bash
   helm upgrade --install chili infra/helm/chili/ \
       --values infra/helm/chili/values-prod.yaml
   ```

## Secrets management

All secret material is loaded from a single Kubernetes Secret object whose
name is configured via `values.yaml -> secret.name` (default: `chili-secrets`).
The chart **never** generates or stores secret values; provision the Secret
out-of-band so values never enter git or any rendered template.

### Required secret keys

| Key                    | Purpose                                           | Required when                    |
|------------------------|---------------------------------------------------|----------------------------------|
| `NEO4J_PASSWORD`       | Bolt password for the Neo4j adapter               | `graph.backend=neo4j`            |
| `REDIS_PASSWORD`       | Auth token for Redis Streams                      | Redis is auth-enabled            |
| `QDRANT_API_KEY`       | API key for managed Qdrant                        | `vectorstore.backend=qdrant`     |
| `MINIO_ACCESS_KEY`     | Object store access key                           | `storage.backend in {minio,s3}`  |
| `MINIO_SECRET_KEY`     | Object store secret key                           | `storage.backend in {minio,s3}`  |
| `OPENAI_API_KEY`       | LLM / embeddings calls to OpenAI                  | `llm.provider=openai`            |
| `ANTHROPIC_API_KEY`    | LLM calls to Anthropic                            | `llm.provider=anthropic`         |
| `JWT_SIGNING_KEY`      | Signing key for service-issued JWTs (E10-S03/S04) | `auth.enabled=true`              |

The backend resolves each one through the `*_env_var` pattern documented in
`backend/config/schema.py`: config sections (`LlmConfig.api_key_env_var`,
`GraphDbConfig.auth_env_var`, …) carry the **name** of the env var, and the
adapter reads `os.environ[<name>]` at construction time. No secret value is
ever written to a config file or rendered template.

### Provisioning the Secret

```bash
kubectl create secret generic chili-secrets \
    --from-literal=NEO4J_PASSWORD='...' \
    --from-literal=REDIS_PASSWORD='...' \
    --from-literal=QDRANT_API_KEY='...' \
    --from-literal=MINIO_ACCESS_KEY='...' \
    --from-literal=MINIO_SECRET_KEY='...' \
    --from-literal=OPENAI_API_KEY='sk-...' \
    --from-literal=ANTHROPIC_API_KEY='...' \
    --from-literal=JWT_SIGNING_KEY="$(openssl rand -base64 32)"
```

Production clusters should source these from a managed secrets provider
(Vault, AWS Secrets Manager, Google Secret Manager, Azure Key Vault) using
the External Secrets Operator or a CSI driver — point that controller at the
same Secret name and the chart will keep working unchanged. `secret-template.yaml`
in `infra/k8s/` lists the keys for reference; do **not** apply it with real
values committed.

### Rotation

To rotate any secret:

```bash
kubectl create secret generic chili-secrets \
    --from-literal=... \
    --dry-run=client -o yaml | kubectl apply -f -
kubectl rollout restart deployment/chili-api deployment/chili-worker
```

The pods re-read env vars on startup; restarting the deployments picks up the
new values without re-installing the chart.

## TLS / HTTPS

TLS termination happens at the ingress (preferred) or at nginx in the
`chili-app` container. The chart supports both.

### Ingress-level termination (recommended)

1. Provision a TLS Secret (cert-manager ClusterIssuer, manual upload, or
   ESO-synced from your secret manager). The Secret must contain `tls.crt`
   and `tls.key`.
2. Set in `values.yaml`:
   ```yaml
   tls:
     enabled: true
     secretName: chili-tls
     hosts: ["chili.example.com"]
   ```
3. The rendered `Ingress` adds a `tls:` block referencing the Secret. With
   cert-manager, add the issuer annotation under `ingress.annotations`.

### nginx-level termination (optional, for ingress-less clusters)

When `tls.enabled=true`, the `chili-app` Deployment also mounts the TLS
Secret at `/etc/nginx/tls`. Build the frontend image with
`chili_app/nginx-tls.conf` (TLS variant) instead of `nginx.conf`, or mount
the TLS variant via a ConfigMap volume. The variant enforces TLS 1.2+, strong
forward-secret cipher suites, HSTS, and a 80→443 redirect.

## Listing of resources

| File                                  | Purpose                                                 |
|---------------------------------------|---------------------------------------------------------|
| `k8s/configmap.yaml`                  | Shared non-secret env (URIs, log level, auth settings)  |
| `k8s/secret-template.yaml`            | **Reference** for required keys — do not apply as-is    |
| `k8s/chili-api-deployment.yaml`       | API gateway Deployment (port 8000, `/health` probes)    |
| `k8s/chili-api-service.yaml`          | API ClusterIP Service                                   |
| `k8s/chili-worker-deployment.yaml`    | Worker Deployment (port 8001 health, `/health` probes)  |
| `k8s/chili-app-deployment.yaml`       | Frontend Deployment (nginx, port 80)                    |
| `k8s/chili-app-service.yaml`          | Frontend ClusterIP Service                              |
| `k8s/redis-statefulset.yaml`          | Bundled Redis 7 StatefulSet for Redis Streams           |
| `k8s/redis-service.yaml`              | Headless Redis Service                                  |
| `k8s/hpa-api.yaml`                    | API HPA: CPU-driven, 2–10 replicas                      |
| `k8s/hpa-worker.yaml`                 | Worker HPA: CPU placeholder, 2–10 replicas              |
| `k8s/ingress.yaml`                    | Ingress (path-based: `/api` → API, `/` → frontend)      |
| `helm/chili/Chart.yaml`               | Helm chart metadata                                     |
| `helm/chili/values.yaml`              | Default Helm values                                     |
| `helm/chili/values-prod.yaml`         | Production overrides example                            |
| `helm/chili/templates/`               | Templated equivalents of the `k8s/` manifests           |

## Future work

- **Custom-metrics worker scaling.** The worker HPA is currently CPU-based
  (a coarse proxy). Long-term, scale on Redis Stream pending-message depth
  via [KEDA's redis-streams scaler](https://keda.sh/docs/2.13/scalers/redis-streams/).
  That requires installing KEDA in the cluster and replacing the HPA with a
  `ScaledObject` CRD — out of scope for E10-S11.
- **Bitnami Redis subchart.** For HA Redis (Sentinel or Cluster mode), depend
  on the Bitnami Redis chart instead of the bundled single-replica StatefulSet.
- **PodDisruptionBudgets / NetworkPolicies.** Add per-component PDBs and
  default-deny NetworkPolicies once the cluster has a CNI that enforces them.
