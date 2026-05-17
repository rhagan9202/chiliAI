# Ingestion Studio UI/UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `/knowledge-bases` with a modular Ingestion Studio that supports knowledge-base management, document ingestion, config-defined structured records ingestion, client preview/validation, separate submissions, and operational run tracking.

**Architecture:** Build a focused frontend feature using TanStack Query for server state and Zustand for client workflow state. Add typed records API helpers, pure ingestion parsing/validation helpers, modular `components/ingestion/` UI units, and a thin `KnowledgeBaseManagerPage` coordinator that composes them. Keep backend contracts unchanged and use the existing records, knowledge-base, workflow, and config APIs.

**Tech Stack:** React 19, TypeScript strict mode, Vite 8, TanStack Query v5, Zustand v5, Vitest, Testing Library, existing chiliAI API client and UI conventions.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `chili_app/src/api/contracts.ts` | Add frontend contract types for domain records config, validation config, records requests, and records receipts. |
| `chili_app/src/api/records.ts` | Typed records API helpers and TanStack Query mutations for `/records/{kb}/push` and `/records/{kb}/files`. |
| `chili_app/src/api/__tests__/records.test.ts` | Unit tests for records API helper payloads and endpoints. |
| `chili_app/src/lib/ingestion/types.ts` | Shared client-only ingestion wizard, validation, preview, and timeline types. |
| `chili_app/src/lib/ingestion/parseRecords.ts` | Pure CSV/JSONL parsing helpers for structured records previews. |
| `chili_app/src/lib/ingestion/validateIngestion.ts` | Pure validation helpers for documents, selected source state, and structured-record rows. |
| `chili_app/src/lib/ingestion/__tests__/parseRecords.test.ts` | Parser tests for CSV, JSONL, malformed input, and empty input. |
| `chili_app/src/lib/ingestion/__tests__/validateIngestion.test.ts` | Validation tests for required fields, type coercion, pattern checks, file type, and file size warnings. |
| `chili_app/src/stores/ingestionStudioStore.ts` | Zustand client workflow state for the wizard; no server-resource shadow copies. |
| `chili_app/src/stores/__tests__/ingestionStudioStore.test.ts` | Store tests for transitions, source/feed selection, previews, validation results, receipts, and reset. |
| `chili_app/src/components/ingestion/IngestionStepper.tsx` | Left stepper with completion/error state. |
| `chili_app/src/components/ingestion/KnowledgeBaseSelector.tsx` | KB list/create/select/delete UI wired by parent-provided server actions. |
| `chili_app/src/components/ingestion/SourceTypeStep.tsx` | Documents vs Structured Records source choice. |
| `chili_app/src/components/ingestion/DocumentSourcePanel.tsx` | Pending document file preview and document validation display. |
| `chili_app/src/components/ingestion/RecordsSourcePanel.tsx` | Feed selector, records file/text input, parse action, and records preview composition. |
| `chili_app/src/components/ingestion/RecordsPreviewTable.tsx` | Compact preview table for parsed structured rows and row-level validation markers. |
| `chili_app/src/components/ingestion/ValidationPanel.tsx` | Grouped client/backend validation messages. |
| `chili_app/src/components/ingestion/SubmitPanel.tsx` | Separate document and records submit controls with disabled and pending states. |
| `chili_app/src/components/ingestion/RunTimeline.tsx` | Operational timeline from workflow data plus receipt fallback for records. |
| `chili_app/src/components/ingestion/ingestion.css` | Ingestion-specific layout and responsive styling. |
| `chili_app/src/components/ingestion/__tests__/*.test.tsx` | Component tests for each major ingestion unit. |
| `chili_app/src/pages/KnowledgeBaseManagerPage.tsx` | Replace old manager body with thin Ingestion Studio coordinator. |
| `chili_app/src/pages/__tests__/KnowledgeBaseManagerPage.test.tsx` | Replace page tests with document flow, records flow, validation, backend error, and mixed outcome coverage. |

---

## Task 1: Frontend Contracts And Records API

**Files:**
- Modify: `chili_app/src/api/contracts.ts`
- Create: `chili_app/src/api/records.ts`
- Create: `chili_app/src/api/__tests__/records.test.ts`

- [ ] **Step 1: Write failing records API tests**

Create `chili_app/src/api/__tests__/records.test.ts`:

```ts
import { describe, expect, it, vi } from 'vitest'

import { apiPost, apiUpload } from '../client'
import {
  pushRecords,
  uploadRecordFile,
  usePushRecords,
  useUploadRecordFile,
} from '../records'

vi.mock('../client', () => ({
  apiPost: vi.fn(),
  apiUpload: vi.fn(),
}))

const apiPostMock = vi.mocked(apiPost)
const apiUploadMock = vi.mocked(apiUpload)

describe('records API helpers', () => {
  it('pushes structured rows to the selected knowledge base records endpoint', async () => {
    apiPostMock.mockResolvedValue({
      knowledge_base_id: 'kb-1',
      feed_name: 'claims_feed',
      record_type: 'claim_record',
      correlation_id: 'corr-1',
      accepted_count: 1,
      created_at: '2026-05-17T00:00:00Z',
    })

    await pushRecords('kb-1', {
      feed_name: 'claims_feed',
      rows: [{ claim_id: 'c1', anomaly_score: 0.8 }],
    })

    expect(apiPostMock).toHaveBeenCalledWith('/records/kb-1/push', {
      feed_name: 'claims_feed',
      rows: [{ claim_id: 'c1', anomaly_score: 0.8 }],
    })
  })

  it('uploads one CSV or JSONL records file with the feed form field', async () => {
    apiUploadMock.mockResolvedValue({
      knowledge_base_id: 'kb-1',
      feed_name: 'claims_feed',
      record_type: 'claim_record',
      correlation_id: 'corr-2',
      accepted_count: 2,
      created_at: '2026-05-17T00:00:00Z',
    })
    const file = new File(['claim_id\\nc1\\n'], 'claims.csv', { type: 'text/csv' })

    await uploadRecordFile('kb-1', 'claims_feed', file)

    expect(apiUploadMock).toHaveBeenCalledTimes(1)
    expect(apiUploadMock.mock.calls[0][0]).toBe('/records/kb-1/files')
    const form = apiUploadMock.mock.calls[0][1] as FormData
    expect(form.get('feed')).toBe('claims_feed')
    expect(form.get('file')).toBe(file)
  })

  it('exports mutation hooks for page composition', () => {
    expect(typeof usePushRecords).toBe('function')
    expect(typeof useUploadRecordFile).toBe('function')
  })
})
```

- [ ] **Step 2: Run the failing records API tests**

Run:

```bash
pnpm test -- src/api/__tests__/records.test.ts
```

Expected: FAIL because `src/api/records.ts` does not exist.

- [ ] **Step 3: Add records and domain-config contract types**

In `chili_app/src/api/contracts.ts`, extend the existing domain config types and add record receipt/request types:

```ts
export type DomainCapabilities = {
  timeseries: boolean
  gnn: boolean
  risk_scoring: boolean
  rag_chat: boolean
  explainability: boolean
  structured_ingestion?: boolean
}

export type RecordEntityMapping = {
  entity_type: string
  id_field: string
  property_fields: Record<string, string>
}

export type RecordRelationshipMapping = {
  relationship_type: string
  source_entity_type: string
  target_entity_type: string
}

export type RecordObservationMapping = {
  metric_name: string
  entity_type: string
  score_field: string
  rationale: string
}

export type RecordFeedConfig = {
  name: string
  record_type: string
  source: 'file_upload' | 'api_push'
  id_field: string
  record_schema: Record<string, DomainPropertyDefinition>
  entities: RecordEntityMapping[]
  relationships: RecordRelationshipMapping[]
  observations: RecordObservationMapping[]
}

export type RecordsConfig = {
  feeds: RecordFeedConfig[]
}

export type ValidationConfig = {
  max_file_size_mb: number
  allowed_content_types: string[]
  max_query_length: number
  max_rag_question_length: number
}

export type DomainConfig = {
  domain: {
    name: string
    display_name: string
    description: string
  }
  entities: DomainEntityDefinition[]
  relationships: DomainRelationshipDefinition[]
  capabilities: DomainCapabilities
  ingestion: Record<string, unknown>
  validation?: ValidationConfig | null
  records?: RecordsConfig | null
  alerts: {
    thresholds: Record<string, Record<string, number>>
  }
  ui?: DomainUiConfig
}

export type RecordPushRequest = {
  feed_name: string
  rows: Record<string, unknown>[]
}

export type RecordIngestReceipt = {
  knowledge_base_id: string
  feed_name: string
  record_type: string
  correlation_id: string
  accepted_count: number
  created_at: string
}
```

Keep the rest of `contracts.ts` unchanged.

- [ ] **Step 4: Implement records API helpers and mutations**

Create `chili_app/src/api/records.ts`:

```ts
import { useMutation, useQueryClient } from '@tanstack/react-query'

import {
  knowledgeBaseDetailQueryKey,
  knowledgeBaseDocumentsQueryKey,
  knowledgeBasesQueryKey,
} from './knowledgebases'
import { workflowsQueryKey } from './workflows'
import { apiPost, apiUpload } from './client'
import type { RecordIngestReceipt, RecordPushRequest } from './contracts'

export function pushRecords(
  knowledgeBaseId: string,
  payload: RecordPushRequest,
): Promise<RecordIngestReceipt> {
  return apiPost<RecordIngestReceipt, RecordPushRequest>(
    `/records/${knowledgeBaseId}/push`,
    payload,
  )
}

export function uploadRecordFile(
  knowledgeBaseId: string,
  feedName: string,
  file: File,
): Promise<RecordIngestReceipt> {
  const formData = new FormData()
  formData.append('feed', feedName)
  formData.append('file', file)
  return apiUpload<RecordIngestReceipt>(
    `/records/${knowledgeBaseId}/files`,
    formData,
  )
}

export function usePushRecords(knowledgeBaseId: string | null) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: RecordPushRequest) =>
      pushRecords(knowledgeBaseId ?? '', payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: knowledgeBasesQueryKey })
      void queryClient.invalidateQueries({ queryKey: workflowsQueryKey })
      if (knowledgeBaseId) {
        void queryClient.invalidateQueries({
          queryKey: knowledgeBaseDetailQueryKey(knowledgeBaseId),
        })
        void queryClient.invalidateQueries({
          queryKey: knowledgeBaseDocumentsQueryKey(knowledgeBaseId),
        })
      }
    },
  })
}

export function useUploadRecordFile(knowledgeBaseId: string | null) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ feedName, file }: { feedName: string; file: File }) =>
      uploadRecordFile(knowledgeBaseId ?? '', feedName, file),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: knowledgeBasesQueryKey })
      void queryClient.invalidateQueries({ queryKey: workflowsQueryKey })
      if (knowledgeBaseId) {
        void queryClient.invalidateQueries({
          queryKey: knowledgeBaseDetailQueryKey(knowledgeBaseId),
        })
        void queryClient.invalidateQueries({
          queryKey: knowledgeBaseDocumentsQueryKey(knowledgeBaseId),
        })
      }
    },
  })
}
```

