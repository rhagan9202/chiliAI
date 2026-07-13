# BL-019: Embedding Cache + Cost/Usage Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retire the embedding-cache TODO in `backend/embeddings/service.py` with a protocol-backed in-process LRU cache, and ship cost/usage tracking (reported OpenAI tokens + estimated local tokens) via Prometheus counters and structured logs.

**Architecture:** The cache is an adapter-level concern inside `backend/embeddings`: a new `EmbeddingCacheProtocol` in `embeddings/adapters/protocols.py` with one v1 implementation, `InMemoryLruEmbeddingCache` in `embeddings/adapters/cache_in_memory.py`. `EmbeddingsService.embed()` partitions submissions into cache hits and misses, embeds only the misses, and back-fills the cache. Usage tracking is the lightest surface that closes the P1: module-level `prometheus_client` counters in a new `embeddings/metrics.py` (registered on the shared default `REGISTRY`, same pattern as `api/middleware/metrics.py`) plus a structured `logging` line per embed call. The OpenAI adapter starts capturing `response.usage.total_tokens` (it currently drops it); local adapters fall back to a chars/4 token estimate computed in the service.

**Cache design decisions (locked in):**
- **In-memory-only v1, protocol kept open.** A Redis-backed cache adapter is deliberately NOT in v1: (a) `embeddings` may only depend on the `events` module through its `EventBus` protocol — reaching into `events/runtime.py` for its Redis client would couple `embeddings` to another module's adapter internals, violating the protocol+adapter rule; (b) a standalone Redis cache adapter would be a new external-system integration needing its own config/factory wiring for marginal benefit — the embedder is a per-process singleton (API: `@lru_cache` in `api/dependencies.py`; worker: built once in `build_worker_dependencies()`), so an in-process cache is warm exactly where repeat embeds happen (the worker); (c) cross-process/durable caching is BL-045 roadmap tier. The `EmbeddingCacheProtocol` means a Redis adapter later is additive.
- **Cache key = SHA-256 of `namespace + "\x1f" + request.model_name + "\x1f" + content`**, where `namespace = f"{provider}:{model}:{dimensions}"` derived from `EmbeddingsConfig`. Model identity AND dimensions are in the key, so a config change (new model or dimension) can never serve a stale vector — dimension-safe by construction. On config hot-swap the API rebuilds `get_embeddings_service` (it is in `CONFIG_CACHE_REGISTRY`), so the cache instance is also replaced.
- **Cached value stores `vector + model_name + provider + dimensions`** so cache hits reproduce full `EmbeddedItem` metadata without calling the embedder.

**Cost/usage surface decision (locked in):** Prometheus counters + structured logs, NO durable store (durable per-request ledger is BL-045, out of scope). Counters register at import time on the prometheus default `REGISTRY` — the API process already serves them at `GET /metrics`; the worker process (where pipeline embedding happens) exposes them once BL-043 lands worker metrics exposure (soft coupling: this plan only requires the default registry, which is exactly what BL-043 scrapes). Structured logs cover the worker in the meantime.

**Tech Stack:** Python 3.12, Pydantic v2, prometheus-client (already a core backend dep), pytest, pyright strict, ruff.

## Global Constraints

- pyright strict, zero `Any`: run bare `.venv/bin/pyright` from `backend/` (the include list already covers `embeddings` and `tests/embeddings`, so test code must be strict-clean too).
- pytest coverage ≥ 85% on `embeddings/` and `vectorstore/`.
- ruff: `backend/.venv/bin/ruff check --no-cache .` (cache dir not writable in sandbox).
- Host pytest for DB-touching suites needs `DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test`.
- `GET /config/domain` has `response_model=DomainConfig`, so the `EmbeddingsConfig` field additions in Task 1 change the OpenAPI contract → regenerate: `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json` (repo root) then `cd chili_app && npm run codegen:api`. CI fails on drift.
- New config fields must have defaults so no pack YAML under `backend/config/defaults/` needs edits (verified: `get_embedder()` and coordinator `build_embedder()` compare against a fresh `EmbeddingsConfig()`, which also picks up the new defaults — equality semantics preserved).
- Never import private `_helpers` into test dirs (`reportPrivateUsage`); test through public surface.
- HARD SCOPE FENCE (BL-045 — do NOT build): object-store persistence of embeddings, graph-metric hybrid flow changes, model routing, architecture guard tests.

---

## File Structure

- Modify `backend/config/schema.py` — add `cache_enabled` / `cache_max_entries` to `EmbeddingsConfig`.
- Modify `backend/embeddings/models.py` — add `CachedEmbedding`, `build_embedding_cache_key`, `EmbeddingMetadata.total_tokens`.
- Modify `backend/embeddings/adapters/protocols.py` — add `EmbeddingCacheProtocol`.
- Create `backend/embeddings/adapters/cache_in_memory.py` — `InMemoryLruEmbeddingCache`, `create_embedding_cache`, `embedding_cache_namespace`.
- Create `backend/embeddings/metrics.py` — counters, `estimate_tokens`, `record_embedding_usage`.
- Modify `backend/embeddings/service.py` — cache-aware `embed()`, usage recording, retire the TODO.
- Modify `backend/embeddings/adapters/openai_adapter.py` — capture `usage.total_tokens`.
- Modify `backend/embeddings/__init__.py` — export new public names.
- Modify `backend/api/dependencies.py` — wire cache into `get_embeddings_service`.
- Modify `backend/agent/coordinator.py` — `build_embedding_cache()` + worker wiring.
- Modify `chili_app/openapi.json` + `chili_app/src/lib/api/schema.ts` — regenerated (no hand edits).
- Tests: `backend/tests/config/test_schema.py`, `backend/tests/embeddings/test_models.py`, create `backend/tests/embeddings/test_cache_in_memory.py`, create `backend/tests/embeddings/test_metrics.py`, `backend/tests/embeddings/test_service.py`, `backend/tests/embeddings/test_openai_adapter.py`, `backend/tests/api/test_dependencies.py`, `backend/tests/agent/test_coordinator.py`.
- Docs: `backend/embeddings/README.md`, `backend/README.md`, `docs/architecture.md`.

Unless a command says otherwise, run backend commands from `/home/rdhagan92/chiliAI/backend`.

---

### Task 1: Config Knobs + Contract Regeneration

**Files:**
- Modify: `backend/config/schema.py:129-138`
- Modify: `chili_app/openapi.json`, `chili_app/src/lib/api/schema.ts` (generated)
- Test: `backend/tests/config/test_schema.py:672-686`

**Interfaces:**
- Produces: `EmbeddingsConfig.cache_enabled: bool = True`, `EmbeddingsConfig.cache_max_entries: int = 4096` — consumed by Task 3's factory and Task 7's DI wiring.

- [ ] **Step 1: Write the failing config tests**

In `backend/tests/config/test_schema.py`, extend `TestEmbeddingsConfig` (currently lines 672-686) to:

```python
class TestEmbeddingsConfig:
    def test_defaults(self) -> None:
        config = EmbeddingsConfig()

        assert config.provider == "sentence_transformers"
        assert config.model == "all-MiniLM-L6-v2"
        assert config.dimensions == 384
        assert config.batch_size == 32
        assert config.api_key_env_var is None
        assert config.cache_enabled is True
        assert config.cache_max_entries == 4096

    def test_dimensions_and_batch_size_must_be_positive(self) -> None:
        with pytest.raises(ValidationError, match="dimensions"):
            EmbeddingsConfig(dimensions=0)
        with pytest.raises(ValidationError, match="batch_size"):
            EmbeddingsConfig(batch_size=0)

    def test_cache_max_entries_must_be_positive(self) -> None:
        with pytest.raises(ValidationError, match="cache_max_entries"):
            EmbeddingsConfig(cache_max_entries=0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/config/test_schema.py -k TestEmbeddingsConfig -q`
Expected: FAIL — `AttributeError`/`ValidationError` absent for `cache_enabled` / `cache_max_entries`.

- [ ] **Step 3: Add the fields**

In `backend/config/schema.py`, change `EmbeddingsConfig` to:

```python
class EmbeddingsConfig(BaseModel):
    """Configuration for selecting the embeddings provider and model."""

    provider: Literal["openai", "sentence_transformers", "local"] = (
        "sentence_transformers"
    )
    model: str = "all-MiniLM-L6-v2"
    dimensions: int = Field(default=384, gt=0)
    batch_size: int = Field(default=32, gt=0)
    api_key_env_var: str | None = None
    cache_enabled: bool = True
    cache_max_entries: int = Field(default=4096, gt=0)
```

- [ ] **Step 4: Run config tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/config/test_schema.py -k TestEmbeddingsConfig -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Regenerate frontend contracts**

