# Story E9-S07: Knowledge Base Manager — document upload and delete

## Story
As an analyst, I want to upload documents to a KB and delete individual documents.

## Acceptance Criteria
1. KB detail view shows document table: filename, content type, size, status, uploaded date.
2. Drag-and-drop upload zone accepts TXT, JSON, CSV, XLSX, PDF, DOCX up to 50 MB.
3. Upload calls `POST /knowledgebases/{kb_id}/documents` with multipart form data.
4. Progress indicator.
5. Delete button per document with confirmation dialog.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | M    | E9-S06, E5-S13 |

## Target Files
- `chili_app/src/pages/KnowledgeBaseManager.tsx` — add KB detail view (or use sub-route)
- `chili_app/src/components/knowledgebase/KbDetailView.tsx` — KB detail view with document table
- `chili_app/src/components/knowledgebase/DocumentTable.tsx` — document list table component
- `chili_app/src/components/knowledgebase/DropZone.tsx` — drag-and-drop file upload zone
- `chili_app/src/components/knowledgebase/DropZone.module.css` — drop zone styles (drag-over highlighting)
- `chili_app/src/components/knowledgebase/UploadProgress.tsx` — upload progress indicator component
- `chili_app/src/components/common/ConfirmDialog.tsx` — reusable confirmation dialog component
- `chili_app/src/hooks/useKnowledgeBaseDocuments.ts` — TanStack Query hook for listing KB documents
- `chili_app/src/hooks/useUploadDocument.ts` — mutation hook for document upload with progress tracking
- `chili_app/src/hooks/useDeleteDocument.ts` — mutation hook for document deletion
- `chili_app/src/types/document.ts` — TypeScript types for document entities

## Reference Files to Read First
- `chili_app/src/pages/KnowledgeBaseManager.tsx` — KB manager with list and create (from E9-S06)
- `chili_app/src/components/knowledgebase/KbTable.tsx` — existing KB table (from E9-S06)
- `chili_app/src/lib/apiClient.ts` — API client for multipart form data support (from E9-S03)
- `chili_app/src/hooks/useKnowledgeBases.ts` — existing hook pattern (from E9-S03)
- `backend/api/routers/` — document upload endpoint reference
- `docs/architecture.md` — §8 for KB Manager page description

## Architectural Constraints
- React 19, TypeScript strict mode (`noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`)
- Functional components with hooks only
- TanStack Query for server state, Zustand for client state, React Router v7 for routing
- No business logic in components — delegate to hooks and services
- Keep builds and lint clean: `npm run build && npm run lint`
- Accepted file types: `.txt`, `.json`, `.csv`, `.xlsx`, `.pdf`, `.docx` — validate on the client before upload
- Max file size: 50 MB — validate on the client and show error for oversized files
- Upload uses `XMLHttpRequest` or `fetch` with progress tracking (for the progress indicator)
- Use `multipart/form-data` for the upload request
- Drag-and-drop zone must also support click-to-browse as fallback
- Delete requires a confirmation dialog before executing — never delete on single click
- Invalidate document list query after successful upload or delete
- Progress indicator should show percentage or indeterminate bar per file

## What NOT To Do
- Do NOT implement the backend upload/delete endpoints — those are in E5-S13
- Do NOT add batch upload with queue management — one file at a time is acceptable
- Do NOT add document preview (PDF viewer, etc.) — out of scope
- Do NOT install a file upload library (react-dropzone, etc.) — implement with native drag events and `input[type=file]`
- Do NOT add document editing or renaming
- Do NOT add search/filter on the document table — simple table is sufficient
- Do NOT process or parse uploaded files on the frontend

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] `npm run build` passes (TypeScript compiles)
- [x] `npm run lint` passes (ESLint clean)
- [x] Components render without errors
- [x] Document table renders: filename, content type, size, status, uploaded date
- [x] Drag-and-drop zone highlights on drag-over and accepts correct file types
- [x] Client-side validation rejects disallowed types and oversized files
- [x] Upload progress indicator displays during upload
- [x] Delete confirmation dialog appears before deletion
- [x] Document list refreshes after upload and delete

## Implementation Note
Completed on April 27, 2026. KB detail is mounted under
`/knowledgebases/:kbId` (nested route added to `App.tsx`) and rendered by
`KbDetailView`. Uploads use a native drag/click `DropZone` (no third-party
library) that validates extension/size against
`ACCEPTED_DOCUMENT_EXTENSIONS` and `MAX_DOCUMENT_SIZE_BYTES = 50 MB` in
`hooks/useKnowledgeBaseDocuments.ts`. The `useUploadDocument` mutation
posts via `XMLHttpRequest` so it can stream `progress` events to a new
`UploadProgress` indicator (percent + ARIA progressbar). On success it
invalidates both the per-KB document list and the top-level KB list query
keys. `DocumentTable` shows filename, MIME type, formatted size, status,
upload timestamp, and a per-row delete button that opens a reusable
`ConfirmDialog` (destructive variant); the `useDeleteDocument` mutation
calls `DELETE /knowledgebases/{kb}/documents/{id}` and invalidates the
list. Validation failures surface via the same toast singleton from
E9-S06. Tests in `components/knowledgebase/__tests__/DropZone.test.tsx`
exercise drag-over toggling, accepted file dispatch, oversize rejection,
and unsupported-extension rejection.

## Validation Note
From `chili_app/`:
- `npx tsc --noEmit` passed (0 errors)
- `npm run lint` passed (0 problems)
- `npx vitest run --pool=threads` passed for all knowledge base + dashboard
  + hooks + alert + store tests (52 of 53 — the lone unrelated failure is
  a pre-existing assertion in `pages/__tests__/InvestigationWorkbench.test.tsx`)
- `npm run build` passed.