- [ ] **Step 5: Run API tests**

Run:

```bash
pnpm test -- src/api/__tests__/records.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/api/contracts.ts src/api/records.ts src/api/__tests__/records.test.ts
git commit -m "feat(ui): add records ingestion api helpers"
```

---

## Task 2: Pure Ingestion Parsing And Validation Helpers

**Files:**
- Create: `chili_app/src/lib/ingestion/types.ts`
- Create: `chili_app/src/lib/ingestion/parseRecords.ts`
- Create: `chili_app/src/lib/ingestion/validateIngestion.ts`
- Create: `chili_app/src/lib/ingestion/__tests__/parseRecords.test.ts`
- Create: `chili_app/src/lib/ingestion/__tests__/validateIngestion.test.ts`

- [ ] **Step 1: Write failing parser tests**

Create `chili_app/src/lib/ingestion/__tests__/parseRecords.test.ts`:

```ts
import { describe, expect, it } from 'vitest'

import { parseCsvRecords, parseJsonlRecords } from '../parseRecords'

describe('record preview parsers', () => {
  it('parses CSV rows into objects using the header row', () => {
    const result = parseCsvRecords(
      'claim_id,provider_npi,billed_amount\\nc1,1234567890,99.50\\n',
    )

    expect(result.rows).toEqual([
      { claim_id: 'c1', provider_npi: '1234567890', billed_amount: '99.50' },
    ])
    expect(result.errors).toEqual([])
  })

  it('keeps commas inside quoted CSV fields', () => {
    const result = parseCsvRecords('claim_id,note\\nc1,\"office, outpatient\"\\n')

    expect(result.rows[0]).toEqual({ claim_id: 'c1', note: 'office, outpatient' })
  })

  it('reports malformed CSV quotes', () => {
    const result = parseCsvRecords('claim_id,note\\nc1,\"unterminated\\n')

    expect(result.rows).toEqual([])
    expect(result.errors[0].message).toContain('Unterminated quoted field')
  })

  it('parses one JSON object per JSONL line', () => {
    const result = parseJsonlRecords('{\"claim_id\":\"c1\"}\\n{\"claim_id\":\"c2\"}\\n')

    expect(result.rows).toEqual([{ claim_id: 'c1' }, { claim_id: 'c2' }])
    expect(result.errors).toEqual([])
  })

  it('reports non-object JSONL lines', () => {
    const result = parseJsonlRecords('[\"not\", \"object\"]\\n')

    expect(result.rows).toEqual([])
    expect(result.errors[0]).toMatchObject({
      rowIndex: 0,
      source: 'client',
      severity: 'error',
    })
  })
})
```

- [ ] **Step 2: Write failing validation tests**

Create `chili_app/src/lib/ingestion/__tests__/validateIngestion.test.ts`:

```ts
import { describe, expect, it } from 'vitest'

import type { RecordFeedConfig, ValidationConfig } from '../../../api/contracts'
import {
  validateDocumentFiles,
  validateRecordRows,
  validateRequiredWizardState,
} from '../validateIngestion'

const feed: RecordFeedConfig = {
  name: 'claims_feed',
  record_type: 'claim_record',
  source: 'file_upload',
  id_field: 'claim_id',
  record_schema: {
    claim_id: { type: 'string', display: 'Claim ID', required: true },
    provider_npi: {
      type: 'string',
      display: 'Provider NPI',
      required: true,
      pattern: '^[0-9]{10}$',
    },
    billed_amount: { type: 'decimal', display: 'Billed Amount', required: true },
    service_date: { type: 'date', display: 'Date of Service', required: true },
    anomaly_score: { type: 'decimal', display: 'Anomaly Score', required: true },
  },
  entities: [],
  relationships: [],
  observations: [],
}

const validationConfig: ValidationConfig = {
  max_file_size_mb: 1,
  allowed_content_types: ['text/csv', 'application/json'],
  max_query_length: 10000,
  max_rag_question_length: 5000,
}

describe('ingestion validation', () => {
  it('requires selected knowledge base and source type', () => {
    const issues = validateRequiredWizardState({
      knowledgeBaseId: null,
      sourceType: null,
      feedName: null,
    })

    expect(issues.map((issue) => issue.message)).toEqual([
      'Select a knowledge base before submitting.',
      'Choose Documents or Structured Records before submitting.',
    ])
  })

  it('validates document content type and size', () => {
    const file = new File(['x'], 'claims.exe', { type: 'application/x-msdownload' })
    Object.defineProperty(file, 'size', { value: 2 * 1024 * 1024 })

    const issues = validateDocumentFiles([file], validationConfig)

    expect(issues.map((issue) => issue.message)).toContain(
      'claims.exe uses unsupported content type application/x-msdownload.',
    )
    expect(issues.map((issue) => issue.message)).toContain(
      'claims.exe exceeds the configured 1 MB file limit.',
    )
  })

  it('validates required record fields and primitive coercion', () => {
    const issues = validateRecordRows(feed, [
      {
        claim_id: 'c1',
        provider_npi: '12345',
        billed_amount: 'not-money',
        service_date: '2026-01-15',
        anomaly_score: '0.8',
      },
    ])

    expect(issues.map((issue) => issue.message)).toEqual([
      'Row 1 field Provider NPI does not match ^[0-9]{10}$.',
      'Row 1 field Billed Amount must be a decimal number.',
    ])
  })

  it('passes valid record rows', () => {
    const issues = validateRecordRows(feed, [
      {
        claim_id: 'c1',
        provider_npi: '1234567890',
        billed_amount: '99.50',
        service_date: '2026-01-15',
        anomaly_score: '0.8',
      },
    ])

    expect(issues).toEqual([])
  })
})
```

- [ ] **Step 3: Run parser and validation tests to verify failure**

Run:

```bash
pnpm test -- src/lib/ingestion/__tests__/parseRecords.test.ts src/lib/ingestion/__tests__/validateIngestion.test.ts
```

Expected: FAIL because the ingestion library files do not exist.

- [ ] **Step 4: Add shared ingestion types**

Create `chili_app/src/lib/ingestion/types.ts`:

```ts
import type { RecordIngestReceipt, WorkflowRunResponse } from '../../api/contracts'

export type IngestionSourceType = 'documents' | 'records'

export type IngestionStepId =
  | 'knowledge-base'
  | 'source'
  | 'preview'
  | 'validate'
  | 'submit'
  | 'runs'

export type ValidationSeverity = 'info' | 'warning' | 'error'
export type ValidationSource = 'client' | 'backend'

export type ValidationIssue = {
  id: string
  source: ValidationSource
  severity: ValidationSeverity
  message: string
  rowIndex?: number
  field?: string
}

export type ParsedRecordsResult = {
  rows: Record<string, unknown>[]
  errors: ValidationIssue[]
}

export type IngestionReceiptEntry = {
  id: string
  sourceType: IngestionSourceType
  status: 'accepted' | 'failed'
  message: string
  createdAt: string
  receipt?: RecordIngestReceipt
}

export type TimelineEntry = {
  id: string
  label: string
  status: 'draft' | 'accepted' | 'running' | 'succeeded' | 'failed'
  detail: string
  timestamp: string | null
  workflow?: WorkflowRunResponse
  receipt?: IngestionReceiptEntry
}
```

- [ ] **Step 5: Implement parsers**

Create `chili_app/src/lib/ingestion/parseRecords.ts`:

```ts
import type { ParsedRecordsResult, ValidationIssue } from './types'

function issue(message: string, rowIndex?: number): ValidationIssue {
  return {
    id: `parse-${rowIndex ?? 'file'}-${message}`,
    source: 'client',
    severity: 'error',
    message,
    rowIndex,
  }
}

function parseCsvLine(line: string): string[] {
  const cells: string[] = []
  let current = ''
  let inQuotes = false
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index]
    const next = line[index + 1]
    if (char === '"' && inQuotes && next === '"') {
      current += '"'
      index += 1
      continue
    }
    if (char === '"') {
      inQuotes = !inQuotes
      continue
    }
    if (char === ',' && !inQuotes) {
      cells.push(current.trim())
      current = ''
      continue
    }
    current += char
  }
  if (inQuotes) {
    throw new Error('Unterminated quoted field')
  }
  cells.push(current.trim())
  return cells
}

export function parseCsvRecords(content: string): ParsedRecordsResult {
  const lines = content.split(/\r?\n/).filter((line) => line.trim().length > 0)
  if (lines.length === 0) {
    return { rows: [], errors: [issue('CSV content is empty.')] }
  }
  try {
    const headers = parseCsvLine(lines[0])
    const rows = lines.slice(1).map((line) => {
      const cells = parseCsvLine(line)
      return headers.reduce<Record<string, unknown>>((row, header, index) => {
        if (header.length > 0 && cells[index] !== undefined && cells[index] !== '') {
          row[header] = cells[index]
        }
        return row
      }, {})
    })
    return { rows, errors: [] }
  } catch (error) {
    return {
      rows: [],
      errors: [issue(error instanceof Error ? error.message : 'CSV parsing failed.')],
    }
  }
}

export function parseJsonlRecords(content: string): ParsedRecordsResult {
  const lines = content.split(/\r?\n/).filter((line) => line.trim().length > 0)
  if (lines.length === 0) {
    return { rows: [], errors: [issue('JSONL content is empty.')] }
  }
  const rows: Record<string, unknown>[] = []
  const errors: ValidationIssue[] = []
  lines.forEach((line, index) => {
    try {
      const parsed = JSON.parse(line) as unknown
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        errors.push(issue(`Line ${index + 1} must be a JSON object.`, index))
        return
      }
      rows.push(parsed as Record<string, unknown>)
    } catch {
      errors.push(issue(`Line ${index + 1} is not valid JSON.`, index))
    }
  })
  return { rows: errors.length > 0 ? [] : rows, errors }
}
```

