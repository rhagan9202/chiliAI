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

## What NOT To Do
- Do not modify the `ObjectStore` protocol — implement it as-is (ensure E3-S08 is complete first or coordinate)
- Do not add any external dependencies — this adapter is stdlib-only
- Do not use `os.path` — use `pathlib.Path` exclusively
- Do not allow directory traversal — this is a security requirement
- Do not implement file locking or concurrency control — single-process use is fine for local dev
- Do not compress or encode stored objects — store raw bytes as-is
- Do not create nested adapter utilities outside `storage/`

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=storage tests/storage/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
