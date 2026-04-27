# Story E3-S06: S3/MinIO Object Storage Adapter

## Story
As a platform operator, I want an object storage adapter using the S3 API, so that document artifacts, chunking results, and graph snapshots are persisted durably.

## Acceptance Criteria
1. `storage/adapters/s3_adapter.py` implements the E3-S08 `ObjectStore` protocol: `put_bytes`, `get_bytes`, `delete`, `exists`, and `list_keys(prefix: str) -> list[str]`.
2. Connection is configured via `ObjectStoreConfig` (`endpoint_url` for MinIO, `bucket`, `base_path`, and `credentials_env_var`).
3. Metadata is stored as S3 object metadata headers.
4. `boto3` is listed as an optional dependency.
5. Integration test validates put → get → delete round-trip using `moto` mock.

## Priority / Size / Dependencies
- **Priority:** P1
- **Size:** M
- **Dependencies:** E1-S06, E3-S08

## Target Files
- `backend/storage/adapters/s3_adapter.py` — **create** — S3/MinIO adapter implementing `ObjectStore` protocol
- `backend/storage/adapters/__init__.py` — **modify** — re-export `S3ObjectStore`
- `backend/storage/__init__.py` — **modify** — re-export `S3ObjectStore` if the storage package exposes adapter classes
- `backend/config/schema.py` — **modify** — add `endpoint_url: str | None = None` to `ObjectStoreConfig` if not already present
- `backend/tests/config/test_schema.py` — **modify** — cover `ObjectStoreConfig.endpoint_url` defaults and configured values
- `backend/config/defaults/*.yaml` — **modify** — document `endpoint_url` for S3/MinIO storage config examples
- `backend/pyproject.toml` — **modify** — add `boto3` as optional dependency under an extras group (e.g., `[s3]`); add `moto[s3]` as a test/dev dependency
- `backend/tests/storage/test_s3_adapter.py` — **create** — integration test using `moto` mock for put → get → delete round-trip

## Reference Files to Read First
- `backend/storage/protocols.py` — `ObjectStore` protocol definition from E3-S08 (the contract to implement, including `delete`, `exists`, `list_keys`)
- `backend/storage/models.py` — storage domain models
- `backend/storage/adapters/in_memory.py` — reference implementation of `ObjectStore`
- `backend/config/schema.py` — `ObjectStoreConfig` (`endpoint_url`, `bucket`, `base_path`, `credentials_env_var`, etc.)
- `backend/shared/types.py` — shared domain types
- `backend/pyproject.toml` — existing dependency structure and optional extras

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase (mirror `InMemoryObjectStore` structure)
- If `ObjectStoreConfig.credentials_env_var` is set, read that environment variable as a JSON object containing `aws_access_key_id`, `aws_secret_access_key`, and optional `aws_session_token`; if unset, use boto3's default credential provider chain — never hardcode credentials
- Use `endpoint_url` parameter for MinIO compatibility — when set, connect to that endpoint instead of AWS
- Use `ObjectStoreConfig.base_path` as the S3 key namespace/prefix. Public adapter methods accept and return logical keys without the prefix.
- Store metadata as S3 object metadata headers (user-defined metadata with `x-amz-meta-` prefix handled by boto3)
- S3 user metadata values must be strings. The adapter should stringify metadata values consistently or reject non-string values with a clear error; tests must cover the chosen behavior.
- The adapter must be usable without `boto3` installed (optional import with clear error if missing)
- Use `moto` to mock S3 in tests — do not require a real S3/MinIO endpoint for unit/integration tests
- This story is adapter-only unless explicitly extended. Do not wire `api.dependencies.get_object_store()` to instantiate S3/MinIO in this story; provider selection/wiring belongs in a separate runtime integration story.

## What NOT To Do
- Do not modify the `ObjectStore` protocol in this story. E3-S08 must be completed first; if it is not complete, stop and implement or coordinate E3-S08 before starting E3-S06.
- Do not add `boto3` as a hard/required dependency — it must be optional
- Do not hardcode AWS credentials, bucket names, or endpoints — read from config/environment
- Do not implement multipart upload in this story — simple put/get is sufficient
- Do not add encryption configuration — use bucket-level defaults
- Do not create custom S3 client wrappers — use `boto3` directly
- Do not require a running S3/MinIO for tests — use `moto` mock

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=storage tests/storage/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)

## Implementation Notes
- Added `storage/adapters/s3_adapter.py` with `S3ObjectStore`, a synchronous
  implementation of `ObjectStore` using lazy `boto3` import and narrow local
  protocols so importing `storage` does not require optional S3 dependencies.
- `ObjectStoreConfig` now includes `endpoint_url` for MinIO/S3-compatible
  endpoints. The adapter validates non-blank buckets, normalizes `base_path` as
  an internal key namespace, and returns logical keys from `list_keys()`.
- Credentials are read from `credentials_env_var` as JSON containing string
  `aws_access_key_id`, string `aws_secret_access_key`, and optional string
  `aws_session_token`; when unset, boto3's default credential chain is used.
- Metadata values are stored through S3 user metadata headers after stringifying
  non-`None` values; `None` metadata values are rejected with `ValueError`.
- `boto3` is exposed as the optional `s3` extra, and `moto[s3]` is included in
  the dev extra for S3 integration testing.

## Validation Notes
- Validation completed from `backend/` on April 25, 2026:
  - `.venv/bin/pytest tests/config/test_schema.py tests/storage/ --cov=storage --cov-report=term-missing` — 83 passed; storage coverage 92%.
  - `.venv/bin/ruff check storage tests/storage config tests/config` — all checks passed.
  - `.venv/bin/pyright storage tests/storage config tests/config` — 0 errors, 0 warnings, 0 informations.
  - Verified `import storage` works without a hard module-import dependency on
    `boto3` by blocking `boto3` imports during a package import regression test.