- [ ] **Step 6: Implement validation helpers**

Create `chili_app/src/lib/ingestion/validateIngestion.ts`:

```ts
import type {
  DomainPropertyDefinition,
  RecordFeedConfig,
  ValidationConfig,
} from '../../api/contracts'
import type { IngestionSourceType, ValidationIssue } from './types'

function issue(id: string, message: string, rowIndex?: number, field?: string): ValidationIssue {
  return { id, source: 'client', severity: 'error', message, rowIndex, field }
}

function warning(id: string, message: string): ValidationIssue {
  return { id, source: 'client', severity: 'warning', message }
}

export function validateRequiredWizardState({
  knowledgeBaseId,
  sourceType,
  feedName,
}: {
  knowledgeBaseId: string | null
  sourceType: IngestionSourceType | null
  feedName: string | null
}): ValidationIssue[] {
  const issues: ValidationIssue[] = []
  if (!knowledgeBaseId) {
    issues.push(issue('missing-kb', 'Select a knowledge base before submitting.'))
  }
  if (!sourceType) {
    issues.push(issue('missing-source', 'Choose Documents or Structured Records before submitting.'))
  }
  if (sourceType === 'records' && !feedName) {
    issues.push(issue('missing-feed', 'Select a structured records feed before submitting.'))
  }
  return issues
}

export function validateDocumentFiles(
  files: File[],
  validationConfig: ValidationConfig | null | undefined,
): ValidationIssue[] {
  if (files.length === 0) {
    return [issue('missing-files', 'Select at least one document file before submitting.')]
  }
  const allowed = validationConfig?.allowed_content_types ?? []
  const maxBytes = validationConfig ? validationConfig.max_file_size_mb * 1024 * 1024 : null
  return files.flatMap((file) => {
    const issues: ValidationIssue[] = []
    if (allowed.length > 0 && file.type && !allowed.includes(file.type)) {
      issues.push(issue(
        `unsupported-${file.name}`,
        `${file.name} uses unsupported content type ${file.type}.`,
      ))
    }
    if (maxBytes !== null && file.size > maxBytes) {
      issues.push(issue(
        `too-large-${file.name}`,
        `${file.name} exceeds the configured ${validationConfig?.max_file_size_mb ?? 0} MB file limit.`,
      ))
    }
    if (maxBytes === null && file.size > 50 * 1024 * 1024) {
      issues.push(warning(
        `large-${file.name}`,
        `${file.name} is larger than 50 MB; backend limits may reject it.`,
      ))
    }
    return issues
  })
}

function isMissing(value: unknown): boolean {
  return value === undefined || value === null || value === ''
}

function validatePrimitive(
  rowNumber: number,
  fieldName: string,
  definition: DomainPropertyDefinition,
  value: unknown,
): ValidationIssue[] {
  const display = definition.display || fieldName
  const fieldIssues: ValidationIssue[] = []
  if (definition.type === 'decimal' && Number.isNaN(Number(value))) {
    fieldIssues.push(issue(
      `row-${rowNumber}-${fieldName}-decimal`,
      `Row ${rowNumber} field ${display} must be a decimal number.`,
      rowNumber - 1,
      fieldName,
    ))
  }
  if (definition.type === 'integer' && !Number.isInteger(Number(value))) {
    fieldIssues.push(issue(
      `row-${rowNumber}-${fieldName}-integer`,
      `Row ${rowNumber} field ${display} must be an integer.`,
      rowNumber - 1,
      fieldName,
    ))
  }
  if (definition.type === 'boolean') {
    const normalized = String(value).toLowerCase()
    if (!['true', 'false', '1', '0', 'yes', 'no'].includes(normalized)) {
      fieldIssues.push(issue(
        `row-${rowNumber}-${fieldName}-boolean`,
        `Row ${rowNumber} field ${display} must be a boolean.`,
        rowNumber - 1,
        fieldName,
      ))
    }
  }
  if (definition.type === 'date' && Number.isNaN(Date.parse(String(value)))) {
    fieldIssues.push(issue(
      `row-${rowNumber}-${fieldName}-date`,
      `Row ${rowNumber} field ${display} must be a valid date.`,
      rowNumber - 1,
      fieldName,
    ))
  }
  if (definition.pattern) {
    const pattern = new RegExp(definition.pattern)
    if (!pattern.test(String(value))) {
      fieldIssues.push(issue(
        `row-${rowNumber}-${fieldName}-pattern`,
        `Row ${rowNumber} field ${display} does not match ${definition.pattern}.`,
        rowNumber - 1,
        fieldName,
      ))
    }
  }
  return fieldIssues
}

export function validateRecordRows(
  feed: RecordFeedConfig,
  rows: Record<string, unknown>[],
): ValidationIssue[] {
  if (rows.length === 0) {
    return [issue('missing-records', 'Provide at least one structured record row before submitting.')]
  }
  return rows.flatMap((row, index) => {
    const rowNumber = index + 1
    return Object.entries(feed.record_schema).flatMap(([fieldName, definition]) => {
      const value = row[fieldName]
      const display = definition.display || fieldName
      if (definition.required && isMissing(value)) {
        return [issue(
          `row-${rowNumber}-${fieldName}-required`,
          `Row ${rowNumber} is missing required field ${display}.`,
          index,
          fieldName,
        )]
      }
      if (isMissing(value)) {
        return []
      }
      return validatePrimitive(rowNumber, fieldName, definition, value)
    })
  })
}
```

- [ ] **Step 7: Run parser and validation tests**

Run:

```bash
pnpm test -- src/lib/ingestion/__tests__/parseRecords.test.ts src/lib/ingestion/__tests__/validateIngestion.test.ts
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/lib/ingestion
git commit -m "feat(ui): add ingestion parsing and validation helpers"
```

---

## Task 3: Zustand Ingestion Studio Store

**Files:**
- Create: `chili_app/src/stores/ingestionStudioStore.ts`
- Create: `chili_app/src/stores/__tests__/ingestionStudioStore.test.ts`

- [ ] **Step 1: Write failing store tests**

Create `chili_app/src/stores/__tests__/ingestionStudioStore.test.ts`:

```ts
import { beforeEach, describe, expect, it } from 'vitest'

import type { ValidationIssue } from '../../lib/ingestion/types'
import { useIngestionStudioStore } from '../ingestionStudioStore'

const issue: ValidationIssue = {
  id: 'missing-feed',
  source: 'client',
  severity: 'error',
  message: 'Select a structured records feed before submitting.',
}

describe('useIngestionStudioStore', () => {
  beforeEach(() => {
    useIngestionStudioStore.getState().reset()
  })

  it('starts at the knowledge-base step with no selected source', () => {
    const state = useIngestionStudioStore.getState()
    expect(state.currentStep).toBe('knowledge-base')
    expect(state.sourceType).toBeNull()
    expect(state.selectedFeedName).toBeNull()
    expect(state.pendingFiles).toEqual([])
    expect(state.parsedRows).toEqual([])
  })

  it('tracks step, source, feed, pending files, parsed rows, and validation issues', () => {
    const file = new File(['x'], 'claims.csv', { type: 'text/csv' })

    useIngestionStudioStore.getState().setCurrentStep('source')
    useIngestionStudioStore.getState().setSourceType('records')
    useIngestionStudioStore.getState().setSelectedFeedName('claims_feed')
    useIngestionStudioStore.getState().setPendingFiles([file])
    useIngestionStudioStore.getState().setParsedRows([{ claim_id: 'c1' }])
    useIngestionStudioStore.getState().setValidationIssues([issue])

    const state = useIngestionStudioStore.getState()
    expect(state.currentStep).toBe('source')
    expect(state.sourceType).toBe('records')
    expect(state.selectedFeedName).toBe('claims_feed')
    expect(state.pendingFiles).toEqual([file])
    expect(state.parsedRows).toEqual([{ claim_id: 'c1' }])
    expect(state.validationIssues).toEqual([issue])
  })

  it('stores document and records receipts without replacing existing entries', () => {
    useIngestionStudioStore.getState().addReceipt({
      id: 'documents-doc-1',
      sourceType: 'documents',
      status: 'accepted',
      message: '1 document accepted.',
      createdAt: '2026-05-17T00:00:00Z',
    })
    useIngestionStudioStore.getState().addReceipt({
      id: 'records-corr-1',
      sourceType: 'records',
      status: 'accepted',
      message: '1 record accepted.',
      createdAt: '2026-05-17T00:01:00Z',
    })

    expect(useIngestionStudioStore.getState().receipts.map((receipt) => receipt.id)).toEqual([
      'records-corr-1',
      'documents-doc-1',
    ])
  })

  it('reset clears draft state and receipts', () => {
    useIngestionStudioStore.getState().setSourceType('documents')
    useIngestionStudioStore.getState().addReceipt({
      id: 'documents-doc-1',
      sourceType: 'documents',
      status: 'accepted',
      message: '1 document accepted.',
      createdAt: '2026-05-17T00:00:00Z',
    })

    useIngestionStudioStore.getState().reset()

    const state = useIngestionStudioStore.getState()
    expect(state.sourceType).toBeNull()
    expect(state.receipts).toEqual([])
  })
})
```

- [ ] **Step 2: Run store test to verify failure**

Run:

```bash
pnpm test -- src/stores/__tests__/ingestionStudioStore.test.ts
```

Expected: FAIL because `ingestionStudioStore.ts` does not exist.

- [ ] **Step 3: Implement the store**

Create `chili_app/src/stores/ingestionStudioStore.ts`:

