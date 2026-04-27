# Subagent Implementation Brief — chiliAI

> Read this **before** starting any story. Repository conventions are non-negotiable.

## Top-level rules (load `/home/rdhagan92/chiliAI/CLAUDE.md` first)

1. **Cross-module interaction is restricted to three paths**: FastAPI gateway (`api/`), agent coordinator (`agent/`), and `shared/` contracts library. **No ad-hoc cross-module imports.**
2. **External systems live behind protocols + adapters**. Module layout: `protocols.py` (contract), `models.py` (internal types), `service_models.py` (API/external types), `service.py` (orchestration), `adapters/` (concrete impls), `exceptions.py` (domain errors).
3. **No hardcoded domain types** in `shared/types.py`. Everything domain-specific is `Entity(type=..., properties=...)` validated against the loaded `DomainConfig`.
4. **Domain configuration drives everything** (`config/schema.py`, `config/loader.py`). The frontend reads `GET /config/domain` at startup.
5. **Strict typing** — `pyright --strict` clean, full annotations, **no untyped `Any`**.
6. **Coverage** — ≥85% per module touched (`pytest --cov`).

## Code style — mirror what's already there

Look at the **most recently completed** files for tone:

| Pattern | Reference file |
|---------|---------------|
| Adapter with optional SDK + 429 retry | `backend/llm/adapters/openai_adapter.py` |
| Adapter, stdlib-only, security-hardened | `backend/storage/adapters/local_fs_adapter.py` |
| Adapter with cloud SDK + moto tests | `backend/storage/adapters/s3_adapter.py` |
| Coordinator handler chain | `backend/agent/coordinator.py` (`handle_graph_updated`) |
| Test pattern using in-memory adapter at protocol boundary | `backend/tests/agent/test_coordinator.py` |
| Pydantic v2 models with strict cross-field validation | `backend/config/schema.py` |
| Service / protocol / models split | `backend/graph/`, `backend/embeddings/` |

## What to do for each story

1. **Read the prompt** at `docs/planning/story_prompts/SP_<EPIC>_<STORY>_prompt.md` in full.
2. **Read the "Reference Files to Read First" listed in the prompt** before writing anything.
3. **Implement target files** listed in the prompt. Don't expand scope beyond the prompt — no surrounding cleanup, no extra abstractions.
4. **Write tests** — protocol implementations get unit tests using in-memory adapters; integration tests for SDK-backed adapters use mocking libs (`moto[s3]` for S3, lightweight stubs / monkeypatch for OpenAI/Anthropic SDKs — never make real API calls).
5. **Update the story prompt** — append "Implementation Note" + "Validation Note" sections (mirror the format in `SP_E4_S01_prompt.md` and `SP_E3_S07_prompt.md`).
6. **Update `docs/planning/backlog.md`** — set Status: Done with date (this date is `2026-04-26`).
7. **Update `docs/project_status_report.md`** if you touch a module's implementation status (coverage %, "Done" markers).

## Validation commands (run before claiming done)

From `backend/`:
```bash
.venv/bin/pytest tests/<module>/ --cov=<module> --cov-report=term-missing  # ≥85%
.venv/bin/ruff check <module> tests/<module>
.venv/bin/pyright <module> tests/<module>                                   # 0 errors
```

For agent / API / events / multi-module changes, run the broader gate:
```bash
.venv/bin/pytest --cov
.venv/bin/ruff check .
.venv/bin/pyright
```

## What NOT to do

- Do **not** import vendor SDKs in business logic (only inside `<module>/adapters/<vendor>_adapter.py`).
- Do **not** introduce `Any` to silence pyright. Add proper types.
- Do **not** add commentary explaining what the code does (well-named identifiers are enough). Comments are for the **why** when non-obvious.
- Do **not** create READMEs / planning docs unless the story prompt asks for them.
- Do **not** wire DI / coordinator unless the story explicitly requires it. Most adapter stories are adapter-only.
- Do **not** write to real network/disk in tests. Use `tmp_path` (pytest fixture), `moto`, or in-memory adapters.
- Do **not** skip the "Implementation Note" / "Validation Note" updates on the story prompt — they are how the next agent knows what's done.

## Optional dependencies — install per story

`backend/pyproject.toml` declares optional extras. If your story implements an SDK adapter, your tests should pass **with** the extra installed:

```bash
cd backend && .venv/bin/pip install -e ".[dev,<extra>]"
```

Available extras: `dev`, `neo4j`, `qdrant`, `sentence-transformers`, `openai`, `anthropic`, `s3`. If you add a new extra, append it to `pyproject.toml` and document it.

## Naming conventions for new files

- Adapters: `<module>/adapters/<vendor>_adapter.py` (e.g., `qdrant_adapter.py`, `openai_adapter.py`). The architecture doc uses unsuffixed names (e.g., `qdrant.py`) — follow the **codebase**, not the doc; the doc is being refreshed.
- Tests: `tests/<module>/test_<vendor>_adapter.py`.
- Routers: `api/routers/<resource>.py` (singular file per resource).
- Frontend pages: `chili_app/src/pages/<PageName>/index.tsx`.
- Frontend hooks: `chili_app/src/hooks/use<Feature>.ts`.

## Common gotchas

- `pyright --strict` requires explicit collection types (`list[str]`, not `list`). It also flags untyped `**kwargs`.
- Pydantic v2 models use `model_validate_json` / `model_dump_json` (not v1's `parse_raw` / `json`).
- `correlation_id` propagation through events is non-negotiable — every new event must carry it forward.
- The graph service's `upsert_task` is per-batch atomic. Coordinator handlers must not mix multiple batches in one transaction.
- `shared/utils.py:utc_now()` is the single timestamp source. Don't write `datetime.utcnow()` or local `_utc_now()` helpers.

## When in doubt

Read the most recently committed story for the same module first. The git log shows the last completed work per epic — that's the authoritative pattern source.
