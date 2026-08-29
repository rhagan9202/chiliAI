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
| `adapters/postgres.py` | `PostgresConversationRepository` over `database.ConnectionProvider` (psycopg-free); jsonb `messages`; idempotent `create` (`ON CONFLICT DO NOTHING`) + CAS-guarded `save`. |
| `service.py` | `ConversationService` — `create` (title default), `get`, `append_messages` (owns `updated_at`, retries the guarded write on a lost race; see below). |
| `exceptions.py` | `ConversationError`, `ConversationPersistenceError`, `ConversationNotFoundError`, `ConversationConcurrentModificationError`. |

## Contract

```python
def create(self, conversation: Conversation) -> Conversation: ...   # idempotent on id
def get(self, conversation_id: str) -> Conversation | None: ...
def save(self, conversation: Conversation, *, expected_updated_at: datetime) -> Conversation: ...
```

`save` is a guarded update, not an upsert: it only persists `conversation` if
the stored row's `updated_at` still equals `expected_updated_at` (the value
the caller last read). `ConversationService.append_messages` owns the new
`updated_at` timestamp (so `list_by_kb`'s "most recently updated first"
ordering, and the `/chat/conversations` docs that promise it, hold under
every adapter, not just the in-memory one that most tests exercise) and
passes the value it read as `expected_updated_at`.

## Concurrency: guarding the append read-modify-write (BL-012-06)

`append_messages` is a `get -> model_copy -> save` read-modify-write. Before
this task, `save` was a full overwrite in both adapters (`ON CONFLICT ... SET
messages = EXCLUDED.messages` in Postgres, a plain dict assignment in
memory), so two turns landing at once both read the same message list and
the second `save` silently discarded the first — the analyst whose message
vanished still got a 200, with no exception raised anywhere to say so.

This follows the lost-write-race contract established in
`backend/monitoring/README.md` (monitoring.22) and mirrored from `cases`:

- `save` compare-and-sets on `updated_at`. Postgres guards the `UPDATE`'s
  `WHERE` clause on it (`adapters/postgres.py`); the in-memory adapter has no
  such guarantee across its separate read/compare/write steps, so it holds a
  `threading.Lock` across all three (`adapters/in_memory.py`, mirroring
  `InMemoryCaseRepository.update`).
- A lost race raises `ConversationConcurrentModificationError`, which
  inherits from both `ConversationError` (module-internal code keeps
  catching it the same way as every other conversations exception) and
  `shared.exceptions.ConcurrentModificationError` (the cross-module marker a
  caller can catch without importing this module's exceptions — this module
  is the marker's second subscriber, after `monitoring`'s
  `AlertConcurrentModificationError`). A missing row raises
  `ConversationNotFoundError` instead, same as `create`/`get`.
- **`cases` and `monitoring` stop there and let the exception propagate to
  the caller** (`monitoring` maps it to a 409 or a per-row batch skip at the
  gateway; `cases` has not yet been wired to a gateway mapping at all).
  `conversations` makes a different, deliberate choice: `append_messages`
  **retries internally** on `ConversationConcurrentModificationError` — it
  re-reads the conversation, re-applies the same messages on top of the
  fresh state, and re-saves, up to `_MAX_APPEND_ATTEMPTS` (10) times. This is
  safe specifically *because* appending is a pure merge: unlike a case
  update (arbitrary field changes) or an alert status transition (order- and
  lifecycle-sensitive), two concurrent turns have no legitimate reason not
  to both land, in either order. A caller-visible 409 would just make the
  analyst's client retry the same no-conflict operation, so the service does
  it for them. The retry budget exists so a pathologically hot conversation
  fails loudly (`ConversationConcurrentModificationError`, still mapped to
  `HTTPException(409)` in `api/dependencies.py`'s `get_chat_message_payload`)
  instead of spinning forever; this is expected to be reached only under
  sustained, unusual contention on a single conversation, not in the normal
  two-turns-race case the tests exercise.

Adapter parity is proven directly, not just through the service's retry
loop: `tests/conversations/test_in_memory_store.py` and
`tests/conversations/test_postgres_store.py` each have a sequential
missing-row test, a sequential stale-snapshot test, and a genuinely
concurrent (`threading.Barrier`-synchronized) test with a **deliberately
widened** compare-to-write window — a slow-writing dict wrapper in memory,
real concurrent connections against Postgres — so the guard is proven under
real overlap rather than lucky GIL scheduling.

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
answer, keeping this module contract-agnostic. `ChatMessageCreateRequest.filters`
is a flat scalar metadata dict (`str | int | float | bool` values only); the
chat dependency forwards it unchanged to `RagQueryRequest.filters`.

`get_chat_message_payload` (`api/dependencies.py`) maps a
`ConversationConcurrentModificationError` that survives `append_messages`'
internal retries to `HTTPException(409)` — see "Concurrency" above.

## Tests

- `tests/conversations/test_in_memory_store.py` — repository round-trip, idempotency,
  citations, and the `save` guard: `test_save_missing_raises`,
  `test_save_raises_when_the_row_changed_concurrently` (sequential CAS
  mismatch), `test_save_is_atomic_under_a_widened_compare_and_write_window`
  (real threads, deliberately widened compare-to-write window).
- `tests/conversations/test_postgres_store.py` — `@pytest.mark.integration` (skipped
  without `DATABASE_URL`); the same round-trip/idempotency coverage plus the
  Postgres-adapter mirrors of the `save` guard tests above, including
  `test_concurrent_append_does_not_silently_drop_the_other_turn` (real
  concurrent connections, `threading.Barrier`-synchronized).
- `tests/conversations/test_concurrent_append.py` — `test_two_concurrent_turns_both_survive`,
  parametrized over both adapters (the Postgres case is `@pytest.mark.integration`):
  the service-level reproduction of the lost-write race (BL-012-06), proving
  `append_messages` closes it end to end rather than just proving the
  repository-level guard exists in isolation.
- `tests/conversations/test_service.py` — service create/append behavior, including
  `test_appending_messages_advances_updated_at_in_every_adapter` (`@pytest.mark.integration`,
  needs `DATABASE_URL`), which asserts `updated_at` parity across the in-memory and
  Postgres repositories.
- `tests/api/test_chat_router.py`, `tests/api/test_read_model_routers.py` — durable chat routes.
