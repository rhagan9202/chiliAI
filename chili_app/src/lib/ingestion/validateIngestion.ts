import type {
  DomainPropertyDefinition,
  RecordFeedConfig,
  ValidationConfig,
} from '../../api/contracts'
import { FALLBACK_MAX_FILE_SIZE_MB } from '../uploadLimits'
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
    issues.push({
      ...issue('missing-kb', 'Select a knowledge base before submitting.'),
      kind: 'prerequisite',
    })
  }

  if (!sourceType) {
    issues.push({
      ...issue('missing-source', 'Choose Documents or Structured Records before submitting.'),
      kind: 'prerequisite',
    })
  }

  if (sourceType === 'records' && !feedName) {
    issues.push({
      ...issue('missing-feed', 'Select a structured records feed before submitting.'),
      kind: 'prerequisite',
    })
  }

  return issues
}

export function validateDocumentFiles(
  files: File[],
  validationConfig: ValidationConfig | null | undefined,
): ValidationIssue[] {
  if (files.length === 0) {
    return [
      {
        ...issue('missing-files', 'Select at least one document file before submitting.'),
        kind: 'prerequisite',
      },
    ]
  }

  const allowed = validationConfig?.allowed_content_types ?? []
  const maxFileSizeMb = validationConfig?.max_file_size_mb
  const maxBytes =
    typeof maxFileSizeMb === 'number' && Number.isFinite(maxFileSizeMb)
      ? maxFileSizeMb * 1024 * 1024
      : null

  return files.flatMap((file) => {
    const issues: ValidationIssue[] = []

    if (allowed.length > 0 && file.type && !allowed.includes(file.type)) {
      issues.push(
        issue(
          `unsupported-${file.name}`,
          `${file.name} uses unsupported content type ${file.type}.`,
        ),
      )
    }

    if (file.size === 0) {
      issues.push(issue(`empty-${file.name}`, `${file.name} is empty.`))
    }

    if (maxBytes !== null && file.size > maxBytes) {
      issues.push(
        issue(
          `too-large-${file.name}`,
          `${file.name} exceeds the configured ${maxFileSizeMb} MB file limit.`,
        ),
      )
    }

    if (maxBytes === null && file.size > FALLBACK_MAX_FILE_SIZE_MB * 1024 * 1024) {
      issues.push(
        warning(
          `large-${file.name}`,
          `${file.name} is larger than ${FALLBACK_MAX_FILE_SIZE_MB} MB; backend limits may reject it.`,
        ),
      )
    }

    return issues
  })
}

export function validateRecordFile(file: File | null): ValidationIssue[] {
  if (file === null) {
    return [
      {
        ...issue('missing-record-file', 'Select a CSV or JSONL records file before submitting this feed.'),
        kind: 'prerequisite',
      },
    ]
  }

  const issues: ValidationIssue[] = []
  const lowerName = file.name.toLowerCase()
  const allowedTypes = ['text/csv', 'application/json', 'application/x-ndjson']
  const hasSupportedExtension = lowerName.endsWith('.csv') || lowerName.endsWith('.jsonl')

  if (file.size === 0) {
    issues.push(issue('empty-record-file', `${file.name} is empty.`))
  }

  if (file.type && !allowedTypes.includes(file.type) && !hasSupportedExtension) {
    issues.push(
      issue(
        'unsupported-record-file',
        `${file.name} must be a CSV or JSONL records file.`,
      ),
    )
  }

  if (!file.type && !hasSupportedExtension) {
    issues.push(
      issue(
        'unsupported-record-file',
        `${file.name} must use a .csv or .jsonl extension.`,
      ),
    )
  }

  return issues
}

function isMissing(value: unknown): boolean {
  return value === undefined || value === null || value === ''
}