```ts
import { create } from 'zustand'

import type {
  IngestionReceiptEntry,
  IngestionSourceType,
  IngestionStepId,
  ValidationIssue,
} from '../lib/ingestion/types'

type IngestionStudioState = {
  currentStep: IngestionStepId
  sourceType: IngestionSourceType | null
  selectedFeedName: string | null
  pendingFiles: File[]
  parsedRows: Record<string, unknown>[]
  validationIssues: ValidationIssue[]
  receipts: IngestionReceiptEntry[]
  activeTimelineEntryId: string | null
  setCurrentStep: (step: IngestionStepId) => void
  setSourceType: (sourceType: IngestionSourceType | null) => void
  setSelectedFeedName: (feedName: string | null) => void
  setPendingFiles: (files: File[]) => void
  setParsedRows: (rows: Record<string, unknown>[]) => void
  setValidationIssues: (issues: ValidationIssue[]) => void
  addValidationIssues: (issues: ValidationIssue[]) => void
  addReceipt: (receipt: IngestionReceiptEntry) => void
  setActiveTimelineEntryId: (entryId: string | null) => void
  reset: () => void
}

const initialState = {
  currentStep: 'knowledge-base' as IngestionStepId,
  sourceType: null,
  selectedFeedName: null,
  pendingFiles: [],
  parsedRows: [],
  validationIssues: [],
  receipts: [],
  activeTimelineEntryId: null,
}

export const useIngestionStudioStore = create<IngestionStudioState>((set) => ({
  ...initialState,
  setCurrentStep: (currentStep) => set({ currentStep }),
  setSourceType: (sourceType) => set({ sourceType }),
  setSelectedFeedName: (selectedFeedName) => set({ selectedFeedName }),
  setPendingFiles: (pendingFiles) => set({ pendingFiles }),
  setParsedRows: (parsedRows) => set({ parsedRows }),
  setValidationIssues: (validationIssues) => set({ validationIssues }),
  addValidationIssues: (issues) =>
    set((state) => ({ validationIssues: [...state.validationIssues, ...issues] })),
  addReceipt: (receipt) =>
    set((state) => ({ receipts: [receipt, ...state.receipts] })),
  setActiveTimelineEntryId: (activeTimelineEntryId) => set({ activeTimelineEntryId }),
  reset: () => set({ ...initialState }),
}))
```

- [ ] **Step 4: Run store tests**

Run:

```bash
pnpm test -- src/stores/__tests__/ingestionStudioStore.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stores/ingestionStudioStore.ts src/stores/__tests__/ingestionStudioStore.test.ts
git commit -m "feat(ui): add ingestion studio client state store"
```

---

## Task 4: Stepper, Validation Panel, And Source Choice Components

**Files:**
- Create: `chili_app/src/components/ingestion/IngestionStepper.tsx`
- Create: `chili_app/src/components/ingestion/SourceTypeStep.tsx`
- Create: `chili_app/src/components/ingestion/ValidationPanel.tsx`
- Create: `chili_app/src/components/ingestion/ingestion.css`
- Create: `chili_app/src/components/ingestion/__tests__/IngestionStepper.test.tsx`
- Create: `chili_app/src/components/ingestion/__tests__/SourceTypeStep.test.tsx`
- Create: `chili_app/src/components/ingestion/__tests__/ValidationPanel.test.tsx`

- [ ] **Step 1: Write failing component tests**

Create `chili_app/src/components/ingestion/__tests__/IngestionStepper.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { IngestionStepper } from '../IngestionStepper'

describe('IngestionStepper', () => {
  it('renders the active step and marks steps with errors', () => {
    render(
      <IngestionStepper
        currentStep="preview"
        errorStepIds={new Set(['validate'])}
        completedStepIds={new Set(['knowledge-base', 'source'])}
      />,
    )

    expect(screen.getByRole('list')).toBeInTheDocument()
    expect(screen.getByText('Preview')).toHaveAttribute('aria-current', 'step')
    expect(screen.getByText('Validate')).toHaveTextContent('ValidateNeeds attention')
  })
})
```

Create `chili_app/src/components/ingestion/__tests__/SourceTypeStep.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { SourceTypeStep } from '../SourceTypeStep'

describe('SourceTypeStep', () => {
  it('lets analysts choose documents or structured records', async () => {
    const onChange = vi.fn()
    render(<SourceTypeStep selectedSourceType={null} onChange={onChange} />)

    await userEvent.click(screen.getByRole('button', { name: /Structured Records/i }))

    expect(onChange).toHaveBeenCalledWith('records')
  })
})
```

Create `chili_app/src/components/ingestion/__tests__/ValidationPanel.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ValidationPanel } from '../ValidationPanel'

describe('ValidationPanel', () => {
  it('groups client and backend validation messages', () => {
    render(
      <ValidationPanel
        issues={[
          {
            id: 'client-1',
            source: 'client',
            severity: 'error',
            message: 'Select a feed.',
          },
          {
            id: 'backend-1',
            source: 'backend',
            severity: 'error',
            message: 'Record storage failure.',
          },
        ]}
      />,
    )

    expect(screen.getByText('Client check')).toBeInTheDocument()
    expect(screen.getByText('Backend response')).toBeInTheDocument()
    expect(screen.getByText('Select a feed.')).toBeInTheDocument()
    expect(screen.getByText('Record storage failure.')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pnpm test -- src/components/ingestion/__tests__/IngestionStepper.test.tsx src/components/ingestion/__tests__/SourceTypeStep.test.tsx src/components/ingestion/__tests__/ValidationPanel.test.tsx
```

Expected: FAIL because the components do not exist.

- [ ] **Step 3: Implement the components and CSS**

Create `chili_app/src/components/ingestion/IngestionStepper.tsx`:

```tsx
import type { IngestionStepId } from '../../lib/ingestion/types'
import './ingestion.css'

const steps: Array<{ id: IngestionStepId; label: string }> = [
  { id: 'knowledge-base', label: 'Knowledge base' },
  { id: 'source', label: 'Source' },
  { id: 'preview', label: 'Preview' },
  { id: 'validate', label: 'Validate' },
  { id: 'submit', label: 'Submit' },
  { id: 'runs', label: 'Runs' },
]

export function IngestionStepper({
  completedStepIds,
  currentStep,
  errorStepIds,
}: {
  completedStepIds: Set<IngestionStepId>
  currentStep: IngestionStepId
  errorStepIds: Set<IngestionStepId>
}) {
  return (
    <ol className="ingestion-stepper" aria-label="Ingestion steps">
      {steps.map((step, index) => {
        const active = step.id === currentStep
        const hasError = errorStepIds.has(step.id)
        const complete = completedStepIds.has(step.id)
        return (
          <li className="ingestion-stepper__item" key={step.id}>
            <span className="ingestion-stepper__index">{index + 1}</span>
            <span
              aria-current={active ? 'step' : undefined}
              className="ingestion-stepper__label"
            >
              {step.label}
              {hasError ? <small>Needs attention</small> : null}
              {!hasError && complete ? <small>Complete</small> : null}
            </span>
          </li>
        )
      })}
    </ol>
  )
}
```

Create `chili_app/src/components/ingestion/SourceTypeStep.tsx`:

```tsx
import { Database, FileText } from 'lucide-react'

import type { IngestionSourceType } from '../../lib/ingestion/types'
import './ingestion.css'

const options: Array<{
  id: IngestionSourceType
  label: string
  description: string
  Icon: typeof FileText
}> = [
  {
    id: 'documents',
    label: 'Documents',
    description: 'Upload policy, reference, or evidence files into a knowledge base.',
    Icon: FileText,
  },
  {
    id: 'records',
    label: 'Structured Records',
    description: 'Ingest config-defined CSV or JSONL feeds such as claims records.',
    Icon: Database,
  },
]

export function SourceTypeStep({
  onChange,
  selectedSourceType,
}: {
  selectedSourceType: IngestionSourceType | null
  onChange: (sourceType: IngestionSourceType) => void
}) {
  return (
    <div className="ingestion-source-grid">
      {options.map(({ id, label, description, Icon }) => (
        <button
          className={
            selectedSourceType === id
              ? 'ingestion-source-card ingestion-source-card--active'
              : 'ingestion-source-card'
          }
          key={id}
          onClick={() => onChange(id)}
          type="button"
        >
          <Icon size={20} />
          <strong>{label}</strong>
          <span>{description}</span>
        </button>
      ))}
    </div>
  )
}
```

Create `chili_app/src/components/ingestion/ValidationPanel.tsx`:

```tsx
import type { ValidationIssue } from '../../lib/ingestion/types'
import { Chip } from '../ui/Chip'
import { EmptyState } from '../ui/EmptyState'
import './ingestion.css'

function labelForSource(source: ValidationIssue['source']): string {
  return source === 'backend' ? 'Backend response' : 'Client check'
}

export function ValidationPanel({ issues }: { issues: ValidationIssue[] }) {
  if (issues.length === 0) {
    return (
      <EmptyState
        description="No blocking validation issues were found for the current source."
        title="Ready for submission"
      />
    )
  }

  const grouped = issues.reduce<Record<string, ValidationIssue[]>>((acc, issue) => {
    const label = labelForSource(issue.source)
    acc[label] = [...(acc[label] ?? []), issue]
    return acc
  }, {})

  return (
    <div className="ingestion-validation">
      {Object.entries(grouped).map(([label, group]) => (
        <section className="ingestion-validation__group" key={label}>
          <div className="metric-row">
            <strong>{label}</strong>
            <Chip label={`${group.length} issues`} tone="warning" />
          </div>
          {group.map((issue) => (
            <div className={`ingestion-validation__issue ingestion-validation__issue--${issue.severity}`} key={issue.id}>
              <span>{issue.message}</span>
            </div>
          ))}
        </section>
      ))}
    </div>
  )
}
```

Create `chili_app/src/components/ingestion/ingestion.css`:

```css
.ingestion-stepper,
.ingestion-validation,
.ingestion-source-grid {
  display: grid;
  gap: 12px;
}

.ingestion-stepper {
  padding: 0;
  margin: 0;
  list-style: none;
}

.ingestion-stepper__item {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
}

.ingestion-stepper__index {
  display: grid;
  width: 28px;
  height: 28px;
  place-items: center;
  border: 1px solid var(--c-b0);
  border-radius: 8px;
  color: var(--c-cyan);
  font-family: var(--font-mono);
  font-size: 11px;
}

.ingestion-stepper__label {
  display: grid;
  gap: 3px;
  color: var(--c-text);
  font-weight: 700;
}

.ingestion-stepper__label small,
.ingestion-source-card span {
  color: var(--c-dim);
  font-size: 12px;
  line-height: 1.45;
}

.ingestion-source-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.ingestion-source-card {
  display: grid;
  gap: 10px;
  min-height: 150px;
  padding: 16px;
  text-align: left;
  color: var(--c-text);
  background: var(--c-s3);
  border: 1px solid var(--c-b0);
  border-radius: 8px;
}

.ingestion-source-card--active,
.ingestion-source-card:hover {
  border-color: rgba(0, 212, 255, 0.45);
  background: rgba(0, 212, 255, 0.08);
}

.ingestion-validation__group {
  display: grid;
  gap: 10px;
}

.ingestion-validation__issue {
  padding: 10px 12px;
  color: var(--c-text);
  background: var(--c-s3);
  border: 1px solid var(--c-b0);
  border-radius: 8px;
}

.ingestion-validation__issue--error {
  border-color: rgba(255, 64, 64, 0.34);
}

.ingestion-validation__issue--warning {
  border-color: rgba(245, 158, 11, 0.38);
}
```

