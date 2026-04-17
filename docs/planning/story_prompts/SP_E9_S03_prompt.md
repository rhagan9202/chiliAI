# Story E9-S03: TanStack Query integration and API client setup

## Story
As a frontend developer, I want TanStack Query configured as server-state library with typed API client.

## Acceptance Criteria
1. `@tanstack/react-query` installed, `QueryClientProvider` wraps app.
2. OpenAPI codegen step generates typed API client functions from backend schema.
3. `package.json` script `codegen:api` runs generation.
4. Sample hook `useKnowledgeBases()` demonstrates pattern.
5. Query defaults: stale time 30s, retry 1, refetch on window focus.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P0       | M    | E5-S14       |

## Target Files
- `chili_app/package.json` — add `@tanstack/react-query`, `@tanstack/react-query-devtools`, OpenAPI codegen dependency (e.g., `openapi-typescript-codegen` or `@hey-api/openapi-ts`)
- `chili_app/src/main.tsx` — add `QueryClientProvider` wrapping app
- `chili_app/src/lib/queryClient.ts` — `QueryClient` instance with default options
- `chili_app/src/lib/apiClient.ts` — base API client configuration (base URL, headers, error handling)
- `chili_app/src/api/generated/` — directory for OpenAPI-generated types and client (output of codegen)
- `chili_app/src/hooks/useKnowledgeBases.ts` — sample TanStack Query hook demonstrating the pattern
- `chili_app/openapi-codegen.config.ts` — codegen configuration file (or equivalent for chosen tool)

## Reference Files to Read First
- `chili_app/package.json` — current dependencies
- `chili_app/src/main.tsx` — current entry point to wrap with QueryClientProvider
- `chili_app/src/App.tsx` — current app structure
- `backend/api/app.py` — FastAPI app to understand API structure
- `backend/api/routers/` — existing API routers for schema understanding
- `docs/architecture.md` — §8 for frontend architecture

## Architectural Constraints
- React 19, TypeScript strict mode (`noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`)
- Functional components with hooks only
- TanStack Query for server state, Zustand for client state, React Router v7 for routing
- No business logic in components — delegate to hooks and services
- Keep builds and lint clean: `npm run build && npm run lint`
- Query defaults: `staleTime: 30_000`, `retry: 1`, `refetchOnWindowFocus: true`
- Include `@tanstack/react-query-devtools` for development (conditionally loaded)
- API client must use a configurable base URL (environment variable via Vite `import.meta.env`)
- OpenAPI codegen should target the backend's OpenAPI schema (typically at `/openapi.json`)
- Generated API code goes in `src/api/generated/` — do NOT hand-write API types that can be generated
- The `codegen:api` script should be runnable standalone: `npm run codegen:api`
- Sample `useKnowledgeBases()` hook should demonstrate: query key convention, typed return, loading/error handling

## What NOT To Do
- Do NOT hand-write API types that should come from OpenAPI codegen
- Do NOT install Axios — use `fetch` or the generated client's built-in HTTP layer
- Do NOT add mutation hooks yet — only query (read) hooks as demonstration
- Do NOT configure authentication headers — that is a separate concern
- Do NOT add WebSocket integration — that is E9-S12
- Do NOT implement full CRUD for knowledge bases — only the list query as a sample
- Do NOT commit generated code to git — add `src/api/generated/` to `.gitignore` (or document the codegen step clearly)

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] `npm run build` passes (TypeScript compiles)
- [ ] `npm run lint` passes (ESLint clean)
- [ ] Components render without errors
- [ ] `npm run codegen:api` script exists and runs (even if backend is not running, script should be wired up)
- [ ] `QueryClientProvider` wraps the app in `main.tsx`
- [ ] `useKnowledgeBases()` hook compiles and follows TanStack Query patterns
- [ ] React Query Devtools visible in development mode
