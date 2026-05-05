# Story E7-S05: GNN — Node Embedding Export

## Story
As a platform developer, I want the GNN service to produce node embeddings for each entity.

## Acceptance Criteria
1. `GnnAnalysisResult` gains `node_embeddings: dict[str, list[float]]`.
2. `GnnService.analyze()` computes node embeddings (default: "node2vec" or "spectral").
3. Embeddings normalized to unit length.
4. Tests verify dimensionality and normalization.

## Priority / Size / Dependencies

| Field        | Value  |
|--------------|--------|
| Priority     | P3     |
| Size         | L      |
| Dependencies | E7-S04 |

## Target Files
- `backend/analytics/gnn/service_models.py` — add `node_embeddings: dict[str, list[float]]` to `GnnAnalysisResponse`; add embedding config fields to request if needed
- `backend/analytics/gnn/service.py` — add embedding computation step in `analyze()`; add `_compute_embeddings()` method
- `backend/analytics/gnn/models.py` — add any supporting domain types for embedding configuration
- `backend/tests/analytics/gnn/test_service.py` — add tests for embedding dimensionality, normalization, and key coverage
- `backend/pyproject.toml` — add `node2vec` to optional `[analytics]` dependency group if using node2vec

## Reference Files to Read First
- `backend/analytics/gnn/service.py` — current GNN service implementation (including community detection from E7-S04)
- `backend/analytics/gnn/service_models.py` — current request/response models (including communities from E7-S04)
- `backend/analytics/gnn/models.py` — current domain models
- `backend/analytics/gnn/protocols.py` — service protocol definition
- `backend/tests/analytics/gnn/test_service.py` — existing test patterns

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- Prefer `networkx` spectral embedding (`numpy.linalg.eigh` on Laplacian) as the default if `node2vec` is not available
- If using `node2vec`, guard import with `try/except ImportError` and fall back to spectral
- Embeddings must be L2-normalized to unit length (each vector's norm == 1.0)
- Embedding dimensionality should be configurable with a sensible default (e.g., 16 or 32)
- Every node in the graph must have an embedding entry in the output dict

## What NOT To Do
- Do NOT modify existing community detection or node scoring logic from E7-S04
- Do NOT import from other analytics sub-modules (timeseries, risk, explainability)
- Do NOT add API endpoints — this is service-layer only
- Do NOT return unnormalized embeddings
- Do NOT make `node2vec` a required dependency — it must be optional with fallback

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=analytics/gnn tests/analytics/gnn/` >= 85% coverage
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)

## Implementation Note
Completed on April 26, 2026. `GnnAnalysisResult` /
`GnnAnalysisResponse` gained `node_embeddings: dict[str, list[float]]`.
`_compute_embeddings()` builds the graph Laplacian, runs `numpy.linalg.eigh`,
keeps the lowest-non-trivial eigenvectors up to the requested
`embedding_dimension` (default 8, max 256), zero-pads short embeddings, and
L2-normalizes. Every node receives a non-zero unit-length embedding, with a
deterministic `[1, 0, ...]` fallback for isolated rows.

## Validation Note
From `backend/`: `.venv/bin/pytest tests/analytics/gnn/` asserts
dimensionality and that `||v|| == 1.0` for all embeddings; sub-module
coverage 97%.