`DomainConfig` (which nests `EmbeddingsConfig`) is the response model of `GET /config/domain`, so the OpenAPI contract changed. From the repo root `/home/rdhagan92/chiliAI`:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json
cd chili_app && npm run codegen:api
```

Expected: `chili_app/openapi.json` and `chili_app/src/lib/api/schema.ts` gain `cache_enabled` / `cache_max_entries` in the `EmbeddingsConfig` schema. No UI code imports these fields, so no other frontend change.

- [ ] **Step 6: Verify frontend stays clean**

From `/home/rdhagan92/chiliAI/chili_app`:

```bash
npm run lint && npm run build
```

Expected: ESLint clean; `tsc -b && vite build` succeed.

- [ ] **Step 7: Verify pack defaults suffice (no pack edits)**

Run: `.venv/bin/python -m pytest tests/config -q`
Expected: PASS — all default packs still validate; no YAML edits needed because both new fields default.

- [ ] **Step 8: Commit**

```bash
git add backend/config/schema.py backend/tests/config/test_schema.py chili_app/openapi.json chili_app/src/lib/api/schema.ts
git commit -m "feat(config): add embedding cache knobs to EmbeddingsConfig"
```

---

### Task 2: Cache Key + Cached-Entry Models

**Files:**
- Modify: `backend/embeddings/models.py`
- Test: `backend/tests/embeddings/test_models.py`

**Interfaces:**
- Produces: `CachedEmbedding(vector: list[float], model_name: str, provider: str, dimensions: int)` and `build_embedding_cache_key(*, namespace: str, model_name: str, content: str) -> str` — consumed by Tasks 3 and 4.

- [ ] **Step 1: Write the failing model tests**

Append to `backend/tests/embeddings/test_models.py` (the file already imports `pytest` and models from `embeddings.models`; extend the import to include the new names):

```python
from embeddings.models import CachedEmbedding, build_embedding_cache_key


def test_build_embedding_cache_key_is_deterministic() -> None:
    first = build_embedding_cache_key(
        namespace="local:model-a:4", model_name="m", content="Alpha"
    )
    second = build_embedding_cache_key(
        namespace="local:model-a:4", model_name="m", content="Alpha"
    )

    assert first == second
    assert len(first) == 64  # sha256 hex digest


def test_build_embedding_cache_key_varies_by_all_parts() -> None:
    base = build_embedding_cache_key(
        namespace="local:model-a:4", model_name="m", content="Alpha"
    )

    assert base != build_embedding_cache_key(
        namespace="local:model-a:8", model_name="m", content="Alpha"
    )
    assert base != build_embedding_cache_key(
        namespace="local:model-a:4", model_name="other", content="Alpha"
    )
    assert base != build_embedding_cache_key(
        namespace="local:model-a:4", model_name="m", content="Beta"
    )


def test_cached_embedding_requires_matching_dimensions() -> None:
    entry = CachedEmbedding(
        vector=[0.1, 0.2], model_name="m", provider="local", dimensions=2
    )
    assert entry.dimensions == 2

    with pytest.raises(ValueError, match="dimensions"):
        CachedEmbedding(
            vector=[0.1, 0.2], model_name="m", provider="local", dimensions=3
        )


