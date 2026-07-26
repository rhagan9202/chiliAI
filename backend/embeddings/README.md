# Embeddings

`embeddings` owns synchronous text embedding generation and multi-channel
embedding artifacts.

## Boundaries

Application code depends on `EmbeddingsServiceProtocol` from
`embeddings.protocols`. Text provider adapters implement `EmbedderProtocol`.
Graph embeddings enter through `GraphEmbeddingProviderProtocol`; `embeddings`
does not import `analytics`, `graph`, `vectorstore`, `api`, or `agent`.

Provider SDK imports are adapter-local:

- `openai` only in provider adapters and tests.
- `sentence_transformers` only in its provider adapter and tests.

## Channels

1.0 supports:

- `text`: semantic embeddings for RAG, semantic search, and citations.
- `graph`: GNN/node embeddings for graph similarity and clustering workflows.

Text and graph vectors are separate records. They may have different dimensions.
RAG query embedding and retrieval use the `text` channel.

## Graph Embeddings

Graph embeddings are optional. When requested, `EmbeddingsService` calls a
configured `GraphEmbeddingProviderProtocol`.

Missing graph vectors are omitted by default and reported in `graph_status`.
Set `require_graph_embeddings=True` on a request to make missing or malformed
graph vectors fail the request.

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
default registry — served by the API `/metrics` route and by the worker
health server's `/metrics` on port 8001 (BL-043); each process exposes
only its own registry) and one structured log line
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

## Live Tests

OpenAI smoke:

```bash
OPENAI_API_KEY=... uv run --project backend pytest backend/tests/embeddings/test_openai_adapter.py -m integration -v
```

Sentence-transformers local smoke:

```bash
SENTENCE_TRANSFORMERS_SMOKE_MODEL=all-MiniLM-L6-v2 uv run --project backend pytest backend/tests/embeddings/test_sentence_transformers_adapter.py -m integration -v
```

Normal CI does not require provider credentials or model downloads.
