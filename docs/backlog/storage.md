# storage backlog

> **Scope:** Object storage protocol + adapters (local FS, S3, MinIO; GCS roadmap), multipart, presigned URLs, encryption, lifecycle, dedup, tenant scoping, replication.
> **Story format and rules:** see [design spec §5](../superpowers/specs/2026-05-24-complete-backlog-design.md#5-story-format).

---

## Story storage.01: Lift `ObjectStoreProtocol` to production surface (streaming, paginated list, presigned URLs)

**ID:** storage.01
**Status:** planned
**Prerequisites:** []
**Unblocks:** [_multitenancy.09, analytics.02, analytics.23, storage.02, storage.03, storage.04, storage.05, storage.06, storage.07, storage.08, storage.09, storage.11, storage.12, vectorstore.04, vectorstore.13]
**Estimated size:** L

**As a** backend engineer wiring ingestion and KB code against the storage layer,
**I need** the object-store protocol to expose streaming reads, streaming writes, paginated `list_keys`, and presigned-URL generation,
**so that** callers can move multi-GB payloads, page through tenant prefixes that hold millions of keys, and offload uploads to the client without buffering through the API.

### Current State
- `ObjectStoreProtocol` (`backend/shared/protocols.py:39-58`) only declares `put_bytes` / `get_bytes` / `delete` / `exists` / `list_keys(prefix) -> list[str]` — no streaming, no pagination, no presign.
- The TODO at `backend/storage/protocols.py:9-15` explicitly enumerates the missing surface: paginated `list_keys(prefix, limit, cursor) -> ListResult`, `get_stream`, `put_stream`, `generate_presigned_url`.
- Every read fully buffers content: `LocalFsObjectStore.get_bytes` calls `object_path.read_bytes()` (`backend/storage/adapters/local_fs_adapter.py:90`); `S3ObjectStore.get_bytes` calls `_read_response_body(response)` which does a single `.read()` on the boto3 stream (`backend/storage/adapters/s3_adapter.py:139, 387-391`).
- `S3ObjectStore.list_keys` already paginates `list_objects_v2` internally (`s3_adapter.py:176-195`) but flattens to `list[str]` and re-sorts in memory — callers cannot resume mid-prefix.
- `models.py` re-exports `StoredObject` / `StoredObjectWriteResult` only; there is no `ListObjectsResult` model (TODO at `backend/storage/models.py:7-9`).

### Acceptance Criteria
- [ ] `backend/shared/protocols.py` declares `get_stream(key: str, *, chunk_size: int = 65536) -> Iterator[bytes]`, `put_stream(key: str, chunks: Iterator[bytes], *, media_type: str | None = None, metadata: dict[str, object] | None = None, content_length: int | None = None) -> StoredObjectWriteResult`, paginated `list_keys(prefix: str, *, limit: int = 1000, cursor: str | None = None) -> ListObjectsResult`, and `generate_presigned_url(key: str, *, mode: Literal["upload", "download"], expires_in: int) -> str`.
- [ ] `backend/storage/models.py` defines `ListObjectsResult(keys: list[str], next_cursor: str | None, is_truncated: bool)` and exports it.
- [ ] Existing `put_bytes` / `get_bytes` / `list_keys(prefix)` keep their current signatures as thin wrappers over the stream / paginated variants (back-compat for current callers).
- [ ] `InMemoryObjectStore`, `LocalFsObjectStore`, and `S3ObjectStore` all implement the four new methods; the in-memory and local-FS adapters may raise `NotImplementedError("not supported on <backend>")` for `generate_presigned_url` only.
- [ ] The TODO at `backend/storage/protocols.py:9-15` and `backend/storage/models.py:7-9` is removed (the work it describes is done).
- [ ] Pyright-strict clean on `backend/storage/` and `backend/shared/protocols.py`; tests cover stream round-trip, paginated listing with `limit < total`, and that `put_stream` + `get_stream` round-trips bytes identical to `put_bytes` + `get_bytes`.

### Verification
- `cd backend && pytest tests/storage --cov=storage --cov=shared.protocols` green; coverage ≥ 85% on `backend/storage/`.
- `cd backend && pyright backend/storage backend/shared/protocols.py` clean.
- Manual: page through ≥ 5 000 keys on the in-memory adapter with `limit=500` and confirm every key returned exactly once with monotone cursors.

### Code touch points
- `backend/shared/protocols.py` (modify)
- `backend/storage/protocols.py` (modify — remove TODO)
- `backend/storage/models.py` (modify — add `ListObjectsResult`, remove TODO)
- `backend/storage/adapters/in_memory.py` (modify)
- `backend/storage/adapters/local_fs_adapter.py` (modify)
- `backend/storage/adapters/s3_adapter.py` (modify)
- `backend/tests/storage/test_in_memory.py` (modify)
- `backend/tests/storage/test_local_fs_adapter.py` (modify)
- `backend/tests/storage/test_s3_adapter.py` (modify)

---

## Story storage.02: Multipart upload for large objects (S3/MinIO) and streaming write for local FS

**ID:** storage.02
**Status:** planned
**Prerequisites:** [storage.01]
**Unblocks:** []
**Estimated size:** L

**As an** ingestion pipeline that handles multi-GB document batches and model artifacts,
**I need** S3-style multipart upload above a configurable threshold and atomic chunked writes on local FS,
**so that** payloads larger than 100 MiB do not hit the single `PutObject` ceiling (5 GiB hard cap), do not OOM the worker, and can be retried per-part without restarting the whole upload.

### Current State
- `S3ObjectStore.put_bytes` issues a single `PutObject` with the full body (`backend/storage/adapters/s3_adapter.py:113-118`). No `create_multipart_upload` / `upload_part` / `complete_multipart_upload` path exists.
- `S3ClientProtocol` (`s3_adapter.py:25-43`) declares only `put_object` / `get_object` / `delete_object` / `head_object` / `list_objects_v2`; multipart methods are not in the structural boundary.
- `LocalFsObjectStore.put_bytes` calls `object_path.write_bytes(content)` (`backend/storage/adapters/local_fs_adapter.py:63`) — single in-memory blob, no atomic rename, no chunked write.
- No multipart configuration exists in `ObjectStoreConfig` (`backend/config/schema.py:140-147`).

### Acceptance Criteria
- [ ] `ObjectStoreConfig` gains `multipart_threshold_bytes: int = 64 * 1024 * 1024` and `multipart_part_size_bytes: int = 16 * 1024 * 1024` (validated `>= 5 MiB` for S3).
- [ ] `S3ClientProtocol` extends to declare `create_multipart_upload`, `upload_part`, `complete_multipart_upload`, `abort_multipart_upload`.
- [ ] `S3ObjectStore.put_stream` auto-selects multipart when `content_length is None` OR `content_length >= multipart_threshold_bytes`; otherwise issues a single `PutObject`. On any per-part failure after configured retries, `abort_multipart_upload` is invoked and `TransientStorageError` (see `storage.08`) is raised.
- [ ] `LocalFsObjectStore.put_stream` streams chunks to a `<key>.partial` sibling under the resolved object path, then atomically renames to the final name (`os.replace`); sidecar is written only after the rename succeeds.
- [ ] `InMemoryObjectStore.put_stream` may stay single-shot (concatenates into a `bytearray`) — documented as not suitable for >100 MiB.
- [ ] Pyright-strict clean; unit test asserts (a) S3 path issues multipart above threshold (verified via `moto` or a recording fake), (b) S3 path issues single PutObject below threshold, (c) local-FS path leaves no `.partial` file behind on success, (d) local-FS path cleans up `.partial` on failure.

### Verification
- `cd backend && pytest tests/storage -k multipart --cov=storage` green; coverage ≥ 85%.
- `cd backend && pytest tests/storage/test_s3_adapter.py -k multipart` confirms `moto` sees the multipart sequence (`CreateMultipartUpload` → N × `UploadPart` → `CompleteMultipartUpload`).
- Manual: stream a 200 MiB payload through `LocalFsObjectStore.put_stream` and confirm peak RSS does not exceed 2× `part_size_bytes`.

### Code touch points
- `backend/config/schema.py` (modify — add multipart fields)
- `backend/storage/adapters/s3_adapter.py` (modify — extend `S3ClientProtocol`, add multipart path)
- `backend/storage/adapters/local_fs_adapter.py` (modify — atomic chunked write)
- `backend/storage/adapters/in_memory.py` (modify — document single-shot)
- `backend/tests/storage/test_s3_adapter.py` (modify)
- `backend/tests/storage/test_local_fs_adapter.py` (modify)

---

## Story storage.03: Presigned URLs for direct client upload and download

**ID:** storage.03
**Status:** planned
**Prerequisites:** [storage.01, _security.02, _multitenancy.09]
**Unblocks:** []
**Estimated size:** L

**As a** frontend uploading large evidence PDFs and an analyst downloading evidence-pack artifacts,
**I need** the API to mint short-lived presigned URLs that the browser talks to directly,
**so that** the API container stops being the bandwidth bottleneck and large transfers no longer block worker request slots.

### Current State
- `KbUploadPanel` and the `POST /knowledgebases/{kb_id}/documents` route currently buffer the file through the API container (no presign route exists — `grep "presign" backend/api/routers/` returns nothing).
- `S3ClientProtocol` (`backend/storage/adapters/s3_adapter.py:25-43`) does not declare `generate_presigned_url`.
- The TODO at `backend/storage/protocols.py:13-14` explicitly calls for S3/GCS presigned download links.
- `LocalFsObjectStore` has no signed-URL story — local dev cannot exercise the direct-upload code path.

### Acceptance Criteria
- [ ] `S3ClientProtocol` declares `generate_presigned_url(ClientMethod: str, Params: Mapping[str, object], ExpiresIn: int) -> str`.
- [ ] `S3ObjectStore.generate_presigned_url(key, *, mode, expires_in)` returns a URL using `put_object` (upload) or `get_object` (download); raises `ValueError` on `expires_in <= 0` or `expires_in > 86400`.
- [ ] `LocalFsObjectStore.generate_presigned_url` returns a token (`HMAC(secret, key + mode + exp)`) resolved by a new `GET /storage/objects/{token}` route in `backend/api/routers/storage.py`; the route enforces expiry and returns 410 once expired.
- [ ] `POST /storage/presigned-upload` and `GET /storage/presigned-download` exist behind `require_role("analyst")` for upload and `require_role("viewer")` for download; both compose with the resource-level ACL gate from `_security.02`.
- [ ] Tenant prefix from `_multitenancy.09` is applied before signing — a presigned URL minted for tenant A cannot point at tenant B's prefix.
- [ ] Frontend `KbUploadPanel` switches to direct upload when `GET /config/capabilities` advertises `presign: true`; falls back to API-mediated upload otherwise.
- [ ] Tests: (a) S3 presign uses correct method/expiry, (b) local-FS token is rejected after `expires_in`, (c) cross-tenant presign request returns 403, (d) the frontend integration test exercises both upload paths.

### Verification
- `cd backend && pytest tests/storage tests/api -k presign --cov=storage --cov=api.routers.storage` green.
- `cd chili_app && npm run test:e2e -- presign-upload` green; large file (>5 MiB fixture) uploads in one PUT directly to MinIO in dev compose.
- Manual: mint a download URL, wait > `expires_in` seconds, confirm 403/410 from S3 or 410 from the local-FS route.

### Code touch points
- `backend/storage/adapters/s3_adapter.py` (modify)
- `backend/storage/adapters/local_fs_adapter.py` (modify)
- `backend/storage/adapters/in_memory.py` (modify — raise `NotImplementedError`)
- `backend/api/routers/storage.py` (new)
- `backend/api/app.py` (modify — register router)
- `backend/api/routers/knowledgebases.py` (modify — surface presign URL on upload-init)
- `chili_app/src/features/knowledgebases/KbUploadPanel.tsx` (modify)
- `backend/tests/storage/test_*` (modify)
- `backend/tests/api/test_routers_storage.py` (new)

---

## Story storage.04: Server-side encryption at rest (SSE-KMS / SSE-S3) per backend

**ID:** storage.04
**Status:** planned
**Prerequisites:** [storage.01, _security.04]
**Unblocks:** [agent.09, embeddings.12, storage.13]
**Estimated size:** M

**As a** compliance owner for Medicare-PII data,
**I need** every object the platform writes to be encrypted at rest with a key the operator controls,
**so that** bucket compromise without the KMS key never yields plaintext PII and every encrypted-write event is auditable.

### Current State
- `S3ObjectStore.put_bytes` sets only `Bucket` / `Key` / `Body` / `Metadata` / `ContentType` (`backend/storage/adapters/s3_adapter.py:106-118`); no `ServerSideEncryption`, `SSEKMSKeyId`, or `BucketKeyEnabled` is forwarded.
- `LocalFsObjectStore.put_bytes` writes plaintext sidecar JSON + plaintext payload (`backend/storage/adapters/local_fs_adapter.py:63, 71-74`).
- `ObjectStoreConfig` (`backend/config/schema.py:140-147`) has no `encryption` field.
- Architecture §12.4 currently delegates at-rest encryption to volume encryption (EBS/PV), which leaves the bucket itself unencrypted by default and provides no per-key audit trail.

### Acceptance Criteria
- [ ] `ObjectStoreConfig.encryption: EncryptionConfig | None = None` with `EncryptionConfig(mode: Literal["none", "sse_s3", "sse_kms", "aes256_local"], kms_key_id: str | None = None, key_env_var: str | None = None)`; `kms_key_id` is required when `mode == "sse_kms"`, `key_env_var` is required when `mode == "aes256_local"`.
- [ ] `S3ObjectStore` forwards `ServerSideEncryption="AES256"` (sse_s3) or `ServerSideEncryption="aws:kms"` + `SSEKMSKeyId=...` + `BucketKeyEnabled=True` (sse_kms) on every `put_object` / `create_multipart_upload`.
- [ ] `LocalFsObjectStore` envelope-encrypts the payload with AES-256-GCM (key from `key_env_var`, nonce random per object, stored in the sidecar) when `mode == "aes256_local"`; sidecar field `encryption: {mode, kms_key_id?, nonce_b64?}`.
- [ ] `StoredObject.metadata["encryption"]` round-trips the mode + key id so consumers can detect a downgrade (e.g., a read returning plaintext when the config demands SSE-KMS triggers a `PermanentStorageError` per `storage.08`).
- [ ] `scripts/storage_reencrypt.py` (new) walks the bucket and re-encrypts legacy plaintext objects under the current config; idempotent and resumable via cursor.
- [ ] Pyright-strict clean; tests cover all four modes round-trip on the in-memory + local-FS + `moto` S3 adapters; cross-mode read failure asserted.

### Verification
- `cd backend && pytest tests/storage -k encryption --cov=storage` green; coverage ≥ 85%.
- `cd backend && pytest tests/storage/test_s3_adapter.py -k sse_kms` confirms `moto` records the `SSEKMSKeyId` argument on `PutObject`.
- Manual: configure `mode: aes256_local`, write an object, `xxd` the resulting file and confirm bytes do not match the source plaintext.

### Code touch points
- `backend/config/schema.py` (modify — add `EncryptionConfig`)
- `backend/storage/adapters/s3_adapter.py` (modify)
- `backend/storage/adapters/local_fs_adapter.py` (modify)
- `backend/storage/adapters/in_memory.py` (modify — accept config, no-op or reject)
- `backend/scripts/storage_reencrypt.py` (new)
- `backend/tests/storage/test_*` (modify)

---

## Story storage.05: Object lifecycle policies (TTL, cold-tier transitions, expired-object reaping)

**ID:** storage.05
**Status:** planned
**Prerequisites:** [storage.01, agent.04]
**Unblocks:** [api.19, ingestion.06, ingestion.22, storage.10]
**Estimated size:** L

**As a** platform operator,
**I need** declarative per-prefix retention and cold-tier transition rules applied to every backend,
**so that** raw uploads, intermediate artifacts, and failed-pipeline temp files do not accumulate forever and storage spend is predictable.

### Current State
- Nothing in `backend/storage/` declares or applies a lifecycle policy. S3 lifecycle rules (`PutBucketLifecycleConfiguration`) are not invoked anywhere in the codebase.
- `LocalFsObjectStore` never expires files; `InMemoryObjectStore` holds objects until process exit.
- `StoredObject` / `StoredObjectWriteResult` (`backend/shared/protocols.py:13-29`) carry no `created_at` / `updated_at` / `expires_at` field — there is no signal a TTL reaper could act on. The TODO at `backend/storage/models.py:7` flags this.
- `ObjectStoreConfig` (`backend/config/schema.py:140-147`) has no `lifecycle` field.

### Acceptance Criteria
- [ ] `StoredObject` and `StoredObjectWriteResult` gain `created_at: datetime`, `updated_at: datetime`, `expires_at: datetime | None`; persisted in the local-FS sidecar and as S3 `Metadata` keys `x-chili-created-at` / `x-chili-expires-at`.
- [ ] `ObjectStoreConfig.lifecycle: list[LifecycleRule] = []` where `LifecycleRule(prefix: str, retention_days: int | None, transition_to_class: Literal["standard_ia", "glacier", "deep_archive"] | None, transition_after_days: int | None)`.
- [ ] `S3ObjectStore` on construction calls `put_bucket_lifecycle_configuration` to sync the declared rules to the bucket; on adapter shutdown does nothing (rules persist).
- [ ] `LocalFsObjectStore` reaping runs as a periodic `agent/coordinator.py` job (see `agent.04`) that walks the configured prefixes and deletes objects whose `expires_at` is in the past; safe to run concurrently with reads (uses sidecar timestamp, no rename racing).
- [ ] `docs/storage_lifecycle.md` documents the mapping logical-prefix → retention class (raw uploads, intermediate artifacts, evidence packs, model artifacts, audit logs).
- [ ] Pyright-strict clean; tests cover (a) S3 `put_bucket_lifecycle_configuration` is called with the declared rules under `moto`, (b) local-FS reaper deletes only expired objects, (c) `expires_at` round-trips through sidecar and S3 metadata.

### Verification
- `cd backend && pytest tests/storage tests/agent -k lifecycle --cov=storage` green; coverage ≥ 85%.
- Manual: run the local-FS reaper twice — second invocation finds nothing to delete (idempotent).
- `aws s3api get-bucket-lifecycle-configuration --bucket <bucket>` reflects the rules declared in `ObjectStoreConfig`.

### Code touch points
- `backend/shared/protocols.py` (modify — add timestamp fields)
- `backend/config/schema.py` (modify — add `LifecycleRule`, `lifecycle` field)
- `backend/storage/adapters/s3_adapter.py` (modify)
- `backend/storage/adapters/local_fs_adapter.py` (modify)
- `backend/storage/adapters/in_memory.py` (modify)
- `backend/agent/coordinator.py` (modify — register reaper job)
- `backend/agent/jobs/storage_reaper.py` (new)
- `docs/storage_lifecycle.md` (new)
- `backend/tests/storage/test_*` (modify)
- `backend/tests/agent/test_storage_reaper.py` (new)

---

## Story storage.06: Tenant-scoped key prefixes with adapter-layer enforcement

**ID:** storage.06
**Status:** planned
**Prerequisites:** [storage.01, _multitenancy.09, _security.03]
**Unblocks:** [ingestion.20, monitoring.06, storage.11]
**Estimated size:** M

**As a** multi-tenant platform owner,
**I need** every object-store call to prepend the active tenant prefix and reject cross-tenant reads/writes,
**so that** a misrouted logical key from tenant A can never overwrite or read tenant B's data.

### Current State
- `S3ObjectStore._storage_key` prepends only the configured `base_path` (`backend/storage/adapters/s3_adapter.py:197-199`); `LocalFsObjectStore._object_path` does the same (`backend/storage/adapters/local_fs_adapter.py:137-146`). Neither reads any tenant context.
- `InMemoryObjectStore` has no scoping at all — keys are global to the process.
- Architecture §12.3 says "Data separation: enforced at the adapter layer — graph queries, vector searches, and object store paths are always scoped to the active tenant", but the storage module reads no tenant context.
- The only repo reference to a `tenants/` prefix is the hard-coded fixture string at `backend/tests/api/test_dependencies.py:257`.

### Acceptance Criteria
- [ ] `ObjectStoreProtocol` adapters accept a `tenant_resolver: Callable[[], TenantId]` constructor injection wired through `backend/api/dependencies.py:get_object_store` (already a `@lru_cache(maxsize=1)` — this story flips it to per-request scope as required by `_multitenancy.09`).
- [ ] Every `put_bytes` / `put_stream` / `get_bytes` / `get_stream` / `delete` / `exists` / `list_keys` / `generate_presigned_url` call rewrites the key to `tenants/<tenant_id>/<base_path><key>` at the adapter boundary; callers never construct tenant-prefixed keys themselves.
- [ ] `CrossTenantAccessError` (defined in `storage.08`) is raised when a caller passes a key already containing a different `tenants/<other>/` segment — adapters never allow callers to bypass the resolver.
- [ ] `list_keys(prefix)` automatically scopes the listed prefix to the active tenant; absolute `tenants/...` prefixes from other tenants raise `CrossTenantAccessError`.
- [ ] A shared contract test (`backend/tests/storage/test_tenant_scope_contract.py`) parametrized over all four adapters asserts: (a) write under tenant A is not visible under tenant B, (b) attempting to delete tenant B's key from tenant A raises `CrossTenantAccessError`, (c) `list_keys("")` from tenant A returns only A's keys.
- [ ] Pyright-strict clean; existing call sites in `agent/coordinator.py`, `knowledgebases/`, `ingestion/`, and the API routers compile without per-call tenant plumbing changes (the resolver does it).

### Verification
- `cd backend && pytest tests/storage -k tenant_scope --cov=storage` green; coverage ≥ 85%.
- Manual: in dev compose with two tenants, write a key from tenant A; confirm `mc ls minio/<bucket>/tenants/A/` shows it and `mc ls minio/<bucket>/tenants/B/` does not.

### Code touch points
- `backend/storage/adapters/in_memory.py` (modify)
- `backend/storage/adapters/local_fs_adapter.py` (modify)
- `backend/storage/adapters/s3_adapter.py` (modify)
- `backend/storage/exceptions.py` (modify — add `CrossTenantAccessError` if not added by `storage.08`)
- `backend/api/dependencies.py` (modify — inject `tenant_resolver`)
- `backend/tests/storage/test_tenant_scope_contract.py` (new)

---

## Story storage.07: Content-addressed dedup with reference counting and SHA-256 integrity

**ID:** storage.07
**Status:** planned
**Prerequisites:** [storage.01, knowledgebases.02]
**Unblocks:** [embeddings.11, storage.11]
**Estimated size:** L

**As an** operator ingesting policy documents that are frequently re-uploaded,
**I need** identical bytes to be stored once and shared by reference (with delete-cascade reference counting),
**so that** re-uploads do not duplicate storage / transfer cost and silent corruption is detected on read via SHA-256 verification.

### Current State
- No checksum is computed or stored. `StoredObject` and `StoredObjectWriteResult` (`backend/shared/protocols.py:13-29`) have no `checksum` field — TODO at `backend/storage/models.py:7-8` flags this.
- Re-uploading the same document under a new logical key copies the bytes again on both S3 (`s3_adapter.py:113-118`) and local FS (`local_fs_adapter.py:63`).
- `LocalFsObjectStore.get_bytes` validates only `size_bytes` against the sidecar, not content (`backend/storage/adapters/local_fs_adapter.py:92-96`).
- The KB document-delete cascade (`knowledgebases.02`) drives the requirement: a refcounted dedup store must decrement on delete, not unconditionally remove the underlying blob.

### Acceptance Criteria
- [ ] `StoredObject` and `StoredObjectWriteResult` gain `checksum: str` (sha256, hex-encoded) and `etag: str | None`; all three adapters populate them on every read and write.
- [ ] When `ObjectStoreConfig.dedup: bool = True`, `put_bytes` / `put_stream` stores payload at `objects/sha256/<hash>` and the logical `<key>` becomes a thin pointer (`StoredObjectPointer` record in the sidecar / a 0-byte S3 object with `x-chili-content-hash` metadata).
- [ ] A refcount table tracks `(content_hash, ref_count)`; `delete(key)` decrements; the underlying blob is removed only when `ref_count` reaches 0. Local FS persists the refcount table in a `objects/.refcount.json` file (atomic rewrite); S3 persists it in an `objects/sha256/<hash>.refcount` sibling object updated with `If-Match` ETag for concurrency.
- [ ] On `get_bytes` / `get_stream`, the adapter recomputes SHA-256 and raises `PermanentStorageError("integrity")` (from `storage.08`) on mismatch.
- [ ] When `dedup=False`, behavior is identical to today (no pointer, no refcount) — feature is fully opt-in per config.
- [ ] KB cascade-delete (`knowledgebases.02`) calls `storage.delete(key)` — never `delete_blob_by_hash` directly — so refcounting is the single source of truth.
- [ ] Pyright-strict clean; tests cover (a) duplicate write reuses the underlying blob, (b) delete decrements refcount without removing the blob until last pointer drops, (c) tampered local-FS blob is detected on read, (d) concurrent refcount update under `moto` does not corrupt the counter.

### Verification
- `cd backend && pytest tests/storage -k dedup --cov=storage` green; coverage ≥ 85%.
- Manual: write the same 50 MiB payload under two logical keys in dev MinIO; `mc du minio/<bucket>/objects/sha256/` shows ≤ 51 MiB (single copy + small overhead).

### Code touch points
- `backend/shared/protocols.py` (modify — add `checksum`, `etag`)
- `backend/storage/models.py` (modify — add pointer / refcount models)
- `backend/storage/adapters/in_memory.py` (modify)
- `backend/storage/adapters/local_fs_adapter.py` (modify)
- `backend/storage/adapters/s3_adapter.py` (modify)
- `backend/config/schema.py` (modify — add `dedup: bool`)
- `backend/tests/storage/test_*` (modify)

---

## Story storage.08: Typed exception hierarchy plus retry / exponential backoff on transient failures

**ID:** storage.08
**Status:** planned
**Prerequisites:** [storage.01]
**Unblocks:** [storage.11, storage.12]
**Estimated size:** M

**As a** caller of the object-store from ingestion / KB / agent code,
**I need** a typed exception hierarchy and adapter-internal retry for transient errors,
**so that** business logic catches `ObjectNotFoundError` / `TransientStorageError` instead of leaking boto3 `ClientError`, and a throttled S3 burst does not surface as a 500 to the client.

### Current State
- `backend/storage/` has no `exceptions.py` (verified with `ls backend/storage/`).
- `S3ObjectStore.get_bytes` catches every exception only to convert 404s into `KeyError` and re-raises everything else (`backend/storage/adapters/s3_adapter.py:134-137`); `put_object` / `delete_object` / `list_objects_v2` have no retry on `ThrottlingException`, `SlowDown`, `RequestTimeout`, or `EndpointConnectionError`.
- `LocalFsObjectStore` surfaces `OSError` / `PermissionError` directly (`backend/storage/adapters/local_fs_adapter.py:106-117, 124-135`).
- Callers (e.g. `knowledgebases/`, `ingestion/`) must `except (KeyError, ValueError, ClientError)`, leaking the boto3 SDK into business logic in violation of CLAUDE.md "Hard Rules" §2.

### Acceptance Criteria
- [ ] `backend/storage/exceptions.py` declares `ObjectStoreError`, `ObjectNotFoundError(ObjectStoreError)`, `ObjectAlreadyExistsError(ObjectStoreError)`, `TransientStorageError(ObjectStoreError)`, `PermanentStorageError(ObjectStoreError)`, `CrossTenantAccessError(PermanentStorageError)`, `StorageQuotaExceededError(PermanentStorageError)`.
- [ ] All adapter methods translate backend-specific exceptions into the typed hierarchy. S3 `ClientError` codes `ThrottlingException`, `SlowDown`, `RequestTimeout`, `ServiceUnavailable`, `InternalError`, and `botocore.exceptions.EndpointConnectionError` map to `TransientStorageError`. `NoSuchKey` / `404` / `NotFound` map to `ObjectNotFoundError` (replaces today's `KeyError`).
- [ ] A retry decorator (in `backend/storage/_retry.py`) with exponential backoff + full jitter wraps every adapter method; configurable via `ObjectStoreConfig.retry: RetryConfig(max_attempts: int = 5, base_delay_ms: int = 100, max_delay_ms: int = 5000, per_call_deadline_ms: int | None = None)`. Only `TransientStorageError` is retried; `PermanentStorageError` and `ObjectNotFoundError` short-circuit.
- [ ] Existing callers that catch `KeyError` are migrated to `ObjectNotFoundError` (search confirms zero remaining `except KeyError` references against the storage layer).
- [ ] Pyright-strict clean; integration tests under `moto`'s failure-injection mode assert retry behavior — three transient failures followed by success result in one successful call; four transient failures raise `TransientStorageError` after 5 attempts.

### Verification
- `cd backend && pytest tests/storage -k 'retry or exceptions' --cov=storage` green; coverage ≥ 85%.
- `cd backend && rg "except KeyError" backend/api backend/agent backend/knowledgebases backend/ingestion` returns nothing storage-related.

### Code touch points
- `backend/storage/exceptions.py` (new)
- `backend/storage/_retry.py` (new)
- `backend/storage/adapters/in_memory.py` (modify)
- `backend/storage/adapters/local_fs_adapter.py` (modify)
- `backend/storage/adapters/s3_adapter.py` (modify)
- `backend/config/schema.py` (modify — add `RetryConfig`)
- `backend/api/routers/knowledgebases.py` (modify — migrate `except KeyError`)
- `backend/agent/coordinator.py` (modify — migrate as needed)
- `backend/tests/storage/test_*` (modify)

---

## Story storage.09: Storage observability — bytes / requests / latency metrics + structured audit

**ID:** storage.09
**Status:** planned
**Prerequisites:** [storage.01, _observability.04, _observability.10]
**Unblocks:** [storage.10, storage.13]
**Estimated size:** M

**As an** SRE on call,
**I need** Prometheus metrics and OpenTelemetry spans on every storage operation plus a structured audit log on writes/deletes,
**so that** latency regressions, error spikes, and per-tenant byte growth are visible in Grafana and every payload mutation is forensically reconstructable.

### Current State
- No adapter emits metrics or trace spans. `S3ObjectStore`, `LocalFsObjectStore`, `InMemoryObjectStore` have no `logger` import (verified with `rg "^import logging|^from shared.logging" backend/storage/`).
- The metric set defined for `_observability.04` does not list storage counters — this story adds them.
- The architecture-defined metric inventory in `docs/architecture.md` §11.2 lists `pipeline_*` and `http_*` metrics but no storage metrics.
- The audit-log subsystem from `_observability.10` does not yet exist; this story is one of its first consumers.

### Acceptance Criteria
- [ ] An adapter base mixin `_ObservableObjectStore` emits OpenTelemetry spans wrapping every public method, with span attributes `chili.storage.backend`, `chili.storage.operation`, `chili.storage.tenant_id`, `chili.storage.key_prefix` (NOT the full key), `chili.storage.bytes`.
- [ ] Prometheus metrics in `backend/storage/metrics.py`:
  - Counter `chili_storage_requests_total{backend, operation, result}` (result ∈ `success` / `not_found` / `transient_error` / `permanent_error`).
  - Counter `chili_storage_bytes_written_total{backend, tenant}` / `chili_storage_bytes_read_total{backend, tenant}`.
  - Histogram `chili_storage_request_duration_seconds{backend, operation}` (buckets tuned for ms-to-multi-second range).
  - Gauge `chili_storage_objects_total{backend, tenant}` (refreshed by a periodic job, NOT per-request).
- [ ] Structured audit-log line on every successful `put_*` / `delete` / `generate_presigned_url("upload")` containing `tenant_id`, `logical_key`, `byte_count`, `checksum`, `actor` (from auth context). **Payload bytes are never logged.**
- [ ] Pyright-strict clean; tests cover (a) span is opened and closed exactly once per method, (b) `transient_error` counter increments on `TransientStorageError`, (c) audit logger receives one line per write — no payload bytes present.

### Verification
- `cd backend && pytest tests/storage -k 'metrics or audit' --cov=storage` green; coverage ≥ 85%.
- Manual: trigger 100 writes; `curl -s api:8000/metrics | grep chili_storage` shows non-zero counter and histogram observations; Jaeger UI shows nested spans `chili.storage.put_bytes` → `chili.s3.put_object`.

### Code touch points
- `backend/storage/metrics.py` (new)
- `backend/storage/_observable.py` (new — mixin)
- `backend/storage/adapters/in_memory.py` (modify)
- `backend/storage/adapters/local_fs_adapter.py` (modify)
- `backend/storage/adapters/s3_adapter.py` (modify)
- `backend/tests/storage/test_observability.py` (new)

---

## Story storage.10: Per-backend cost tracking and storage-class usage attribution

**ID:** storage.10
**Status:** planned
**Prerequisites:** [storage.05, storage.09, _multitenancy.16, database.05]
**Unblocks:** []
**Estimated size:** L

**As a** finance/operations owner,
**I need** rolled-up per-tenant byte / request / storage-class accounting persisted to TimescaleDB and exposed via API,
**so that** chargeback, quota enforcement, and "which tenant is driving Glacier transitions" reporting are first-class.

### Current State
- Nothing in `backend/storage/` tracks cumulative bytes written / read, request counts, or storage-class distribution per tenant.
- `backend/database/migrations/` has no `storage_usage` table.
- No link exists between `backend/analytics/metrics` and storage utilization.
- This becomes load-bearing once `_multitenancy.16` introduces per-tenant quotas / rate limits.

### Acceptance Criteria
- [ ] Alembic migration adds a TimescaleDB hypertable `storage_usage(tenant_id, prefix, backend, storage_class, bytes_written, bytes_read, request_count, period_start, period_end)` with hypertable partitioning on `period_start`.
- [ ] `StorageUsageRecorder` (subscribes to the same metric stream as `storage.09`) batches updates and writes daily rollups via an `agent/coordinator.py` job; live request accounting stays in Prometheus, not Postgres, to avoid per-call DB overhead.
- [ ] Cost-rate mapping table per backend (S3 Standard / IA / Glacier / Deep Archive; MinIO / local FS = 0) lives in `backend/storage/cost_rates.py` and is overrideable via `ObjectStoreConfig.cost_overrides`.
- [ ] `GET /storage/usage?tenant_id=&from=&to=` returns aggregated bytes / requests / estimated cost per tenant / storage class; gated by `require_role("admin")`.
- [ ] Frontend admin panel renders a per-tenant cost panel (deferred to the frontend backlog; this story exposes the API only).
- [ ] Optional alert wiring: when a tenant exceeds `storage_quota_bytes` (from `_multitenancy.16`), publish `StorageQuotaExceededEvent`.
- [ ] Pyright-strict clean; tests cover the rollup job, the API filter, and the cost calculation across mixed storage classes.

### Verification
- `cd backend && pytest tests/storage tests/api/test_routers_storage.py tests/agent -k usage --cov=storage` green; coverage ≥ 85%.
- Manual: in dev compose, write ≥ 100 MiB across two tenant prefixes, run the rollup job, query `GET /storage/usage`, confirm per-tenant byte totals match `mc du`.

### Code touch points
- `backend/database/migrations/versions/000X_storage_usage.py` (new)
- `backend/storage/cost_rates.py` (new)
- `backend/storage/usage.py` (new — recorder + rollup)
- `backend/agent/coordinator.py` (modify — register rollup job)
- `backend/api/routers/storage.py` (modify — `GET /storage/usage`)
- `backend/config/schema.py` (modify — `cost_overrides`)
- `backend/tests/storage/test_usage.py` (new)
- `backend/tests/api/test_routers_storage.py` (modify)

---

## Story storage.11: Shared adapter contract test suite (in-memory / local-FS / MinIO / S3 live)

**ID:** storage.11
**Status:** planned
**Prerequisites:** [storage.01, storage.06, storage.07, storage.08]
**Unblocks:** [storage.12]
**Estimated size:** M

**As a** maintainer adding the GCS adapter (`storage.12`) or modifying any existing adapter,
**I need** a single parametrized contract suite that exercises every adapter against the same behavioural spec,
**so that** key-validation rules, list ordering, missing-key semantics, metadata preservation, tenant scoping, dedup, and retry behavior cannot diverge between adapters.

### Current State
- Only `backend/tests/storage/test_s3_adapter.py` uses `moto`; the local-FS and in-memory adapters are covered by their own per-adapter tests (`test_local_fs_adapter.py`, `test_in_memory.py`).
- No shared `contract.py` exists — each adapter test file re-asserts the same expectations independently, with subtle drift (e.g. list-ordering is asserted on local-FS but not on in-memory).
- The dev compose stack runs MinIO at `:9000` (`docker-compose.dev.yaml`) but no test runs against it; live AWS S3 is not exercised either.
- Without a contract harness, the GCS adapter from `storage.12` has nothing to bind to and live MinIO regressions are invisible.

### Acceptance Criteria
- [ ] `backend/tests/storage/contract.py` defines a `StorageContractTestBase` with test methods covering: round-trip put/get/delete, missing-key behavior (`ObjectNotFoundError`), list ordering, list pagination, metadata round-trip (Unicode + nested), key-validation rules (empty / null / `..` / `/abs`), streaming round-trip, presigned-URL round-trip (skip on backends that raise `NotImplementedError`), tenant-scope isolation, dedup refcount on delete, retry under injected transient failure.
- [ ] Five concrete subclasses: `TestInMemoryContract`, `TestLocalFsContract`, `TestS3MotoContract`, `TestMinioLiveContract` (skipped unless `CHILI_MINIO_LIVE=1`), `TestS3AwsLiveContract` (marked `@pytest.mark.integration`, skipped unless `AWS_S3_TEST_BUCKET` is set).
- [ ] CI runs in-memory + local-FS + moto on every PR; the MinIO live job runs in the existing compose-based integration workflow; AWS live is documented as opt-in for release-cut validation only.
- [ ] Every existing adapter passes the full suite; gaps surface as failing tests, not skipped ones (skips allowed only for the documented `NotImplementedError` paths on the in-memory and local-FS adapters).
- [ ] Pyright-strict clean.

### Verification
- `cd backend && pytest tests/storage/contract.py tests/storage/test_*_contract* --cov=storage` green; coverage ≥ 85%.
- `CHILI_MINIO_LIVE=1 cd backend && pytest tests/storage -k MinioLive` green against the compose MinIO.

### Code touch points
- `backend/tests/storage/contract.py` (new)
- `backend/tests/storage/test_in_memory_contract.py` (new)
- `backend/tests/storage/test_local_fs_contract.py` (new)
- `backend/tests/storage/test_s3_moto_contract.py` (new)
- `backend/tests/storage/test_minio_live_contract.py` (new)
- `backend/tests/storage/test_s3_aws_live_contract.py` (new)
- `.github/workflows/ci.yml` (modify — add MinIO live job)

---

## Story storage.12: GCS adapter (parity with S3, behind shared contract suite)

**ID:** storage.12
**Status:** planned
**Prerequisites:** [storage.01, storage.08, storage.11]
**Unblocks:** []
**Estimated size:** L

**As an** operator deploying chiliAI on GCP/GKE,
**I need** a native Google Cloud Storage adapter,
**so that** we do not rely on MinIO-on-GKE or S3-interop and we can use Workload Identity for credentials.

### Current State
- `ObjectStoreConfig.backend: Literal["s3", "minio", "local"]` (`backend/config/schema.py:143`) does not include `gcs`.
- `backend/api/dependencies.py:get_object_store` (lines 444-462) rejects unknown backends via `_raise_unsupported_backend("storage", backend, ("local", "s3", "minio"))`.
- The TODO at `backend/storage/protocols.py:14-15` explicitly calls for `GCSObjectStore`.
- Architecture §11 lists "GCP GKE" as a supported deployment target but the application provides no native GCS adapter.
- CLAUDE.md "Hard Rules" §2 forbids extending the `Literal` without protocol + factory wiring + tests landing atomically — this story ships all three.

### Acceptance Criteria
- [ ] `backend/storage/adapters/gcs_adapter.py` implements `ObjectStoreProtocol` against `google-cloud-storage` (lazy import behind the optional extra, mirroring `s3_adapter.py:252-259`).
- [ ] New `[gcs]` optional extra in `backend/pyproject.toml` pinning a known-good `google-cloud-storage` version.
- [ ] `ObjectStoreConfig.backend` widened to `Literal["s3", "minio", "local", "gcs"]`; `get_object_store` factory branch added; `_raise_unsupported_backend` tuple updated.
- [ ] Adapter supports the full surface from `storage.01` (streaming, paginated list, presigned URLs via `blob.generate_signed_url`), encryption from `storage.04` (CSEK + CMEK via `kms_key_name`), tenant scoping from `storage.06`, dedup from `storage.07`, typed exceptions + retry from `storage.08`, lifecycle from `storage.05` (`bucket.lifecycle_rules`).
- [ ] Credentials loaded via `GOOGLE_APPLICATION_CREDENTIALS` env var OR Workload Identity (no app code change needed); validated at construction.
- [ ] Passes the full shared contract suite from `storage.11` via `TestGcsLiveContract` (skipped unless `CHILI_GCS_LIVE=1` and a test bucket is configured); `moto`-equivalent fake (`fake-gcs-server`) used in unit tests.
- [ ] `docs/architecture.md` §3 (line 119), §5.2, and §11 updated to list GCS as a supported backend.
- [ ] Pyright-strict clean.

### Verification
- `cd backend && pytest tests/storage -k gcs --cov=storage` green; coverage ≥ 85%.
- `CHILI_GCS_LIVE=1 GOOGLE_APPLICATION_CREDENTIALS=... cd backend && pytest tests/storage/test_gcs_live_contract.py` green against a real GCS bucket.
- `cd backend && pyright backend/storage` clean.

### Code touch points
- `backend/storage/adapters/gcs_adapter.py` (new)
- `backend/pyproject.toml` (modify — add `[gcs]` extra)
- `backend/config/schema.py` (modify — widen `Literal`)
- `backend/api/dependencies.py` (modify — add factory branch)
- `backend/storage/protocols.py` (modify — remove GCS TODO entry)
- `backend/tests/storage/test_gcs_adapter.py` (new — unit, fake-gcs-server)
- `backend/tests/storage/test_gcs_live_contract.py` (new)
- `docs/architecture.md` (modify)

---

## Story storage.13: Cross-region replication strategy (RPO/RTO, failover playbook, Terraform module)

**ID:** storage.13
**Status:** planned
**Prerequisites:** [storage.04, storage.09, _infra.09, _infra.13, _observability.08]
**Unblocks:** []
**Estimated size:** L

**As an** operator with a DR obligation,
**I need** a documented active-passive cross-region replication posture, Terraform that provisions it, a circuit-breaker fallback to the secondary endpoint, replication-lag alerting, and a rehearsed failover runbook,
**so that** a regional outage does not result in unbounded data loss or unbounded recovery time.

### Current State
- Nothing in `backend/storage/` or `infra/` declares a replication or disaster-recovery posture.
- S3 cross-region replication (CRR) is bucket-level config not managed by the application; MinIO site-replication is undocumented for this project.
- `S3ObjectStore` (`backend/storage/adapters/s3_adapter.py:66-95`) accepts a single `endpoint_url`; there is no `secondary_endpoint_url` fallback and no circuit breaker.
- `_infra.13` covers "backup, restore, DR drills" at the infrastructure layer; this story is its application-layer counterpart.
- No replication-lag metric exists; `_observability.08` would have nothing to alert on today.

### Acceptance Criteria
- [ ] `docs/storage_replication.md` captures the chosen strategy (active-passive CRR with bucket versioning + object lock, RPO target ≤ 15 min, RTO target ≤ 1 h, failover trigger: 5 min of consecutive `TransientStorageError` from the primary endpoint).
- [ ] Terraform module `infra/terraform/aws/modules/storage-replication/` declares: primary bucket with versioning + replication role, secondary bucket in `secondary_region`, replication configuration (full bucket, KMS key replication, replica-modification sync), object-lock configuration on the secondary in compliance mode for evidence packs only.
- [ ] `ObjectStoreConfig` gains `secondary_endpoint_url: str | None` and `failover_after_consecutive_errors: int = 5`; `S3ObjectStore` opens a circuit breaker on `failover_after_consecutive_errors` `TransientStorageError`s in a row and switches reads to the secondary endpoint (writes continue to fail loudly — active-passive, not active-active).
- [ ] Replication-lag SLO surfaced as Prometheus gauge `chili_storage_replication_lag_seconds{primary_region, secondary_region}` populated by a periodic job that reads CloudWatch `ReplicationLatency` (S3) or `mc admin replicate status` (MinIO).
- [ ] Alert rule (lives in `_observability.08` Grafana / Alertmanager bundle, referenced here) fires when `chili_storage_replication_lag_seconds > 900` for 10 min.
- [ ] Tabletop failover runbook in `docs/runbooks/storage_failover.md` exercised once and the result recorded; runbook includes the manual cut-over command, the integrity-check procedure (re-checksum a sample of N objects), and the cut-back procedure.
- [ ] Pyright-strict clean; tests cover circuit-breaker open / half-open / closed transitions and that the secondary endpoint receives reads only after the threshold is crossed.

### Verification
- `cd backend && pytest tests/storage -k 'replication or circuit_breaker' --cov=storage` green; coverage ≥ 85%.
- `cd infra/terraform/aws && terraform plan -target=module.storage_replication` shows the expected resources.
- Manual tabletop failover exercise completed and signed off; runbook lessons-learned section updated.

### Code touch points
- `docs/storage_replication.md` (new)
- `docs/runbooks/storage_failover.md` (new)
- `infra/terraform/aws/modules/storage-replication/main.tf` (new)
- `infra/terraform/aws/modules/storage-replication/variables.tf` (new)
- `infra/terraform/aws/modules/storage-replication/outputs.tf` (new)
- `backend/storage/adapters/s3_adapter.py` (modify — circuit breaker, secondary endpoint)
- `backend/storage/replication.py` (new — lag-poller job)
- `backend/agent/coordinator.py` (modify — register lag job)
- `backend/config/schema.py` (modify — secondary endpoint, threshold)
- `backend/tests/storage/test_replication.py` (new)
