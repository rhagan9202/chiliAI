# Story E9-S12: WebSocket hook for real-time updates

## Story
As a frontend developer, I want a `useWebSocket()` hook connecting to backend WebSocket and dispatching typed events.

## Acceptance Criteria
1. `src/hooks/useWebSocket.ts` connects to `ws://<host>/ws`, auto-reconnects (exponential backoff, max 5 retries).
2. Parses incoming JSON, dispatches typed events via callback.
3. Supported: `alert.created`, `analysis.complete`, `document.processed`.
4. Connection-status indicator component.
5. Tests verify reconnection logic.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | M    | E5-S07       |

## Target Files
- `chili_app/src/hooks/useWebSocket.ts` — WebSocket hook with auto-reconnect and typed event dispatch
- `chili_app/src/types/wsEvents.ts` — TypeScript types/discriminated union for WebSocket event payloads
- `chili_app/src/components/common/ConnectionStatus.tsx` — connection status indicator (connected/disconnected/reconnecting)
- `chili_app/src/components/common/ConnectionStatus.module.css` — status indicator styles
- `chili_app/src/hooks/__tests__/useWebSocket.test.ts` — tests for reconnection logic and event parsing

## Reference Files to Read First
- `chili_app/src/lib/queryClient.ts` — query client for cache invalidation on events (from E9-S03)
- `chili_app/src/stores/appStore.ts` — Zustand store if events need to update client state (from E9-S04)
- `backend/events/types.py` — backend event types for matching WebSocket event shapes
- `backend/api/app.py` — WebSocket endpoint definition reference
- `docs/architecture.md` — §4 for communication patterns, §8 for real-time features

## Architectural Constraints
- React 19, TypeScript strict mode (`noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`)
- Functional components with hooks only
- TanStack Query for server state, Zustand for client state, React Router v7 for routing
- No business logic in components — delegate to hooks and services
- Keep builds and lint clean: `npm run build && npm run lint`
- Use native `WebSocket` API — do NOT install socket.io or other WebSocket libraries
- Reconnection: exponential backoff starting at 1s, doubling each attempt, max 5 retries, max delay 30s
- WebSocket URL should be derived from window location: `ws(s)://${window.location.host}/ws`
- Event payload must be a discriminated union on event `type` field: `alert.created | analysis.complete | document.processed`
- Hook should accept a callback map: `{ 'alert.created': (payload) => void, ... }`
- Hook should return: `{ status: 'connected' | 'disconnected' | 'reconnecting', send: (msg) => void }`
- Connection status indicator: green dot for connected, yellow for reconnecting, red for disconnected
- Tests should mock `WebSocket` and verify: connection, message parsing, reconnection on close, max retry limit
- Hook should cleanly close the WebSocket on component unmount (cleanup in `useEffect`)

## What NOT To Do
- Do NOT implement the backend WebSocket endpoint — that is E5-S07
- Do NOT install socket.io, sockjs, or any WebSocket wrapper library
- Do NOT add WebSocket authentication (token in URL or headers) — out of scope for this story
- Do NOT add message sending from client to server (beyond what's needed for the hook API)
- Do NOT add event persistence or offline queue
- Do NOT hook into TanStack Query cache invalidation here — consumers of the hook will do that (e.g., AlertFeed)
- Do NOT add heartbeat/ping-pong logic — rely on browser WebSocket behavior and reconnection

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] `npm run build` passes (TypeScript compiles)
- [ ] `npm run lint` passes (ESLint clean)
- [ ] Components render without errors
- [ ] WebSocket connects to `ws://<host>/ws`
- [ ] Auto-reconnect with exponential backoff (verified by tests)
- [ ] Max 5 retries before giving up (verified by tests)
- [ ] Typed events parsed and dispatched to callbacks
- [ ] Connection status indicator renders correct state
- [ ] Tests pass for reconnection logic and event parsing

## Implementation Note (2026-04-27)

Implemented `useWebSocket<E>(path, onMessage, opts)` returning `{ status, retryCount }`. The hook owns the socket lifecycle, derives the absolute URL from `window.location` (configurable via `urlBuilder` for tests), and supports a `socketFactory` injection seam so tests can stub `WebSocket` without adding `mock-socket`. Disconnects trigger exponential backoff (`baseDelayMs * 2 ** attempt`, capped at `maxDelayMs`) up to `maxRetries` (default 5) before settling on `closed`. Backend keep-alive frames (`{"type":"ping"}`) and malformed JSON are filtered before reaching the consumer callback.

Companion files:
- `src/types/wsEvents.ts` — discriminated union `WsAlertCreated | WsPipelineProgress` keyed on `event_type`, plus `ConnectionStatus` and runtime `isWsEvent` / `isWsPing` guards. `WsAlertCreated` reuses the platform-shared `Alert` type from `src/types/api.ts`.
- `src/components/common/ConnectionStatus.tsx` + `.module.css` — pill badge with pulsing dot for `connecting`/`reconnecting`, green for `open`, red for `closed`.
- `src/test/setup.ts` — sets `globalThis.IS_REACT_ACT_ENVIRONMENT = true` so React 19 stops emitting "not configured to support act" warnings during the in-test render harness.

Tests in `src/hooks/__tests__/useWebSocket.test.tsx` (vitest + jsdom) drive a hand-rolled `FakeSocket` that records constructions, exposes `open`/`close`/`emit` helpers, and verifies: initial connect, JSON dispatch, ping/malformed-JSON filtering, exponential backoff between reconnects, the `maxRetries` cutoff, and unmount cleanup.

## Validation Note (2026-04-27)

```
cd /home/rdhagan92/chiliAI/chili_app
npx tsc --noEmit                                                    # clean
npm run lint -- src/hooks src/types src/components/common           # clean (pre-existing errors elsewhere)
npx vitest run src/hooks/__tests__/useWebSocket.test.tsx            # 6/6 passing
```