function numericValue(value: unknown): number | null {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null
  }

  if (typeof value === 'string') {
    const trimmed = value.trim()
    if (trimmed.length === 0) {
      return null
    }

    const parsed = Number(trimmed)
    return Number.isFinite(parsed) ? parsed : null
  }

  return null
}

function matchesFullString(pattern: string, value: unknown): boolean {
  return new RegExp(`^(?:${pattern})$`).test(String(value))
}

// Date formats accepted by the backend's `_coerce_value` in
// `backend/records/validation.py`. Kept in lock-step here so a row that the UI
// flags as invalid is the same row the API would reject.
const ISO_YMD_RE = /^(\d{4})-(\d{2})-(\d{2})$/
const YYYYMMDD_RE = /^(\d{4})(\d{2})(\d{2})$/
const MM_DD_YYYY_RE = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/

function isValidCalendarDate(year: number, month: number, day: number): boolean {
  const dt = new Date(Date.UTC(year, month - 1, day))
  return (
    !Number.isNaN(dt.getTime()) &&
    dt.getUTCFullYear() === year &&
    dt.getUTCMonth() === month - 1 &&
    dt.getUTCDate() === day
  )
}

export function isValidDateValue(value: unknown): boolean {
  if (value instanceof Date) {
    return !Number.isNaN(value.getTime())
  }
  if (typeof value !== 'string') {
    return false
  }
  const text = value.trim()
  if (text.length === 0) {
    return false
  }
  let match = ISO_YMD_RE.exec(text)
  if (match) {
    return isValidCalendarDate(Number(match[1]), Number(match[2]), Number(match[3]))
  }
  match = YYYYMMDD_RE.exec(text)
  if (match) {
    return isValidCalendarDate(Number(match[1]), Number(match[2]), Number(match[3]))
  }
  match = MM_DD_YYYY_RE.exec(text)
  if (match) {
    return isValidCalendarDate(Number(match[3]), Number(match[1]), Number(match[2]))
  }
  return false
}

