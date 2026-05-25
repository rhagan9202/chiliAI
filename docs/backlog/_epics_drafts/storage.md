## File: docs/backlog/storage.md

**Scope:** Object storage protocol + adapters (in-memory, local FS, S3/MinIO; GCS roadmap), large-object I/O (multipart, streaming), presigned URLs, encryption at rest, lifecycle/retention, tenant-scoped prefixes, content-addressed dedup, observability + cost tracking, retry/backoff, and cross-region replication strategy.

Source-of-truth audit of `backend/storage/` against `docs/architecture.md` §5.2 (storage row, line 443), §3 container catalog (object store row, line 181), §11/§12 (deployment, data protection — lines 1225-1300), and §14.2 (future capabilities, lines 1350-1361). The TODO at `backend/storage/protocols.py:9-15` and `backend/storage/models.py:7-9` already enumerate several of these gaps; this file turns them into named epics. Current adapters: `InMemoryObjectStore` (`adapters/in_memory.py:10`), `LocalFsObjectStore` (`adapters/local_fs_adapter.py:20`), `S3ObjectStore` (`adapters/s3_adapter.py:66`). Wiring in `api/dependencies.py:444-462` selects the backend from `ObjectStoreConfig.backend ∈ {local, s3, minio}` (`config/schema.py:140-147`).

Done and intentionally **not** carried forward as epics:
- Local-FS sidecar metadata + path-traversal guardrails (`local_fs_adapter.py:60-145`, `_validate_logical_*` helpers at `:238-296`).
- S3/MinIO adapter behind shared `S3ObjectStore` with `endpoint_url` switch (`s3_adapter.py:79-94`, `dependencies.py:453-461`).
- Credential loading from JSON env var with strict validation (`s3_adapter.py:302-352`).
- S3 paginated listing via `ContinuationToken` (`s3_adapter.py:176-195`).
- `delete()` no-op on missing keys across all three adapters (`in_memory.py:49`, `local_fs_adapter.py:106`, `s3_adapter.py:148`).
- `moto`-based round-trip integration tests for the S3 adapter (`tests/storage/test_s3_adapter.py:205+`).

---

## Epic 1: Lift `ObjectStoreProtocol` to production surface (streaming, paginated list, presigned URLs)

**Gap:** `ObjectStoreProtocol` (`backend/shared/protocols.py:40-58`) exposes only `put_bytes`/`get_bytes`/`delete`/`exists`/`list_keys(prefix) -> list[str]`. The TODO at `backend/storage/protocols.py:9-15` explicitly calls out the missing surface: paginated `list_keys(prefix, limit, cursor) -> ListResult`, `get_stream`, `put_stream`, and `generate_presigned_url`. Today every read fully buffers content into `bytes` (`s3_adapter.py:139`, `local_fs_adapter.py:90`) and every list returns a sorted in-memory list, which will not scale past the dev fixtures.

**Outcome:** protocol extended with `get_stream(key) -> Iterator[bytes]`, `put_stream(key, chunks, *, media_type, metadata, content_length)`, paginated `list_keys(prefix, *, limit, cursor) -> ListObjectsResult`, and `generate_presigned_url(key, *, mode, expires_in)`; all four implemented across in-memory / local-FS / S3; existing `bytes` methods stay as convenience wrappers around the stream variants.

---

## Epic 2: Add multipart upload for large objects (S3/MinIO + local-FS streaming equivalent)

**Gap:** `S3ObjectStore.put_bytes` issues a single `PutObject` with the full body (`s3_adapter.py:113-118`). S3 hard-caps single `PutObject` at 5 GiB and recommends multipart above 100 MiB. There is no `create_multipart_upload`/`upload_part`/`complete_multipart_upload` path, no part-size config, and no resumable-upload story. The ingestion service (large PDFs, claims batches) and future model-artifact persistence will exceed this limit. Local-FS writes are equally non-streaming (`local_fs_adapter.py:63 write_bytes`).

**Outcome:** S3 adapter gains multipart uploads above a configurable threshold (default 64 MiB), with retry per part and abort-on-failure; local-FS gains chunked write + atomic rename; in-memory stays single-shot; protocol exposes a single `put_stream` surface that auto-selects multipart on S3.

---

