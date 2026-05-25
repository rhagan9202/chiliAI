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

function parseCsvRows(content: string): string[][] {
  const rows: string[][] = []
  let currentRow: string[] = []
  let current = ''
  let inQuotes = false

  for (let index = 0; index < content.length; index += 1) {
    const char = content[index]
    const next = content[index + 1]

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
      currentRow.push(current.trim())
      current = ''
      continue
    }

    if ((char === '\n' || char === '\r') && !inQuotes) {
      if (char === '\r' && next === '\n') {
        index += 1
      }
      currentRow.push(current.trim())
      rows.push(currentRow)
      currentRow = []
      current = ''
      continue
    }

    current += char
  }

  if (inQuotes) {
    throw new Error('Unterminated quoted field')
  }

  currentRow.push(current.trim())
  rows.push(currentRow)

  return rows.filter((row) => row.some((cell) => cell.length > 0))
}

export function parseCsvRecords(content: string): ParsedRecordsResult {
  try {
    const parsedRows = parseCsvRows(content)
    if (parsedRows.length === 0) {
      return { rows: [], errors: [issue('CSV content is empty.')] }
    }

    const headers = parsedRows[0]
    const rows = parsedRows.slice(1).map((cells) => {
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