function validatePrimitive(
  rowNumber: number,
  fieldName: string,
  definition: DomainPropertyDefinition,
  value: unknown,
): ValidationIssue[] {
  const display = definition.display || fieldName
  const rowIndex = rowNumber - 1
  const fieldIssues: ValidationIssue[] = []

  if (definition.type === 'decimal' && numericValue(value) === null) {
    fieldIssues.push(
      issue(
        `row-${rowNumber}-${fieldName}-decimal`,
        `Row ${rowNumber} field ${display} must be a decimal number.`,
        rowIndex,
        fieldName,
      ),
    )
  }

  const integerValue = definition.type === 'integer' ? numericValue(value) : null
  if (definition.type === 'integer' && !Number.isInteger(integerValue)) {
    fieldIssues.push(
      issue(
        `row-${rowNumber}-${fieldName}-integer`,
        `Row ${rowNumber} field ${display} must be an integer.`,
        rowIndex,
        fieldName,
      ),
    )
  }

  if (definition.type === 'boolean') {
    const normalized = String(value).trim().toLowerCase()
    if (!['true', 'false', '1', '0', 'yes', 'no'].includes(normalized)) {
      fieldIssues.push(
        issue(
          `row-${rowNumber}-${fieldName}-boolean`,
          `Row ${rowNumber} field ${display} must be a boolean.`,
          rowIndex,
          fieldName,
        ),
      )
    }
  }

  if (definition.type === 'date' && !isValidDateValue(value)) {
    fieldIssues.push(
      issue(
        `row-${rowNumber}-${fieldName}-date`,
        `Row ${rowNumber} field ${display} must be a valid date.`,
        rowIndex,
        fieldName,
      ),
    )
  }

  if (definition.type === 'enum') {
    const values = definition.enum_values ?? []
    if (!values.includes(String(value))) {
      fieldIssues.push(
        issue(
          `row-${rowNumber}-${fieldName}-enum`,
          `Row ${rowNumber} field ${display} must be one of ${values.join(', ')}.`,
          rowIndex,
          fieldName,
        ),
      )
    }
  }

  if (definition.type === 'decimal' || definition.type === 'integer') {
    const parsed = numericValue(value)
    const numericTypeValid =
      definition.type === 'decimal'
        ? parsed !== null
        : Number.isInteger(parsed)
    if (numericTypeValid && parsed !== null) {
      if (
        definition.min_value !== undefined &&
        definition.min_value !== null &&
        parsed < definition.min_value
      ) {
        fieldIssues.push(
          issue(
            `row-${rowNumber}-${fieldName}-min`,
            `Row ${rowNumber} field ${display} must be >= ${definition.min_value}.`,
            rowIndex,
            fieldName,
          ),
        )
      }
      if (
        definition.max_value !== undefined &&
        definition.max_value !== null &&
        parsed > definition.max_value
      ) {
        fieldIssues.push(
          issue(
            `row-${rowNumber}-${fieldName}-max`,
            `Row ${rowNumber} field ${display} must be <= ${definition.max_value}.`,
            rowIndex,
            fieldName,
          ),
        )
      }
    }
  }

  if (['string', 'list', 'nested'].includes(definition.type)) {
    const length =
      definition.type === 'string' && typeof value === 'string'
        ? value.length
        : definition.type === 'list' && Array.isArray(value)
          ? value.length
          : definition.type === 'nested' &&
              value !== null &&
              typeof value === 'object' &&
              !Array.isArray(value)
            ? Object.keys(value).length
            : null
    if (length !== null) {
      if (
        definition.min_length !== undefined &&
        definition.min_length !== null &&
        length < definition.min_length
      ) {
        fieldIssues.push(
          issue(
            `row-${rowNumber}-${fieldName}-min-length`,
            `Row ${rowNumber} field ${display} must have length >= ${definition.min_length}.`,
            rowIndex,
            fieldName,
          ),
        )
      }
      if (
        definition.max_length !== undefined &&
        definition.max_length !== null &&
        length > definition.max_length
      ) {
        fieldIssues.push(
          issue(
            `row-${rowNumber}-${fieldName}-max-length`,
            `Row ${rowNumber} field ${display} must have length <= ${definition.max_length}.`,
            rowIndex,
            fieldName,
          ),
        )
      }
    }
  }

  if (definition.pattern) {
    if (!matchesFullString(definition.pattern, value)) {
      fieldIssues.push(
        issue(
          `row-${rowNumber}-${fieldName}-pattern`,
          `Row ${rowNumber} field ${display} does not match ${definition.pattern}.`,
          rowIndex,
          fieldName,
        ),
      )
    }
  }

  return fieldIssues
}

export function validateRecordRows(
  feed: RecordFeedConfig,
  rows: Record<string, unknown>[],
  options?: {
    recordFile?: File | null
  },
): ValidationIssue[] {
  if (rows.length === 0) {
    if (feed.source === 'file_upload') {
      if (options?.recordFile) {
        return [
          {
            ...issue(
              'unparsed-record-file',
              'Parse the selected records file before submitting.',
            ),
            kind: 'prerequisite',
          },
        ]
      }

      return []
    }

    return [
      {
        ...issue('missing-records', 'Provide at least one structured record row before submitting.'),
        kind: 'prerequisite',
      },
    ]
  }

  return rows.flatMap((row, index) => {
    const rowNumber = index + 1

    return Object.entries(feed.record_schema).flatMap(([fieldName, definition]) => {
      const value = row[fieldName]
      const display = definition.display || fieldName

      if (definition.required && isMissing(value)) {
        return [
          issue(
            `row-${rowNumber}-${fieldName}-required`,
            `Row ${rowNumber} is missing required field ${display}.`,
            index,
            fieldName,
          ),
        ]
      }

      if (isMissing(value)) {
        return []
      }

      return validatePrimitive(rowNumber, fieldName, definition, value)
    })
  })
}