- [ ] **Step 4: Run component tests**

Run:

```bash
pnpm test -- src/components/ingestion/__tests__/IngestionStepper.test.tsx src/components/ingestion/__tests__/SourceTypeStep.test.tsx src/components/ingestion/__tests__/ValidationPanel.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/components/ingestion
git commit -m "feat(ui): add ingestion wizard foundation components"
```

---

## Task 5: Knowledge Base Selector Component

**Files:**
- Create: `chili_app/src/components/ingestion/KnowledgeBaseSelector.tsx`
- Create: `chili_app/src/components/ingestion/__tests__/KnowledgeBaseSelector.test.tsx`
- Modify: `chili_app/src/components/ingestion/ingestion.css`

- [ ] **Step 1: Write failing selector tests**

Create `chili_app/src/components/ingestion/__tests__/KnowledgeBaseSelector.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { KnowledgeBaseSummaryResponse } from '../../../api/contracts'
import { KnowledgeBaseSelector } from '../KnowledgeBaseSelector'

const knowledgeBases: KnowledgeBaseSummaryResponse[] = [
  {
    id: 'kb-1',
    name: 'Fraud KB',
    description: 'Claims investigation corpus',
    status: 'active',
    document_count: 2,
    entity_count: 3,
    relationship_count: 4,
    created_at: '2026-05-10T00:00:00Z',
  },
]

describe('KnowledgeBaseSelector', () => {
  it('selects an existing knowledge base', async () => {
    const onSelect = vi.fn()
    render(
      <KnowledgeBaseSelector
        activeKnowledgeBaseId={null}
        createDescription=""
        createDisabled={false}
        createName=""
        deleteDisabled={false}
        knowledgeBases={knowledgeBases}
        onCreateDescriptionChange={vi.fn()}
        onCreateNameChange={vi.fn()}
        onCreateSubmit={vi.fn()}
        onDelete={vi.fn()}
        onSelect={onSelect}
      />,
    )

    await userEvent.click(screen.getByRole('button', { name: /Fraud KB/i }))

    expect(onSelect).toHaveBeenCalledWith('kb-1')
  })

  it('submits create fields without owning server state', async () => {
    const onSubmit = vi.fn()
    render(
      <KnowledgeBaseSelector
        activeKnowledgeBaseId={null}
        createDescription="Reference docs"
        createDisabled={false}
        createName="New KB"
        deleteDisabled={false}
        knowledgeBases={[]}
        onCreateDescriptionChange={vi.fn()}
        onCreateNameChange={vi.fn()}
        onCreateSubmit={onSubmit}
        onDelete={vi.fn()}
        onSelect={vi.fn()}
      />,
    )

    await userEvent.click(screen.getByRole('button', { name: 'Create knowledge base' }))

    expect(onSubmit).toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run selector tests to verify failure**

Run:

```bash
pnpm test -- src/components/ingestion/__tests__/KnowledgeBaseSelector.test.tsx
```

Expected: FAIL because `KnowledgeBaseSelector.tsx` does not exist.

- [ ] **Step 3: Implement selector component**

Create `chili_app/src/components/ingestion/KnowledgeBaseSelector.tsx`:

```tsx
import type { KnowledgeBaseSummaryResponse } from '../../api/contracts'
import { Chip } from '../ui/Chip'
import { EmptyState } from '../ui/EmptyState'
import './ingestion.css'

