# conversations

Durable **RAG chat conversation** persistence (BL-012).

Chat conversations and their message history (including assistant-message
citations) are persisted across the API and worker containers. This module
replaces the previous in-memory-only, seeded `ApiState` conversation store.

## Layout

| File | Responsibility |
|------|----------------|
| `models.py` | `Conversation`, `ConversationMessage`, `ConversationCitation` domain models. |
| `adapters/protocols.py` | `ConversationRepository` protocol — `create / get / save`. |
| `adapters/in_memory.py` | `InMemoryConversationRepository` (dict keyed by `conversation_id`) for tests/dev. |
| `adapters/postgres.py` | `PostgresConversationRepository` over `database.ConnectionProvider` (psycopg-free); jsonb `messages`; idempotent `create` (`ON CONFLICT DO NOTHING`) + upserting `save`. |
| `service.py` | `ConversationService` — `create` (title default), `get`, `append_messages`. |
| `exceptions.py` | `ConversationError`, `ConversationPersistenceError`, `ConversationNotFoundError`. |

## Contract

```python
def create(self, conversation: Conversation) -> Conversation: ...   # idempotent on id
def get(self, conversation_id: str) -> Conversation | None: ...
def save(self, conversation: Conversation) -> Conversation: ...      # upsert (append messages)
```

## Persistence

The `conversations` table is created by Alembic migration
`database/migrations/versions/0005_conversations.py` (`down_revision =
0004_record_submissions`), with `PRIMARY KEY (conversation_id)` and an
`ix_conversations_kb` index. Backend selection mirrors `cases`/`policy`:
`get_conversation_repository` (`api/dependencies.py`) returns the in-memory
adapter when no connection provider is configured, otherwise the Postgres
adapter.

## API surface

Routed by `api/routers/rag.py` / `api/dependencies.py`:

- `POST /chat/conversations` (analyst) — create a conversation.
- `GET /chat/conversations/{id}` (viewer) — read the conversation + message history.
- `POST /chat/conversations/{id}/messages` (analyst) — append a user message and
  the generated assistant reply (non-streaming) or stream SSE token chunks with
  `?stream=true`.

The API layer (`api/_conversation_payloads.py`) adapts these domain models to
the frontend `Chat*` contracts and builds the user/assistant turn from a RAG
answer, keeping this module contract-agnostic.

## Tests

- `tests/conversations/test_in_memory_store.py` — repository round-trip, idempotency, citations.
- `tests/conversations/test_postgres_store.py` — `@pytest.mark.integration` (skipped without `DATABASE_URL`).
- `tests/conversations/test_service.py` — service create/append behavior.
- `tests/api/test_chat_router.py`, `tests/api/test_read_model_routers.py` — durable chat routes.
