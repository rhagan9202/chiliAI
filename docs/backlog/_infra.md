# _infra backlog

> **Scope:** Container images, Docker Compose, Kubernetes manifests, Helm chart, cloud IaC, network policy, persistent volumes, ingress/TLS, image registry/promotion, backup/restore, scaling, hybrid deployment.
> **Story format and rules:** see [design spec §5](../superpowers/specs/2026-05-24-complete-backlog-design.md#5-story-format).

## Story _infra.01: Harden backend and frontend container images

**ID:** _infra.01
**Status:** planned
**Prerequisites:** []
**Unblocks:** [_infra.03, _infra.07, _infra.10, _security.05, llm.05, vectorstore.04, vectorstore.06]
**Estimated size:** L

**As a** platform engineer,
**I need** the `chili-api`, `chili-worker`, and `chili-app` images to run as a non-root user with a digest-pinned, minimized base, a `.dockerignore`, multi-platform manifests, and an SBOM emitted at build time,
**so that** running pods satisfy `runAsNonRoot: true` without the chart relying on Kubernetes-side overrides, supply-chain attestation tooling can be wired in `_infra.10` and `_security.NN`, and image-scan results map cleanly to known component versions.

### Current State
- `backend/Dockerfile:1-40` is a multi-stage `python:3.12-slim` build with `RUN apt-get install … curl` (lines 24-26) for healthchecks, but **no** `USER` directive — the container runs as root. The chart compensates by setting `runAsNonRoot: true`, `runAsUser: 1000` (`infra/helm/chili/templates/api-deployment.yaml:17-20`).
- `chili_app/Dockerfile:1-26` ships a `node:22-alpine` → `nginx:alpine` build with no `USER` line either; nginx in the official image binds privileged port 80 as root by default.
- Both Dockerfiles reference base images by tag (`python:3.12-slim`, `node:22-alpine`, `nginx:alpine`) with no `@sha256:` digest pin, no SBOM emission, and no multi-platform build instruction.
- The repo has no `.dockerignore` review noted in `infra/README.md` and no image-scan step in CI (`infra/README.md` `## Future work` does not list one).

### Acceptance Criteria
- [ ] `backend/Dockerfile` runtime stage adds a dedicated `chili` UID (e.g. `groupadd -r chili && useradd -r -g chili -u 1000 chili`), `chown`s `/app` and `/opt/venv`, and ends with `USER chili`; image runs successfully with `docker run --user 1000:1000` and the API responds on `/health`.
- [ ] `chili_app/Dockerfile` switches the runtime stage to nginx's unprivileged image (`nginxinc/nginx-unprivileged:alpine`) or rewrites the config to listen on `:8080` and adds a non-root `USER` line; updated `nginx.conf` / `nginx-tls.conf` listen on the unprivileged port and the chart updates `containerPort` and the Service port to match.
- [ ] Both Dockerfiles pin their `FROM` lines by `@sha256:` digest; a `make refresh-base-digests` (or equivalent script under `scripts/`) regenerates the digests against the published `slim`/`alpine` tags.
- [ ] `backend/.dockerignore` and `chili_app/.dockerignore` are added; build context excludes `.git/`, `tests/`, `__pycache__/`, `.venv/`, `node_modules/`, `dist/`, `.env*`, `*.md` (except `README.md`).
- [ ] `docker buildx build --platform linux/amd64,linux/arm64` succeeds for both images; the build documented in `infra/README.md`.
- [ ] An SBOM (CycloneDX JSON) is emitted alongside each image — either via `docker buildx build --sbom=true` or a `syft` step — and persisted under `dist/sboms/<image>-<tag>.cdx.json` so `_infra.10` can attach it to the registry artifact.
- [ ] `chili_app/Dockerfile` ends with the matching `USER` directive; the chart's `chili-app` Deployment can set `runAsNonRoot: true` without breaking.

### Verification
- `docker build -t chili-api:test backend/ && docker run --rm --user 1000:1000 -p 8000:8000 chili-api:test` returns 200 on `GET /health` within 30 s.
- `docker build -t chili-app:test chili_app/ && docker run --rm -p 8080:8080 chili-app:test` serves the SPA shell on the configured port.
- `docker inspect chili-api:test --format '{{.Config.User}}'` returns `chili` (or `1000`).
- `docker buildx imagetools inspect <local-registry>/chili-api:test --raw` shows both `linux/amd64` and `linux/arm64` manifests.
- `syft chili-api:test -o cyclonedx-json | jq '.components | length'` returns ≥ 1.

### Code touch points
- `backend/Dockerfile` (modify)
- `backend/.dockerignore` (new)
- `chili_app/Dockerfile` (modify)
- `chili_app/.dockerignore` (new)
- `chili_app/nginx.conf` (modify — listen port)
- `chili_app/nginx-tls.conf` (modify — listen port)
- `infra/helm/chili/templates/app-deployment.yaml` (modify — containerPort + securityContext)
- `infra/helm/chili/templates/app-service.yaml` (modify — service targetPort)
- `infra/k8s/chili-app-deployment.yaml` (modify — securityContext + containerPort)
- `infra/k8s/chili-app-service.yaml` (modify — port mapping)
- `infra/README.md` (modify — document non-root posture + digest refresh)
- `scripts/refresh_base_digests.sh` (new — optional helper)

---

## Story _infra.02: Collapse flat-manifest / Helm template duplication

**ID:** _infra.02
**Status:** planned
**Prerequisites:** []
**Unblocks:** [_infra.03, _infra.04, _infra.05, _infra.06, _infra.07, _infra.08, _infra.11, _infra.12, _infra.14]
**Estimated size:** M

**As a** platform engineer,
**I need** a single source of truth for the Kubernetes manifests,
**so that** chart edits and flat-manifest edits cannot drift apart (the `chili-app` Deployment is already inconsistent — flat says `runAsNonRoot: false`, the chart sets `runAsNonRoot: true`).

### Current State
- The repo maintains parallel manifest trees: flat YAML under `infra/k8s/` (12 files: api/app/worker/redis deployments+services, ingress, configmap, two HPAs, secret-template) and templated equivalents under `infra/helm/chili/templates/` (10 files).
- `infra/k8s/chili-app-deployment.yaml:21` sets `runAsNonRoot: false` while `infra/helm/chili/templates/api-deployment.yaml:17-20` and `worker-deployment.yaml:17-20` set `runAsNonRoot: true` — concrete drift, not a hypothetical risk.
- `infra/k8s/configmap.yaml:14` hardcodes `API_WORKERS: "4"` which is absent from `infra/helm/chili/templates/configmap.yaml`.
- `infra/k8s/ingress.yaml:8-13` carries inline comments for nginx/traefik/cert-manager annotations that the chart template (`infra/helm/chili/templates/ingress.yaml:8-11`) handles via `.Values.ingress.annotations`.
- `infra/k8s/redis-statefulset.yaml` has no Helm equivalent (chart assumes external Redis or uses Bitnami subchart eventually).
- `infra/README.md` documents both paths as supported but offers no contract for keeping them in sync.

### Acceptance Criteria
- [ ] A decision recorded in `infra/README.md` selecting one of: (a) Helm is canonical, flat manifests are generated; or (b) flat manifests are canonical, chart is generated; or (c) flat manifests are deleted entirely.
- [ ] If (a): a `make k8s-render` target runs `helm template chili infra/helm/chili/ --output-dir infra/k8s/` and a CI check fails when committed `infra/k8s/*.yaml` differs from the rendered output.
- [ ] If (c): the `infra/k8s/` directory is removed (including `redis-statefulset.yaml`, `redis-service.yaml`) and the chart absorbs the bundled Redis StatefulSet behind a `redis.embedded.enabled` value defaulting `true` for dev, `false` for prod.
- [ ] `infra/k8s/chili-app-deployment.yaml` and `infra/helm/chili/templates/app-deployment.yaml` agree on `runAsNonRoot` post-collapse.
- [ ] `infra/README.md` "Listing of resources" table updated to reflect the new layout.
- [ ] No Helm template still contains hardcoded image tags or secret names that were previously parametric only in the flat manifests.

### Verification
- `diff <(helm template chili infra/helm/chili/) <(cat infra/k8s/*.yaml)` either matches (option a) or `infra/k8s/` no longer exists (option c).
- `helm lint infra/helm/chili/` passes.
- `helm template chili infra/helm/chili/ | kubectl apply --dry-run=client -f -` returns no validation errors.
- `grep -r "runAsNonRoot: false" infra/` returns no matches outside an intentional, documented exception.

### Code touch points
- `infra/README.md` (modify)
- `infra/k8s/*.yaml` (delete or regenerate)
- `infra/helm/chili/templates/redis-statefulset.yaml` (new — if option c)
- `infra/helm/chili/templates/redis-service.yaml` (new — if option c)
- `infra/helm/chili/values.yaml` (modify — add `redis.embedded.enabled`)
- `Makefile` (modify — add `k8s-render` if option a)
- `.github/workflows/*.yml` (modify — CI drift check if option a)

---

## Story _infra.03: Tighten pod-level security across the chart

**ID:** _infra.03
**Status:** planned
**Prerequisites:** [_infra.01, _infra.02]
**Unblocks:** []
**Estimated size:** L

**As a** security-focused operator,
**I need** the chart's deployments to run with `readOnlyRootFilesystem: true`, namespace-level PodSecurity admission, per-component PodDisruptionBudgets, and PriorityClasses,
**so that** containers cannot mutate their image filesystem, the API namespace is rejected by the cluster admission controller if a pod regresses, voluntary disruptions cannot take all api/worker replicas at once, and the scheduler honors api/worker priority over best-effort workloads.

### Current State
- `infra/helm/chili/templates/api-deployment.yaml:60-64` and `worker-deployment.yaml:53-57` set `allowPrivilegeEscalation: false` and `capabilities.drop: [ALL]` but `readOnlyRootFilesystem: false`.
- `infra/helm/chili/templates/app-deployment.yaml` (entire file, lines 1-60) has no `securityContext` block on the container — it inherits the pod default (also absent).
- No `PodDisruptionBudget` template exists under `infra/helm/chili/templates/`.
- No `PriorityClass` template or value exists; pods use the cluster default priority.
- No PodSecurity admission label is applied to a target namespace (the chart never renders a `Namespace` resource and `infra/README.md` does not mention `pod-security.kubernetes.io/enforce`).

### Acceptance Criteria
- [ ] All three Deployments add container-level `securityContext` with `readOnlyRootFilesystem: true`, `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`, `runAsNonRoot: true`.
- [ ] Each Deployment mounts the writable paths it actually needs as `emptyDir` volumes (api/worker: `/tmp` and any logging or cache dirs; app: `/var/cache/nginx`, `/var/run`, `/tmp`); the api/worker uvicorn process and the worker coordinator boot and pass `/health` with the read-only root.
- [ ] A new `infra/helm/chili/templates/pdb.yaml` template renders a `PodDisruptionBudget` per component (api, worker, app) controlled by `pdb.<component>.enabled` (default `true` for prod values, optional for dev), with `minAvailable` derived from `replicaCount.<component>` minus one (or a configurable absolute number).
- [ ] A new `infra/helm/chili/templates/priorityclass.yaml` defines `chili-api` / `chili-worker` PriorityClasses (value 100000 for api, 90000 for worker) and the Deployments reference them via `spec.template.spec.priorityClassName`; gated by `priorityClass.enabled`.
- [ ] A new `infra/helm/chili/templates/namespace.yaml` (rendered only when `namespace.create=true`) labels the namespace with `pod-security.kubernetes.io/enforce=restricted`, `…/warn=restricted`, `…/audit=restricted`.
- [ ] `infra/README.md` documents the namespace labels, the read-only-root posture, and the PDB / PriorityClass values.

### Verification
- `helm template chili infra/helm/chili/ --set namespace.create=true | grep -c "readOnlyRootFilesystem: true"` returns ≥ 3.
- `helm template chili infra/helm/chili/ | kubectl apply --dry-run=server -f -` against a cluster with PodSecurity admission enabled at `restricted` returns no warnings or errors.
- `kubectl get pdb -l app.kubernetes.io/instance=chili` after install lists three PDBs.
- API pod logs show successful startup with `/tmp` mounted as `emptyDir` (validated by `kubectl exec` showing `/` is read-only and `/tmp` is writable).

### Code touch points
- `infra/helm/chili/templates/api-deployment.yaml` (modify)
- `infra/helm/chili/templates/worker-deployment.yaml` (modify)
- `infra/helm/chili/templates/app-deployment.yaml` (modify)
- `infra/helm/chili/templates/pdb.yaml` (new)
- `infra/helm/chili/templates/priorityclass.yaml` (new)
- `infra/helm/chili/templates/namespace.yaml` (new)
- `infra/helm/chili/values.yaml` (modify — pdb, priorityClass, namespace blocks)
- `infra/helm/chili/values-prod.yaml` (modify — production defaults)
- `infra/README.md` (modify)

---

## Story _infra.04: Default-deny NetworkPolicies for every component

**ID:** _infra.04
**Status:** planned
**Prerequisites:** [_infra.02]
**Unblocks:** [graph.14, rag.15]
**Estimated size:** L

**As a** security-focused operator,
**I need** default-deny ingress and egress NetworkPolicies with explicit allow-lists per component (api → redis/neo4j/qdrant/minio/postgres, worker → same, app → api, ingress controller → api/app),
**so that** a compromised pod cannot move laterally to backends it does not need and the architectural cross-module boundary in `docs/architecture.md` §10.3 is enforced at the network layer instead of only at the protocol layer.

### Current State
- `find infra/ -iname '*networkpolicy*'` returns no matches; no NetworkPolicy template or flat manifest exists.
- `infra/README.md` `## Future work` mentions PDBs and NetworkPolicies as deferred but does not specify the allow-list.
- The chart's ConfigMap (`infra/helm/chili/templates/configmap.yaml:9-16`) names every backend the api/worker must reach (`REDIS_URL`, `NEO4J_URI`, `QDRANT_URL`, `MINIO_ENDPOINT`), so the egress allow-list shape is already implicit.
- The service-mesh question raised in the audit (Linkerd/Istio vs. NetworkPolicy alone) is unresolved.

### Acceptance Criteria
- [ ] Decision recorded in `infra/README.md`: "v1 uses NetworkPolicy only; service mesh deferred to a follow-up story."
- [ ] A new `infra/helm/chili/templates/networkpolicy.yaml` renders, controlled by `networkPolicy.enabled` (default `true`):
  - A default-deny policy selecting all pods in the chart's namespace (ingress + egress).
  - Per-component allow policies: api allows ingress from the configured ingress controller namespace/label and from the `app` and `worker` pods; api allows egress to Redis, Neo4j, Qdrant, MinIO, Postgres on their configured ports and to `kube-dns` (port 53 UDP/TCP).
  - Worker allows ingress from monitoring scrapers only; egress mirrors api.
  - App allows ingress from the ingress controller; egress only to `api` and `kube-dns`.
- [ ] External backend endpoints surface as values (`networkPolicy.egress.redis.cidr`, `…neo4j.cidr`, etc.) so the policy works for in-cluster or external addresses; defaults match the in-cluster Service names from `_infra.02`.
- [ ] Allow-lists explicitly include `monitoring` namespace pods that scrape `/metrics` (gated by a value so the namespace name is configurable).
- [ ] `infra/README.md` documents the policy model and the per-cloud caveats (some CNIs do not enforce NetworkPolicy by default).

### Verification
- `helm template chili infra/helm/chili/ --set networkPolicy.enabled=true | grep -c "kind: NetworkPolicy"` returns ≥ 4 (default-deny + per-component allow).
- On a cluster with Calico/Cilium, `kubectl exec chili-app-xxxx -- curl -m 2 chili-redis:6379` returns connection-refused/timeout (denied), while `kubectl exec chili-api-xxxx -- redis-cli -h chili-redis ping` returns `PONG`.
- `kubectl exec chili-worker-xxxx -- curl -m 2 https://api.openai.com` is denied unless an explicit egress rule is added (documented as the intentional model — external LLM access requires an explicit allow rule paired with `_security.NN`).

### Code touch points
- `infra/helm/chili/templates/networkpolicy.yaml` (new)
- `infra/helm/chili/values.yaml` (modify — networkPolicy block)
- `infra/helm/chili/values-prod.yaml` (modify — production allow-list)
- `infra/README.md` (modify)

---

## Story _infra.05: Per-environment Helm values and chart-test CI

**ID:** _infra.05
**Status:** planned
**Prerequisites:** [_infra.02]
**Unblocks:** [_cicd.07, _cicd.08, _cicd.10, _infra.11, _infra.14, embeddings.02, llm.12]
**Estimated size:** M

**As a** release engineer,
**I need** distinct Helm values files for dev/staging/prod plus automated chart linting and templating gates in CI,
**so that** every PR that touches `infra/helm/chili/` fails fast on schema, template, or rendering errors and there is a documented production-vs-staging-vs-dev parameter delta.

### Current State
- Only two values files exist: `infra/helm/chili/values.yaml` (defaults, dev-friendly: `auth.enabled: false`, `tls.enabled: false`, in-cluster Redis) and `infra/helm/chili/values-prod.yaml` (external services, cert-manager TLS, `auth.enabled: true`).
- No `values-staging.yaml` or dev-cluster overlay; staging deploys would have to copy and modify `values-prod.yaml` ad hoc.
- No CI step invokes `helm lint`, `helm template --validate`, or [chart-testing (`ct`)](https://github.com/helm/chart-testing). Searching `.github/workflows/` for `helm` returns no current job.
- The chart has no `values.schema.json`, so invalid values (typos in `image.api.tag`, missing `auth.issuerUrl`) only surface at install time.

### Acceptance Criteria
- [ ] A `infra/helm/chili/values-staging.yaml` exists with: external backends pointed at staging hostnames, `auth.enabled: true` with the staging IdP, `tls.enabled: true` with a staging cert-manager ClusterIssuer, replica counts between dev and prod (e.g. api=2, worker=2, app=2), and a smaller HPA `maxReplicas`.
- [ ] A `infra/helm/chili/values-dev-cluster.yaml` (or rename `values.yaml` semantics) exists for an in-cluster developer install: `auth.enabled: false`, in-cluster Redis, no TLS, single replica per component.
- [ ] `infra/helm/chili/values.schema.json` validates the values tree (image repository/tag, replicaCount, resources, auth, tls, ingress, hpa, redis, neo4j, qdrant, minio, secret.name) and `helm install --dry-run` rejects a typo in any required key.
- [ ] A new `.github/workflows/helm-chart-ci.yml` (or job added to the existing workflow) runs on PRs touching `infra/helm/**`: installs Helm 3.13+, runs `helm lint infra/helm/chili/`, runs `helm template chili infra/helm/chili/ --values <each-values-file> | kubectl --dry-run=client apply -f -`, and runs `ct lint --chart-dirs infra/helm`.
- [ ] `infra/README.md` table lists every values file and which environment it targets.

### Verification
- `helm lint infra/helm/chili/` exits 0 against each values file.
- `helm template chili infra/helm/chili/ --values infra/helm/chili/values-staging.yaml | kubectl apply --dry-run=client -f -` returns no errors.
- A deliberate typo (e.g. `auth.enabbled: true`) in any values file fails the new CI job (validated by a sandbox PR or `act -j helm-chart-ci`).
- `ct lint --chart-dirs infra/helm --target-branch main` exits 0.

### Code touch points
- `infra/helm/chili/values-staging.yaml` (new)
- `infra/helm/chili/values-dev-cluster.yaml` (new)
- `infra/helm/chili/values.schema.json` (new)
- `.github/workflows/helm-chart-ci.yml` (new) or modify existing workflow
- `infra/README.md` (modify)

---

## Story _infra.06: Production persistent-volume strategy for stateful services

**ID:** _infra.06
**Status:** planned
**Prerequisites:** [_infra.02]
**Unblocks:** [_infra.12, _infra.13, database.06, events.12]
**Estimated size:** L

**As a** platform engineer,
**I need** a documented StorageClass, PVC sizing, reclaim-policy, and snapshot policy per stateful backend (Neo4j, Qdrant, MinIO, Postgres/TimescaleDB, Redis),
**so that** self-hosted prod installs do not silently default to a `Delete`-reclaim StorageClass that loses data on PVC removal, and so `_infra.13` (backup/restore) has named PVCs to snapshot.

### Current State
- The only in-chart PVC is `infra/k8s/redis-statefulset.yaml:47-54` — `accessModes: ReadWriteOnce`, `storage: 5Gi`, **no** `storageClassName` (uses cluster default).
- The Helm chart has no Redis StatefulSet template (`infra/helm/chili/templates/` lists no `redis*`) and assumes Redis is external (`infra/helm/chili/values.yaml:51` `redis.uri: "redis://chili-redis:6379"` references a Service that the chart does not render).
- Neo4j, Qdrant, MinIO, and Postgres are all assumed external in both flat manifests and the chart — no PVC, no StorageClass, no volume sizing documented in `infra/README.md`.
- `docker-compose.dev.yaml:217-223` declares unsized local volumes (`neo4j-data`, `qdrant-data`, `minio-data`, `postgres-data`, `redis-data`, `chili-object-data`) which is fine for dev but offers no guidance for prod sizing.
- `infra/README.md` lists "Bitnami Redis subchart" and "self-hosted infra" under `## Future work` but does not specify storage requirements.

### Acceptance Criteria
- [ ] A new `infra/storage.md` (or `docs/storage_sizing.md`) documents per-service PVC defaults: Neo4j (RWO, 100 Gi starter, `Retain` reclaim), Qdrant (RWO, 50 Gi), MinIO (RWO or RWX, 200 Gi), Postgres+TimescaleDB (RWO, 100 Gi + 50 Gi WAL), Redis (RWO, 5 Gi current default), plus growth/observation guidance.
- [ ] Helm values gain a `storage:` block: `storage.storageClassName` (default empty → cluster default), `storage.<service>.size`, `storage.<service>.reclaimPolicy`, with one entry per stateful service.
- [ ] If `_infra.12`'s on-prem subchart family is in scope, the embedded StatefulSet templates honor the new values; otherwise the values are documented as inputs to whichever subchart the operator wires.
- [ ] The Redis StatefulSet (whether flat manifest or chart-embedded) sets `storageClassName: {{ .Values.storage.storageClassName }}` and the requested `size` rather than the hardcoded 5 Gi.
- [ ] The new doc cross-references the corresponding module backlog items (`database.NN` for Postgres, `graph.NN` for Neo4j, `vectorstore.NN` for Qdrant, `storage.NN` for MinIO) so per-service sizing decisions stay together.
- [ ] `infra/README.md` "Prerequisites" section is updated to require "a StorageClass with `WaitForFirstConsumer` binding mode and `Retain` reclaim policy for the chili-prod namespace."

### Verification
- `helm template chili infra/helm/chili/ --values infra/helm/chili/values-prod.yaml --set storage.storageClassName=gp3 | grep -E "storageClassName: gp3" -c` returns ≥ 1 per stateful PVC rendered.
- A `kubectl get sc` against the target cluster shows a StorageClass with the documented properties before install; the install fails fast (or warns) if not present.
- The Redis PVC after install reports `Bound` and the documented size; deleting the PVC requires explicit operator action (because reclaim is `Retain`).

### Code touch points
- `infra/storage.md` (new)
- `infra/helm/chili/values.yaml` (modify — storage block)
- `infra/helm/chili/values-prod.yaml` (modify — storage overrides)
- `infra/helm/chili/values.schema.json` (modify — storage schema; depends on _infra.05)
- `infra/helm/chili/templates/redis-statefulset.yaml` (new or modify — if Redis is embedded per _infra.02)
- `infra/k8s/redis-statefulset.yaml` (modify — add storageClassName) or delete per _infra.02
- `infra/README.md` (modify)

---

## Story _infra.07: Ingress TLS by default and a working nginx-TLS variant

**ID:** _infra.07
**Status:** planned
**Prerequisites:** [_infra.01, _infra.02]
**Unblocks:** [api.06]
**Estimated size:** M

**As a** platform engineer,
**I need** ingress-level TLS to be the chart default for any non-dev profile and a real wiring of the nginx-TLS config when ingress-less termination is required,
**so that** production installs cannot accidentally serve the SPA over HTTP and the alternative termination path in `chili_app/nginx-tls.conf` is exercised instead of being documentation-only.

### Current State
- `infra/k8s/ingress.yaml:33-36` has the `tls:` block commented out.
- `infra/helm/chili/values.yaml:96-98` defaults `tls.enabled: false` with empty `secretName`/`hosts`; only `values-prod.yaml:61-65` enables it (`tls.enabled: true`, `secretName: chili-tls`, hosts list).
- `infra/helm/chili/templates/ingress.yaml:32-39` renders the `tls:` block only when `tls.enabled` is true — correct, but the default leaves prod-like installs without TLS unless the operator remembers to flip it.
- `chili_app/nginx-tls.conf` exists (TLS 1.2+, HSTS, 80→443 redirect, 82 lines) but is **not** baked into the image — `chili_app/Dockerfile:19` copies `nginx.conf` only.
- `infra/helm/chili/templates/app-deployment.yaml:48-58` mounts the TLS Secret at `/etc/nginx/tls` only when `tls.enabled` is true, but the nginx process is still reading `nginx.conf` (HTTP-only), so the mounted certs are never used.
- `infra/README.md` `### nginx-level termination (optional, …)` documents the constraint but offers no automation.

### Acceptance Criteria
- [ ] `infra/helm/chili/values-prod.yaml` keeps `tls.enabled: true`; `values-staging.yaml` (from _infra.05) sets `tls.enabled: true`; `values.yaml` keeps `tls.enabled: false` for the dev profile only.
- [ ] When `tls.enabled` is true and `ingress.enabled` is true, the chart fails template rendering (`{{ fail }}`) if `tls.secretName` is empty or `tls.hosts` is empty.
- [ ] The chart adds a `chili-app-nginx-config` ConfigMap that holds both `nginx.conf` and `nginx-tls.conf`; the `chili-app` Deployment selects the appropriate one via a ConfigMap subPath mount keyed by `tls.enabled`. Alternatively (documented as the chosen approach), the image accepts an `NGINX_CONFIG` env var and an entrypoint script copies the matching file into `/etc/nginx/conf.d/default.conf`.
- [ ] Cert-manager annotations (`cert-manager.io/cluster-issuer`) are surfaced via `tls.certManager.clusterIssuer` instead of relying on operators to set them in `ingress.annotations` manually; rendered Ingress includes the annotation only when the value is set.
- [ ] `infra/README.md` `## TLS / HTTPS` section is rewritten to describe (a) the new default, (b) the ingress-level path, (c) the in-pod nginx-TLS path with the ConfigMap mount.
- [ ] `_infra.05`'s chart-test CI step validates rendering with `tls.enabled=true` and a fake `secretName`/`hosts` set.

### Verification
- `helm template chili infra/helm/chili/ --values infra/helm/chili/values-prod.yaml` includes a populated `spec.tls` block and the `cert-manager.io/cluster-issuer` annotation.
- `helm template chili infra/helm/chili/ --set ingress.enabled=true --set tls.enabled=true --set tls.secretName="" --debug` fails with a clear "tls.secretName must be set" error.
- On a test cluster: after install with `tls.enabled=true`, `curl -kvI https://chili.example.com/` returns `200` and `curl -I http://chili.example.com/` returns `308` (redirect) — confirms the redirect path; the served certificate matches the mounted Secret.
- `kubectl exec chili-app-xxxx -- cat /etc/nginx/conf.d/default.conf | grep -q "ssl_certificate"` returns 0 when TLS is on.

### Code touch points
- `infra/helm/chili/values.yaml` (modify)
- `infra/helm/chili/values-prod.yaml` (modify)
- `infra/helm/chili/templates/ingress.yaml` (modify — add `fail` guards, cert-manager annotation)
- `infra/helm/chili/templates/app-deployment.yaml` (modify — ConfigMap mount, conditional nginx config selection)
- `infra/helm/chili/templates/app-nginx-configmap.yaml` (new) — or
- `chili_app/Dockerfile` (modify — entrypoint script + both configs baked in)
- `chili_app/docker-entrypoint.sh` (new — if going the entrypoint-script route)
- `infra/k8s/ingress.yaml` (modify — uncomment TLS) or delete per _infra.02
- `infra/README.md` (modify)

---

## Story _infra.08: Externalize secrets via External Secrets Operator or CSI driver

**ID:** _infra.08
**Status:** planned
**Prerequisites:** [_infra.02]
**Unblocks:** [_security.04, api.18]
**Estimated size:** L

**As a** platform engineer,
**I need** per-cloud templates that synchronize the `chili-secrets` Kubernetes Secret from the cloud's managed secret store (AWS Secrets Manager, GCP Secret Manager, Azure Key Vault, or HashiCorp Vault) via External Secrets Operator (ESO) or the Secrets Store CSI driver,
**so that** secret rotation does not require `kubectl create secret … --dry-run | kubectl apply` and a rolling restart, and so the chart works in environments where `kubectl create secret` is forbidden. (Cross-edge: see `_security.NN` for the broader secret-hygiene story.)

### Current State
- `infra/helm/chili/templates/secret.yaml` is a comment-only file (lines 1-14 are a `{{/* … */}}` documenting the `kubectl create secret generic chili-secrets …` command).
- `infra/k8s/secret-template.yaml` is a YAML reference with `REPLACE_ME` placeholders that the README explicitly warns not to apply.
- `infra/README.md` `## Secrets management` says "Production clusters should source these from a managed secrets provider … using the External Secrets Operator or a CSI driver — point that controller at the same Secret name and the chart will keep working unchanged" — describes the integration but does not ship it.
- The rotation procedure documented in `infra/README.md` `### Rotation` is purely manual.

### Acceptance Criteria
- [ ] A new optional Helm dependency or template group `infra/helm/chili/templates/external-secrets/` ships `ExternalSecret` manifests for AWS Secrets Manager, GCP Secret Manager, and Azure Key Vault, gated by `externalSecrets.enabled` + `externalSecrets.provider` (`aws|gcp|azure|vault|none`).
- [ ] Each `ExternalSecret` targets the Secret name from `secret.name` and enumerates the required keys (`NEO4J_PASSWORD`, `REDIS_PASSWORD`, `QDRANT_API_KEY`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `JWT_SIGNING_KEY`) mapped to provider-specific secret paths via values overrides.
- [ ] An alternative CSI-driver template (`SecretProviderClass`) for at least one provider is included, with the api/worker Deployments switching between the `envFrom: secretRef` mount and CSI volume mount based on a value (`externalSecrets.csi.enabled`).
- [ ] A `vault` profile uses ESO's `VaultDynamicSecret` (or static lookup) targeting a documented path (`secret/chiliai/prod/*`).
- [ ] The chart's `secret.name` Secret is no longer required to be pre-created when `externalSecrets.enabled=true`; the README's `## Secrets management` section is rewritten to describe both paths.
- [ ] `_infra.05`'s chart-test CI lints renderings for each provider.
- [ ] Rotation cadence documented per provider (e.g. ESO `refreshInterval: 1h`, manual provider rotation cadence at least 90 days for prod).

### Verification
- `helm template chili infra/helm/chili/ --set externalSecrets.enabled=true --set externalSecrets.provider=aws --set externalSecrets.aws.region=us-east-1 --set externalSecrets.aws.secretName=chiliai/prod | grep -c "kind: ExternalSecret"` returns ≥ 1.
- After install on a cluster with ESO + an AWS SecretStore: rotating the underlying AWS Secrets Manager secret causes the Kubernetes Secret to refresh within the configured `refreshInterval`, observed via `kubectl get secret chili-secrets -o jsonpath='{.metadata.resourceVersion}'` changing.
- The api Deployment picks up new env-var values after a `kubectl rollout restart deploy/chili-api` triggered by ESO reconcile or operator action.

### Code touch points
- `infra/helm/chili/templates/external-secrets/aws-externalsecret.yaml` (new)
- `infra/helm/chili/templates/external-secrets/gcp-externalsecret.yaml` (new)
- `infra/helm/chili/templates/external-secrets/azure-externalsecret.yaml` (new)
- `infra/helm/chili/templates/external-secrets/vault-externalsecret.yaml` (new)
- `infra/helm/chili/templates/external-secrets/csi-secretproviderclass.yaml` (new)
- `infra/helm/chili/values.yaml` (modify — externalSecrets block)
- `infra/helm/chili/values-prod.yaml` (modify — production provider example)
- `infra/helm/chili/templates/api-deployment.yaml` (modify — CSI mount path)
- `infra/helm/chili/templates/worker-deployment.yaml` (modify — CSI mount path)
- `infra/README.md` (modify)

---

## Story _infra.09: Cloud IaC modules — Terraform per cloud

**ID:** _infra.09
**Status:** planned
**Prerequisites:** []
**Unblocks:** [api.19, storage.13]
**Estimated size:** XL

**As a** platform engineer,
**I need** Terraform modules under `infra/terraform/{aws,gcp,azure}/` that provision the cluster (EKS/GKE/AKS), VPC/VNet, managed Redis, managed object storage, managed Postgres (where applicable), DNS, certificate issuance, and IAM bindings consumed by Workload Identity / IRSA,
**so that** the chiliAI Helm chart has a reproducible cloud substrate to install onto and `docs/architecture.md` §14.3's gap — "Add cloud-provider Terraform/Pulumi" — is closed for the chosen cloud(s). (XL — must be split into per-cloud sub-stories before merge.)

### Current State
- `find infra/ -iname '*.tf'` returns no matches; there is no Terraform, Pulumi, CloudFormation, or Crossplane code anywhere in the repo.
- `docs/architecture.md:1372` records the explicit next-milestone gap: "Add cloud-provider Terraform/Pulumi and production hardening as needed."
- `docs/architecture.md:1334` lists "Terraform or Pulumi" under technology stack but does not pick one.
- The Helm chart's `values-prod.yaml:36-43` references opaque hostnames (`prod-redis.internal`, `prod-neo4j.internal`, `prod-qdrant.internal`, `minio.internal:9000`) — these resources have to come from somewhere.
- §10.5 of the architecture promises "same images deploy to AWS EKS, GCP GKE, Azure AKS" but offers no IaC to back the promise.

### Acceptance Criteria
- [ ] Tool choice recorded in `infra/terraform/README.md` (recommendation: Terraform; rationale captured; Pulumi/Crossplane explicitly out of scope for v1).
- [ ] **Split before merge**: this story must be decomposed into per-cloud sub-stories (e.g. `_infra.09a` AWS, `_infra.09b` GCP, `_infra.09c` Azure) before any sub-story exits `planned`. The split should at minimum land AWS first; GCP/Azure may be deferred but must each get their own story ID in a follow-up backlog edit.
- [ ] AWS module (`infra/terraform/aws/`) provisions: VPC with public + private subnets across 3 AZs, EKS cluster (managed node groups), ElastiCache for Redis, S3 bucket for chili object storage, RDS for Postgres + TimescaleDB extension (or self-hosted on EKS depending on follow-up decision), Route 53 hosted zone wiring, ACM certificate (DNS-validated), and IAM roles for IRSA-bound api/worker ServiceAccounts.
- [ ] GCP module (`infra/terraform/gcp/`) provisions the analogous resources: VPC, GKE Autopilot (or standard), Memorystore for Redis, GCS bucket, Cloud SQL for Postgres, Cloud DNS, Google-managed certificate, Workload Identity bindings.
- [ ] Azure module (`infra/terraform/azure/`) provisions: VNet, AKS, Azure Cache for Redis, Blob Storage, Azure Database for PostgreSQL, Azure DNS, App Gateway / Front Door certificate, Workload Identity (AAD Workload Identity).
- [ ] Each module emits Terraform outputs that map 1:1 to the Helm `values-prod.yaml` keys (`redis.uri`, `neo4j.uri`, `qdrant.uri`, `minio.endpoint`, `storage.storageClassName`).
- [ ] Per-cloud README sections in `infra/terraform/<cloud>/README.md` show: `terraform init`, `terraform plan -var-file=...`, `terraform apply`, and the follow-up `helm install` command with the matching values file.
- [ ] `tflint` and `terraform validate` run in CI for each module (gated to PRs touching `infra/terraform/**`).

### Verification
- `terraform -chdir=infra/terraform/aws init && terraform -chdir=infra/terraform/aws validate` exit 0.
- `terraform -chdir=infra/terraform/aws plan -var environment=staging -var region=us-east-1` produces a plan with the documented resource count and no drift.
- After `terraform apply` on a sandbox AWS account: `aws eks describe-cluster --name chili-staging` succeeds, ElastiCache returns a Redis endpoint, S3 bucket exists, and the IRSA role can be assumed by a test pod.
- `helm install chili infra/helm/chili/ --values infra/helm/chili/values-prod.yaml --set redis.uri=$(terraform -chdir=infra/terraform/aws output -raw redis_uri) …` brings the platform up against the Terraform-provisioned substrate.

### Code touch points
- `infra/terraform/README.md` (new)
- `infra/terraform/aws/` (new — main.tf, variables.tf, outputs.tf, README.md, plus modules/{vpc,eks,elasticache,s3,rds,route53,iam}/)
- `infra/terraform/gcp/` (new — analogous structure)
- `infra/terraform/azure/` (new — analogous structure)
- `.github/workflows/terraform-ci.yml` (new) or modify existing workflow
- `infra/README.md` (modify — top-level pointer to terraform/)
- `docs/architecture.md` §14.3 row for `infra/` (modify — update once any cloud module lands)

---

## Story _infra.10: Container registry, image promotion, signing, and SBOM publication

**ID:** _infra.10
**Status:** planned
**Prerequisites:** [_infra.01]
**Unblocks:** [_cicd.05, api.23]
**Estimated size:** L

**As a** release engineer,
**I need** a defined registry, an immutable-tag policy, multi-arch publication on every `main` push, cosign signing, CycloneDX/SPDX SBOM publication, and a `promote` workflow that retags `:edge` → `:rcN` → `:vX.Y.Z`,
**so that** the chart can pull verifiable images, downstream `_security.NN` admission policies (sigstore policy-controller) have something to verify, and rollbacks pin to a known-good tag rather than a moving target. (Cross-edge: `_cicd.NN` runs the workflow.)

### Current State
- `infra/helm/chili/values.yaml:9-19` defaults `image.<component>.repository` to `ghcr.io/chiliai/chili-{api,worker,app}` and `tag: "0.1.0"` — a single static tag that is presumably mutable.
- No `.github/workflows/*.yml` step pushes images today (no `docker/build-push-action` step found in the workflows present at the time of writing).
- No cosign signing, no provenance attestation, no SBOM artifacts published, no `tag-mutability=immutable` configuration.
- Registry choice (GHCR vs ECR/GAR/ACR per cloud) is implicit and undocumented; the `_infra.09` follow-up may need per-cloud pull-through caches.
- `infra/README.md` "Quick start" says "override via `values.yaml -> image.<component>.repository|tag`" without documenting a promotion contract.

### Acceptance Criteria
- [ ] Registry decision recorded in `infra/registry.md` (or equivalent doc): GHCR as the canonical public registry; per-cloud registries (ECR/GAR/ACR) populated by mirror pulls from GHCR using documented pull-through-cache instructions.
- [ ] A new `.github/workflows/build-and-publish.yml` triggers on push to `main`: builds `chili-api`, `chili-worker`, `chili-app` multi-arch (`linux/amd64`, `linux/arm64`) using buildx, pushes to GHCR with tags `:edge` and `:sha-<short>`.
- [ ] Each pushed image is signed with cosign (`cosign sign --yes <image>@<digest>` using the GitHub OIDC keyless flow); signatures verifiable with `cosign verify --certificate-identity ... --certificate-oidc-issuer https://token.actions.githubusercontent.com ...`.
- [ ] Each pushed image has a CycloneDX SBOM attached as an OCI artifact (`cosign attach sbom` or buildx native SBOM) and a SLSA provenance attestation (`actions/attest-build-provenance@v1` or equivalent).
- [ ] GHCR repository settings (or a documented `gh api` script) enforce immutable tags so `:vX.Y.Z` cannot be overwritten.
- [ ] A new `.github/workflows/promote.yml` accepts `from` and `to` inputs (e.g. `from=sha-abc123 to=v0.2.0`) and uses `crane copy` (or `regctl image copy`) to retag without rebuilding; gated by an environment with required reviewers.
- [ ] `infra/helm/chili/values-prod.yaml:11-18` switches `image.<component>.tag` to a digest reference (`tag: ""` + `image.<component>.digest: "sha256:…"`) once a stable image lands, and the deployment templates render `image: "<repo>@<digest>"` when `digest` is set.

### Verification
- A PR to `main` results in three new images in GHCR with `:edge` and `:sha-<short>` tags within the workflow's runtime.
- `cosign verify ghcr.io/chiliai/chili-api:edge --certificate-identity-regexp='https://github.com/chiliai/chili/.*' --certificate-oidc-issuer=https://token.actions.githubusercontent.com` succeeds.
- `cosign download sbom ghcr.io/chiliai/chili-api:edge | jq '.bomFormat'` returns `"CycloneDX"`.
- Manually running the `promote` workflow with `from=sha-abc123 to=v0.2.0-rc.1` results in the new tag appearing in GHCR; a second invocation with the same `to` fails because of tag-immutability.

### Code touch points
- `infra/registry.md` (new)
- `.github/workflows/build-and-publish.yml` (new) — see `_cicd.NN` for shared CI scaffolding
- `.github/workflows/promote.yml` (new)
- `infra/helm/chili/templates/_helpers.tpl` (modify — add image-ref helper that prefers digest)
- `infra/helm/chili/templates/api-deployment.yaml` (modify — image ref via helper)
- `infra/helm/chili/templates/worker-deployment.yaml` (modify — image ref via helper)
- `infra/helm/chili/templates/app-deployment.yaml` (modify — image ref via helper)
- `infra/helm/chili/values.yaml` (modify — add `digest` field per component)
- `infra/helm/chili/values-prod.yaml` (modify — digest pinning for prod)
- `infra/README.md` (modify — promotion section)

---

## Story _infra.11: KEDA-driven worker autoscaling on Redis Stream pending depth

**ID:** _infra.11
**Status:** planned
**Prerequisites:** [_infra.02, _infra.05]
**Unblocks:** []
**Estimated size:** M

**As a** platform engineer,
**I need** the worker Deployment to scale on Redis Stream pending-message depth per consumer group rather than container CPU,
**so that** pipelines that are I/O- or LLM-bound (not CPU-bound) actually scale out under load and the explicit deferral in `infra/README.md` `## Future work` is resolved. (Cross-edge: `events.NN` for the stream-name contract.)

### Current State
- `infra/helm/chili/templates/hpa.yaml:23-47` defines the worker HPA on `type: Resource → cpu` only (commented inline: "Worker scaling: CPU is a coarse proxy. Future work: scale on Redis Stream pending-message depth via KEDA's redis-streams scaler").
- `infra/k8s/hpa-worker.yaml:1-6` carries the same caveat verbatim.
- `infra/README.md` `## Future work` opens with "Custom-metrics worker scaling … long-term, scale on Redis Stream pending-message depth via KEDA's redis-streams scaler … out of scope for E10-S11."
- KEDA is not installed by the chart, not listed as a dependency, and no `ScaledObject` CRD reference exists anywhere in `infra/`.
- The agent coordinator's consumer groups (per `agent.NN` and `events.NN` backlog entries) are the natural scaling target but there is no documented mapping of `(stream, group) → worker replica pool`.

### Acceptance Criteria
- [ ] A new `infra/helm/chili/templates/keda-scaledobject.yaml` renders a `ScaledObject` (apiVersion `keda.sh/v1alpha1`) gated by `keda.enabled` (default `false` in `values.yaml`, `true` in `values-prod.yaml`), targeting the worker Deployment.
- [ ] The ScaledObject uses the `redis-streams` scaler, configured with `address` (from `redis.uri`), `stream` (parameterized), `consumerGroup` (parameterized), and `pendingEntriesCount` threshold (default 10) per `(stream, group)` pair; multiple triggers supported via a `keda.triggers: list` value.
- [ ] When `keda.enabled` is true, the chart's existing `HorizontalPodAutoscaler` for the worker is **not** rendered (KEDA creates its own HPA; double-managed HPAs fight).
- [ ] `infra/README.md` `## Future work` "Custom-metrics worker scaling" item is replaced by a `## Worker autoscaling` section documenting both modes (CPU HPA default, KEDA opt-in) and the `helm install keda --namespace keda --create-namespace kedacore/keda` prerequisite.
- [ ] Redis auth (when `REDIS_PASSWORD` is set in the chili-secrets Secret) is plumbed via `TriggerAuthentication`.
- [ ] The chosen `(stream, group)` pairs are cross-referenced with the `events.NN` and `agent.NN` stories that define the consumer groups; values defaults match those names.

### Verification
- `helm template chili infra/helm/chili/ --set keda.enabled=true --set keda.triggers[0].stream=ingest --set keda.triggers[0].consumerGroup=ingest-workers --set keda.triggers[0].pendingEntriesCount=50 | grep -c 'kind: ScaledObject'` returns 1; same render contains no `kind: HorizontalPodAutoscaler` for the worker.
- On a cluster with KEDA installed: pushing 200 messages to the configured stream causes `kubectl get hpa -l keda.sh/name=…` to scale the worker Deployment to its `maxReplicaCount`; clearing the backlog scales back down after the cooldown.
- `kubectl logs -n keda -l app=keda-operator | grep chili-worker` shows the scaler is registered without auth errors.

### Code touch points
- `infra/helm/chili/templates/keda-scaledobject.yaml` (new)
- `infra/helm/chili/templates/keda-triggerauthentication.yaml` (new)
- `infra/helm/chili/templates/hpa.yaml` (modify — wrap worker HPA in `if not .Values.keda.enabled`)
- `infra/helm/chili/values.yaml` (modify — keda block)
- `infra/helm/chili/values-prod.yaml` (modify — enable + production thresholds)
- `infra/k8s/hpa-worker.yaml` (modify or delete per _infra.02)
- `infra/README.md` (modify)

---

## Story _infra.12: Hybrid / on-prem deployment bundle for stateful backends

**ID:** _infra.12
**Status:** planned
**Prerequisites:** [_infra.02, _infra.06]
**Unblocks:** []
**Estimated size:** XL

**As a** platform engineer deploying chiliAI on-prem,
**I need** an opt-in "self-hosted infra" Helm subchart family (Neo4j, Qdrant, MinIO, Postgres+TimescaleDB) plus an air-gapped image-mirror workflow,
**so that** `docs/architecture.md` §10.5's promise — "same container images deploy to AWS/GCP/Azure or on-prem with managed vs self-hosted backends" — actually works end-to-end without each operator hand-wiring their own subcharts. (XL — should split into per-backend sub-stories.)

### Current State
- The chart's `infra/helm/chili/Chart.yaml:1-13` declares no `dependencies` block. No subcharts are wired.
- `infra/README.md` `## Future work` lists "Bitnami Redis subchart" as the only mentioned subchart candidate; nothing for Neo4j/Qdrant/MinIO/Postgres.
- `docker-compose.dev.yaml:147-216` runs `timescale/timescaledb:latest-pg16`, `neo4j:5`, `qdrant/qdrant:latest`, `minio/minio:latest` locally — fine for dev, no parity in K8s.
- §10.5's "on-premises" bullet (`docs/architecture.md:1226`) says "self-managed Kubernetes with self-hosted Redis, Neo4j, Qdrant, and MinIO or local filesystem" but the chart leaves all four as operator-supplied URIs.
- No documented procedure for air-gapped image mirroring (no `regctl image copy` script, no `images.txt` manifest, no offline-bundle build target).

### Acceptance Criteria
- [ ] Decision recorded in `infra/README.md`: which of (a) bundled subcharts with `selfHosted.<service>.enabled` toggles, (b) keep BYO and document recommended upstream charts, or (c) ship a sibling umbrella chart (`infra/helm/chili-onprem/`) that depends on `chili` plus stateful subcharts.
- [ ] **Split before merge**: this story decomposes into per-backend sub-stories (`_infra.12a` Neo4j, `_infra.12b` Qdrant, `_infra.12c` MinIO, `_infra.12d` Postgres+TimescaleDB, `_infra.12e` air-gapped mirror) before any sub-story exits `planned`.
- [ ] If (a) or (c) is chosen: `Chart.yaml` adds dependencies on community/Bitnami subcharts (e.g. `neo4j` from Neo4j Helm Labs, `qdrant` from Qdrant, `minio` from Bitnami or upstream MinIO operator, `postgresql` from Bitnami with the `timescaledb` extension preloaded); each dependency gated by `selfHosted.<service>.enabled`.
- [ ] When self-hosted backends are enabled, the chart wires their in-cluster Service names into `values.yaml` automatically (no operator action required) — `redis.uri`, `neo4j.uri`, `qdrant.uri`, `minio.endpoint`.
- [ ] PVC sizing inherits the values from `_infra.06`'s storage block; subcharts forward `persistence.size` and `persistence.storageClass`.
- [ ] An air-gapped image-mirror script (`scripts/mirror_images.sh`) reads a curated `infra/images.txt` (chili images + every subchart's image at pinned tags) and runs `regctl image copy` to a target private registry; documented in `infra/README.md` `## Air-gapped install`.
- [ ] `helm install` in a sandbox cluster with no external Redis/Neo4j/Qdrant/MinIO succeeds when `selfHosted.*.enabled=true` is set and the platform passes the existing smoke tests.

### Verification
- `helm dep update infra/helm/chili/` (or sibling chart) succeeds.
- `helm template chili infra/helm/chili/ --set selfHosted.neo4j.enabled=true --set selfHosted.qdrant.enabled=true --set selfHosted.minio.enabled=true --set selfHosted.postgres.enabled=true | grep -E 'kind: (StatefulSet|Deployment)' | sort -u | wc -l` returns ≥ 4.
- After install on a sandbox cluster with no external services: `kubectl get pods -l app.kubernetes.io/instance=chili` shows all four stateful workloads `Running` and `/health` returns 200 on the api pod.
- `bash scripts/mirror_images.sh --target registry.internal.example.com` copies every image in `infra/images.txt` and the install with `image.<component>.repository=registry.internal.example.com/...` succeeds.

### Code touch points
- `infra/helm/chili/Chart.yaml` (modify — dependencies block) **or**
- `infra/helm/chili-onprem/` (new — umbrella chart)
- `infra/helm/chili/values.yaml` (modify — selfHosted block)
- `infra/helm/chili/values-onprem.yaml` (new)
- `infra/images.txt` (new — pinned image list)
- `scripts/mirror_images.sh` (new)
- `infra/README.md` (modify — Air-gapped install section)

---

## Story _infra.13: Backup, restore, and disaster-recovery drills for stateful services

**ID:** _infra.13
**Status:** planned
**Prerequisites:** [_infra.06]
**Unblocks:** [database.12, storage.13]
**Estimated size:** L

**As a** platform operator,
**I need** scheduled backups (CronJobs or Velero hooks) for Neo4j dumps, Qdrant snapshots, MinIO bucket replication, Postgres `pg_basebackup`/continuous archiving, and Redis AOF/RDB, plus a documented restore runbook and a recurring DR drill,
**so that** the persistent volumes provisioned in `_infra.06` are recoverable after data corruption, accidental deletion, or cluster loss, and the architecture's `## Disaster recovery` posture is testable rather than aspirational. (Cross-edge: `_cicd.NN` runs the backup CronJobs as part of the install.)

### Current State
- No `kind: CronJob`, no `kind: Backup` (Velero), and no `kind: VolumeSnapshot`/`VolumeSnapshotClass` exists anywhere in `infra/`.
- `infra/README.md` "Future work" section does not mention backup/restore at all.
- `docs/architecture.md` does not document a backup/restore policy under §10; nothing in §11 (Observability) or §12 (Security) references RTO/RPO targets.
- The Redis StatefulSet (`infra/k8s/redis-statefulset.yaml:48-54`) uses RWO PVC with no snapshot schedule.
- Module backlog files (`graph.NN`, `vectorstore.NN`, `storage.NN`, `database.NN`) own the per-service dump/restore procedures and protocols, but the cron orchestration belongs here.

### Acceptance Criteria
- [ ] Documented RTO and RPO targets per service in `infra/backup.md` (e.g. Postgres RPO ≤ 15 min, Neo4j RPO ≤ 24 h, Qdrant RPO ≤ 24 h, MinIO RPO via replication = continuous, Redis RPO ≤ 5 min via AOF every-sec).
- [ ] A new `infra/helm/chili/templates/backups/` group ships:
  - `neo4j-backup-cronjob.yaml` — daily `neo4j-admin database dump` to an object-store target, gated by `backup.neo4j.enabled`.
  - `qdrant-snapshot-cronjob.yaml` — daily Qdrant snapshot API call + upload, gated by `backup.qdrant.enabled`.
  - `postgres-basebackup-cronjob.yaml` — `pg_basebackup` + WAL archiving to object storage, plus a separate continuous WAL-archive Job (or sidecar); gated by `backup.postgres.enabled`.
  - `minio-mirror-cronjob.yaml` — `mc mirror` to a secondary bucket/region, gated by `backup.minio.enabled`.
  - `redis-aof-config.yaml` — ConfigMap + StatefulSet patch that enables `appendonly yes` + `appendfsync everysec` when Redis is self-hosted, plus a snapshot-upload CronJob.
- [ ] Backup object-store target (`backup.target.endpoint`, `backup.target.bucket`, `backup.target.credentialsSecretName`) is parameterized so the same chart can target S3, GCS, Azure Blob, or an external MinIO.
- [ ] Each CronJob writes a `last-success` annotation/timestamp to a sentinel ConfigMap so `_observability.NN` can alert on backup-stale conditions.
- [ ] A restore runbook (`infra/restore.md`) documents step-by-step procedures per service: locate the latest backup, scale workloads to zero, run the restore Job, validate, scale back up.
- [ ] A documented "DR drill" runbook describes how to spin up a sandbox namespace, restore from a known backup, and validate end-to-end functionality; the drill is scheduled at least quarterly (documented expectation only — automation is a follow-up).
- [ ] Velero is documented as the alternative for cluster-level disaster recovery (PV-level snapshots + cluster-resource backup), with a sample `Schedule` manifest in `infra/velero-example.yaml`.

### Verification
- `helm template chili infra/helm/chili/ --set backup.neo4j.enabled=true --set backup.qdrant.enabled=true --set backup.postgres.enabled=true --set backup.minio.enabled=true | grep -c 'kind: CronJob'` returns ≥ 4.
- On a sandbox cluster: a manually triggered Neo4j backup Job uploads a `.dump` artifact to the configured bucket within its time budget; the restore runbook successfully reproduces the original entity counts in a new database.
- A simulated DR drill: delete the Neo4j PVC, restore from yesterday's dump, run `pytest -m integration tests/graph/` against the restored database — green within RTO.
- Backup `last-success` ConfigMap is updated within the configured schedule window; manually setting the timestamp 25 h ago triggers the observability alert from `_observability.NN`.

### Code touch points
- `infra/backup.md` (new — RTO/RPO + per-service strategy)
- `infra/restore.md` (new — runbooks)
- `infra/velero-example.yaml` (new)
- `infra/helm/chili/templates/backups/neo4j-backup-cronjob.yaml` (new)
- `infra/helm/chili/templates/backups/qdrant-snapshot-cronjob.yaml` (new)
- `infra/helm/chili/templates/backups/postgres-basebackup-cronjob.yaml` (new)
- `infra/helm/chili/templates/backups/minio-mirror-cronjob.yaml` (new)
- `infra/helm/chili/templates/backups/redis-aof-config.yaml` (new)
- `infra/helm/chili/templates/backups/backup-status-configmap.yaml` (new)
- `infra/helm/chili/values.yaml` (modify — backup block)
- `infra/helm/chili/values-prod.yaml` (modify — production backup target)
- `infra/README.md` (modify)

---

## Story _infra.14: Bundled observability stack with the chart

**ID:** _infra.14
**Status:** planned
**Prerequisites:** [_infra.02, _infra.05]
**Unblocks:** [_observability.07]
**Estimated size:** L

**As a** platform operator,
**I need** the chart to optionally install `kube-prometheus-stack` (Prometheus + Grafana + Alertmanager) plus an OpenTelemetry Collector and ship default Grafana dashboards / Prometheus alert rules wired to chiliAI's `/metrics` endpoints,
**so that** `docs/architecture.md` §11 (Observability) is reachable from a single `helm install --set observability.enabled=true` and ops teams do not have to hand-roll the scrape configs and dashboards. (Cross-edge: `_observability.NN` provides the metrics and dashboards JSON.)

### Current State
- Neither `docker-compose.dev.yaml` nor `infra/helm/chili/templates/` contains Prometheus, Grafana, Alertmanager, Jaeger, Tempo, or OTLP collector resources.
- `docs/architecture.md` §11.2 lists seven canonical metrics; §11.3 calls for OTLP export to Jaeger or Tempo — none are wired in `infra/`.
- The API exposes `/metrics` (per `backend/api/middleware/metrics.py`) and the worker exposes its own `/metrics`, but no scrape target / ServiceMonitor / PodMonitor exists in the chart to consume them.
- `infra/helm/chili/Chart.yaml:1-13` declares no observability dependencies.
- The audit explicitly flags this as the §11 single-command-bringup epic.

### Acceptance Criteria
- [ ] `Chart.yaml` adds an optional dependency on `kube-prometheus-stack` (Prometheus Community Charts) gated by `observability.kubePrometheusStack.enabled` (default `false`); a sibling optional dependency on `opentelemetry-collector` gated by `observability.otelCollector.enabled`.
- [ ] A new `infra/helm/chili/templates/observability/servicemonitor.yaml` (or `PodMonitor`) selects the api and worker Services and scrapes `/metrics` every 30 s (default), gated by `observability.serviceMonitor.enabled`.
- [ ] A new `infra/helm/chili/templates/observability/prometheusrule.yaml` ships starter alert rules: API error-rate > 5 % for 5 m, pipeline DLQ growth > 10 events/min, worker pod restarts, `/health` failing for 2 m; gated by `observability.alerts.enabled`.
- [ ] A new `infra/helm/chili/templates/observability/grafana-dashboards-configmap.yaml` packages JSON dashboards (chiliAI API overview, Pipeline throughput, DLQ status, RAG latency) as a ConfigMap labeled `grafana_dashboard: "1"` so the kube-prometheus-stack's Grafana sidecar auto-imports them.
- [ ] OTLP collector configuration (when enabled) routes traces to a configurable backend (Jaeger / Tempo / external OTLP endpoint) and is referenced by the api/worker Deployments via `OTEL_EXPORTER_OTLP_ENDPOINT` env var (sourced from the configmap so chiliAI picks it up at startup).
- [ ] `infra/README.md` gains an `## Observability stack` section explaining the opt-in install, the alternative of using an existing in-cluster Prometheus/Grafana, and how chiliAI metrics map to the dashboards.
- [ ] Dashboards and alert rule JSON live under `infra/helm/chili/dashboards/` and `infra/helm/chili/alerts/` so they can be edited as files and rendered by the templates via `tpl (.Files.Get ...)`.

### Verification
- `helm dep update infra/helm/chili/` resolves the optional charts.
- `helm template chili infra/helm/chili/ --set observability.kubePrometheusStack.enabled=true --set observability.serviceMonitor.enabled=true --set observability.alerts.enabled=true | grep -cE 'kind: (ServiceMonitor|PrometheusRule|ConfigMap)'` returns ≥ 3.
- On a sandbox cluster after install: `kubectl port-forward svc/<release>-grafana 3000:80` opens Grafana; the chiliAI dashboards appear automatically; manually triggering a /health failure produces an Alertmanager alert.
- Tracing: a sample API request produces spans visible in the configured OTLP backend (Jaeger UI shows the trace).

### Code touch points
- `infra/helm/chili/Chart.yaml` (modify — dependencies)
- `infra/helm/chili/templates/observability/servicemonitor.yaml` (new)
- `infra/helm/chili/templates/observability/prometheusrule.yaml` (new)
- `infra/helm/chili/templates/observability/grafana-dashboards-configmap.yaml` (new)
- `infra/helm/chili/templates/observability/otel-collector-config.yaml` (new) — or rely on subchart values
- `infra/helm/chili/templates/configmap.yaml` (modify — add `OTEL_EXPORTER_OTLP_ENDPOINT`)
- `infra/helm/chili/dashboards/*.json` (new — produced jointly with `_observability.NN`)
- `infra/helm/chili/alerts/*.yaml` (new)
- `infra/helm/chili/values.yaml` (modify — observability block)
- `infra/helm/chili/values-prod.yaml` (modify — enable + production endpoint)
- `infra/README.md` (modify)