## Epic 3: Add presigned URLs for direct client upload/download and offload backend bandwidth

**Gap:** All document uploads currently hit the API container, which buffers the file and re-streams to the object store — backend bandwidth scales with upload volume. `S3ClientProtocol` (`s3_adapter.py:25-43`) has no `generate_presigned_url` method, and the API has no `/storage/presign` endpoint. The TODO at `protocols.py:13-14` explicitly calls out S3/GCS presigned download links.

**Outcome:** protocol method `generate_presigned_url(key, *, mode: Literal["upload", "download"], expires_in, content_length_range)`; S3 adapter delegates to `boto3` `generate_presigned_url`; local-FS returns a signed token resolved by a new `GET /storage/objects/{token}` route; in-memory raises `NotImplementedError`. API exposes RBAC-gated `POST /storage/presigned-upload` and `GET /storage/presigned-download` (returns 410 once URL expired). Frontend `KbUploadPanel` switches to direct upload when the backend advertises presign capability.

---

## Epic 4: Add server-side encryption at rest (SSE-KMS / SSE-S3) configurable per backend

**Gap:** `S3ObjectStore.put_bytes` sets only `Bucket`/`Key`/`Body`/`Metadata`/`ContentType` (`s3_adapter.py:106-118`). No `ServerSideEncryption`, `SSEKMSKeyId`, or `BucketKeyEnabled` arguments are passed. Architecture §12.4 (line 1300) currently delegates at-rest encryption to volume encryption (EBS/PV), which leaves the bucket itself unencrypted by default and provides no per-key KMS audit trail. Local-FS writes plaintext sidecars (`local_fs_adapter.py:71-74`). Cross-edge to `_security.md`.

**Outcome:** new `ObjectStoreConfig.encryption: EncryptionConfig` with `mode ∈ {none, sse_s3, sse_kms, aes256_local}` and optional `kms_key_id`/`kms_key_arn`; S3 adapter forwards encryption headers per write; local-FS optionally envelope-encrypts payloads using a key from env/Vault; encryption mode surfaced in `StoredObject.metadata.encryption` so consumers can detect inconsistency. Re-encryption migration helper for legacy plaintext objects.

---

## Epic 5: Add object lifecycle policies (TTL, transitions to cold storage, expired-object reaping)

**Gap:** Nothing in `storage/` declares or applies a lifecycle policy. S3 lifecycle rules (`PutBucketLifecycleConfiguration`) are not invoked; the local-FS adapter never expires files; the in-memory adapter holds objects until process exit. Raw uploaded files (`raw_records`, ingestion bytes, intermediate artifacts) accumulate forever — there is no archival path to Glacier/Coldline, no expiry for failed-pipeline temp files, and no `created_at`/`updated_at` field on `StoredObject` (`shared/protocols.py:22-29`) to drive TTL decisions in the first place. The TODO at `storage/models.py:7` flags the missing timestamps.

**Outcome:** add `created_at`/`updated_at`/`expires_at` to `StoredObject` and the sidecar; declarative lifecycle rules in `ObjectStoreConfig.lifecycle` (per-prefix retention + transition tier); S3 adapter syncs rules to bucket lifecycle config on first connect; local-FS reaps expired files via a periodic `agent/coordinator.py` job; documented mapping of logical-key prefix → retention class.

---

## Epic 6: Add tenant-scoped key prefixes and adapter-layer tenancy enforcement

**Gap:** `_storage_key` (`s3_adapter.py:197-199`) and `_object_path` (`local_fs_adapter.py:137-146`) prepend only a configured `base_path` — no tenant ID. The in-memory adapter has no scoping at all. Architecture §12.3 (line 1293) states "Data separation: enforced at the adapter layer — graph queries, vector searches, and object store paths are always scoped to the active tenant," but nothing in `storage/` reads a tenant context. Today a misrouted `key` from one tenant can collide with or overwrite another tenant's object. Cross-edge to `_multitenancy.md`, `_security.md`.

**Outcome:** tenant-aware constructor (`tenant_resolver: Callable[[], TenantId]` injected via DI); every `put_bytes`/`get_bytes`/`delete`/`list_keys` automatically rewrites the key to `tenants/<tenant_id>/<base_path>/<key>`; cross-tenant access raises `CrossTenantAccessError`; tenant prefix is validated in shared contract tests so future adapters cannot regress.

