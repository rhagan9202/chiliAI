# Module: llm

**Verified against codebase:** 2026-05-20
**Source:** `backend/llm/`

## Purpose

LLM client abstraction. Provides text completion (single-shot and streaming) for entity extraction during ingestion and answer generation during RAG. Never imported directly in business logic — only via `LlmServiceProtocol`.

---

## Service Protocol (`llm/protocols.py`)

```python
class LlmServiceProtocol(Protocol):
    def generate(self, request: GenerateRequest) -> CompletionResponse: ...

    def generate_stream(self, request: GenerateRequest) -> AsyncIterator[str]:
        """Stream completion chunks. Not all adapters implement native streaming;
        fallback yields a single one-shot chunk."""
```

---

## Service Models (`llm/service_models.py`)

Last verified: 2026-05-20

```python
PromptVariableValue = str | int | float | bool

class ChatMessageInput(BaseModel):
    role: MessageRole    # from llm/models.py
    content: str         # non-empty; enforced by model_validator

class PromptTemplate(BaseModel):
    system_prompt: str | None = None
    user_prompt: str                         # non-empty; enforced by model_validator
    variables: dict[str, PromptVariableValue] = {}

class GenerateRequest(BaseModel):
    knowledge_base_id: str | None = None
    model_name: str = "in-memory-test-model"
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=256, gt=0)
    messages: list[ChatMessageInput] = []
    prompt_template: PromptTemplate | None = None
    # Validation: messages or prompt_template must be provided

class CompletionResponse(BaseModel):
    request_id: str
    completion: str
    provider: str
    model_name: str
```

---

## Adapters

| Backend | File | Config | Optional extra |
|---------|------|--------|---------------|
| In-memory (deterministic stub) | `adapters/in_memory.py` | `LlmConfig.provider = "local"` | None |
| OpenAI | `adapters/openai_adapter.py` | `provider = "openai"`, `api_key_env_var` | `[openai]` |
| Anthropic | `adapters/anthropic_adapter.py` | `provider = "anthropic"`, `api_key_env_var` | `[anthropic]` |

Inner adapter protocol: `adapters/protocols.py`.

---

## Module Dependencies

- `config/schema.py` — `LlmConfig`
- Optional: `openai`, `anthropic`

---

## Tests

Location: `backend/tests/llm/`
