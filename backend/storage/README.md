# storage

Object storage for raw bytes (uploaded documents and other blobs other modules
key into it). The contract is `shared.protocols.ObjectStoreProtocol`; this
package re-exports it as `ObjectStore` and provides three adapters: in-memory,
local filesystem, and S3-compatible (AWS S3 and MinIO).

## Layout

| File | Responsibility |
|------|----------------|
| `protocols.py` | `ObjectStore` — alias of `shared.protocols.ObjectStoreProtocol`. |
| `models.py` | Re-exports `StoredObject` and `StoredObjectWriteResult` from `shared.protocols`. |
| `adapters/in_memory.py` | `InMemoryObjectStore` — process-local dict keyed by object key. |
| `adapters/local_fs_adapter.py` | `LocalFsObjectStore` — object bytes on disk plus a `<name>.meta.json` sidecar holding media type and metadata. Root is the `base_directory` argument, else `ObjectStoreConfig.base_path`, else `./data/objects/`. |
| `adapters/s3_adapter.py` | `S3ObjectStore` — boto3 client (loaded lazily via `importlib`, `[s3]` extra) over `put_object` / `get_object` / `head_object` / `delete_object` / paginated `list_objects_v2`. Keys are prefixed with `ObjectStoreConfig.base_path`; `endpoint_url` points it at MinIO. |

## Contract

```python
class ObjectStoreProtocol(Protocol):
    def put_bytes(self, key: str, content: bytes, *, media_type: str | None = None,
                  metadata: dict[str, object] | None = None) -> StoredObjectWriteResult: ...
    def get_bytes(self, key: str) -> StoredObject: ...   # KeyError when missing
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...
    def list_keys(self, prefix: str) -> list[str]: ...
```

Invariants:

- **Missing object → `KeyError`** from `get_bytes` in every adapter, so callers
  branch on it portably.
- `InMemoryObjectStore.delete` treats a missing key as a no-op.
- `list_keys` returns sorted logical keys (the S3 adapter strips `base_path`
  and follows continuation tokens until the listing is exhausted).
- `LocalFsObjectStore` validates logical keys and prefixes: it rejects empty or
  whitespace-only values, null bytes, backslashes, Windows drive prefixes, and
  keys ending in the sidecar suffix, so a key cannot escape the base directory.
- S3 metadata is normalized to `dict[str, str]` (S3 user metadata is
  string-only).

## Configuration

`DomainConfig.storage` (`ObjectStoreConfig` in `config/schema.py`): `backend`
(`local` | `s3` | `minio`, default `local`), `endpoint_url`, `bucket`,
`base_path`, `credentials_env_var`.

When `credentials_env_var` is set, `S3ObjectStore` reads that environment
variable as a JSON object with `aws_access_key_id`, `aws_secret_access_key`
and optional `aws_session_token`; a missing, blank or non-JSON value raises
`ValueError`. When it is unset, boto3's default credential chain applies.

## How it is reached

- **API**: `get_object_store()` in `api/dependencies.py`. With `backend: local`
  and an all-default `storage` section it returns `InMemoryObjectStore`;
  a non-default local section returns `LocalFsObjectStore`; `s3`/`minio`
  return `S3ObjectStore`. Constructor errors surface as `ConfigurationError`.
- **Worker**: `build_object_store()` in `agent/coordinator.py`, through
  `_OBJECT_STORE_REGISTRY` (`in_memory`, `local`, `s3`, `minio`); an all-default
  section also yields `InMemoryObjectStore`.
- Consumers include `ingestion/`, `knowledgebases/`, `graph/service.py`,
  `vectorstore/service.py`, `analytics/explainability/adapters/evidence_object_store.py`
  and `analytics/gnn/adapters/cluster_store.py`.

Because the default resolves to an in-memory store in each process, the API and
worker share stored bytes only when a non-default `storage` section (local path
on a shared volume, S3, or MinIO) is configured.

## Persistence

No database tables. Bytes live in the selected backend.

## Current gaps

From `TODO(production)` comments in this package:

- `protocols.py`: no paginated `list_keys`, streaming `get_stream`/`put_stream`,
  or presigned URLs.
- `models.py`: `StoredObject` has no timestamps, etag/version id, or checksum.
- `adapters/in_memory.py`: `InMemoryObjectStore` is not thread-safe.

## Tests

`tests/storage/` — `test_in_memory.py`, `test_local_fs_adapter.py`,
`test_s3_adapter.py`, `test_models.py`.

See also [docs/architecture.md](../../docs/architecture.md) and
[docs/ledger/protocol-contracts.md](../../docs/ledger/protocol-contracts.md).