export function KnowledgeBaseSelector({
  activeKnowledgeBaseId,
  createDescription,
  createDisabled,
  createName,
  deleteDisabled,
  knowledgeBases,
  onCreateDescriptionChange,
  onCreateNameChange,
  onCreateSubmit,
  onDelete,
  onSelect,
}: {
  knowledgeBases: KnowledgeBaseSummaryResponse[]
  activeKnowledgeBaseId: string | null
  createName: string
  createDescription: string
  createDisabled: boolean
  deleteDisabled: boolean
  onSelect: (knowledgeBaseId: string) => void
  onDelete: (knowledgeBaseId: string) => void
  onCreateNameChange: (value: string) => void
  onCreateDescriptionChange: (value: string) => void
  onCreateSubmit: () => void
}) {
  return (
    <div className="metric-stack">
      <div className="metric-row">
        <strong>Knowledge bases</strong>
        <Chip label={`${knowledgeBases.length} available`} tone="info" />
      </div>

      {knowledgeBases.length === 0 ? (
        <EmptyState
          description="Create a corpus before uploading documents or structured records."
          title="No knowledge bases yet"
        />
      ) : (
        <div className="ingestion-kb-list">
          {knowledgeBases.map((knowledgeBase) => (
            <button
              className={
                activeKnowledgeBaseId === knowledgeBase.id
                  ? 'page-list-item page-list-item--active'
                  : 'page-list-item'
              }
              key={knowledgeBase.id}
              onClick={() => onSelect(knowledgeBase.id)}
              type="button"
            >
              <strong>{knowledgeBase.name}</strong>
              <span className="metric-row__label">{knowledgeBase.description}</span>
              <div className="alert-row-card__meta">
                <Chip label={knowledgeBase.status} tone="network" />
                <Chip label={`${knowledgeBase.document_count} docs`} tone="default" />
                <Chip label={`${knowledgeBase.entity_count} entities`} tone="default" />
              </div>
            </button>
          ))}
        </div>
      )}

      {activeKnowledgeBaseId ? (
        <button
          className="page-button page-button--secondary"
          disabled={deleteDisabled}
          onClick={() => onDelete(activeKnowledgeBaseId)}
          type="button"
        >
          Delete selected knowledge base
        </button>
      ) : null}

      <div className="knowledge-base-form">
        <input
          className="page-input"
          onChange={(event) => onCreateNameChange(event.target.value)}
          placeholder="Knowledge base name"
          type="text"
          value={createName}
        />
        <textarea
          className="page-textarea"
          onChange={(event) => onCreateDescriptionChange(event.target.value)}
          placeholder="Description"
          value={createDescription}
        />
        <button
          className="page-button"
          disabled={createDisabled || createName.trim().length === 0}
          onClick={onCreateSubmit}
          type="button"
        >
          Create knowledge base
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Extend CSS**

Append to `chili_app/src/components/ingestion/ingestion.css`:

```css
.ingestion-kb-list {
  display: grid;
  gap: 10px;
}
```

- [ ] **Step 5: Run selector tests**

Run:

```bash
pnpm test -- src/components/ingestion/__tests__/KnowledgeBaseSelector.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/components/ingestion/KnowledgeBaseSelector.tsx src/components/ingestion/__tests__/KnowledgeBaseSelector.test.tsx src/components/ingestion/ingestion.css
git commit -m "feat(ui): add ingestion knowledge base selector"
```

---

## Task 6: Document And Records Source Panels

**Files:**
- Create: `chili_app/src/components/ingestion/DocumentSourcePanel.tsx`
- Create: `chili_app/src/components/ingestion/RecordsPreviewTable.tsx`
- Create: `chili_app/src/components/ingestion/RecordsSourcePanel.tsx`
- Create: `chili_app/src/components/ingestion/__tests__/DocumentSourcePanel.test.tsx`
- Create: `chili_app/src/components/ingestion/__tests__/RecordsPreviewTable.test.tsx`
- Create: `chili_app/src/components/ingestion/__tests__/RecordsSourcePanel.test.tsx`
- Modify: `chili_app/src/components/ingestion/ingestion.css`

- [ ] **Step 1: Write failing panel tests**

Create `chili_app/src/components/ingestion/__tests__/DocumentSourcePanel.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { DocumentSourcePanel } from '../DocumentSourcePanel'

describe('DocumentSourcePanel', () => {
  it('previews selected document files', async () => {
    const onFilesChange = vi.fn()
    const file = new File(['hello'], 'policy.txt', { type: 'text/plain' })

    render(<DocumentSourcePanel files={[]} onFilesChange={onFilesChange} />)

    await userEvent.upload(screen.getByLabelText('Document files'), file)

    expect(onFilesChange).toHaveBeenCalledWith([file])
  })
})
```

Create `chili_app/src/components/ingestion/__tests__/RecordsPreviewTable.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { RecordsPreviewTable } from '../RecordsPreviewTable'

describe('RecordsPreviewTable', () => {
  it('renders row values and validation markers', () => {
    render(
      <RecordsPreviewTable
        rows={[{ claim_id: 'c1', anomaly_score: '0.8' }]}
        issues={[{
          id: 'row-1-provider',
          source: 'client',
          severity: 'error',
          rowIndex: 0,
          field: 'provider_npi',
          message: 'Row 1 is missing required field Provider NPI.',
        }]}
      />,
    )

    expect(screen.getByText('claim_id')).toBeInTheDocument()
    expect(screen.getByText('c1')).toBeInTheDocument()
    expect(screen.getByText('1 issue')).toBeInTheDocument()
  })
})
```

Create `chili_app/src/components/ingestion/__tests__/RecordsSourcePanel.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { RecordFeedConfig } from '../../../api/contracts'
import { RecordsSourcePanel } from '../RecordsSourcePanel'

const feed: RecordFeedConfig = {
  name: 'claims_feed',
  record_type: 'claim_record',
  source: 'file_upload',
  id_field: 'claim_id',
  record_schema: {
    claim_id: { type: 'string', display: 'Claim ID', required: true },
  },
  entities: [],
  relationships: [],
  observations: [],
}

describe('RecordsSourcePanel', () => {
  it('selects a config-defined feed and parses pasted JSONL', async () => {
    const onFeedChange = vi.fn()
    const onRowsParsed = vi.fn()

    render(
      <RecordsSourcePanel
        feeds={[feed]}
        selectedFeedName={null}
        rows={[]}
        issues={[]}
        onFeedChange={onFeedChange}
        onRowsParsed={onRowsParsed}
      />,
    )

    await userEvent.selectOptions(screen.getByLabelText('Records feed'), 'claims_feed')
    await userEvent.type(screen.getByLabelText('Records content'), '{"claim_id":"c1"}')
    await userEvent.click(screen.getByRole('button', { name: 'Parse records' }))

    expect(onFeedChange).toHaveBeenCalledWith('claims_feed')
    expect(onRowsParsed).toHaveBeenCalledWith([{ claim_id: 'c1' }], [])
  })
})
```

- [ ] **Step 2: Run panel tests to verify failure**

Run:

```bash
pnpm test -- src/components/ingestion/__tests__/DocumentSourcePanel.test.tsx src/components/ingestion/__tests__/RecordsPreviewTable.test.tsx src/components/ingestion/__tests__/RecordsSourcePanel.test.tsx
```

Expected: FAIL because the panel components do not exist.

- [ ] **Step 3: Implement document panel**

Create `chili_app/src/components/ingestion/DocumentSourcePanel.tsx`:

```tsx
import { Chip } from '../ui/Chip'
import './ingestion.css'

function formatFileSize(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

export function DocumentSourcePanel({
  files,
  onFilesChange,
}: {
  files: File[]
  onFilesChange: (files: File[]) => void
}) {
  return (
    <div className="metric-stack">
      <label className="metric-row__label" htmlFor="ingestion-document-files">
        Document files
      </label>
      <input
        className="page-input page-input--file"
        id="ingestion-document-files"
        multiple
        onChange={(event) => onFilesChange(Array.from(event.target.files ?? []))}
        type="file"
      />
      <div className="ingestion-file-list">
        {files.map((file) => (
          <div className="ingestion-file-list__item" key={`${file.name}-${file.size}`}>
            <strong>{file.name}</strong>
            <span className="metric-row__label">{file.type || 'unknown type'}</span>
            <Chip label={formatFileSize(file.size)} tone="default" />
          </div>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Implement records preview table**

Create `chili_app/src/components/ingestion/RecordsPreviewTable.tsx`:

```tsx
import type { ValidationIssue } from '../../lib/ingestion/types'
import { Chip } from '../ui/Chip'
import { EmptyState } from '../ui/EmptyState'
import './ingestion.css'

export function RecordsPreviewTable({
  issues,
  rows,
}: {
  issues: ValidationIssue[]
  rows: Record<string, unknown>[]
}) {
  if (rows.length === 0) {
    return <EmptyState description="Parse CSV or JSONL records to preview rows." title="No records parsed" />
  }

  const columns = Array.from(new Set(rows.flatMap((row) => Object.keys(row)))).slice(0, 8)

  return (
    <div className="ingestion-table-wrap">
      <table className="ingestion-table">
        <thead>
          <tr>
            <th>Row</th>
            {columns.map((column) => <th key={column}>{column}</th>)}
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 25).map((row, index) => {
            const rowIssues = issues.filter((issue) => issue.rowIndex === index)
            return (
              <tr key={index}>
                <td>{index + 1}</td>
                {columns.map((column) => (
                  <td key={column}>{String(row[column] ?? '')}</td>
                ))}
                <td>
                  <Chip
                    label={rowIssues.length === 0 ? 'valid' : `${rowIssues.length} issue`}
                    tone={rowIssues.length === 0 ? 'success' : 'warning'}
                  />
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
```

- [ ] **Step 5: Implement records source panel**

Create `chili_app/src/components/ingestion/RecordsSourcePanel.tsx`:

```tsx
import { useState } from 'react'

import type { RecordFeedConfig } from '../../api/contracts'
import { parseCsvRecords, parseJsonlRecords } from '../../lib/ingestion/parseRecords'
import type { ValidationIssue } from '../../lib/ingestion/types'
import { Chip } from '../ui/Chip'
import { RecordsPreviewTable } from './RecordsPreviewTable'
import './ingestion.css'

export function RecordsSourcePanel({
  feeds,
  issues,
  onFeedChange,
  onRowsParsed,
  rows,
  selectedFeedName,
}: {
  feeds: RecordFeedConfig[]
  selectedFeedName: string | null
  rows: Record<string, unknown>[]
  issues: ValidationIssue[]
  onFeedChange: (feedName: string | null) => void
  onRowsParsed: (rows: Record<string, unknown>[], issues: ValidationIssue[]) => void
}) {
  const [content, setContent] = useState('')
  const [format, setFormat] = useState<'csv' | 'jsonl'>('csv')
  const selectedFeed = feeds.find((feed) => feed.name === selectedFeedName) ?? null

  return (
    <div className="metric-stack">
      <label className="metric-row__label" htmlFor="records-feed">
        Records feed
      </label>
      <select
        className="page-input"
        id="records-feed"
        onChange={(event) => onFeedChange(event.target.value || null)}
        value={selectedFeedName ?? ''}
      >
        <option value="">Select a configured feed</option>
        {feeds.map((feed) => (
          <option key={feed.name} value={feed.name}>{feed.name}</option>
        ))}
      </select>

      {selectedFeed ? (
        <div className="alert-row-card__meta">
          <Chip label={selectedFeed.record_type} tone="network" />
          <Chip label={`${Object.keys(selectedFeed.record_schema).length} fields`} tone="default" />
        </div>
      ) : null}

      <label className="metric-row__label" htmlFor="records-format">
        Records format
      </label>
      <select
        className="page-input"
        id="records-format"
        onChange={(event) => setFormat(event.target.value === 'jsonl' ? 'jsonl' : 'csv')}
        value={format}
      >
        <option value="csv">CSV</option>
        <option value="jsonl">JSONL</option>
      </select>

      <label className="metric-row__label" htmlFor="records-content">
        Records content
      </label>
      <textarea
        className="page-textarea"
        id="records-content"
        onChange={(event) => setContent(event.target.value)}
        value={content}
      />
      <button
        className="page-button"
        onClick={() => {
          const result = format === 'jsonl' ? parseJsonlRecords(content) : parseCsvRecords(content)
          onRowsParsed(result.rows, result.errors)
        }}
        type="button"
      >
        Parse records
      </button>
      <RecordsPreviewTable rows={rows} issues={issues} />
    </div>
  )
}
```

- [ ] **Step 6: Extend ingestion CSS**

Append to `chili_app/src/components/ingestion/ingestion.css`:

```css
.ingestion-file-list {
  display: grid;
  gap: 10px;
}

.ingestion-file-list__item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(150px, auto) auto;
  gap: 10px;
  align-items: center;
  padding: 12px;
  background: var(--c-s3);
  border: 1px solid var(--c-b0);
  border-radius: 8px;
}

.ingestion-table-wrap {
  overflow-x: auto;
  border: 1px solid var(--c-b0);
  border-radius: 8px;
}

.ingestion-table {
  width: 100%;
  border-collapse: collapse;
  color: var(--c-text);
  font-size: 13px;
}

.ingestion-table th,
.ingestion-table td {
  padding: 10px;
  border-bottom: 1px solid var(--c-b0);
  text-align: left;
  white-space: nowrap;
}

.ingestion-table th {
  color: var(--c-dim);
  font-family: var(--font-mono);
  font-size: 10px;
  text-transform: uppercase;
}
```

- [ ] **Step 7: Run panel tests**

Run:

```bash
pnpm test -- src/components/ingestion/__tests__/DocumentSourcePanel.test.tsx src/components/ingestion/__tests__/RecordsPreviewTable.test.tsx src/components/ingestion/__tests__/RecordsSourcePanel.test.tsx
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/components/ingestion
git commit -m "feat(ui): add ingestion source panels"
```

---

## Task 7: Submit Panel And Run Timeline

**Files:**
- Create: `chili_app/src/components/ingestion/SubmitPanel.tsx`
- Create: `chili_app/src/components/ingestion/RunTimeline.tsx`
- Create: `chili_app/src/components/ingestion/__tests__/SubmitPanel.test.tsx`
- Create: `chili_app/src/components/ingestion/__tests__/RunTimeline.test.tsx`

- [ ] **Step 1: Write failing submit and timeline tests**

Create `chili_app/src/components/ingestion/__tests__/SubmitPanel.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { SubmitPanel } from '../SubmitPanel'

describe('SubmitPanel', () => {
  it('shows separate document and records submit actions', async () => {
    const onSubmitDocuments = vi.fn()
    const onSubmitRecords = vi.fn()
    render(
      <SubmitPanel
        canSubmitDocuments
        canSubmitRecords={false}
        documentPending={false}
        recordsPending={false}
        onSubmitDocuments={onSubmitDocuments}
        onSubmitRecords={onSubmitRecords}
      />,
    )

    await userEvent.click(screen.getByRole('button', { name: 'Submit documents' }))

    expect(onSubmitDocuments).toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Submit records' })).toBeDisabled()
  })
})
```

Create `chili_app/src/components/ingestion/__tests__/RunTimeline.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { RunTimeline } from '../RunTimeline'

describe('RunTimeline', () => {
  it('renders workflow runs and receipt fallback entries', () => {
    render(
      <RunTimeline
        receipts={[{
          id: 'records-corr-1',
          sourceType: 'records',
          status: 'accepted',
          message: '1 record accepted.',
          createdAt: '2026-05-17T00:00:00Z',
        }]}
        workflows={[{
          id: 'wf-1',
          workflow_type: 'ingestion',
          status: 'running',
          knowledge_base_id: 'kb-1',
          started_at: '2026-05-17T00:00:00Z',
          updated_at: '2026-05-17T00:01:00Z',
          current_step: 'embedding',
        }]}
      />,
    )

    expect(screen.getByText('ingestion')).toBeInTheDocument()
    expect(screen.getByText('1 record accepted.')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pnpm test -- src/components/ingestion/__tests__/SubmitPanel.test.tsx src/components/ingestion/__tests__/RunTimeline.test.tsx
```

Expected: FAIL because the components do not exist.

- [ ] **Step 3: Implement submit panel**

Create `chili_app/src/components/ingestion/SubmitPanel.tsx`:

```tsx
import './ingestion.css'

export function SubmitPanel({
  canSubmitDocuments,
  canSubmitRecords,
  documentPending,
  onSubmitDocuments,
  onSubmitRecords,
  recordsPending,
}: {
  canSubmitDocuments: boolean
  canSubmitRecords: boolean
  documentPending: boolean
  recordsPending: boolean
  onSubmitDocuments: () => void
  onSubmitRecords: () => void
}) {
  return (
    <div className="ingestion-submit">
      <button
        className="page-button"
        disabled={!canSubmitDocuments || documentPending}
        onClick={onSubmitDocuments}
        type="button"
      >
        {documentPending ? 'Submitting documents...' : 'Submit documents'}
      </button>
      <button
        className="page-button"
        disabled={!canSubmitRecords || recordsPending}
        onClick={onSubmitRecords}
        type="button"
      >
        {recordsPending ? 'Submitting records...' : 'Submit records'}
      </button>
    </div>
  )
}
```

- [ ] **Step 4: Implement run timeline**

Create `chili_app/src/components/ingestion/RunTimeline.tsx`:

```tsx
import type { WorkflowRunResponse } from '../../api/contracts'
import type { IngestionReceiptEntry } from '../../lib/ingestion/types'
import { Chip } from '../ui/Chip'
import { EmptyState } from '../ui/EmptyState'
import './ingestion.css'

export function RunTimeline({
  receipts,
  workflows,
}: {
  receipts: IngestionReceiptEntry[]
  workflows: WorkflowRunResponse[]
}) {
  if (receipts.length === 0 && workflows.length === 0) {
    return <EmptyState description="Submit documents or records to see run activity." title="No runs yet" />
  }

  return (
    <div className="knowledge-base-timeline">
      {workflows.map((workflow) => (
        <div className="knowledge-base-timeline__item" key={workflow.id}>
          <div className="metric-row">
            <strong>{workflow.workflow_type}</strong>
            <Chip label={workflow.status} tone={workflow.status === 'failed' ? 'warning' : 'info'} />
          </div>
          <span className="metric-row__label">{workflow.current_step}</span>
        </div>
      ))}
      {receipts.map((receipt) => (
        <div className="knowledge-base-timeline__item" key={receipt.id}>
          <div className="metric-row">
            <strong>{receipt.sourceType}</strong>
            <Chip label={receipt.status} tone={receipt.status === 'failed' ? 'warning' : 'success'} />
          </div>
          <span className="metric-row__label">{receipt.message}</span>
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Step 5: Extend CSS**

Append to `chili_app/src/components/ingestion/ingestion.css`:

```css
.ingestion-submit {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
```

- [ ] **Step 6: Run submit and timeline tests**

Run:

```bash
pnpm test -- src/components/ingestion/__tests__/SubmitPanel.test.tsx src/components/ingestion/__tests__/RunTimeline.test.tsx
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/components/ingestion
git commit -m "feat(ui): add ingestion submit and run timeline"
```

---

## Task 8: Replace KnowledgeBaseManagerPage With Ingestion Studio Coordinator

**Files:**
- Modify: `chili_app/src/pages/KnowledgeBaseManagerPage.tsx`
- Modify: `chili_app/src/pages/pages.css`
- Modify: `chili_app/src/pages/__tests__/KnowledgeBaseManagerPage.test.tsx`

- [ ] **Step 1: Replace page tests with integrated document and records cases**

Replace `chili_app/src/pages/__tests__/KnowledgeBaseManagerPage.test.tsx` with:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useIngestionStudioStore } from '../../stores/ingestionStudioStore'
import { KnowledgeBaseManagerPage } from '../KnowledgeBaseManagerPage'

function renderWithClient(node: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })

  function Wrapper({ children }: { children: ReactNode }): React.ReactElement {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }

  return render(node, { wrapper: Wrapper })
}

const domainConfig = {
  domain: { name: 'medicare_fraud', display_name: 'Medicare Fraud', description: '' },
  entities: [],
  relationships: [],
  capabilities: {
    timeseries: true,
    gnn: true,
    risk_scoring: true,
    rag_chat: true,
    explainability: true,
    structured_ingestion: true,
  },
  ingestion: {},
  validation: {
    max_file_size_mb: 50,
    allowed_content_types: ['text/plain', 'text/csv', 'application/json'],
    max_query_length: 10000,
    max_rag_question_length: 5000,
  },
  records: {
    feeds: [{
      name: 'claims_feed',
      record_type: 'claim_record',
      source: 'file_upload',
      id_field: 'claim_id',
      record_schema: {
        claim_id: { type: 'string', display: 'Claim ID', required: true },
        provider_npi: { type: 'string', display: 'Provider NPI', required: true, pattern: '^[0-9]{10}$' },
        billed_amount: { type: 'decimal', display: 'Billed Amount', required: true },
      },
      entities: [],
      relationships: [],
      observations: [],
    }],
  },
  alerts: { thresholds: {} },
}

function installFetchMock() {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString()
    if (url.endsWith('/config/domain')) {
      return new Response(JSON.stringify(domainConfig), { status: 200, headers: { 'content-type': 'application/json' } })
    }
    if (url.endsWith('/workflows')) {
      return new Response(JSON.stringify({ items: [] }), { status: 200, headers: { 'content-type': 'application/json' } })
    }
    if (url.endsWith('/knowledgebases')) {
      return new Response(JSON.stringify({
        items: [{
          id: 'kb-1',
          name: 'Fraud KB',
          description: 'Active backend shape',
          status: 'active',
          document_count: 0,
          entity_count: 2,
          relationship_count: 1,
          created_at: '2026-05-10T00:00:00Z',
        }],
        total: 1,
      }), { status: 200, headers: { 'content-type': 'application/json' } })
    }
    if (url.endsWith('/knowledgebases/kb-1')) {
      return new Response(JSON.stringify({
        id: 'kb-1',
        name: 'Fraud KB',
        description: 'Active backend shape',
        status: 'active',
        document_count: 0,
        entity_count: 2,
        relationship_count: 1,
        created_at: '2026-05-10T00:00:00Z',
      }), { status: 200, headers: { 'content-type': 'application/json' } })
    }
    if (url.endsWith('/knowledgebases/kb-1/documents') && init?.method === 'POST') {
      return new Response(JSON.stringify({
        documents: [{
          knowledge_base_id: 'kb-1',
          source_document_id: 'doc-1',
          filename: 'policy.txt',
          status: 'registered',
          storage_key: null,
          uri: null,
          document_format: 'txt',
          created_at: '2026-05-17T00:00:00Z',
        }],
      }), { status: 200, headers: { 'content-type': 'application/json' } })
    }
    if (url.endsWith('/knowledgebases/kb-1/documents')) {
      return new Response(JSON.stringify({ items: [], total: 0 }), { status: 200, headers: { 'content-type': 'application/json' } })
    }
    if (url.endsWith('/records/kb-1/push')) {
      return new Response(JSON.stringify({
        knowledge_base_id: 'kb-1',
        feed_name: 'claims_feed',
        record_type: 'claim_record',
        correlation_id: 'corr-1',
        accepted_count: 1,
        created_at: '2026-05-17T00:00:00Z',
      }), { status: 202, headers: { 'content-type': 'application/json' } })
    }
    return new Response('{}', { status: 404, headers: { 'content-type': 'application/json' } })
  }) as unknown as typeof fetch
}

describe('KnowledgeBaseManagerPage Ingestion Studio', () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    useIngestionStudioStore.getState().reset()
    installFetchMock()
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.restoreAllMocks()
  })

  it('renders the Ingestion Studio shell and existing knowledge base', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    expect(await screen.findByText('Ingestion Studio')).toBeInTheDocument()
    expect(await screen.findAllByText('Fraud KB')).toHaveLength(2)
    expect(screen.getByText('Knowledge base')).toBeInTheDocument()
  })

  it('submits documents and stores a receipt in the timeline', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByText('Ingestion Studio')
    await userEvent.click(screen.getByRole('button', { name: /Documents/i }))
    await userEvent.upload(
      screen.getByLabelText('Document files'),
      new File(['hello'], 'policy.txt', { type: 'text/plain' }),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Submit documents' }))

    expect(await screen.findByText('1 document accepted.')).toBeInTheDocument()
  })

  it('parses and submits records through a configured feed', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByText('Ingestion Studio')
    await userEvent.click(screen.getByRole('button', { name: /Structured Records/i }))
    await userEvent.selectOptions(screen.getByLabelText('Records feed'), 'claims_feed')
    await userEvent.selectOptions(screen.getByLabelText('Records format'), 'CSV')
    await userEvent.type(
      screen.getByLabelText('Records content'),
      'claim_id,provider_npi,billed_amount\\nc1,1234567890,99.50\\n',
    )
    await userEvent.click(screen.getByRole('button', { name: 'Parse records' }))
    await userEvent.click(screen.getByRole('button', { name: 'Submit records' }))

    expect(await screen.findByText('1 records accepted for claims_feed.')).toBeInTheDocument()
  })

  it('shows client validation before records submit', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByText('Ingestion Studio')
    await userEvent.click(screen.getByRole('button', { name: /Structured Records/i }))
    await userEvent.click(screen.getByRole('button', { name: 'Submit records' }))

    expect(await screen.findByText('Select a structured records feed before submitting.')).toBeInTheDocument()
  })

  it('preserves successful document receipt when records validation fails', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByText('Ingestion Studio')
    await userEvent.click(screen.getByRole('button', { name: /Documents/i }))
    await userEvent.upload(
      screen.getByLabelText('Document files'),
      new File(['hello'], 'policy.txt', { type: 'text/plain' }),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Submit documents' }))
    await screen.findByText('1 document accepted.')

    await userEvent.click(screen.getByRole('button', { name: /Structured Records/i }))
    await userEvent.click(screen.getByRole('button', { name: 'Submit records' }))

    await waitFor(() => {
      expect(screen.getByText('1 document accepted.')).toBeInTheDocument()
      expect(screen.getByText('Select a structured records feed before submitting.')).toBeInTheDocument()
    })
  })
})
```

- [ ] **Step 2: Run page tests to verify failure**

Run:

```bash
pnpm test -- src/pages/__tests__/KnowledgeBaseManagerPage.test.tsx
```

Expected: FAIL because the current page is still the old Knowledge Base Manager and does not render Ingestion Studio controls.

- [ ] **Step 3: Replace page implementation**

Replace `chili_app/src/pages/KnowledgeBaseManagerPage.tsx` with a thin coordinator that imports and composes the components from previous tasks. The implementation should:

```tsx
// Keep existing imports for knowledge-base hooks and UI primitives.
// Add:
import { useDomainConfig } from '../api/config'
import { usePushRecords } from '../api/records'
import { useWorkflows } from '../api/workflows'
import { DocumentSourcePanel } from '../components/ingestion/DocumentSourcePanel'
import { IngestionStepper } from '../components/ingestion/IngestionStepper'
import { RecordsSourcePanel } from '../components/ingestion/RecordsSourcePanel'
import { RunTimeline } from '../components/ingestion/RunTimeline'
import { SourceTypeStep } from '../components/ingestion/SourceTypeStep'
import { SubmitPanel } from '../components/ingestion/SubmitPanel'
import { ValidationPanel } from '../components/ingestion/ValidationPanel'
import {
  validateDocumentFiles,
  validateRecordRows,
  validateRequiredWizardState,
} from '../lib/ingestion/validateIngestion'
import { useIngestionStudioStore } from '../stores/ingestionStudioStore'
```

Inside the component:

```tsx
const domainConfigQuery = useDomainConfig()
const workflowsQuery = useWorkflows()
const studio = useIngestionStudioStore()
const pushRecordsMutation = usePushRecords(activeKnowledgeBaseId)
const uploadMutation = useUploadKnowledgeBaseDocuments(activeKnowledgeBaseId)
const feeds = domainConfigQuery.data?.records?.feeds ?? []
const selectedFeed = feeds.find((feed) => feed.name === studio.selectedFeedName) ?? null
const documentIssues = validateDocumentFiles(
  studio.pendingFiles,
  domainConfigQuery.data?.validation,
)
const recordIssues = selectedFeed
  ? validateRecordRows(selectedFeed, studio.parsedRows)
  : []
const requiredIssues = validateRequiredWizardState({
  knowledgeBaseId: activeKnowledgeBaseId,
  sourceType: studio.sourceType,
  feedName: studio.selectedFeedName,
})
const currentIssues = [
  ...requiredIssues,
  ...(studio.sourceType === 'documents' ? documentIssues : []),
  ...(studio.sourceType === 'records' ? recordIssues : []),
  ...studio.validationIssues,
]
```

Render:

```tsx
<section className="page-grid">
  <SectionHeader
    actions={<Chip label="Documents + records" tone="info" />}
    eyebrow="Ingestion control"
    subtitle="Guide documents and config-defined structured records into the selected knowledge base."
    title="Ingestion Studio"
  />
  <div className="ingestion-studio-layout">
    <Card>
      <IngestionStepper
        currentStep={studio.currentStep}
        completedStepIds={new Set(['knowledge-base'])}
        errorStepIds={new Set(currentIssues.length > 0 ? ['validate'] : [])}
      />
    </Card>
    <div className="ingestion-studio-main">
      <Card>
        <KnowledgeBaseSelector
          activeKnowledgeBaseId={activeKnowledgeBaseId}
          createDescription={knowledgeBaseDescription}
          createDisabled={createKnowledgeBaseMutation.isPending}
          createName={knowledgeBaseName}
          deleteDisabled={deleteKnowledgeBaseMutation.isPending}
          knowledgeBases={knowledgeBases}
          onCreateDescriptionChange={setKnowledgeBaseDescription}
          onCreateNameChange={setKnowledgeBaseName}
          onCreateSubmit={() => {
            createKnowledgeBaseMutation.mutate(
              {
                name: knowledgeBaseName.trim(),
                description: knowledgeBaseDescription.trim(),
              },
              {
                onSuccess: (created) => {
                  setSelectedKnowledgeBaseId(created.id)
                  setKnowledgeBaseName('')
                  setKnowledgeBaseDescription('')
                  studio.setCurrentStep('source')
                },
              },
            )
          }}
          onDelete={(knowledgeBaseId) => {
            deleteKnowledgeBaseMutation.mutate(knowledgeBaseId, {
              onSuccess: () => {
                setSelectedKnowledgeBaseId(null)
                studio.setCurrentStep('knowledge-base')
              },
            })
          }}
          onSelect={(knowledgeBaseId) => {
            setSelectedKnowledgeBaseId(knowledgeBaseId)
            studio.setCurrentStep('source')
          }}
        />
      </Card>
      <Card>
        <SourceTypeStep
          selectedSourceType={studio.sourceType}
          onChange={(sourceType) => {
            studio.setSourceType(sourceType)
            studio.setCurrentStep('preview')
          }}
        />
      </Card>
      {studio.sourceType === 'documents' ? (
        <Card>
          <DocumentSourcePanel
            files={studio.pendingFiles}
            onFilesChange={studio.setPendingFiles}
          />
        </Card>
      ) : null}
      {studio.sourceType === 'records' ? (
        <Card>
          <RecordsSourcePanel
            feeds={feeds}
            selectedFeedName={studio.selectedFeedName}
            rows={studio.parsedRows}
            issues={recordIssues}
            onFeedChange={studio.setSelectedFeedName}
            onRowsParsed={(rows, parseIssues) => {
              studio.setParsedRows(rows)
              studio.setValidationIssues(parseIssues)
            }}
          />
        </Card>
      ) : null}
      <Card>
        <ValidationPanel issues={currentIssues} />
      </Card>
      <Card>
        <SubmitPanel
          canSubmitDocuments={
            studio.sourceType === 'documents' &&
            studio.pendingFiles.length > 0 &&
            documentIssues.every((issue) => issue.severity !== 'error')
          }
          canSubmitRecords={
            studio.sourceType === 'records' &&
            selectedFeed !== null &&
            studio.parsedRows.length > 0 &&
            recordIssues.every((issue) => issue.severity !== 'error')
          }
          documentPending={uploadMutation.isPending}
          recordsPending={pushRecordsMutation.isPending}
          onSubmitDocuments={submitDocuments}
          onSubmitRecords={submitRecords}
        />
      </Card>
    </div>
    <Card>
      <RunTimeline
        receipts={studio.receipts}
        workflows={workflowsQuery.data?.items ?? []}
      />
    </Card>
  </div>
</section>
```

For submit handlers:

```tsx
function submitDocuments() {
  const issues = [
    ...validateRequiredWizardState({
      knowledgeBaseId: activeKnowledgeBaseId,
      sourceType: 'documents',
      feedName: studio.selectedFeedName,
    }),
    ...validateDocumentFiles(studio.pendingFiles, domainConfigQuery.data?.validation),
  ]
  if (issues.some((issue) => issue.severity === 'error')) {
    studio.setValidationIssues(issues)
    return
  }
  uploadMutation.mutate(studio.pendingFiles, {
    onSuccess: (response) => {
      studio.addReceipt({
        id: `documents-${response.documents.map((document) => document.source_document_id).join('-')}`,
        sourceType: 'documents',
        status: 'accepted',
        message: `${response.documents.length} document accepted.`,
        createdAt: response.documents[0]?.created_at ?? new Date().toISOString(),
      })
      studio.setCurrentStep('runs')
    },
    onError: (error) => {
      studio.addValidationIssues([{
        id: 'documents-backend-error',
        source: 'backend',
        severity: 'error',
        message: error instanceof Error ? error.message : 'Document submission failed.',
      }])
    },
  })
}

function submitRecords() {
  const issues = [
    ...validateRequiredWizardState({
      knowledgeBaseId: activeKnowledgeBaseId,
      sourceType: 'records',
      feedName: studio.selectedFeedName,
    }),
    ...(selectedFeed ? validateRecordRows(selectedFeed, studio.parsedRows) : []),
  ]
  if (issues.some((issue) => issue.severity === 'error') || !selectedFeed) {
    studio.setValidationIssues(issues)
    return
  }
  pushRecordsMutation.mutate({
    feed_name: selectedFeed.name,
    rows: studio.parsedRows,
  }, {
    onSuccess: (receipt) => {
      studio.addReceipt({
        id: `records-${receipt.correlation_id}`,
        sourceType: 'records',
        status: 'accepted',
        message: `${receipt.accepted_count} records accepted for ${receipt.feed_name}.`,
        createdAt: receipt.created_at,
        receipt,
      })
      studio.setCurrentStep('runs')
    },
    onError: (error) => {
      studio.addValidationIssues([{
        id: 'records-backend-error',
        source: 'backend',
        severity: 'error',
        message: error instanceof Error ? error.message : 'Records submission failed.',
      }])
    },
  })
}
```

Use `KnowledgeBaseSelector` from Task 5 for existing create/delete/select behavior. Do not remove document inventory rendering; place it below the timeline in the right context rail and keep the existing document delete action available there.

- [ ] **Step 4: Add layout CSS**

Append to `chili_app/src/pages/pages.css`:

```css
.ingestion-studio-layout {
  display: grid;
  grid-template-columns: minmax(220px, 260px) minmax(0, 1fr) minmax(280px, 340px);
  gap: 16px;
  align-items: start;
}

.ingestion-studio-main {
  display: grid;
  gap: 16px;
}

@media (max-width: 1100px) {
  .ingestion-studio-layout {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 5: Run page integration tests**

Run:

```bash
pnpm test -- src/pages/__tests__/KnowledgeBaseManagerPage.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/pages/KnowledgeBaseManagerPage.tsx src/pages/pages.css src/pages/__tests__/KnowledgeBaseManagerPage.test.tsx
git commit -m "feat(ui): replace knowledge base manager with ingestion studio"
```

---

## Task 9: Full Frontend Verification And Polish Pass

**Files:**
- No planned file changes. If verification fails, edit only the feature files named in the failing test, TypeScript, or Vite output from Tasks 1-8.

- [ ] **Step 1: Run the full frontend test suite**

Run:

```bash
pnpm test
```

Expected: PASS. If tests fail, fix only the failing behavior in the relevant feature files and rerun `pnpm test`.

- [ ] **Step 2: Run the production build**

Run:

```bash
pnpm build
```

Expected: PASS. If TypeScript or Vite reports errors, fix the exact reported files and rerun `pnpm build`.

- [ ] **Step 3: Optional browser verification if dev server is available**

Run:

```bash
pnpm dev -- --host 0.0.0.0
```

Open `/knowledge-bases` and verify:

- The page title is `Ingestion Studio`.
- The left stepper is visible.
- Selecting Documents shows document file preview and submit controls.
- Selecting Structured Records shows feed selection, parser, preview table, validation panel, and submit controls.
- A records validation failure preserves the current rows and shows the client validation issue.

Stop the dev server after verification.

- [ ] **Step 4: Commit verification fixes if any**

If Step 1 or Step 2 required fixes:

```bash
git add src
git commit -m "fix(ui): harden ingestion studio verification"
```

If no fixes were required, do not create an empty commit.

---

## Self-Review Checklist

- Spec coverage: This plan covers records API helpers, parsing/validation helpers, Zustand client state, TanStack Query server mutations, modular ingestion components, `/knowledge-bases` replacement, run timeline, mixed outcome handling, and full frontend verification.
- Scope control: The plan does not add backend schema changes, UI feed mapping editors, combined backend runs, or full observability diagnostics.
- State consistency: Zustand stores only draft/session data, parsed client artifacts, validation issues, and receipts. TanStack Query remains the owner of domain config, knowledge bases, documents, workflows, and mutations.
- Acceptance: The final gate requires `pnpm test` and `pnpm build`.
