## File: docs/backlog/_infra.md

**Scope:** Container images, Docker Compose, Kubernetes manifests, Helm chart, cloud IaC, network policy, persistent volumes, ingress/TLS, image registry/promotion, backup/restore, scaling, hybrid deployment.

> Cross-cutting concern: container images, Docker Compose, Kubernetes manifests, Helm chart, cloud IaC, network policy, persistent volumes, ingress/TLS, image registry/promotion, backup/restore, scaling, hybrid deployment.
>
> Audit reference: `infra/README.md`, `infra/k8s/*.yaml`, `infra/helm/chili/{Chart.yaml,values*.yaml,templates/*.yaml}`, `backend/Dockerfile`, `chili_app/Dockerfile`, `chili_app/nginx.conf`, `chili_app/nginx-tls.conf`, `docker-compose.dev.yaml`, `docker-compose.yaml`, `Makefile`, `.env.example`, `docs/architecture.md` §10 + §14.2 + §14.3.

## Current-state snapshot

- **Container images.** Backend (`backend/Dockerfile`) is a multi-stage `python:3.12-slim` build but does **not** drop to a non-root user (no `USER` line, no `groupadd`); installs adapters via `[neo4j,qdrant,postgres]` extras. Frontend (`chili_app/Dockerfile`) is multi-stage `node:22-alpine` → `nginx:alpine`, also missing a non-root `USER`. No `.dockerignore` review, no image digest pinning, no SBOM, no image-scan CI hook.
- **Docker Compose.** `docker-compose.dev.yaml` runs the full local stack (api, worker, app + redis, neo4j, qdrant, minio, postgres/timescale) with hardcoded creds (`neo4j` `NEO4J_AUTH=none`, `minioadmin/minioadmin`, `chili/chili` for Postgres) and no per-service resource limits. `docker-compose.yaml` is a "prod-ish" single-host variant using `.env`/`env_file` and `restart: unless-stopped`.
- **Kubernetes — flat manifests** (`infra/k8s/`): api, worker, app deployments + services, redis StatefulSet + headless service, two HPAs (CPU-based), ingress (TLS commented out), `configmap.yaml`, `secret-template.yaml`. `chili-app-deployment.yaml` ships with `runAsNonRoot: false` while api/worker/redis are non-root — inconsistent.
- **Kubernetes — Helm chart** (`infra/helm/chili/`, `apiVersion: v2`, version `0.1.0`): templated equivalents of the flat manifests plus `auth`, `tls`, `hpa`, `ingress`, `secret.name`, per-component `image.repository/tag`. Only two values files: `values.yaml` (defaults, in-cluster Redis, `auth.enabled: false`, `tls.enabled: false`) and `values-prod.yaml` (external Redis/Neo4j/Qdrant/MinIO URIs, cert-manager TLS, `auth.enabled: true`). **Flat manifests and Helm templates are maintained in parallel** — duplication / drift risk.
- **Pod security.** API and worker templates set `runAsNonRoot: true`, `runAsUser: 1000`, `capabilities.drop: [ALL]`, `allowPrivilegeEscalation: false`, but `readOnlyRootFilesystem: false`. No PodSecurity admission labels on namespace. No PodDisruptionBudgets. No NetworkPolicies. No PriorityClasses.
- **Persistent volumes.** Only the in-chart Redis StatefulSet declares a PVC (5 Gi, no `storageClassName`). **Neo4j, Qdrant, MinIO, and Postgres are assumed external** in the chart — no PVC/StorageClass strategy for self-hosted prod, no snapshot/backup hooks anywhere.
- **HPA.** CPU-based for api and worker (2–10 replicas dev, 4–20 prod). `infra/README.md` Future-work section explicitly flags KEDA (Redis-streams pending-message scaler) as out of scope.
- **Ingress / TLS.** Helm `values-prod.yaml` enables cert-manager + `chili-tls` Secret + ingress-class `nginx`. Flat `infra/k8s/ingress.yaml` has TLS commented out. nginx variant `chili_app/nginx-tls.conf` exists (TLS 1.2+, HSTS, redirect 80→443) but is **not** wired into the `chili-app` image by default — the chart only mounts the TLS Secret as a volume; the variant config must be baked or ConfigMap-mounted manually.
- **Secrets.** All sensitive values flow through a single externally-provisioned `chili-secrets` Secret (`infra/helm/chili/templates/secret.yaml` is a comment-only stub). README documents External Secrets Operator / CSI as the prod path but neither is wired.
- **Cloud IaC.** No Terraform, no Pulumi, no CloudFormation, no Crossplane — `docs/architecture.md` §14.3 lists "Add cloud-provider Terraform/Pulumi" as the explicit next-milestone gap for `infra/`.
- **Container registry / promotion.** Defaults reference `ghcr.io/chiliai/chili-{api,worker,app}:0.1.0`. No image-tag-promotion workflow, no cosign/sigstore signing, no provenance/SBOM publication, no per-environment registry routing, no tag-mutability policy.
- **Hybrid deployment story** (§10.5). The architecture asserts "same images deploy to cloud or on-prem with managed vs self-hosted backends" but no on-prem bundle exists (no Bitnami Neo4j/Qdrant/MinIO/Postgres subcharts, no air-gapped image-mirror workflow, no offline registry instructions).
- **Backup / restore.** No backup CronJobs or Velero hooks for Neo4j, Qdrant, MinIO, Postgres, or Redis AOF/RDB. No documented restore drill.