---

## Epic 7: Add server-side dedup via content-addressed storage and integrity checksums

**Gap:** No checksum is computed or stored. `StoredObject` (`shared/protocols.py:22-29`) has no `checksum` field — the TODO at `storage/models.py:7-8` already flags this. Re-uploading the same document under a new logical key copies the bytes again (S3 and local-FS both pay the storage + transfer cost). There is no SHA-256 verification on read, so silent corruption (disk bit-rot, S3 multipart misassembly) cannot be detected. The Local-FS adapter at `local_fs_adapter.py:92-96` only verifies `size_bytes` against the sidecar, not content.

**Outcome:** add `checksum: str` (sha256, base64-encoded) and `etag: str | None` to `StoredObject` and `StoredObjectWriteResult`; on write, store bytes at `objects/sha256/<hash>` and keep `<key>` as a thin pointer (S3: empty object with `x-amz-website-redirect-location`; local-FS: hardlink or symlink); on read, recompute and compare; `put_bytes` returns the existing key when the hash already exists. Repointable when an old hash is re-encrypted.

---

## Epic 8: Add retry / exponential backoff for transient failures and a typed exception hierarchy

**Gap:** `S3ObjectStore.get_bytes` catches every exception only to convert 404s into `KeyError` and re-raises everything else (`s3_adapter.py:134-137`); `put_object`/`delete_object`/`list_objects_v2` have no retry on `ThrottlingException`, `SlowDown`, `RequestTimeout`, or network resets. There is no `storage/exceptions.py` module — failures bubble up as boto3 `ClientError`/`EndpointConnectionError`, which leaks the adapter SDK into business logic in violation of CLAUDE.md "Hard Rules" §2. Local-FS surfaces `OSError`/`PermissionError` directly.

**Outcome:** `storage/exceptions.py` with `ObjectStoreError`, `ObjectNotFoundError`, `ObjectAlreadyExistsError`, `TransientStorageError`, `PermanentStorageError`, `CrossTenantAccessError`, `StorageQuotaExceededError`; retry decorator with exponential backoff + jitter on `TransientStorageError`, configurable max attempts and per-call deadline; integration tests using `moto`'s failure injection to assert retry behavior.

---

## Epic 9: Add storage observability — bytes-stored / request-count / latency metrics + structured audit

**Gap:** No adapter emits metrics or trace spans. `S3ObjectStore` and `LocalFsObjectStore` have no `logger` import; `InMemoryObjectStore` is silent. There is no counter for `chili_storage_bytes_written_total`, `chili_storage_requests_total{operation,backend,result}`, no histogram for `put_duration_seconds`, no gauge for `chili_storage_objects_total{tenant}`. Failures are visible only when they propagate to the caller. Cross-edge to `_observability.md`.

**Outcome:** adapter base mixin emits OpenTelemetry spans wrapping `put_bytes`/`get_bytes`/`delete`/`list_keys`; Prometheus metrics for bytes/requests/duration/errors labeled by backend, tenant, and operation; structured audit log on every write/delete with logical key, tenant, byte count, checksum — no payload bytes logged.

---

## Epic 10: Add per-backend cost tracking and storage-class reporting

**Gap:** Nothing in `storage/` tracks cumulative bytes written/read, request counts, or storage-class distribution per tenant — operators cannot answer "what is each tenant costing us on S3?" or "which prefix is driving Glacier transitions?" There is no link between `analytics/metrics` and storage usage. This becomes load-bearing once multi-tenancy lands (cross-edge to `_multitenancy.md`) and chargeback/cost-allocation is required.

**Outcome:** `StorageUsageRecorder` updates a Postgres `storage_usage` hypertable (tenant, prefix, backend, storage_class, bytes_written, bytes_read, request_count, period_start); rolled up daily; exposed via `GET /storage/usage` endpoint and dashboard panel. Cost mapping table per backend (S3 Standard vs IA vs Glacier; local-FS = 0); optional alerts when a tenant exceeds quota.

---

## Epic 11: Add live integration tests for local-FS + MinIO + S3 (production-mode parity matrix)

