# conversations backlog

> **Scope:** Durable RAG chat persistence (`backend/conversations/`): `Conversation`/`ConversationMessage` models, the `ConversationRepository` protocol with in-memory and Postgres adapters, and `ConversationService`, which backs the `/chat/conversations` create/read/append routes.
> **Story format and rules:** see [design spec §5](../superpowers/specs/2026-05-24-complete-backlog-design.md#5-story-format).

---

## Story conversations.06: Guard the conversation read-modify-write against concurrent turns

**ID:** conversations.06
**Status:** done
**Prerequisites:** []
**Unblocks:** []
**Estimated size:** S
**Done:** `save` compare-and-sets on `updated_at` in both adapters and raises `ConversationConcurrentModificationError` (a `ConcurrentModificationError` subclass, the marker's second subscriber after alerts) on a lost race. `ConversationService.append_messages` retries that error up to `MAX_APPEND_ATTEMPTS` rather than surfacing it, since appending is a pure merge — both turns belong in the final list regardless of order — so the resolution is re-read and re-apply, not a caller-visible 409.

**As an** analyst in a RAG chat,
**I need** two turns landing at once to both be kept,
**so that** a message I sent does not silently vanish.

### Current State
- Sprint 2026-35 Task 13 made `ConversationService` own `updated_at` so both adapters agree and list ordering reflects real activity rather than creation time.
- It did not close the surrounding race. `append_messages` is an unguarded `get -> model_copy -> save`, and `PostgresConversationRepository.save` upserts with `ON CONFLICT ... SET messages = EXCLUDED.messages` — a full overwrite. Two concurrent turns on the same conversation both read the same message list, and the second write discards the first.
- This is the same compare-and-set shape the sprint applied to alerts (`monitoring/adapters/postgres.py`) and to cases (`cases/adapters/postgres.py`, plus a `threading.Lock` on the in-memory adapter so both adapters agree). Conversations is the one race the sprint touched and left open.
- Related: `monitoring.22` covers deciding how a lost write race is signalled to callers. Whatever that story settles should apply here too, rather than adding a fourth answer.
- Found by the sprint 2026-35 whole-branch review.

### Acceptance Criteria
- [x] A concurrent append cannot silently discard another turn's messages.
- [x] Both adapters implement the same guard, including the in-memory one.
- [x] Signalling follows whatever `monitoring.22` settles rather than introducing another lost-race contract.
- [x] A barrier-synchronised test demonstrates the loss against the unguarded code first.

### Verification
- Two-thread test through `ConversationService.append_messages` asserting both turns survive, run against both adapters.

### Code touch points
- `backend/conversations/service.py` (modify — `append_messages`)
- `backend/conversations/adapters/postgres.py` (modify — guard the upsert)
- `backend/conversations/adapters/in_memory.py` (modify — matching guard)
