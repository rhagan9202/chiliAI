# Module: storage

**Verified against codebase:** 2026-05-20
**Source:** `backend/storage/`

## Purpose

Object/file storage abstraction. Persists raw ingested files for audit and reprocessing. Also used for intermediate pipeline artifacts (parsed docs, chunks, extractions) keyed under `knowledgebases/{kb_id}/documents/{doc_id}/`.

---

## Protocol

`storage/protocols.py` re-exports `ObjectStore = ObjectStoreProtocol` from `shared/protocols.py`:

```python
class ObjectStoreProtocol(Protocol):
    def put_bytes(self, key: str, content: bytes, *, media_type: str | None, metadata: dict | None) -> StoredObjectWriteResult: ...
    def get_bytes(self, key: str) -> StoredObject: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...
    def list_keys(self, prefix: str) -> list[str]: ...
```

---

## Adapters

| Backend | File | Config |
|---------|------|--------|
| In-memory | `adapters/in_memory.py` | `ObjectStoreConfig.backend = "local"` (in tests) |
| Local filesystem | `adapters/local_fs_adapter.py` | `backend = "local"`, uses `base_path` |
| S3 / MinIO | `adapters/s3_adapter.py` | `backend = "s3"` or `"minio"`, uses `endpoint_url`, `bucket`, `credentials_env_var` |

The S3 adapter serves both AWS S3 and MinIO (same boto3 client, different `endpoint_url`).

---

## Storage Key Convention

```
knowledgebases/{kb_id}/                          # KB root
knowledgebases/{kb_id}/documents/{doc_id}/       # document artifacts
  raw.{ext}                                      # original uploaded bytes
  parsed.json                                    # ParsedDocument output
  chunks.json                                    # ChunkingResult output
  extraction.json                                # ExtractionResult output
  validation.json                                # ValidationReport output
  graph_update.json                              # GraphBuildReceipt
  embeddings.json                                # EmbeddedItem list
```

---

## Module Dependencies

- `shared/protocols.py` — re-exports `ObjectStoreProtocol` as `ObjectStore`
