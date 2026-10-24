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

---

## Story conversations.07: BL-060 — Streaming chat persists its transcript

**ID:** conversations.07
**Status:** planned
**Prerequisites:** [rag.18]
**Unblocks:** []
**Estimated size:** M
**Spec:** docs/superpowers/specs/2026-08-27-audit-burndown-design.md

### Current State
- BL-060, 3 SP in the burn-down spec.
- Source: the 2026-08-25 full-codebase audit, burn-down design `docs/superpowers/specs/2026-08-27-audit-burndown-design.md` (approved 2026-08-27). Planned for sprint 2026-36, moved to 2026-37 when 2026-36 became the stabilisation sprint; no 2026-37 sprint file exists and no commit references this story as of 2026-10-24.
- The spec states findings and grouping only; it does not give a user story, so none is invented here. Acceptance criteria below are the spec's per-finding and per-story Definition of Done.
- `POST /chat/conversations/{id}/messages?stream=true` (`backend/api/routers/rag.py`) returns a `StreamingResponse` over `_stream_sse`, which receives only the RAG service and never calls `append_messages`; the non-streaming branch persists both turns. A streamed exchange is lost on reload.
- Spec sequencing: lands after BL-059 (`rag.18`) — both edit `rag/` and `api/routers/rag.py`.

### Acceptance Criteria
- [ ] The streaming branch durably stores the user message and assistant reply, matching the non-streaming branch; `GET /chat/conversations/{id}` returns them after a streamed turn.
- [ ] Each cited finding no longer reproduces its failure scenario, verified against a running stack (`make dev`), not only a green suite.
- [ ] Each fix's test was watched failing against the real defect before the fix landed (spec § Definition of done).

### Code touch points
- `backend/api/routers/rag.py` (`_stream_sse` and the streaming branch)
- `backend/conversations/service.py` (read — `append_messages`)