**Gap:** Only `tests/storage/test_s3_adapter.py` uses `moto`; there is no live MinIO test even though the dev compose stack runs MinIO at `:9000` (`docker-compose.dev.yaml:198-208`). `LocalFsObjectStore` is covered only by its unit tests (`tests/storage/test_local_fs_adapter.py`) — there is no shared contract suite proving the three adapters behave identically (e.g., key validation rules, list ordering, missing-key semantics, metadata preservation). When GCS is added (Epic 12) there is no contract harness to bind it to.

**Outcome:** shared `tests/storage/contract.py` parametrized over (in_memory, local_fs, s3_moto, s3_minio_live, s3_aws_live); live MinIO test runs against the compose service when `CHILI_MINIO_LIVE=1`; live AWS test runs under `pytest -m integration` when AWS env vars present; CI gate asserts every adapter passes the full contract.

---

## Epic 12: Add GCS adapter to align with multi-cloud deployment targets

**Gap:** `ObjectStoreConfig.backend: Literal["s3", "minio", "local"]` (`config/schema.py:143`) does not list `gcs`. `api/dependencies.py:444-462` rejects unknown backends via `_raise_unsupported_backend`. The TODO at `storage/protocols.py:14` calls for `GCSObjectStore`. Architecture §11 (line 1225) lists "GCP GKE" as a supported deployment target but offers no native object-store adapter — operators are forced to deploy MinIO-on-GKE or use S3 interop. CLAUDE.md "Hard Rules" §2 explicitly forbids extending the `Literal` without protocol + factory wiring + tests, so this epic must ship the adapter, the factory branch, and contract-suite coverage atomically.

**Outcome:** `storage/adapters/gcs_adapter.py` implementing `ObjectStoreProtocol` against `google-cloud-storage`; new `[gcs]` optional extra in `pyproject.toml`; `ObjectStoreConfig.backend` widened to include `"gcs"`; factory branch added; passes the shared contract suite (Epic 11); credentials loaded via `GOOGLE_APPLICATION_CREDENTIALS` or workload-identity. Architecture §3 / §5.2 / §11 updated to list GCS as a supported backend.

---

## Epic 13: Define cross-region replication strategy (RPO/RTO targets, failover playbook)

**Gap:** Nothing in `storage/` or `infra/` declares a replication or disaster-recovery posture. S3 cross-region replication (CRR) is bucket-level config not managed by the application; MinIO site-replication is undocumented for this project; local-FS has no replication. There is no documented RPO/RTO, no failover runbook, no automated failover in `api/dependencies.py` if the primary bucket becomes unreachable, and no integrity check after a failover. Cross-edge to `_infra.md` (Terraform/Pulumi resource declarations) and `_observability.md` (replication-lag alerting).

**Outcome:** design doc capturing the chosen strategy (active-passive CRR with versioning + object lock vs active-active with conflict resolution); Terraform module declares bucket replication + KMS key replication for S3; `S3ObjectStore` supports a `secondary_endpoint_url` fallback with circuit-breaker; replication-lag SLO published as a metric; tabletop failover exercise scripted and documented.

---

## Open Questions

1. Encryption (Epic 4) — own the application-level envelope (consistent across local-FS / S3 / GCS, more code) vs delegate entirely to bucket-level SSE (zero app-side code, no portability)? Spec stance suggests both modes selectable; confirm.
2. Content-addressed dedup (Epic 7) — should re-uploads return the existing key (transparent dedup with reference counting on delete) or always create a new pointer (simpler, no GC needed)? The reference-counting model interacts with the KB delete cascade in `knowledgebases.md`.
3. Tenant isolation (Epic 6) — single-bucket prefix-per-tenant vs bucket-per-tenant? Bucket-per-tenant gives stronger IAM isolation but explodes bucket-count / lifecycle-rule limits; defer to `_multitenancy.md` or decide here?
4. Presigned URLs for local-FS (Epic 3) — is it worth signing for the dev backend, or limit the feature to S3/GCS and have the frontend fall back to API-mediated upload locally?
5. Multipart threshold tuning (Epic 2) — pick a static default (64 MiB?) or expose it per-tenant in `ObjectStoreConfig`? Affects memory footprint of the worker on large uploads.
6. Cost tracking (Epic 10) — is real-time per-request accounting required, or is a nightly rollup based on S3 inventory + CloudWatch metrics sufficient? Real-time adds adapter overhead.
