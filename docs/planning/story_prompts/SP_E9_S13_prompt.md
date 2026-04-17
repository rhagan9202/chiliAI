# Story E9-S13: RAG Chat page

## Story
As an analyst, I want a RAG Chat page where I can ask questions and receive answers with citations.

## Acceptance Criteria
1. `src/pages/RagChat.tsx` renders chat UI with input and response area.
2. KB selector dropdown.
3. Submit calls RAG chat endpoint, displays streaming response.
4. Citations as clickable links to source/entity in Investigation Workbench.
5. Conversation history maintained in client state.
6. Loading indicator.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | L    | E9-S03, E5-S05, E6-S06 |

## Target Files
- `chili_app/src/pages/RagChat.tsx` — replace placeholder with full chat page
- `chili_app/src/components/chat/ChatContainer.tsx` — main chat layout (messages + input area)
- `chili_app/src/components/chat/ChatContainer.module.css` — chat layout styles
- `chili_app/src/components/chat/MessageList.tsx` — scrollable message list
- `chili_app/src/components/chat/MessageList.module.css` — message list styles
- `chili_app/src/components/chat/ChatMessage.tsx` — individual message bubble (user or assistant)
- `chili_app/src/components/chat/ChatMessage.module.css` — message styles
- `chili_app/src/components/chat/ChatInput.tsx` — text input with submit button
- `chili_app/src/components/chat/ChatInput.module.css` — input styles
- `chili_app/src/components/chat/KbSelector.tsx` — knowledge base selector dropdown
- `chili_app/src/components/chat/Citation.tsx` — clickable citation component linking to Investigation Workbench
- `chili_app/src/components/chat/StreamingIndicator.tsx` — loading/streaming indicator
- `chili_app/src/hooks/useRagChat.ts` — hook for sending chat queries and handling streaming responses
- `chili_app/src/hooks/useChatHistory.ts` — hook for managing conversation history in client state
- `chili_app/src/stores/chatStore.ts` — Zustand store for chat state (messages, active KB, streaming status)
- `chili_app/src/types/chat.ts` — TypeScript types for chat messages, citations, streaming events

## Reference Files to Read First
- `chili_app/src/pages/RagChat.tsx` — current placeholder (from E9-S01)
- `chili_app/src/hooks/useKnowledgeBases.ts` — KB list hook for selector (from E9-S03)
- `chili_app/src/stores/appStore.ts` — Zustand pattern reference (from E9-S04)
- `chili_app/src/lib/queryClient.ts` — query client (from E9-S03)
- `chili_app/src/lib/apiClient.ts` — API client (from E9-S03)
- `backend/rag/models.py` — RAG domain models for type reference
- `backend/shared/types.py` — shared types
- `docs/architecture.md` — §8 for RAG Chat page description

## Architectural Constraints
- React 19, TypeScript strict mode (`noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`)
- Functional components with hooks only
- TanStack Query for server state, Zustand for client state, React Router v7 for routing
- No business logic in components — delegate to hooks and services
- Keep builds and lint clean: `npm run build && npm run lint`
- Streaming responses: use `fetch` with `ReadableStream` / `response.body.getReader()` for server-sent streaming
- Chat history maintained in Zustand store (`chatStore`) — not in TanStack Query cache
- KB selector fetches available KBs via TanStack Query (`useKnowledgeBases` from E9-S03)
- Citations must be clickable links that navigate to `/investigation?entity={entityId}` using React Router
- Message list should auto-scroll to bottom on new messages
- Chat input should support Enter to send, Shift+Enter for newline
- Loading indicator should show during streaming (pulsing dots or similar)
- Messages should distinguish user vs assistant with different styles (left/right alignment or color)
- Conversation history persists within the session (Zustand) — no backend persistence
- Each message from the assistant may contain zero or more citations embedded in the response

## What NOT To Do
- Do NOT implement the backend RAG chat endpoint — that is E5-S05 / E6-S06
- Do NOT add conversation persistence to backend or localStorage — session-only via Zustand
- Do NOT add markdown rendering for responses — plain text is sufficient (can be enhanced later)
- Do NOT add file attachment or image support in chat
- Do NOT add multiple concurrent conversations or conversation tabs
- Do NOT add copy-to-clipboard for messages
- Do NOT add message editing or deletion
- Do NOT implement backend streaming — only consume the stream on the frontend

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] `npm run build` passes (TypeScript compiles)
- [ ] `npm run lint` passes (ESLint clean)
- [ ] Components render without errors
- [ ] Chat UI renders with input area and message list
- [ ] KB selector dropdown populates with available knowledge bases
- [ ] Submitting a question sends to chat endpoint and renders streaming response
- [ ] Citations render as clickable links to Investigation Workbench
- [ ] Conversation history maintained across messages within session
- [ ] Loading indicator shows during streaming
- [ ] Auto-scroll to newest message works
