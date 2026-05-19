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
