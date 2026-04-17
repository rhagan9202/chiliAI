# Story E9-S09: Configuration Editor page

## Story
As a platform operator, I want a Configuration Editor page to display and edit domain config YAML.

## Acceptance Criteria
1. `src/pages/ConfigEditor.tsx` fetches config, renders in code editor (Monaco/CodeMirror).
2. YAML syntax highlighting.
3. "Save" button calls `PUT /config` with feedback.
4. "Reset to defaults" button.
5. Validation errors displayed inline.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P2       | M    | E9-S02, E5-S09 |

## Target Files
- `chili_app/package.json` — add code editor dependency (e.g., `@codemirror/lang-yaml` + `@uiw/react-codemirror`, or `@monaco-editor/react`)
- `chili_app/src/pages/ConfigEditor.tsx` — replace placeholder with config editor page
- `chili_app/src/components/config/YamlEditor.tsx` — code editor wrapper with YAML syntax highlighting
- `chili_app/src/components/config/YamlEditor.module.css` — editor styles
- `chili_app/src/components/config/ConfigToolbar.tsx` — toolbar with Save, Reset, and validation status
- `chili_app/src/hooks/useConfig.ts` — TanStack Query hook for fetching config
- `chili_app/src/hooks/useSaveConfig.ts` — mutation hook for saving config (PUT /config)
- `chili_app/src/hooks/useResetConfig.ts` — mutation hook for resetting to defaults
- `chili_app/src/types/config.ts` — TypeScript types for config API responses

## Reference Files to Read First
- `chili_app/src/pages/ConfigEditor.tsx` — current placeholder (from E9-S01)
- `chili_app/src/contexts/DomainConfigContext.tsx` — domain config context (from E9-S02)
- `chili_app/src/hooks/useDomainConfig.ts` — existing config fetch hook (from E9-S02)
- `chili_app/src/lib/queryClient.ts` — query client (from E9-S03)
- `backend/config/schema.py` — backend config schema for understanding structure
- `backend/config/defaults/` — default config for "Reset to defaults" reference
- `docs/architecture.md` — §9 for domain configuration surface

## Architectural Constraints
- React 19, TypeScript strict mode (`noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`)
- Functional components with hooks only
- TanStack Query for server state, Zustand for client state, React Router v7 for routing
- No business logic in components — delegate to hooks and services
- Keep builds and lint clean: `npm run build && npm run lint`
- Prefer CodeMirror over Monaco for smaller bundle size — but either is acceptable
- YAML syntax highlighting is required — the editor must handle YAML properly
- Save feedback: show success toast on save, or inline error message on failure
- "Reset to defaults" must confirm before executing — use a confirmation dialog
- Validation errors from the backend should be displayed inline near the editor (not just in a toast)
- After successful save, invalidate the domain config query so the app-wide context refreshes
- Editor should have reasonable defaults: line numbers, word wrap, minimum height

## What NOT To Do
- Do NOT implement the backend `PUT /config` or `GET /config` endpoints — those are in E5-S09
- Do NOT build a form-based config editor — use a YAML code editor
- Do NOT implement config versioning or change history
- Do NOT add config file import/export
- Do NOT add JSON editing mode — YAML only
- Do NOT implement real-time collaborative editing
- Do NOT validate YAML schema on the frontend — send to backend and display returned errors

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] `npm run build` passes (TypeScript compiles)
- [ ] `npm run lint` passes (ESLint clean)
- [ ] Components render without errors
- [ ] Code editor renders with YAML syntax highlighting
- [ ] Config loads from API and populates editor
- [ ] Save button sends updated YAML to backend and shows feedback
- [ ] Reset to defaults button works with confirmation
- [ ] Validation errors display inline
