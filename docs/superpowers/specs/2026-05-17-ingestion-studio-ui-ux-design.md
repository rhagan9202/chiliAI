# Ingestion Studio UI/UX Design

## Goal

Replace the current Knowledge Base Manager at `/knowledge-bases` with a modular Ingestion Studio that guides analysts through knowledge-base setup, document ingestion, structured-record ingestion, validation, submission, and operational run tracking.

The first implementation must be production-quality frontend work: typed API helpers, clear component boundaries, explicit client/server state ownership, client-side preview and validation, and full frontend test coverage before acceptance.

## Current Context

The existing React/Vite frontend has a Knowledge Base Manager page that can list, create, delete, and upload documents for knowledge bases. The backend also now exposes structured-record ingestion endpoints:

- `POST /records/{knowledge_base_id}/files`
- `POST /records/{knowledge_base_id}/push`

Domain config already defines structured feeds such as `claims_feed`. For v1, the UI uses those config-defined feeds only. Analysts will not create or edit feed mappings in the UI.

## Product Shape

The Ingestion Studio is a guided left-stepper workbench. It replaces the current page rather than adding a separate records page, so analysts have one coherent place for data onboarding.

Primary flow:

1. Select or create a knowledge base.
2. Choose a source type: Documents or Structured Records.
3. Configure the source.
4. Preview client-side data.
5. Review validation results.
6. Submit.
7. Track the resulting run or receipt.

Document and structured-record submissions remain separate runs even when configured in one session. This keeps failures and receipts clear: a records validation failure must not hide a successful document upload.

## UX Layout

Use a left-stepper layout:

- Left rail: wizard steps and completion state.
- Main panel: current step content, previews, validation messages, and submit controls.
- Right context rail: selected knowledge base summary, selected feed metadata, recent receipts, and run timeline highlights.

The UI should feel like a dense analyst tool rather than a marketing page. It should use existing app conventions where they work: cards for bounded tools and repeated items, compact labels, chips, existing page spacing, and lucide icons for commands.

## Component Architecture

Add a focused ingestion component area under `chili_app/src/components/ingestion/`.

Core components:

- `IngestionStepper`: renders steps and current completion state.
- `KnowledgeBaseSelector`: lists, creates, selects, and deletes knowledge bases.
- `SourceTypeStep`: chooses Documents or Structured Records.
- `DocumentSourcePanel`: handles document file selection and file preview.
- `RecordsSourcePanel`: handles feed selection, CSV/JSONL selection or text input, parsing, and preview entry points.
- `RecordsPreviewTable`: renders parsed rows, required-field status, and compact row-level validation indicators.
- `ValidationPanel`: groups client checks and backend response errors with source labels.
- `SubmitPanel`: exposes separate document and records submit actions and disabled states.
- `RunTimeline`: shows workflow/run state where available, and receipt fallback where workflow projection is unavailable.

The replacement `KnowledgeBaseManagerPage.tsx` should become a thin page coordinator that composes these units.

## State Ownership

Use Zustand for client workflow state and TanStack Query for server state.

Zustand owns client-only state:

- Current wizard step.
- Selected source type.
- Selected config-defined feed.
- Pending document files.
- Parsed records preview rows.
- Client validation results.
- Submit receipts.
- Active timeline or receipt selection.
- Wizard reset and step-transition actions.

TanStack Query owns server state:

- Domain config and feed definitions.
- Knowledge-base inventory and detail.
- Knowledge-base document inventory.
- Workflow/run data.
- Document upload mutation.
- Records file/push mutations.
- Cache invalidation and refetching after successful mutations.

Zustand must not shadow-copy server resources. It may store IDs, local drafts, parsed client artifacts, validation results, and receipts produced by mutations.

## API Layer

Add `chili_app/src/api/records.ts` with typed helpers and hooks for the existing backend records endpoints.

Required API behavior:

- Push parsed JSON rows to `POST /records/{knowledge_base_id}/push`.
- Upload CSV/JSONL files to `POST /records/{knowledge_base_id}/files`.
- Return typed receipt data with `knowledge_base_id`, `feed_name`, `record_type`, `correlation_id`, `accepted_count`, and `created_at`.
- Integrate with TanStack Query mutation patterns already used by `knowledgebases.ts`.

Document upload continues to use the existing knowledge-base API helpers.

## Client Parsing And Validation

Add pure parsing and validation helpers under `chili_app/src/lib/ingestion/`.

Client-side validation catches fast, obvious problems:

- No selected knowledge base.
- No selected source type.
- No selected records feed.
- Unsupported document type based on the existing document upload accept rules.
- File-size issues based on the active domain validation config when that value is available to the frontend; otherwise show a non-blocking size warning only.
- Malformed CSV or JSONL.
- Missing required fields from the config-defined feed schema.
- Basic decimal, integer, boolean, and date coercion.
- Regex patterns from domain config for string fields.

The backend remains authoritative. Backend errors must render in the same validation/results area with a clear source label, such as `Backend response`.

## Run Tracking

Run tracking uses an operational timeline.

For document uploads, show workflow/run information from existing workflow APIs where available. For structured records, show the receipt and correlation ID immediately after submit. If workflow projection later exposes records-specific processing, the timeline should be able to render it without changing the records submission components.

Timeline entries should distinguish:

- Draft or not submitted.
- Submitted or accepted.
- Running or processing where known.
- Succeeded where known.
- Failed with actionable error detail where known.

## Error Handling

The wizard must preserve inputs after failures so analysts can fix and retry.

If document submission succeeds and records submission fails, show the document run as accepted and the records run as failed. Do not collapse mixed outcomes into a single generic failure state.

Validation and backend errors should be shown close to the relevant submit path, and the main stepper should indicate which step needs attention.

## Testing And Acceptance

The feature is not accepted until the full frontend suite passes.

Required tests:

- `records.ts` API helper and mutation tests for push and file endpoints.
- Parser and validator unit tests for CSV, JSONL, required fields, primitive coercion, pattern checks, and malformed input.
- Zustand store tests for initial state, step transitions, source selection, parsed-row updates, validation updates, receipt storage, and reset behavior.
- Component tests for source selection, document preview, records feed selection, records preview table, validation messages, submit disabled states, and retry-after-error behavior.
- Replacement page integration tests covering document happy path, records happy path, validation failure path, backend error path, and mixed document/records outcome behavior.

Verification commands:

```bash
pnpm test
pnpm build
```

Both commands must pass before the implementation is considered complete.

## Out Of Scope For V1

- Creating or editing records feed mappings in the UI.
- Combining document and records submission into one backend run.
- Full observability diagnostics such as raw logs, spans, event payload browsers, or backend traces.
- Backend schema changes.
- New workflow projection endpoints unless already required by existing frontend contracts.