## Provisional epic list

1. **Harden backend and frontend Docker images.** Add non-root `USER`, distroless or `slim`-pinned base by digest, `.dockerignore`, multi-platform builds, SBOM emission, and an image-scan CI hook — current `backend/Dockerfile` and `chili_app/Dockerfile` run as root and pull bases by tag only.
2. **Collapse flat-manifest / Helm duplication.** Either generate `infra/k8s/*.yaml` from `helm template` or delete the flat tree, removing the drift surface between `infra/k8s/` and `infra/helm/chili/templates/`.
3. **Tighten pod-level security across the chart.** Set `readOnlyRootFilesystem: true` (with `emptyDir` for writable paths), drop `runAsNonRoot: false` on the `chili-app` Deployment, add namespace-level PodSecurity admission labels, per-component PodDisruptionBudgets, and PriorityClasses for api/worker.
4. **Add default-deny NetworkPolicies and a service-mesh decision.** No NetworkPolicy exists today; define ingress/egress allow-lists per component (api↔redis/neo4j/qdrant/minio/postgres, worker↔same, app↔api) and decide whether Linkerd/Istio is in scope or NetworkPolicy alone suffices.
5. **Per-environment Helm values and chart-test CI.** Only `values.yaml` and `values-prod.yaml` exist; add `values-staging.yaml` (and a dev-cluster variant), wire `helm lint`, `helm template --validate`, and `chart-testing` into CI so manifest regressions fail PRs.
6. **Production persistent-volume strategy for stateful services.** Define StorageClass, PVC sizing, retention reclaim policy, and snapshot schedules for Neo4j, Qdrant, MinIO, and Postgres in self-hosted mode — currently only Redis has a 5 Gi PVC with no `storageClassName`.
7. **Wire ingress-level TLS by default and finish the nginx-TLS path.** Flat `infra/k8s/ingress.yaml` has TLS commented out, and the `chili-app` image does not bake `nginx-tls.conf`; either ConfigMap-mount the TLS variant or make the image select it at runtime, then make `tls.enabled: true` the chart default for any non-dev profile.
8. **Externalize secrets via External Secrets Operator or CSI driver.** Today, `chili-secrets` is created with `kubectl create secret` and manually rotated; add ESO/CSI templates per cloud provider (AWS Secrets Manager, GCP Secret Manager, Azure Key Vault, Vault) and document rotation cadence. (Cross-edge: `_security.md`.)
9. **Stand up cloud IaC modules (Terraform).** Greenfield: pick Terraform (Pulumi as alternative), create `infra/terraform/{aws,gcp,azure}/` modules covering VPC, EKS/GKE/AKS, managed Redis (ElastiCache / Memorystore / Azure Cache), object storage (S3 / GCS / Blob), DNS, ACM/Cert Manager DNS-01, and IAM bindings consumed by Workload Identity / IRSA.
10. **Container registry, image promotion, signing, and SBOM.** Decide registry (GHCR vs ECR/GAR/ACR), publish multi-arch images per push to `main`, sign with cosign, publish SBOM (CycloneDX/SPDX), enforce immutable tags, and add a `promote` GitHub Action that retags `:edge` → `:rcN` → `:vX.Y.Z`. (Cross-edge: `_cicd.md`.)
11. **Custom-metrics HPA for the worker via KEDA.** CPU is a coarse proxy; install KEDA and replace the worker HPA with a `ScaledObject` that scales on Redis Stream pending-message depth per consumer group (already flagged as future work in `infra/README.md`).
12. **Hybrid / on-prem deployment bundle.** Add an opt-in "self-hosted infra" Helm subchart family (Neo4j, Qdrant, MinIO, Postgres with TimescaleDB) plus air-gapped image-mirror instructions so §10.5's "same images, managed or self-hosted" story actually works end-to-end.
13. **Backup, restore, and disaster-recovery drills for stateful services.** Add CronJobs (or Velero hooks) for Neo4j dumps, Qdrant snapshots, MinIO bucket replication, Postgres `pg_basebackup` / continuous archiving, and Redis AOF/RDB; document and rehearse a restore runbook. (Cross-edge: `_cicd.md`.)
14. **Ship a baseline observability stack with the chart.** Optional dependency on `kube-prometheus-stack` + an OTLP collector + Grafana dashboards/alerts wired to `/metrics` endpoints so the §11 observability spec is reachable from a single `helm install`. (Cross-edge: `_observability.md`.)

