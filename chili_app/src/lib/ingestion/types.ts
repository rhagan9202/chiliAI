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

export type ValidationKind = 'prerequisite' | 'content'

export type ValidationIssue = {
  id: string
  source: ValidationSource
  severity: ValidationSeverity
  kind?: ValidationKind
  message: string
  rowIndex?: number
  field?: string
}

export type ParsedRecordsResult = {
  rows: Record<string, unknown>[]
  errors: ValidationIssue[]
}

