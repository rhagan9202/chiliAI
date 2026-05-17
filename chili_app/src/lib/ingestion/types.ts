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
