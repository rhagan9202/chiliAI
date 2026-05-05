# Story E3-S07: Local Filesystem Object Storage Adapter

## Story
As a platform developer, I want a local filesystem adapter implementing `ObjectStore`, so that developers can run the full pipeline locally without S3/MinIO.

## Acceptance Criteria
1. `storage/adapters/local_fs_adapter.py` implements `ObjectStore` protocol.
2. Objects are stored as files under a configurable base directory (default: `./data/objects/`).
3. Metadata is stored in a sidecar `.meta.json` file alongside each object.
4. `list_keys` supports prefix-based listing.
5. File paths are sanitized to prevent directory traversal (reject keys containing `..` or absolute paths).
6. Unit tests cover put/get/delete/list/exists and path-traversal rejection.

## Priority / Size / Dependencies
- **Priority:** P2
- **Size:** S
- **Dependencies:** None

## Target Files
- `backend/storage/adapters/local_fs_adapter.py` — **create** — local filesystem adapter implementing `ObjectStore` protocol
- `backend/storage/adapters/__init__.py` — **modify** — re-export `LocalFsObjectStore`
- `backend/tests/storage/test_local_fs_adapter.py` — **create** — unit tests for all protocol methods and path-traversal rejection

## Reference Files to Read First
- `backend/storage/protocols.py` — `ObjectStore` protocol definition (the contract to implement, including `delete`, `exists`, `list_keys` from E3-S08)
- `backend/storage/models.py` — storage domain models
- `backend/storage/adapters/in_memory.py` — reference implementation of `ObjectStore`
- `backend/config/schema.py` — `ObjectStoreConfig` (for base directory configuration)
- `backend/shared/types.py` — shared domain types

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase (mirror `InMemoryObjectStore` structure)
- **No external dependencies** — use only `pathlib.Path` and standard library modules
- Use `pathlib.Path` for all path construction — never use string concatenation for paths
- **Security: sanitize all keys** — reject keys containing `..`, absolute paths (starting with `/`), or null bytes; raise a clear exception on violation
- Store metadata in sidecar `.meta.json` files as JSON — one per object, same directory as the object file
- `list_keys(prefix)` should walk the directory tree and return keys matching the prefix
- Use `tmp_path` pytest fixture for test isolation — never write to real filesystem paths in tests
- This story is adapter-only. Do not wire `api.dependencies.get_object_store()` or the agent coordinator to instantiate `LocalFsObjectStore`; runtime provider selection remains separate integration work.

## What NOT To Do
- Do not modify the `ObjectStore` protocol — implement it as-is (ensure E3-S08 is complete first or coordinate)
- Do not add any external dependencies — this adapter is stdlib-only
- Do not use `os.path` — use `pathlib.Path` exclusively
- Do not allow directory traversal — this is a security requirement
- Do not implement file locking or concurrency control — single-process use is fine for local dev
- Do not compress or encode stored objects — store raw bytes as-is
- Do not create nested adapter utilities outside `storage/`
- Do not claim this story makes the full local pipeline use filesystem storage until DI/provider wiring is implemented separately.

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=storage tests/storage/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)

## Implementation Notes
- Added `LocalFsObjectStore` in `backend/storage/adapters/local_fs_adapter.py` implementing the synchronous `ObjectStore` protocol.
- Objects are written as raw files below a resolved configurable base directory. `ObjectStoreConfig.base_path` is used as the physical local root, and the adapter defaults to `./data/objects/` when no config path or explicit test path is supplied.
- Metadata is stored in adjacent `.meta.json` sidecars with `key`, `size_bytes`, `media_type`, and JSON-compatible `metadata` fields.
- Logical keys are POSIX-style only. The adapter rejects empty keys, null bytes, absolute paths, `..` path segments, `.` segments, empty object-key segments, backslashes, Windows drive forms, UNC-style prefixes, and keys ending in the reserved `.meta.json` sidecar suffix, with containment checks after path resolution.
- `list_keys(prefix)` recursively walks the base directory, excludes sidecar files, and returns sorted logical keys matching the prefix.
- `LocalFsObjectStore` is exported from both `storage` and `storage.adapters`.
- This remains adapter-only. API dependency selection and worker/coordinator provider wiring were intentionally not changed.

## Validation Notes
- `cd backend && .venv/bin/pytest tests/storage/ --cov=storage --cov-report=term-missing` passed: 82 tests, 92% storage coverage.
- `cd backend && .venv/bin/ruff check storage tests/storage` passed.
- `cd backend && .venv/bin/pyright storage tests/storage` passed with 0 errors.
