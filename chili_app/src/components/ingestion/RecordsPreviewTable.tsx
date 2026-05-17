import { Chip } from '../ui/Chip'
import { EmptyState } from '../ui/EmptyState'
import type { ValidationIssue } from '../../lib/ingestion/types'
import './ingestion.css'

type RecordsPreviewTableProps = {
  rows: Record<string, unknown>[]
  issues: ValidationIssue[]
}

function getColumns(rows: Record<string, unknown>[]): string[] {
  const columns: string[] = []

  rows.forEach((row) => {
    Object.keys(row).forEach((key) => {
      if (!columns.includes(key) && columns.length < 8) {
        columns.push(key)
      }
    })
  })

  return columns
}

function formatValue(value: unknown): string {
  if (value === null) {
    return 'null'
  }

  if (value === undefined) {
    return ''
  }

  if (typeof value === 'object') {
    return JSON.stringify(value)
  }

  return String(value)
}

function statusLabel(count: number): string {
  return count === 0 ? 'valid' : `${count} ${count === 1 ? 'issue' : 'issues'}`
}

const previewRowLimit = 25

export function RecordsPreviewTable({ rows, issues }: RecordsPreviewTableProps) {
  if (rows.length === 0) {
    return <EmptyState title="No records parsed" />
  }

  const columns = getColumns(rows)
  const previewRows = rows.slice(0, previewRowLimit)

  return (
    <div className="ingestion-records-preview">
      <div className="ingestion-records-preview__scroller">
        <table className="ingestion-records-table" aria-label="Records preview">
          <thead>
            <tr>
              <th scope="col">Row</th>
              {columns.map((column) => (
                <th scope="col" key={column}>
                  {column}
                </th>
              ))}
              <th scope="col">Status</th>
            </tr>
          </thead>
          <tbody>
            {previewRows.map((row, index) => {
              const rowIssueCount = issues.filter((issue) => issue.rowIndex === index).length

              return (
                <tr key={`record-${index}`}>
                  <th scope="row">{index + 1}</th>
                  {columns.map((column) => (
                    <td key={column}>{formatValue(row[column])}</td>
                  ))}
                  <td>
                    <Chip
                      tone={rowIssueCount === 0 ? 'success' : 'warning'}
                      label={statusLabel(rowIssueCount)}
                    />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
