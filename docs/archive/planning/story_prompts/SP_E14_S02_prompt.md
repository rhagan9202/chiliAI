# Story E14-S02: EmbeddingsService — graph-metric hybrid embedding flow

## Story
As a platform developer, I want `EmbeddingsService` to support a hybrid embedding mode that combines text embeddings with graph-structural signals (degree, community membership, PageRank) to produce richer entity representations.

## Acceptance Criteria
1. `embeddings/service.py` accepts an optional `graph_service: GraphServiceProtocol | None = None` parameter.
2. When `graph_service` is provided and `request.use_graph_signals = True`, the service fetches entity graph metrics (degree, community_id, risk_score) for each entity in the batch via `graph_service.query_entities()`, then concatenates a normalized metric vector to the text embedding before indexing.
3. The combined embedding dimension is `text_dim + metric_dim`; `metric_dim` is a constructor parameter defaulting to 3.
4. When `graph_service` is absent or `use_graph_signals = False`, the service falls back to pure text embedding (backward-compatible).
5. `embeddings/models.py` adds `use_graph_signals: bool = False` to `EmbeddingRequest`.
6. Unit tests cover: pure text mode, hybrid mode with mocked graph service, missing graph service with `use_graph_signals=True` raises `EmbeddingsConfigError`.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P2       | M    | E14-S01, E2-S03 |

## Target Files
- `backend/embeddings/service.py` — add graph-metric hybrid embedding logic
- `backend/embeddings/models.py` — add `use_graph_signals` to `EmbeddingRequest`
- `backend/embeddings/exceptions.py` — add `EmbeddingsConfigError`
- `backend/tests/embeddings/test_service.py` — add hybrid embedding tests

## Reference Files to Read First
- `backend/embeddings/service.py` — current `EmbeddingsService`
- `backend/embeddings/models.py` — `EmbeddingRequest`, `EmbeddingResult`
- `backend/graph/service.py` — `GraphService.query_entities()` (post E2-S03)
- `backend/graph/protocols.py` — `GraphServiceProtocol`
- `docs/architecture.md` §5 — embeddings module and hybrid embedding design

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- Metric vector components must be individually normalized to `[0, 1]` before concatenation
- If graph metric fetch fails, log a warning and fall back to pure text embedding (do not fail the pipeline)
- The combined embedding must be stored with the correct `dimensions` count in `EmbeddingResult`

## What NOT To Do
- Do not implement GNN node embeddings here — that is E7-S05
- Do not change the `EmbedderProtocol` — graph mixing happens at the service layer, not adapter layer
- Do not hardcode entity property names for metric extraction

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=embeddings tests/embeddings/` >= 85% coverage
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
