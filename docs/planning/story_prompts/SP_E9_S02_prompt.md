# Story E9-S02: Domain config fetching and context provider

## Story
As a frontend developer, I want the app to fetch domain configuration from API at startup and provide it via React context.

## Acceptance Criteria
1. `useDomainConfig()` hook fetches `GET /config` on mount, provides via `DomainConfigContext`.
2. App shell shows loading spinner while fetching, error boundary if fails.
3. TypeScript types for `DomainConfig` match backend `config/schema.py`.
4. Mock provider exists for component tests.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P0       | S    | E5-S09       |

## Target Files
- `chili_app/src/types/domainConfig.ts` — `DomainConfig` TypeScript interface matching backend schema
- `chili_app/src/contexts/DomainConfigContext.tsx` — React context definition and provider component
- `chili_app/src/hooks/useDomainConfig.ts` — hook that fetches config and manages loading/error state
- `chili_app/src/components/common/LoadingSpinner.tsx` — reusable loading spinner component
- `chili_app/src/components/common/ErrorBoundary.tsx` — error boundary component for config fetch failure
- `chili_app/src/App.tsx` — wrap routes with `DomainConfigProvider`, show spinner/error states
- `chili_app/src/test-utils/MockDomainConfigProvider.tsx` — mock provider for component tests

## Reference Files to Read First
- `backend/config/schema.py` — backend `DomainConfig` schema to mirror in TypeScript
- `backend/config/defaults/` — default config values for understanding structure
- `chili_app/src/App.tsx` — current app shell (from E9-S01) to wrap with provider
- `chili_app/src/main.tsx` — entry point
- `docs/architecture.md` — §9 for domain configuration surface

## Architectural Constraints
- React 19, TypeScript strict mode (`noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`)
- Functional components with hooks only
- TanStack Query for server state, Zustand for client state, React Router v7 for routing
- No business logic in components — delegate to hooks and services
- Keep builds and lint clean: `npm run build && npm run lint`
- Config is fetched once at startup and cached — no polling or refetching
- Use plain `fetch()` for this single config call (TanStack Query may not be available yet depending on story order)
- If TanStack Query is available (E9-S03 done), prefer using it with `staleTime: Infinity`
- `DomainConfig` types must stay in sync with backend schema — add a comment noting the source
- Error boundary should show a user-friendly message, not a stack trace
- Mock provider must accept partial config overrides for testing flexibility

## What NOT To Do
- Do NOT implement the backend `GET /config` endpoint — that is E5-S09
- Do NOT add config editing or mutation — that is E9-S09
- Do NOT poll or refetch config after initial load
- Do NOT store config in Zustand — React context is appropriate for read-only, app-wide config
- Do NOT add domain-specific logic that interprets config values — just provide the raw config
- Do NOT create a full test suite — only the mock provider for downstream consumers

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] `npm run build` passes (TypeScript compiles)
- [ ] `npm run lint` passes (ESLint clean)
- [ ] Components render without errors
- [ ] Loading spinner displays while config is fetching
- [ ] Error boundary displays on fetch failure
- [ ] `useDomainConfig()` returns typed config object after load
- [ ] Mock provider works for test usage