## Provisional dependency edges (epic → epic)

- **2** (collapse flat/Helm duplication) blocks **3, 4, 5, 7, 11, 14** — they all edit chart templates and would otherwise need two-place updates.
- **1** (harden images) blocks **10** (signing/SBOM needs a stable base layer first).
- **9** (cloud IaC) unblocks **8** (per-cloud ESO/CSI), **10** (per-cloud registry wiring), and **13** (per-cloud snapshot APIs).
- **6** (PV strategy) blocks **13** (backups need durable PVs) and is a prereq for **12** (on-prem bundle).
- **5** (per-env values + chart-test CI) is a soft prereq for **3, 4, 7, 11, 14** — they should land with CI validation in place.
- **7** (ingress TLS by default) depends on **2** and is referenced by `_security.md` (cross-cutting).

## Cross-cutting fan-out

- → `_security.md`: TLS termination posture (epic 7), External-Secrets wiring (epic 8), image signing/SBOM (epic 10), pod-security hardening (epic 3), default-deny NetworkPolicy (epic 4).
- → `_cicd.md`: chart-test CI (epic 5), image-promotion workflow (epic 10), backup CronJob deployment (epic 13).
- → `_observability.md`: kube-prometheus-stack + OTLP collector wiring (epic 14).
- → `_multitenancy.md`: per-tenant namespace + NetworkPolicy stance (epic 4) and per-tenant storage scoping (epic 6).
- → `database.md`, `graph.md`, `vectorstore.md`, `storage.md`: PV sizing and backup details per stateful service (epics 6, 13).
- → `events.md`: KEDA Redis-streams scaler exposes consumer-group lag as the scaling signal (epic 11).

## Open questions

1. **Terraform vs Pulumi vs Crossplane.** §13 lists "Terraform or Pulumi" — do we lock in Terraform now (epic 9)? If multi-cloud is real, Crossplane in-cluster is also worth a beat.
2. **Service mesh in or out?** Epic 4 currently bundles "NetworkPolicy ± Linkerd/Istio decision." Default-deny NetworkPolicy is cheap; a mesh is a significant operational tax. Confirm whether mTLS-between-services is required for v1 multi-tenancy, since that materially changes the answer.
3. **Flat manifests: keep or delete?** Epic 2 assumes we collapse to Helm-only. The flat tree is useful for "no-Helm" environments (some on-prem K8s shops forbid Tiller-history-style charts). Confirm whether we can drop them or must generate-and-commit.
4. **On-prem stateful infra: bundled or BYO?** Epic 12 proposes a subchart family; the alternative is documenting "bring your own Neo4j/Qdrant/MinIO/Postgres" and keeping the chart slim. Confirm which way the §10.5 hybrid story leans.
5. **Registry choice.** GHCR is the current default (`ghcr.io/chiliai/...`) but cloud customers may need ECR/GAR/ACR for pull-through cache + IAM-based pulls. Epic 10 needs a pick before the promotion workflow can be written.
6. **Image base.** Distroless (`gcr.io/distroless/python3-debian12`) vs continuing on `python:3.12-slim`? Distroless removes shells (kills the `curl` healthcheck) — the API healthcheck would need to switch to a Python one-liner or `httpProbe` only.
