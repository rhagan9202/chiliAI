# Story E3-S06: S3/MinIO Object Storage Adapter

## Story
As a platform operator, I want an object storage adapter using the S3 API, so that document artifacts, chunking results, and graph snapshots are persisted durably.

## Acceptance Criteria
1. `storage/adapters/s3_adapter.py` implements `ObjectStore` protocol: `put_bytes`, `get_bytes`, `delete`, `exists`, `list_keys`.
2. Connection is configured via `ObjectStoreConfig` (endpoint_url for MinIO, bucket, credentials_env_var).
3. Metadata is stored as S3 object metadata headers.
4. `boto3` is listed as an optional dependency.
5. Integration test validates put → get → delete round-trip using `moto` mock.

## Priority / Size / Dependencies
- **Priority:** P1
- **Size:** M
- **Dependencies:** E1-S06

## Target Files
- `backend/storage/adapters/s3_adapter.py` — **create** — S3/MinIO adapter implementing `ObjectStore` protocol
- `backend/storage/adapters/__init__.py` — **modify** — re-export `S3ObjectStore`
- `backend/pyproject.toml` — **modify** — add `boto3` as optional dependency under an extras group (e.g., `[s3]`); add `moto[s3]` as a test/dev dependency
- `backend/tests/storage/test_s3_adapter.py` — **create** — integration test using `moto` mock for put → get → delete round-trip

## Reference Files to Read First
- `backend/storage/protocols.py` — `ObjectStore` protocol definition (the contract to implement, including `delete`, `exists`, `list_keys` from E3-S08)
- `backend/storage/models.py` — storage domain models
- `backend/storage/adapters/in_memory.py` — reference implementation of `ObjectStore`
- `backend/config/schema.py` — `ObjectStoreConfig` (endpoint_url, bucket, credentials_env_var, etc.)
- `backend/shared/types.py` — shared domain types
- `backend/pyproject.toml` — existing dependency structure and optional extras

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase (mirror `InMemoryObjectStore` structure)
- Read AWS credentials from environment variables specified in `ObjectStoreConfig.credentials_env_var` — never hardcode credentials
- Use `endpoint_url` parameter for MinIO compatibility — when set, connect to that endpoint instead of AWS
- Store metadata as S3 object metadata headers (user-defined metadata with `x-amz-meta-` prefix handled by boto3)
- The adapter must be usable without `boto3` installed (optional import with clear error if missing)
- Use `moto` to mock S3 in tests — do not require a real S3/MinIO endpoint for unit/integration tests

## What NOT To Do
- Do not modify the `ObjectStore` protocol — implement it as-is (ensure E3-S08 is complete first or coordinate)
- Do not add `boto3` as a hard/required dependency — it must be optional
- Do not hardcode AWS credentials, bucket names, or endpoints — read from config/environment
- Do not implement multipart upload in this story — simple put/get is sufficient
- Do not add encryption configuration — use bucket-level defaults
- Do not create custom S3 client wrappers — use `boto3` directly
- Do not require a running S3/MinIO for tests — use `moto` mock

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=storage tests/storage/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
