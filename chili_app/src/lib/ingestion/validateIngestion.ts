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

    if (maxBytes !== null && file.size > maxBytes) {
      issues.push(
        issue(
          `too-large-${file.name}`,
          `${file.name} exceeds the configured ${maxFileSizeMb} MB file limit.`,
        ),
      )
    }

    if (maxBytes === null && file.size > 50 * 1024 * 1024) {
      issues.push(
        warning(
          `large-${file.name}`,
          `${file.name} is larger than 50 MB; backend limits may reject it.`,
        ),
      )
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
  const rowIndex = rowNumber - 1
  const fieldIssues: ValidationIssue[] = []

  if (definition.type === 'decimal' && Number.isNaN(Number(value))) {
    fieldIssues.push(
      issue(
        `row-${rowNumber}-${fieldName}-decimal`,
        `Row ${rowNumber} field ${display} must be a decimal number.`,
        rowIndex,
        fieldName,
      ),
    )
  }

  if (definition.type === 'integer' && !Number.isInteger(Number(value))) {
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
    const normalized = String(value).toLowerCase()
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

  if (definition.type === 'date' && Number.isNaN(Date.parse(String(value)))) {
    fieldIssues.push(
      issue(
        `row-${rowNumber}-${fieldName}-date`,
        `Row ${rowNumber} field ${display} must be a valid date.`,
        rowIndex,
        fieldName,
      ),
    )
  }

  if (definition.pattern) {
    const pattern = new RegExp(definition.pattern)
    if (!pattern.test(String(value))) {
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
