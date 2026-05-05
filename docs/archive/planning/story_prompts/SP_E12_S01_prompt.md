# Story E12-S01: Ingestion document idempotency via content-hash deduplication

## Story
As a platform developer, I want the ingestion service to compute and store a content hash for each submitted document so that resubmitting the same file does not create duplicate parsed records.

## Acceptance Criteria
1. `ingestion/service.py` computes a SHA-256 hex digest of the raw document bytes before parsing.
2. The hash is stored on the `SourceDocument` model as `content_hash: str`.
3. Before enqueueing a document, the service checks if a document with the same `content_hash` already exists in the knowledge base (via object store metadata lookup); if found, it returns the existing document ID with a `DeduplicatedResult` outcome instead of re-processing.
4. `ingestion/models.py` is updated to add `content_hash: str` to `SourceDocument`.
5. Unit tests cover: first submission (full processing), duplicate submission (returns existing), different content (different hash, full processing).

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | M    | E3-S08       |

## Target Files
- `backend/ingestion/models.py` — add `content_hash: str` to `SourceDocument`
- `backend/ingestion/service.py` — add SHA-256 hashing and deduplication check
- `backend/tests/ingestion/test_service.py` — add deduplication tests

## Reference Files to Read First
- `backend/ingestion/service.py` — current ingestion service implementation
- `backend/ingestion/models.py` — `SourceDocument` and related models
- `backend/storage/protocols.py` — `ObjectStore` protocol (put_bytes, get_bytes, exists)
- `backend/tests/ingestion/test_service.py` — existing ingestion service tests

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- Use `hashlib.sha256` from the standard library — no new dependencies
- The hash must be computed from the original bytes before any transformation
- Deduplication scope is per knowledge base — the same file in two different KBs must both process
- Store the deduplication index as a JSON file in object store under `knowledgebases/{kb_id}/.index/content_hashes.json`

## What NOT To Do
- Do not dedup at the API layer (router) — dedup belongs in the service
- Do not block concurrent ingestion during hash lookup — optimize for throughput
- Do not change the `IngestionOutcome` base model; add a `DeduplicatedResult` subtype instead

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=ingestion tests/ingestion/` >= 85% coverage
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
