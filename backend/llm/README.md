# LLM Module

`llm/` provides a vendor-agnostic LLM client abstraction for the chiliAI platform. Application code depends only on `LlmClientProtocol` from `llm.protocols`; concrete provider SDKs are confined to `llm/adapters/`.

## Adapters

| Provider value | Adapter class | Notes |
|----------------|---------------|-------|
| `"local"` | `InMemoryLlmClient` | Deterministic stub; returns configured canned responses. Used in tests and local runs with no API key. |
| `"openai"` | `OpenAiLlmClient` | OpenAI Chat Completions API. Requires `[openai]` extra and a key in the env var named by `LlmConfig.api_key_env_var`. |
| `"anthropic"` | `AnthropicLlmClient` | Anthropic Messages API. Requires `[anthropic]` extra and a key in the env var named by `LlmConfig.api_key_env_var`. |
| `"ollama"` | `OllamaLlmClient` | Self-hosted Ollama server via its OpenAI-compatible `/v1/chat/completions` endpoint. No API key required; point `LlmConfig.base_url` at the Ollama host (default `http://localhost:11434`). |

## Configuration

```yaml
llm:
  provider: ollama          # local | openai | anthropic | ollama
  model: llama3.2           # model tag served by Ollama (or model name for cloud providers)
  base_url: http://localhost:11434   # Ollama only; ignored by cloud adapters
  api_key_env_var: OPENAI_API_KEY   # ignored when provider=ollama or local
```

## FallbackLlmClient

`FallbackLlmClient` is a decorator that wraps a primary `LlmClientProtocol` with one or more fallback clients. If the primary raises an exception the decorator tries each fallback in order and re-raises only after all are exhausted. Configure a fallback chain in `LlmConfig.fallback`:

```yaml
llm:
  provider: ollama
  model: llama3.2
  base_url: http://ollama:11434
  fallback:
    - provider: openai
      model: gpt-4o-mini
      api_key_env_var: OPENAI_API_KEY
```

The factory in `api/dependencies.py` reads `LlmConfig.fallback` and wraps the primary adapter automatically. See [`docs/superpowers/specs/2026-05-22-ingestion-pipeline-e2e-demo-design.md`](../../docs/superpowers/specs/2026-05-22-ingestion-pipeline-e2e-demo-design.md) for the demo-stack wiring.

## Usage in Ingestion

`LlmDocumentExtractor` (in `ingestion/extractor.py`) uses an injected `LlmClientProtocol` to drive schema-guided entity and relationship extraction. If no LLM client is configured the ingestion service falls back to `PatternDocumentExtractor`. See `backend/ingestion/README.md` for details.
