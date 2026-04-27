import type { DocumentSummary } from '../../types/api'
import styles from './KbTable.module.css'

export interface DocumentTableProps {
  documents: DocumentSummary[]
  onDelete: (document: DocumentSummary) => void
  emptyMessage?: string
}

function formatBytes(size: number | null | undefined): string {
  if (size === null || size === undefined) return '—'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString()
}

export function DocumentTable({
  documents,
  onDelete,
  emptyMessage = 'No documents uploaded yet.',
}: DocumentTableProps): React.ReactElement {
  if (documents.length === 0) {
    return (
      <div className={styles.tableWrapper}>
        <div className={styles.empty}>{emptyMessage}</div>
      </div>
    )
  }

  return (
    <div className={styles.tableWrapper}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Filename</th>
            <th>Type</th>
            <th>Size</th>
            <th>Status</th>
            <th>Uploaded</th>
            <th aria-label="Actions" />
          </tr>
        </thead>
        <tbody>
          {documents.map((doc) => (
            <tr key={doc.id} data-testid="document-row">
              <td>{doc.filename}</td>
              <td>{doc.content_type ?? '—'}</td>
              <td>{formatBytes(doc.size_bytes ?? null)}</td>
              <td>{doc.status}</td>
              <td>{formatDate(doc.created_at)}</td>
              <td style={{ textAlign: 'right' }}>
                <button
                  type="button"
                  onClick={() => onDelete(doc)}
                  aria-label={`Delete ${doc.filename}`}
                  style={{
                    background: 'transparent',
                    border: '1px solid var(--border, #e5e4e7)',
                    borderRadius: 4,
                    padding: '4px 10px',
                    cursor: 'pointer',
                    color: '#b91c1c',
                    fontSize: 13,
                  }}
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