def test_cached_embedding_rejects_empty_vector() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        CachedEmbedding(vector=[], model_name="m", provider="local", dimensions=1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/embeddings/test_models.py -q`
Expected: FAIL — `ImportError: cannot import name 'CachedEmbedding'`.

- [ ] **Step 3: Implement the model + key helper**

In `backend/embeddings/models.py`, add `import hashlib` to the imports, then add after the `GraphEmbeddingStatus` class:

```python
class CachedEmbedding(BaseModel):
    """A cached text-channel embedding with its producing model identity."""

    vector: list[float]
    model_name: str
    provider: str
    dimensions: int = Field(gt=0)

    @model_validator(mode="after")
    def _validate_vector(self) -> CachedEmbedding:
        if not self.vector:
            raise ValueError("CachedEmbedding vector must be non-empty.")
        if len(self.vector) != self.dimensions:
            raise ValueError("CachedEmbedding vector length must match dimensions.")
        return self


def build_embedding_cache_key(
    *, namespace: str, model_name: str, content: str
) -> str:
    """Build a collision-resistant cache key for one text + model identity."""

    digest = hashlib.sha256()
    digest.update(namespace.encode("utf-8"))
    digest.update(b"\x1f")
    digest.update(model_name.encode("utf-8"))
    digest.update(b"\x1f")
    digest.update(content.encode("utf-8"))
    return digest.hexdigest()
```

Add `"CachedEmbedding"` and `"build_embedding_cache_key"` to `__all__` (keep it sorted).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/embeddings/test_models.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/embeddings/models.py backend/tests/embeddings/test_models.py
git commit -m "feat(embeddings): add cache key and cached-entry models"
```

---

### Task 3: Cache Protocol + In-Memory LRU Adapter + Config Factory

**Files:**
- Modify: `backend/embeddings/adapters/protocols.py`
- Create: `backend/embeddings/adapters/cache_in_memory.py`
- Modify: `backend/embeddings/__init__.py`
- Test: `backend/tests/embeddings/test_cache_in_memory.py`

**Interfaces:**
- Consumes: `CachedEmbedding` (Task 2), `EmbeddingsConfig.cache_enabled/cache_max_entries` (Task 1).
- Produces: `EmbeddingCacheProtocol` with `get(key: str) -> CachedEmbedding | None` and `set(key: str, value: CachedEmbedding) -> None`; `InMemoryLruEmbeddingCache(*, max_entries: int)`; `create_embedding_cache(config: EmbeddingsConfig) -> InMemoryLruEmbeddingCache | None`; `embedding_cache_namespace(config: EmbeddingsConfig) -> str` returning `f"{provider}:{model}:{dimensions}"` — consumed by Tasks 4 and 7.

- [ ] **Step 1: Write the failing cache tests**

Create `backend/tests/embeddings/test_cache_in_memory.py`:

```python
"""Tests for the in-memory LRU embedding cache."""

from __future__ import annotations

import pytest

from config.schema import EmbeddingsConfig
from embeddings.adapters.cache_in_memory import (
    InMemoryLruEmbeddingCache,
    create_embedding_cache,
    embedding_cache_namespace,
)
from embeddings.adapters.protocols import EmbeddingCacheProtocol
from embeddings.models import CachedEmbedding


def _entry(value: float) -> CachedEmbedding:
    return CachedEmbedding(
        vector=[value], model_name="m", provider="local", dimensions=1
    )


def test_cache_returns_none_for_missing_key() -> None:
    cache = InMemoryLruEmbeddingCache(max_entries=2)

    assert cache.get("missing") is None


def test_cache_roundtrips_entries() -> None:
    cache = InMemoryLruEmbeddingCache(max_entries=2)
    cache.set("key-1", _entry(0.1))

    stored = cache.get("key-1")

    assert stored is not None
    assert stored.vector == [0.1]
    assert stored.provider == "local"


def test_cache_evicts_least_recently_used_entry() -> None:
    cache = InMemoryLruEmbeddingCache(max_entries=2)
    cache.set("key-1", _entry(0.1))
    cache.set("key-2", _entry(0.2))
    assert cache.get("key-1") is not None  # refresh key-1 recency
    cache.set("key-3", _entry(0.3))

    assert cache.get("key-2") is None
    assert cache.get("key-1") is not None
    assert cache.get("key-3") is not None


def test_cache_set_overwrites_and_refreshes_recency() -> None:
    cache = InMemoryLruEmbeddingCache(max_entries=2)
    cache.set("key-1", _entry(0.1))
    cache.set("key-2", _entry(0.2))
    cache.set("key-1", _entry(0.9))
    cache.set("key-3", _entry(0.3))

    assert cache.get("key-2") is None
    stored = cache.get("key-1")
    assert stored is not None
    assert stored.vector == [0.9]


def test_cache_rejects_non_positive_max_entries() -> None:
    with pytest.raises(ValueError, match="max_entries"):
        InMemoryLruEmbeddingCache(max_entries=0)


def test_cache_satisfies_protocol() -> None:
    cache = InMemoryLruEmbeddingCache(max_entries=1)

    assert isinstance(cache, EmbeddingCacheProtocol)


def test_create_embedding_cache_respects_disabled_flag() -> None:
    assert create_embedding_cache(EmbeddingsConfig(cache_enabled=False)) is None


def test_create_embedding_cache_uses_configured_max_entries() -> None:
    cache = create_embedding_cache(EmbeddingsConfig(cache_max_entries=1))

    assert cache is not None
    cache.set("key-1", _entry(0.1))
    cache.set("key-2", _entry(0.2))
    assert cache.get("key-1") is None
    assert cache.get("key-2") is not None


def test_embedding_cache_namespace_pins_model_identity() -> None:
    config = EmbeddingsConfig(provider="local", model="mini", dimensions=128)

    assert embedding_cache_namespace(config) == "local:mini:128"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/embeddings/test_cache_in_memory.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'embeddings.adapters.cache_in_memory'`.

- [ ] **Step 3: Add the protocol**

In `backend/embeddings/adapters/protocols.py`, extend the models import and add the protocol:

```python
from embeddings.models import (
    CachedEmbedding,
    EmbeddingRequest,
    EmbeddingResult,
    GraphEmbeddingBatch,
)
```

After `GraphEmbeddingProviderProtocol`:

```python
@runtime_checkable
class EmbeddingCacheProtocol(Protocol):
    """Key-value cache for previously generated text embeddings."""

    def get(self, key: str) -> CachedEmbedding | None: ...

    def set(self, key: str, value: CachedEmbedding) -> None: ...
```

Add `"EmbeddingCacheProtocol"` to `__all__` (sorted).

- [ ] **Step 4: Implement the adapter and factory**

Create `backend/embeddings/adapters/cache_in_memory.py`:

```python
"""In-process LRU cache adapter for text embeddings."""

from __future__ import annotations

import threading
from collections import OrderedDict

from config.schema import EmbeddingsConfig
from embeddings.models import CachedEmbedding

__all__ = [
    "InMemoryLruEmbeddingCache",
    "create_embedding_cache",
    "embedding_cache_namespace",
]


class InMemoryLruEmbeddingCache:
    """Thread-safe LRU cache bounded by entry count.

    Per-process only by design: the embedder is a per-process singleton, so
    hits accrue exactly where repeat embeds happen. A shared/durable cache is
    BL-045 roadmap tier and would arrive as another EmbeddingCacheProtocol
    adapter.
    """

    def __init__(self, *, max_entries: int) -> None:
        if max_entries <= 0:
            raise ValueError(
                "InMemoryLruEmbeddingCache max_entries must be positive."
            )
        self._max_entries = max_entries
        self._entries: OrderedDict[str, CachedEmbedding] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> CachedEmbedding | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            self._entries.move_to_end(key)
            return entry

    def set(self, key: str, value: CachedEmbedding) -> None:
        with self._lock:
            self._entries[key] = value
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)


def embedding_cache_namespace(config: EmbeddingsConfig) -> str:
    """Derive the cache namespace pinning provider, model, and dimensions."""

    return f"{config.provider}:{config.model}:{config.dimensions}"


def create_embedding_cache(
    config: EmbeddingsConfig,
) -> InMemoryLruEmbeddingCache | None:
    """Build the config-selected embedding cache; None when disabled."""

    if not config.cache_enabled:
        return None
    return InMemoryLruEmbeddingCache(max_entries=config.cache_max_entries)
```

- [ ] **Step 5: Export the new public names**

In `backend/embeddings/__init__.py`, add:

```python
from embeddings.adapters.cache_in_memory import (
    InMemoryLruEmbeddingCache,
    create_embedding_cache,
    embedding_cache_namespace,
)
from embeddings.adapters.protocols import (
    EmbedderProtocol,
    EmbeddingCacheProtocol,
    GraphEmbeddingProviderProtocol,
)
from embeddings.models import (
    CachedEmbedding,
    EmbeddingChannel,
    EmbeddingItem,
    EmbeddingMetadata,
    EmbeddingRequest,
    EmbeddingResult,
    EmbeddingVector,
    GraphEmbeddingBatch,
    GraphEmbeddingStatus,
    build_embedding_cache_key,
)
```

Add to `__all__` (sorted): `"CachedEmbedding"`, `"EmbeddingCacheProtocol"`, `"InMemoryLruEmbeddingCache"`, `"build_embedding_cache_key"`, `"create_embedding_cache"`, `"embedding_cache_namespace"`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/embeddings/test_cache_in_memory.py tests/embeddings/test_models.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/embeddings/adapters/protocols.py backend/embeddings/adapters/cache_in_memory.py backend/embeddings/__init__.py backend/tests/embeddings/test_cache_in_memory.py
git commit -m "feat(embeddings): add LRU embedding cache behind protocol"
```

---

### Task 4: Cache-Aware Embedding Service (Retires the TODO)

**Files:**
- Modify: `backend/embeddings/service.py`
- Test: `backend/tests/embeddings/test_service.py`

**Interfaces:**
- Consumes: `EmbeddingCacheProtocol`, `InMemoryLruEmbeddingCache` (Task 3); `CachedEmbedding`, `build_embedding_cache_key` (Task 2).
- Produces: `EmbeddingsService.__init__` / `create_embeddings_service` gain keyword params `cache: EmbeddingCacheProtocol | None = None` and `cache_namespace: str = ""` — consumed by Task 7. `_embed_graph_channel` signature changes to `(self, request: EmbedRequest, content_ids: list[str])`. Task 6 later inserts a `self._record_usage(...)` call before `return response`.

- [ ] **Step 1: Write the failing service cache tests**

Append to `backend/tests/embeddings/test_service.py`. Extend the existing imports: add

```python
from embeddings.adapters.cache_in_memory import InMemoryLruEmbeddingCache
```

and change the existing service import line to also pull in the service class (needed by `_cached_service`'s return annotation):

```python
from embeddings.service import EmbeddingsService, create_embeddings_service
```

(`EmbeddingRequest`/`EmbeddingResult` are already imported in this file — `_CountingEmbedder` needs nothing else.)

Add the counting fake and tests:

```python
class _CountingEmbedder(EmbedderProtocol):
    """Delegate to InMemoryEmbedder while recording every provider call."""

    def __init__(self, *, dimensions: int = 4) -> None:
        self._inner = InMemoryEmbedder(dimensions=dimensions)
        self.requests: list[EmbeddingRequest] = []

    def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        self.requests.append(request)
        return self._inner.embed(request)


def _cached_service(
    embedder: EmbedderProtocol,
    event_bus: InMemoryEventBus,
    *,
    graph_embedding_provider: GraphEmbeddingProviderProtocol | None = None,
) -> EmbeddingsService:
    return create_embeddings_service(
        embedder,
        event_bus=event_bus,
        graph_embedding_provider=graph_embedding_provider,
        cache=InMemoryLruEmbeddingCache(max_entries=16),
        cache_namespace="local:test-model:4",
    )


def test_embeddings_service_serves_repeated_content_from_cache() -> None:
    event_bus = InMemoryEventBus()
    embedder = _CountingEmbedder()
    service = _cached_service(embedder, event_bus)
    request = EmbedRequest(
        knowledge_base_id="kb-1",
        submissions=[EmbedSubmission(content_id="content-1", content="Alpha")],
    )

    first = service.embed(request)
    second = service.embed(request)

    assert len(embedder.requests) == 1
    assert second.items[0].vector == first.items[0].vector
    assert second.items[0].provider == "in-memory"
    assert second.model_name == first.model_name
    assert second.dimensions == first.dimensions
    assert second.request_id != first.request_id


def test_embeddings_service_embeds_only_cache_misses_in_order() -> None:
    event_bus = InMemoryEventBus()
    embedder = _CountingEmbedder()
    service = _cached_service(embedder, event_bus)

    service.embed(
        EmbedRequest(
            submissions=[EmbedSubmission(content_id="content-1", content="Alpha")]
        )
    )
    response = service.embed(
        EmbedRequest(
            submissions=[
                EmbedSubmission(content_id="content-1", content="Alpha"),
                EmbedSubmission(content_id="content-2", content="Beta"),
            ]
        )
    )

    assert [item.id for item in embedder.requests[-1].items] == ["content-2"]
    assert [item.content_id for item in response.items] == [
        "content-1",
        "content-2",
    ]


def test_embeddings_service_cache_key_includes_request_model_name() -> None:
    event_bus = InMemoryEventBus()
    embedder = _CountingEmbedder()
    service = _cached_service(embedder, event_bus)

    service.embed(
        EmbedRequest(
            model_name="model-a",
            submissions=[EmbedSubmission(content_id="content-1", content="Alpha")],
        )
    )
    service.embed(
        EmbedRequest(
            model_name="model-b",
            submissions=[EmbedSubmission(content_id="content-1", content="Alpha")],
        )
    )

    assert len(embedder.requests) == 2


def test_embeddings_service_without_cache_always_embeds() -> None:
    event_bus = InMemoryEventBus()
    embedder = _CountingEmbedder()
    service = create_embeddings_service(embedder, event_bus=event_bus)
    request = EmbedRequest(
        submissions=[EmbedSubmission(content_id="content-1", content="Alpha")]
    )

    service.embed(request)
    service.embed(request)

    assert len(embedder.requests) == 2


def test_embeddings_service_publishes_event_on_full_cache_hit() -> None:
    event_bus = InMemoryEventBus()
    service = _cached_service(_CountingEmbedder(), event_bus)
    request = EmbedRequest(
        knowledge_base_id="kb-1",
        submissions=[EmbedSubmission(content_id="content-1", content="Alpha")],
    )

    service.embed(request)
    service.embed(request)

    assert len(event_bus.published_events) == 2
    event = event_bus.published_events[-1]
    assert isinstance(event, EmbeddingsGeneratedEvent)
    assert event.batches[0].item_count == 1


def test_embeddings_service_graph_channel_covers_cached_submissions() -> None:
    event_bus = InMemoryEventBus()
    graph_provider = _GraphProvider(
        vectors={"content-1": [0.3, 0.4, 0.5], "content-2": [0.6, 0.7, 0.8]}
    )
    service = _cached_service(
        _CountingEmbedder(), event_bus, graph_embedding_provider=graph_provider
    )

    service.embed(
        EmbedRequest(
            knowledge_base_id="kb-1",
            submissions=[EmbedSubmission(content_id="content-1", content="Alpha")],
        )
    )
    service.embed(
        EmbedRequest(
            knowledge_base_id="kb-1",
            include_graph_embeddings=True,
            graph_embedding_dimension=3,
            submissions=[
                EmbedSubmission(content_id="content-1", content="Alpha"),
                EmbedSubmission(content_id="content-2", content="Beta"),
            ],
        )
    )

    assert graph_provider.calls[-1] == ("kb-1", ["content-1", "content-2"], 3)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/embeddings/test_service.py -q`
Expected: FAIL — `create_embeddings_service() got an unexpected keyword argument 'cache'`.

- [ ] **Step 3: Rewrite the service with cache partitioning**

Replace `backend/embeddings/service.py` in full:

```python
"""Service entry point for embedding generation flows."""

from __future__ import annotations

from embeddings.adapters.protocols import (
    EmbedderProtocol,
    EmbeddingCacheProtocol,
    GraphEmbeddingProviderProtocol,
)
from embeddings.exceptions import EmbeddingConfigurationError, EmbeddingProviderError
from embeddings.models import (
    CachedEmbedding,
    EmbeddingItem,
    EmbeddingMetadata,
    EmbeddingRequest,
    GraphEmbeddingStatus,
    build_embedding_cache_key,
)
from embeddings.service_models import (
    EmbedRequest,
    EmbedResponse,
    EmbedSubmission,
    EmbeddedItem,
)
from events.protocols import EventBus
from events.types import EmbeddingGeneratedReference, EmbeddingsGeneratedEvent
from shared.utils import generate_id


class EmbeddingsService:
    """Coordinate request normalization, caching, generation, and events."""

    # Roadmap (BL-045): object-store persistence of embedding results, model
    # routing across multiple configured providers, and a durable per-request
    # usage ledger. Batch chunking and provider retry live in the adapters.

    def __init__(
        self,
        embedder: EmbedderProtocol,
        *,
        event_bus: EventBus,
        graph_embedding_provider: GraphEmbeddingProviderProtocol | None = None,
        cache: EmbeddingCacheProtocol | None = None,
        cache_namespace: str = "",
    ) -> None:
        self._embedder = embedder
        self._event_bus = event_bus
        self._graph_embedding_provider = graph_embedding_provider
        self._cache = cache
        self._cache_namespace = cache_namespace

    def embed(self, request: EmbedRequest) -> EmbedResponse:
        request_id = generate_id()
        cached_items, miss_submissions = self._partition_cached(request)

        fresh_items: dict[str, EmbeddedItem] = {}
        result_metadata: EmbeddingMetadata | None = None
        if miss_submissions:
            result_metadata, fresh_items = self._embed_misses(
                request, request_id, miss_submissions
            )

        text_items = [
            fresh_items[submission.content_id]
            if submission.content_id in fresh_items
            else cached_items[submission.content_id]
            for submission in request.submissions
        ]
        model_name, dimensions = _response_identity(
            request, result_metadata, text_items
        )
        graph_items, graph_status = self._embed_graph_channel(
            request,
            [submission.content_id for submission in request.submissions],
        )
        response = EmbedResponse(
            request_id=request_id,
            model_name=model_name,
            dimensions=dimensions,
            items=[*text_items, *graph_items],
            graph_status=graph_status,
        )
        self._event_bus.publish(
            EmbeddingsGeneratedEvent(
                batches=[
                    EmbeddingGeneratedReference(
                        knowledge_base_id=request.knowledge_base_id,
                        request_id=response.request_id,
                        item_count=len(request.submissions),
                        dimensions=response.dimensions,
                        model_name=response.model_name,
                    )
                ]
            )
        )
        return response

    def _cache_key(self, model_name: str, content: str) -> str:
        return build_embedding_cache_key(
            namespace=self._cache_namespace,
            model_name=model_name,
            content=content,
        )

    def _partition_cached(
        self, request: EmbedRequest
    ) -> tuple[dict[str, EmbeddedItem], list[EmbedSubmission]]:
        """Split submissions into cached text items and cache misses."""

        if self._cache is None:
            return {}, list(request.submissions)

        cached: dict[str, EmbeddedItem] = {}
        misses: list[EmbedSubmission] = []
        for submission in request.submissions:
            entry = self._cache.get(
                self._cache_key(request.model_name, submission.content)
            )
            if entry is None:
                misses.append(submission)
                continue
            cached[submission.content_id] = EmbeddedItem(
                content_id=submission.content_id,
                vector=list(entry.vector),
                channel="text",
                model_name=entry.model_name,
                provider=entry.provider,
                dimensions=entry.dimensions,
            )
        return cached, misses

    def _embed_misses(
        self,
        request: EmbedRequest,
        request_id: str,
        miss_submissions: list[EmbedSubmission],
    ) -> tuple[EmbeddingMetadata, dict[str, EmbeddedItem]]:
        """Embed cache misses, validate completeness, and back-fill the cache."""

        embedding_request = EmbeddingRequest(
            request_id=request_id,
            knowledge_base_id=request.knowledge_base_id,
            model_name=request.model_name,
            items=[
                EmbeddingItem(id=submission.content_id, content=submission.content)
                for submission in miss_submissions
            ],
        )
        try:
            result = self._embedder.embed(embedding_request)
        except ValueError as exc:
            raise EmbeddingConfigurationError(str(exc)) from exc
        except Exception as exc:
            raise EmbeddingProviderError("Failed to generate embeddings.") from exc

        expected_ids = {item.id for item in embedding_request.items}
        actual_ids = set(result.vectors)
        missing_ids = sorted(expected_ids - actual_ids)
        extra_ids = sorted(actual_ids - expected_ids)
        if missing_ids or extra_ids:
            details: list[str] = []
            if missing_ids:
                details.append(f"missing vectors for: {', '.join(missing_ids)}")
            if extra_ids:
                details.append(f"unexpected vectors for: {', '.join(extra_ids)}")
            raise EmbeddingProviderError(
                "Embedding provider returned incomplete batch results: "
                + "; ".join(details)
            )

        fresh_items: dict[str, EmbeddedItem] = {}
        for submission in miss_submissions:
            vector = result.vectors[submission.content_id]
            fresh_items[submission.content_id] = EmbeddedItem(
                content_id=submission.content_id,
                vector=vector,
                channel="text",
                model_name=result.metadata.model_name,
                provider=result.metadata.provider,
                dimensions=result.metadata.dimensions,
            )
            if self._cache is not None:
                self._cache.set(
                    self._cache_key(request.model_name, submission.content),
                    CachedEmbedding(
                        vector=list(vector),
                        model_name=result.metadata.model_name,
                        provider=result.metadata.provider,
                        dimensions=result.metadata.dimensions,
                    ),
                )
        return result.metadata, fresh_items

    def _embed_graph_channel(
        self,
        request: EmbedRequest,
        content_ids: list[str],
    ) -> tuple[list[EmbeddedItem], GraphEmbeddingStatus | None]:
        if not request.include_graph_embeddings and not request.require_graph_embeddings:
            return [], None

        if request.knowledge_base_id is None:
            if request.require_graph_embeddings:
                raise EmbeddingProviderError(
                    "Graph embeddings require knowledge_base_id."
                )
            return [], GraphEmbeddingStatus(
                requested=True,
                provider_configured=self._graph_embedding_provider is not None,
                missing_content_ids=content_ids,
                failure_message="knowledge_base_id is required for graph embeddings.",
            )

        if self._graph_embedding_provider is None:
            if request.require_graph_embeddings:
                raise EmbeddingProviderError(
                    "Graph embeddings require a graph provider."
                )
            return [], GraphEmbeddingStatus(
                requested=True,
                provider_configured=False,
                missing_content_ids=content_ids,
            )

        try:
            batch = self._graph_embedding_provider.get_node_embeddings(
                knowledge_base_id=request.knowledge_base_id,
                content_ids=content_ids,
                dimensions=request.graph_embedding_dimension,
            )
        except Exception as exc:
            if request.require_graph_embeddings:
                raise EmbeddingProviderError(
                    "Failed to generate graph embeddings."
                ) from exc
            return [], GraphEmbeddingStatus(
                requested=True,
                provider_configured=True,
                missing_content_ids=content_ids,
                failure_message=str(exc),
            )

        graph_items: list[EmbeddedItem] = []
        missing_content_ids: list[str] = []
        for content_id in content_ids:
            vector = batch.vectors.get(content_id)
            if vector is None:
                missing_content_ids.append(content_id)
                continue
            if (
                batch.dimensions != request.graph_embedding_dimension
                or len(vector) != request.graph_embedding_dimension
            ):
                if request.require_graph_embeddings:
                    raise EmbeddingProviderError(
                        "Graph embedding dimension does not match requested "
                        "graph embedding dimension."
                    )
                missing_content_ids.append(content_id)
                continue
            graph_items.append(
                EmbeddedItem(
                    content_id=content_id,
                    vector=list(vector),
                    channel="graph",
                    model_name=batch.model_name,
                    provider=batch.provider,
                    dimensions=batch.dimensions,
                )
            )

        if request.require_graph_embeddings and missing_content_ids:
            raise EmbeddingProviderError(
                "Provider returned missing graph embeddings for: "
                + ", ".join(missing_content_ids)
            )

        return graph_items, GraphEmbeddingStatus(
            requested=True,
            provider_configured=True,
            missing_content_ids=missing_content_ids,
        )


def _response_identity(
    request: EmbedRequest,
    result_metadata: EmbeddingMetadata | None,
    text_items: list[EmbeddedItem],
) -> tuple[str, int]:
    """Resolve the response model name and dimensions for hit/miss mixes."""

    if result_metadata is not None:
        return result_metadata.model_name, result_metadata.dimensions
    first = text_items[0]
    return (
        first.model_name or request.model_name,
        first.dimensions or len(first.vector),
    )


def create_embeddings_service(
    embedder: EmbedderProtocol,
    *,
    event_bus: EventBus,
    graph_embedding_provider: GraphEmbeddingProviderProtocol | None = None,
    cache: EmbeddingCacheProtocol | None = None,
    cache_namespace: str = "",
) -> EmbeddingsService:
    """Create the default embeddings service."""

    return EmbeddingsService(
        embedder,
        event_bus=event_bus,
        graph_embedding_provider=graph_embedding_provider,
        cache=cache,
        cache_namespace=cache_namespace,
    )


__all__ = ["EmbeddingsService", "create_embeddings_service"]
```

Notes on the rewrite:
- The `TODO(production)` block at the old line 24 is retired: caching is implemented; graph-metric flow, batch chunking, and retry already exist elsewhere; the remaining items are labeled BL-045 roadmap.
- Behavior preserved for the no-cache path: same exceptions, same completeness validation, same event (with `item_count` = all submissions, as before), and `response.request_id` still equals the id given to the embedder (adapters echo `request.request_id`, so using the pre-generated id is equivalent).
- `_embed_graph_channel` now receives ALL submission content ids, not just misses — the graph channel must not shrink when text is cached (covered by `test_embeddings_service_graph_channel_covers_cached_submissions`).
- Duplicate `content_id`s within one request were already unsupported (the old code built a dict keyed by content id); that assumption is unchanged.

- [ ] **Step 4: Run the full embeddings suite**

Run: `.venv/bin/python -m pytest tests/embeddings -q`
Expected: PASS — all pre-existing graph-channel/error tests plus the six new cache tests.

- [ ] **Step 5: Run the downstream consumers' suites (regression check)**

Run: `DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/python -m pytest tests/agent/test_coordinator.py tests/rag/test_embeddings_bridge.py -q`
Expected: PASS — the service signature only gained optional keywords.

- [ ] **Step 6: Commit**

```bash
git add backend/embeddings/service.py backend/tests/embeddings/test_service.py
git commit -m "feat(embeddings): cache-aware embed flow, retire caching TODO"
```

---

### Task 5: Capture Provider-Reported Token Usage (OpenAI)

**Files:**
- Modify: `backend/embeddings/models.py` (EmbeddingMetadata)
- Modify: `backend/embeddings/adapters/openai_adapter.py`
- Test: `backend/tests/embeddings/test_models.py`, `backend/tests/embeddings/test_openai_adapter.py`

**Interfaces:**
- Produces: `EmbeddingMetadata.total_tokens: int | None` (None ⇒ provider reported nothing) — consumed by Task 6's `_record_usage`.

- [ ] **Step 1: Write the failing metadata test**

Append to `backend/tests/embeddings/test_models.py` (`EmbeddingMetadata` is already imported there):

```python
def test_embedding_metadata_total_tokens_defaults_to_none() -> None:
    metadata = EmbeddingMetadata(model_name="m", dimensions=2, provider="local")

    assert metadata.total_tokens is None


def test_embedding_metadata_rejects_negative_total_tokens() -> None:
    with pytest.raises(ValueError, match="total_tokens"):
        EmbeddingMetadata(
            model_name="m", dimensions=2, provider="local", total_tokens=-1
        )
```

- [ ] **Step 2: Write the failing OpenAI usage tests**

In `backend/tests/embeddings/test_openai_adapter.py`, extend the fakes (lines 31-44): add a usage dataclass and give the response an optional usage field, and let the endpoint stamp usage on default responses:

```python
@dataclass(frozen=True)
class FakeUsage:
    """Represent the usage block of a fake API response."""

    total_tokens: int
```

Change `FakeEmbeddingResponse` to:

```python
@dataclass(frozen=True)
class FakeEmbeddingResponse:
    """Represent the fake API response surface used by the adapter."""

    data: list[FakeEmbeddingRecord]
    usage: FakeUsage | None = None
```

Change `FakeEmbeddingsEndpoint.__init__` to accept `usage_tokens: int | None = None` (store as `self._usage_tokens = usage_tokens`), and its default-response return to:

```python
        return FakeEmbeddingResponse(
            data=records,
            usage=(
                FakeUsage(total_tokens=self._usage_tokens)
                if self._usage_tokens is not None
                else None
            ),
        )
```

Then append tests (reuse the module's existing `_build_embedder`-style construction — the file constructs `OpenAIEmbedder(EmbeddingsConfig(...), client=cast(OpenAIClientProtocol, FakeOpenAIClient(endpoint)))` in its happy-path tests; mirror that exact pattern):

```python
def test_openai_embedder_captures_reported_usage_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    endpoint = FakeEmbeddingsEndpoint(vector_size=3, usage_tokens=7)
    embedder = OpenAIEmbedder(
        EmbeddingsConfig(
            provider="openai",
            model="text-embedding-3-small",
            dimensions=3,
            batch_size=4,
            api_key_env_var="OPENAI_API_KEY",
        ),
        client=cast(OpenAIClientProtocol, FakeOpenAIClient(endpoint)),
    )

    result = embedder.embed(
        EmbeddingRequest(
            request_id="request-1",
            model_name="ignored",
            items=[
                EmbeddingItem(id="item-1", content="Alpha"),
                EmbeddingItem(id="item-2", content="Beta"),
            ],
        )
    )

    assert result.metadata.total_tokens == 7


def test_openai_embedder_sums_usage_tokens_across_batches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    endpoint = FakeEmbeddingsEndpoint(vector_size=3, usage_tokens=7)
    embedder = OpenAIEmbedder(
        EmbeddingsConfig(
            provider="openai",
            model="text-embedding-3-small",
            dimensions=3,
            batch_size=1,
            api_key_env_var="OPENAI_API_KEY",
        ),
        client=cast(OpenAIClientProtocol, FakeOpenAIClient(endpoint)),
    )

    result = embedder.embed(
        EmbeddingRequest(
            request_id="request-1",
            model_name="ignored",
            items=[
                EmbeddingItem(id="item-1", content="Alpha"),
                EmbeddingItem(id="item-2", content="Beta"),
            ],
        )
    )

    assert len(endpoint.calls) == 2
    assert result.metadata.total_tokens == 14


def test_openai_embedder_reports_none_usage_when_provider_omits_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    endpoint = FakeEmbeddingsEndpoint(vector_size=3)
    embedder = OpenAIEmbedder(
        EmbeddingsConfig(
            provider="openai",
            model="text-embedding-3-small",
            dimensions=3,
            batch_size=4,
            api_key_env_var="OPENAI_API_KEY",
        ),
        client=cast(OpenAIClientProtocol, FakeOpenAIClient(endpoint)),
    )

    result = embedder.embed(
        EmbeddingRequest(
            request_id="request-1",
            model_name="ignored",
            items=[EmbeddingItem(id="item-1", content="Alpha")],
        )
    )

    assert result.metadata.total_tokens is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/embeddings/test_models.py tests/embeddings/test_openai_adapter.py -m "not integration" -q`
Expected: FAIL — `total_tokens` unknown to `EmbeddingMetadata` / `FakeEmbeddingsEndpoint` rejects `usage_tokens`.

- [ ] **Step 4: Extend EmbeddingMetadata**

In `backend/embeddings/models.py`, change `EmbeddingMetadata` to:

```python
class EmbeddingMetadata(BaseModel):
    """Metadata attached to an embedding batch result."""

    model_name: str
    dimensions: int = Field(gt=0)
    provider: str
    created_at: datetime = Field(default_factory=utc_now)
    total_tokens: int | None = Field(default=None, ge=0)
```

- [ ] **Step 5: Capture usage in the OpenAI adapter**

In `backend/embeddings/adapters/openai_adapter.py`:

Change `embed()` (currently lines 80-102) to aggregate usage:

```python
    def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        """Embed request items while respecting batch-size and token budgets."""

        vectors: dict[str, list[float]] = {}
        total_tokens: int | None = None

        for batch in _iter_batches(
            request.items,
            batch_size=self._batch_size,
            token_limit=_MAX_INPUT_TOKENS,
        ):
            batch_vectors, batch_tokens = self._embed_batch(batch)
            for item in batch:
                vectors[item.id] = batch_vectors[item.id]
            if batch_tokens is not None:
                total_tokens = (total_tokens or 0) + batch_tokens

        return EmbeddingResult(
            request_id=request.request_id,
            vectors=vectors,
            metadata=EmbeddingMetadata(
                model_name=self._model_name,
                dimensions=self._dimensions,
                provider=_PROVIDER_NAME,
                total_tokens=total_tokens,
            ),
        )
```

Change `_embed_batch` (currently lines 104-113) to return the usage too:

```python
    def _embed_batch(
        self, items: Sequence[EmbeddingItem]
    ) -> tuple[dict[str, list[float]], int | None]:
        """Send one provider batch and parse vectors plus reported usage."""

        texts = [item.content for item in items]
        response = self._create_embeddings_with_retry(texts)
        vectors = _parse_embedding_response(
            response,
            items,
            expected_dimensions=self._dimensions,
        )
        return vectors, _extract_usage_tokens(response)
```

Add a module-level helper (near `_parse_embedding_response`):

```python
def _extract_usage_tokens(response: object) -> int | None:
    """Read usage.total_tokens from a provider response, if reported."""

    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    total_tokens = getattr(usage, "total_tokens", None)
    if isinstance(total_tokens, int) and total_tokens >= 0:
        return total_tokens
    return None
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/embeddings -m "not integration" -q`
Expected: PASS (the sentence-transformers and in-memory adapters are untouched — their `EmbeddingMetadata` simply defaults `total_tokens=None`, which Task 6 treats as "estimate").

- [ ] **Step 7: Commit**

```bash
git add backend/embeddings/models.py backend/embeddings/adapters/openai_adapter.py backend/tests/embeddings/test_models.py backend/tests/embeddings/test_openai_adapter.py
git commit -m "feat(embeddings): capture provider-reported token usage"
```

---

### Task 6: Usage Metrics + Structured Logging

**Files:**
- Create: `backend/embeddings/metrics.py`
- Modify: `backend/embeddings/service.py`
- Test: `backend/tests/embeddings/test_metrics.py` (create), `backend/tests/embeddings/test_service.py`

**Interfaces:**
- Consumes: `EmbeddingMetadata.total_tokens` (Task 5), cache hit/miss partition (Task 4).
- Produces: prometheus counters `embedding_requests_total{provider,model}`, `embedding_texts_total{provider,model,cache_result}`, `embedding_tokens_total{provider,model,knowledge_base_id,source}`; `estimate_tokens(content: str) -> int`; `TokenSource = Literal["reported", "estimated", "cached"]`; `record_embedding_usage(*, provider: str, model_name: str, knowledge_base_id: str | None, cache_hits: int, cache_misses: int, tokens: int, token_source: TokenSource) -> None`.

- [ ] **Step 1: Write the failing metrics-module tests**

Create `backend/tests/embeddings/test_metrics.py`:

```python
"""Tests for embeddings usage metrics."""

from __future__ import annotations

from prometheus_client import REGISTRY

from embeddings.metrics import estimate_tokens, record_embedding_usage


def _sample(name: str, labels: dict[str, str]) -> float:
    value = REGISTRY.get_sample_value(name, labels)
    return 0.0 if value is None else value


def test_estimate_tokens_rounds_up_and_floors_at_one() -> None:
    assert estimate_tokens("") == 1
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcde") == 2


def test_record_embedding_usage_increments_counters() -> None:
    labels = {"provider": "metrics-test", "model": "metrics-model-a"}
    token_labels = {
        **labels,
        "knowledge_base_id": "kb-metrics",
        "source": "reported",
    }
    requests_before = _sample("embedding_requests_total", labels)
    hits_before = _sample("embedding_texts_total", {**labels, "cache_result": "hit"})
    misses_before = _sample(
        "embedding_texts_total", {**labels, "cache_result": "miss"}
    )
    tokens_before = _sample("embedding_tokens_total", token_labels)

    record_embedding_usage(
        provider="metrics-test",
        model_name="metrics-model-a",
        knowledge_base_id="kb-metrics",
        cache_hits=2,
        cache_misses=3,
        tokens=42,
        token_source="reported",
    )

    assert _sample("embedding_requests_total", labels) - requests_before == 1.0
    assert (
        _sample("embedding_texts_total", {**labels, "cache_result": "hit"})
        - hits_before
        == 2.0
    )
    assert (
        _sample("embedding_texts_total", {**labels, "cache_result": "miss"})
        - misses_before
        == 3.0
    )
    assert _sample("embedding_tokens_total", token_labels) - tokens_before == 42.0


def test_record_embedding_usage_skips_empty_series() -> None:
    labels = {"provider": "metrics-test", "model": "metrics-model-zero"}

    record_embedding_usage(
        provider="metrics-test",
        model_name="metrics-model-zero",
        knowledge_base_id=None,
        cache_hits=0,
        cache_misses=0,
        tokens=0,
        token_source="cached",
    )

    assert _sample("embedding_requests_total", labels) == 1.0
    assert (
        REGISTRY.get_sample_value(
            "embedding_texts_total", {**labels, "cache_result": "hit"}
        )
        is None
    )
    assert (
        REGISTRY.get_sample_value(
            "embedding_tokens_total",
            {**labels, "knowledge_base_id": "none", "source": "cached"},
        )
        is None
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/embeddings/test_metrics.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'embeddings.metrics'`.

- [ ] **Step 3: Implement the metrics module**

Create `backend/embeddings/metrics.py` (same module-level counter pattern as `backend/api/middleware/metrics.py`; `prometheus-client` is already a core dependency; counters register on the default `REGISTRY`, which the API `/metrics` route serves today and BL-043 will expose from the worker — the only requirement here is to use the default registry, nothing BL-043-specific):

```python
"""Prometheus usage counters and token estimation for embeddings (BL-019)."""

from __future__ import annotations

import math
from typing import Literal

from prometheus_client import Counter

__all__ = [
    "TokenSource",
    "embedding_requests_total",
    "embedding_texts_total",
    "embedding_tokens_total",
    "estimate_tokens",
    "record_embedding_usage",
]

TokenSource = Literal["reported", "estimated", "cached"]

_CHARS_PER_TOKEN_ESTIMATE = 4

embedding_requests_total: Counter = Counter(
    "embedding_requests_total",
    "Total embed() calls served by the embeddings service.",
    ["provider", "model"],
)

embedding_texts_total: Counter = Counter(
    "embedding_texts_total",
    "Total texts submitted for embedding, split by cache result.",
    ["provider", "model", "cache_result"],
)

embedding_tokens_total: Counter = Counter(
    "embedding_tokens_total",
    "Embedding tokens consumed, provider-reported or estimated.",
    ["provider", "model", "knowledge_base_id", "source"],
)


def estimate_tokens(content: str) -> int:
    """Estimate token usage conservatively without a tokenizer dependency."""

    return max(1, math.ceil(len(content) / _CHARS_PER_TOKEN_ESTIMATE))


def record_embedding_usage(
    *,
    provider: str,
    model_name: str,
    knowledge_base_id: str | None,
    cache_hits: int,
    cache_misses: int,
    tokens: int,
    token_source: TokenSource,
) -> None:
    """Record one embed() call on the shared default Prometheus registry."""

    embedding_requests_total.labels(provider=provider, model=model_name).inc()
    if cache_hits > 0:
        embedding_texts_total.labels(
            provider=provider, model=model_name, cache_result="hit"
        ).inc(cache_hits)
    if cache_misses > 0:
        embedding_texts_total.labels(
            provider=provider, model=model_name, cache_result="miss"
        ).inc(cache_misses)
    if tokens > 0:
        embedding_tokens_total.labels(
            provider=provider,
            model=model_name,
            knowledge_base_id=knowledge_base_id or "none",
            source=token_source,
        ).inc(tokens)
```

Label-cardinality note (document in README, Task 8): `knowledge_base_id` is bounded by operator-created KBs; acceptable for v1, revisit if multi-tenant KB counts explode.

- [ ] **Step 4: Run metrics tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/embeddings/test_metrics.py -q`
Expected: PASS.

- [ ] **Step 5: Write the failing service-level usage tests**

Append to `backend/tests/embeddings/test_service.py`. Add imports:

```python
import logging

from prometheus_client import REGISTRY
```

Add a usage-reporting fake and the tests (each test uses a unique `model_name` so its label series starts at zero):

```python
class _UsageReportingEmbedder(EmbedderProtocol):
    """Embedder whose metadata carries provider-reported token usage."""

    def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        return EmbeddingResult(
            request_id=request.request_id,
            vectors={item.id: [0.1, 0.2] for item in request.items},
            metadata=EmbeddingMetadata(
                model_name="usage-model",
                dimensions=2,
                provider="usage-provider",
                total_tokens=42,
            ),
        )


def _sample_or_zero(name: str, labels: dict[str, str]) -> float:
    value = REGISTRY.get_sample_value(name, labels)
    return 0.0 if value is None else value


def test_embeddings_service_records_reported_token_usage() -> None:
    labels = {
        "provider": "usage-provider",
        "model": "usage-model",
        "knowledge_base_id": "kb-usage",
        "source": "reported",
    }
    before = _sample_or_zero("embedding_tokens_total", labels)
    service = create_embeddings_service(
        _UsageReportingEmbedder(), event_bus=InMemoryEventBus()
    )

    service.embed(
        EmbedRequest(
            knowledge_base_id="kb-usage",
            submissions=[EmbedSubmission(content_id="content-1", content="Alpha")],
        )
    )

    assert _sample_or_zero("embedding_tokens_total", labels) - before == 42.0


def test_embeddings_service_records_estimated_tokens_and_cache_results() -> None:
    hit_labels = {
        "provider": "in-memory",
        "model": "svc-usage-model",
        "cache_result": "hit",
    }
    miss_labels = {**hit_labels, "cache_result": "miss"}
    token_labels = {
        "provider": "in-memory",
        "model": "svc-usage-model",
        "knowledge_base_id": "none",
        "source": "estimated",
    }
    hits_before = _sample_or_zero("embedding_texts_total", hit_labels)
    misses_before = _sample_or_zero("embedding_texts_total", miss_labels)
    tokens_before = _sample_or_zero("embedding_tokens_total", token_labels)
    service = _cached_service(_CountingEmbedder(), InMemoryEventBus())
    request = EmbedRequest(
        model_name="svc-usage-model",
        submissions=[
            EmbedSubmission(content_id="content-1", content="Alpha beta!")
        ],
    )

    service.embed(request)
    service.embed(request)

    assert _sample_or_zero("embedding_texts_total", miss_labels) - misses_before == 1.0
    assert _sample_or_zero("embedding_texts_total", hit_labels) - hits_before == 1.0
    # "Alpha beta!" is 11 chars -> ceil(11 / 4) = 3 estimated tokens, misses only.
    assert _sample_or_zero("embedding_tokens_total", token_labels) - tokens_before == 3.0


def test_embeddings_service_logs_structured_usage_line(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = _cached_service(_CountingEmbedder(), InMemoryEventBus())
    request = EmbedRequest(
        knowledge_base_id="kb-log",
        submissions=[EmbedSubmission(content_id="content-1", content="Alpha")],
    )

    with caplog.at_level(logging.INFO, logger="embeddings.service"):
        service.embed(request)
        service.embed(request)

    usage_lines = [
        record.getMessage()
        for record in caplog.records
        if record.name == "embeddings.service"
        and record.getMessage().startswith("embedding usage:")
    ]
    assert len(usage_lines) == 2
    assert "cache_misses=1" in usage_lines[0]
    assert "token_source=estimated" in usage_lines[0]
    assert "cache_hits=1" in usage_lines[1]
    assert "token_source=cached" in usage_lines[1]
    assert "knowledge_base_id=kb-log" in usage_lines[1]
```

Note: `_UsageReportingEmbedder`'s InMemoryEmbedder-independent `model_name`/`provider` come from its own metadata; the model label for `_CountingEmbedder` tests is the request `model_name` because `InMemoryEmbedder` echoes it, and its provider is `"in-memory"`.

- [ ] **Step 6: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/embeddings/test_service.py -q`
Expected: the three new tests FAIL (no counters incremented, no log line); all others PASS.

- [ ] **Step 7: Wire usage recording into the service**

In `backend/embeddings/service.py`:

Add to the imports:

```python
import logging

from embeddings.metrics import TokenSource, estimate_tokens, record_embedding_usage
```

Add after the imports (before the class):

```python
logger = logging.getLogger(__name__)
```

In `embed()`, insert immediately before `return response`:

```python
        self._record_usage(
            request,
            result_metadata,
            provider=_usage_provider(result_metadata, text_items),
            model_name=model_name,
            cache_hits=len(cached_items),
            miss_submissions=miss_submissions,
        )
```

Add these methods/functions:

```python
    def _record_usage(
        self,
        request: EmbedRequest,
        result_metadata: EmbeddingMetadata | None,
        *,
        provider: str,
        model_name: str,
        cache_hits: int,
        miss_submissions: list[EmbedSubmission],
    ) -> None:
        """Record counters and a structured log line for one embed() call."""

        token_source: TokenSource
        if result_metadata is not None and result_metadata.total_tokens is not None:
            tokens = result_metadata.total_tokens
            token_source = "reported"
        elif miss_submissions:
            tokens = sum(
                estimate_tokens(submission.content)
                for submission in miss_submissions
            )
            token_source = "estimated"
        else:
            tokens = 0
            token_source = "cached"
        record_embedding_usage(
            provider=provider,
            model_name=model_name,
            knowledge_base_id=request.knowledge_base_id,
            cache_hits=cache_hits,
            cache_misses=len(miss_submissions),
            tokens=tokens,
            token_source=token_source,
        )
        logger.info(
            "embedding usage: provider=%s model=%s knowledge_base_id=%s "
            "texts=%d cache_hits=%d cache_misses=%d tokens=%d token_source=%s",
            provider,
            model_name,
            request.knowledge_base_id or "none",
            len(request.submissions),
            cache_hits,
            len(miss_submissions),
            tokens,
            token_source,
        )
```

And a module-level helper next to `_response_identity`:

```python
def _usage_provider(
    result_metadata: EmbeddingMetadata | None,
    text_items: list[EmbeddedItem],
) -> str:
    """Resolve the provider label for usage recording."""

    if result_metadata is not None:
        return result_metadata.provider
    return text_items[0].provider or "unknown"
```

- [ ] **Step 8: Run the embeddings suite**

Run: `.venv/bin/python -m pytest tests/embeddings -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/embeddings/metrics.py backend/embeddings/service.py backend/tests/embeddings/test_metrics.py backend/tests/embeddings/test_service.py
git commit -m "feat(embeddings): usage counters and structured usage logs"
```

---

### Task 7: Dependency Injection — API Gateway and Worker

**Files:**
- Modify: `backend/api/dependencies.py:1170-1173`
- Modify: `backend/agent/coordinator.py` (imports, after `build_embedder` ~line 819, `build_worker_dependencies` ~line 937, `__all__` ~line 244)
- Test: `backend/tests/api/test_dependencies.py`, `backend/tests/agent/test_coordinator.py`

**Interfaces:**
- Consumes: `create_embedding_cache`, `embedding_cache_namespace` (Task 3); `cache`/`cache_namespace` service params (Task 4).
- Produces: `agent.coordinator.build_embedding_cache(config: DomainConfig) -> tuple[EmbeddingCacheProtocol | None, str]`.

- [ ] **Step 1: Write the failing API DI tests**

Append to `backend/tests/api/test_dependencies.py`. Extend imports:

```python
from prometheus_client import REGISTRY

from embeddings.service_models import EmbedRequest, EmbedSubmission
```

Add tests (the file's autouse `clear_dependency_caches` fixture already clears `get_embedder`/`get_embeddings_service`, so each test builds a fresh service; unique `model_name` values isolate metric label series):

```python
def test_get_embeddings_service_uses_config_driven_cache(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    config = base_config.model_copy(
        update={"embeddings": EmbeddingsConfig(provider="local", model="di-probe")}
    )
    _install_config(monkeypatch, config)
    service = dependencies.get_embeddings_service()
    request = EmbedRequest(
        model_name="di-cache-model",
        submissions=[EmbedSubmission(content_id="content-1", content="DI probe")],
    )
    hit_labels = {
        "provider": "local",
        "model": "di-cache-model",
        "cache_result": "hit",
    }
    before = REGISTRY.get_sample_value("embedding_texts_total", hit_labels) or 0.0

    service.embed(request)
    service.embed(request)

    after = REGISTRY.get_sample_value("embedding_texts_total", hit_labels) or 0.0
    assert after - before == 1.0


def test_get_embeddings_service_honors_cache_disabled(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    config = base_config.model_copy(
        update={
            "embeddings": EmbeddingsConfig(
                provider="local", model="di-probe", cache_enabled=False
            )
        }
    )
    _install_config(monkeypatch, config)
    service = dependencies.get_embeddings_service()
    request = EmbedRequest(
        model_name="di-nocache-model",
        submissions=[EmbedSubmission(content_id="content-1", content="DI probe")],
    )
    miss_labels = {
        "provider": "local",
        "model": "di-nocache-model",
        "cache_result": "miss",
    }
    hit_labels = {**miss_labels, "cache_result": "hit"}
    misses_before = (
        REGISTRY.get_sample_value("embedding_texts_total", miss_labels) or 0.0
    )
    hits_before = REGISTRY.get_sample_value("embedding_texts_total", hit_labels) or 0.0

    service.embed(request)
    service.embed(request)

    misses_after = (
        REGISTRY.get_sample_value("embedding_texts_total", miss_labels) or 0.0
    )
    hits_after = REGISTRY.get_sample_value("embedding_texts_total", hit_labels) or 0.0
    assert misses_after - misses_before == 2.0
    assert hits_after - hits_before == 0.0
```

(Provider label is `"local"` in both: `get_embedder()` passes `provider` from config into `InMemoryEmbedder(provider=...)`, and the in-memory metadata echoes it. Model label is the request `model_name` because `InMemoryEmbedder` echoes it.)

- [ ] **Step 2: Write the failing worker DI tests**

Append to `backend/tests/agent/test_coordinator.py` (the file already imports `EmbeddingsConfig` from `config.schema` and defines `_base_config()`; add `from embeddings.adapters.cache_in_memory import InMemoryLruEmbeddingCache` to its imports):

```python
def test_build_embedding_cache_returns_cache_and_namespace() -> None:
    from agent.coordinator import build_embedding_cache

    config = _base_config().model_copy(
        update={
            "embeddings": EmbeddingsConfig(
                provider="local",
                model="worker-cache-model",
                dimensions=128,
            ),
        }
    )

    cache, namespace = build_embedding_cache(config)

    assert isinstance(cache, InMemoryLruEmbeddingCache)
    assert namespace == "local:worker-cache-model:128"


def test_build_embedding_cache_disabled_returns_none() -> None:
    from agent.coordinator import build_embedding_cache

    config = _base_config().model_copy(
        update={"embeddings": EmbeddingsConfig(cache_enabled=False)}
    )

    cache, namespace = build_embedding_cache(config)

    assert cache is None
    assert namespace == "sentence_transformers:all-MiniLM-L6-v2:384"
```

- [ ] **Step 3: Run tests to verify they fail**

Run:
```bash
DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/python -m pytest tests/api/test_dependencies.py -k "embeddings_service_uses_config_driven_cache or embeddings_service_honors_cache_disabled" -q
DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/python -m pytest tests/agent/test_coordinator.py -k build_embedding_cache -q
```
Expected: FAIL — no hits recorded (API), `ImportError: cannot import name 'build_embedding_cache'` (worker).

- [ ] **Step 4: Wire the API gateway**

In `backend/api/dependencies.py`, add to the embeddings imports (next to line 116-119):

```python
from embeddings.adapters.cache_in_memory import (
    create_embedding_cache,
    embedding_cache_namespace,
)
```

Replace `get_embeddings_service` (lines 1170-1173):

```python
@lru_cache(maxsize=1)
def get_embeddings_service() -> EmbeddingsServiceProtocol:
    """Return the embeddings service assembled from configured dependencies."""
    embeddings_config = get_domain_config().embeddings or EmbeddingsConfig()
    return create_embeddings_service(
        get_embedder(),
        event_bus=get_event_bus(),
        cache=create_embedding_cache(embeddings_config),
        cache_namespace=embedding_cache_namespace(embeddings_config),
    )
```

(`get_embeddings_service` is already registered in `CONFIG_CACHE_REGISTRY`, so hot-swap rebuilds the cache with the service — no registry change needed.)

- [ ] **Step 5: Wire the worker**

In `backend/agent/coordinator.py`:

Add to the embeddings imports (near lines 120-124):

```python
from embeddings.adapters.cache_in_memory import (
    create_embedding_cache,
    embedding_cache_namespace,
)
from embeddings.adapters.protocols import EmbeddingCacheProtocol
```

(If `EmbedderProtocol` is already imported from `embeddings.adapters.protocols`, merge `EmbeddingCacheProtocol` into that existing import instead of duplicating it.)

Add after `build_embedder` (~line 819):

```python
def build_embedding_cache(
    config: DomainConfig,
) -> tuple[EmbeddingCacheProtocol | None, str]:
    """Build the config-driven embedding cache and its key namespace."""

    embeddings_config = config.embeddings or EmbeddingsConfig()
    return (
        create_embedding_cache(embeddings_config),
        embedding_cache_namespace(embeddings_config),
    )
```

Add `"build_embedding_cache"` to `__all__` next to `"build_embedder"` (~line 244).

In `build_worker_dependencies()`, replace the `embeddings_service = create_embeddings_service(...)` call (~line 937):

```python
    embedding_cache, embedding_cache_ns = build_embedding_cache(config)
    embeddings_service = create_embeddings_service(
        embedder,
        event_bus=event_bus,
        graph_embedding_provider=(
            GnnGraphEmbeddingProvider(gnn_service)
            if config.capabilities.gnn
            else None
        ),
        cache=embedding_cache,
        cache_namespace=embedding_cache_ns,
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run:
```bash
DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/python -m pytest tests/api/test_dependencies.py tests/agent/test_coordinator.py -q
```
Expected: PASS — new tests green, no regressions.

- [ ] **Step 7: Live-stack verification (backend behavior change)**

Per CLAUDE.md, verify against the running stack. From the repo root:

```bash
make dev
```

Wait for services, then trigger an embed twice through the worker path (upload the same small document twice into a KB via the UI at `http://localhost:5173` or the API), and verify:

1. Worker logs (`docker compose -f docker-compose.dev.yaml logs chili-worker | grep "embedding usage"`) show `cache_misses=N` on the first run and `cache_hits>0 token_source=cached` (or reduced misses) on the re-run of identical content.
2. API metrics: `curl -s -H "Authorization: Bearer <service-role-token>" http://localhost:8000/metrics | grep embedding_` shows the `embedding_*` series after exercising an API-side embed (e.g., a RAG query). If only worker-side embedding was exercised, the API serves no embedding series yet — that is the documented BL-043 gap; the worker log line is the verification surface.

Then `make down`.

- [ ] **Step 8: Commit**

```bash
git add backend/api/dependencies.py backend/agent/coordinator.py backend/tests/api/test_dependencies.py backend/tests/agent/test_coordinator.py
git commit -m "feat(embeddings): wire config-driven cache into api and worker"
```

---

### Task 8: Documentation + Final Gates

**Files:**
- Modify: `backend/embeddings/README.md`
- Modify: `backend/README.md:57`
- Modify: `docs/architecture.md:280-286`

- [ ] **Step 1: Update the embeddings README**

In `backend/embeddings/README.md`, insert the following two sections between the existing `## Graph Embeddings` and `## Live Tests` sections:

```markdown
## Caching (BL-019)

`EmbeddingsService` accepts an optional `EmbeddingCacheProtocol`
(`embeddings.adapters.protocols`) so repeated identical texts skip the
provider. v1 ships one adapter: `InMemoryLruEmbeddingCache`
(`embeddings.adapters.cache_in_memory`) — a thread-safe, per-process LRU.

- Config: `EmbeddingsConfig.cache_enabled` (default `true`) and
  `EmbeddingsConfig.cache_max_entries` (default `4096`). Defaults apply, so
  domain packs need no edits.
- Cache key: SHA-256 over `namespace + model_name + content`, where
  `namespace = "{provider}:{model}:{dimensions}"` from `EmbeddingsConfig` —
  a model or dimension change can never serve a stale vector.
- Scope: per-process by design. The embedder is a per-process singleton
  (API `@lru_cache`, worker `build_worker_dependencies`), so hits accrue
  where repeat embeds happen. A Redis/durable cache is BL-045 roadmap and
  would arrive as another `EmbeddingCacheProtocol` adapter; reusing the
  `events` module's Redis client is off-limits (protocol-only dependency).
- Graph-channel requests always cover every submission, cached or not.

## Cost & Usage Tracking (BL-019)

Each `embed()` call records Prometheus counters (`embeddings.metrics`,
default registry — served by the API `/metrics` route; worker-process
exposure lands with BL-043) and one structured log line
(`embedding usage: provider=... model=... knowledge_base_id=... texts=...
cache_hits=... cache_misses=... tokens=... token_source=...`).

| Metric | Labels | Meaning |
| --- | --- | --- |
| `embedding_requests_total` | provider, model | embed() calls |
| `embedding_texts_total` | provider, model, cache_result | texts by hit/miss |
| `embedding_tokens_total` | provider, model, knowledge_base_id, source | tokens spent |

Token `source` is `reported` when the provider returns usage (OpenAI
`usage.total_tokens`, summed across batches into
`EmbeddingMetadata.total_tokens`) and `estimated` (chars/4, misses only)
for local/sentence-transformers. Fully cached calls spend zero tokens.
`knowledge_base_id` label cardinality is bounded by operator-created KBs;
revisit before high-tenancy deployments. A durable per-request usage
ledger is BL-045, not this module.
```

- [ ] **Step 2: Update backend/README.md**

Change line 57 from:

```
├── embeddings/      # Abstract embedder protocol + adapters (OpenAI, sentence-transformers)
```

to:

```
├── embeddings/      # Embedder protocol + adapters (OpenAI, sentence-transformers), LRU cache, usage metrics
```

- [ ] **Step 3: Update docs/architecture.md**

Change the embeddings tree entry (lines 280-286) from:

```
├── embeddings/                 # Embedding generation
│   ├── __init__.py
│   ├── service.py, service_models.py, protocols.py, models.py, exceptions.py
│   └── adapters/
│       ├── in_memory.py
│       ├── openai_adapter.py
│       └── sentence_transformers_adapter.py
```

to:

```
├── embeddings/                 # Embedding generation
│   ├── __init__.py
│   ├── service.py, service_models.py, protocols.py, models.py, exceptions.py
│   ├── metrics.py              # Prometheus usage counters + token estimation (BL-019)
│   └── adapters/
│       ├── in_memory.py
│       ├── cache_in_memory.py  # Per-process LRU embedding cache (BL-019)
│       ├── openai_adapter.py
│       └── sentence_transformers_adapter.py
```

- [ ] **Step 4: Run the story gates**

From `/home/rdhagan92/chiliAI/backend`:

```bash
.venv/bin/python -m pytest tests/embeddings tests/vectorstore --cov=embeddings --cov=vectorstore --cov-report=term-missing -q
```
Expected: PASS; coverage ≥ 85% for both `embeddings/` and `vectorstore/` packages.

```bash
.venv/bin/pyright
```
Expected: `0 errors, 0 warnings, 0 informations` (bare pyright is the real gate — includes cover `embeddings` and `tests/embeddings`).

```bash
.venv/bin/ruff check --no-cache .
```
Expected: `All checks passed!`

```bash
DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/python -m pytest -q
```
Expected: full backend suite PASS (integration-marked tests skip without their extras/services).

From `/home/rdhagan92/chiliAI/chili_app`:

```bash
npm run lint && npm run build && npm run test:run
```
Expected: clean (only generated contract files changed on the frontend).

- [ ] **Step 5: Contract drift check**

From the repo root, re-run the export and confirm zero diff (proves Task 1's regen is current):

```bash
PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json
git diff --stat chili_app/openapi.json
```
Expected: no output from `git diff` (no drift).

- [ ] **Step 6: Commit**

```bash
git add backend/embeddings/README.md backend/README.md docs/architecture.md
git commit -m "docs(embeddings): document cache and usage tracking (BL-019)"
```

---

## Implementation Order Notes

1. Tasks are strictly ordered: config (1) → models (2) → cache adapter (3) → service cache (4) → provider usage (5) → metrics (6) → DI (7) → docs/gates (8). Task 6 edits the same `service.py` that Task 4 rewrote — do not reorder.
2. Do not add a Redis cache adapter, object-store persistence, model routing, or new architecture guard tests — BL-045 scope fence.
3. The existing `tests/embeddings/test_architecture.py` guard forbids `embeddings` importing `analytics`/`agent`/`api`/`graph`/`vectorstore`. Nothing in this plan does (prometheus_client and config.schema are both already sanctioned imports); if it goes red, you imported something wrong — fix the import, not the guard.
4. Metric assertions must be delta-based (counters are process-global) and use test-unique `model` label values.
5. `.github/copilot-instructions.md` and `CLAUDE.md` need no edits: no new commands, boundaries, or workflows — verify this claim while doing Task 8 and update only if you find a real contradiction.
