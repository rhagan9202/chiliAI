import { useMemo, useState } from 'react'

import type { KnowledgeBase } from '../../types/api'
import styles from './KbTable.module.css'
import { StatusBadge } from './StatusBadge'

export interface KbTableProps {
  knowledgeBases: KnowledgeBase[]
  onSelect?: (kb: KnowledgeBase) => void
  emptyMessage?: string
}

type SortDir = 'asc' | 'desc'

function formatDate(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleDateString()
}

export function KbTable({
  knowledgeBases,
  onSelect,
  emptyMessage = 'No knowledge bases yet. Click "Create Knowledge Base" to add one.',
}: KbTableProps): React.ReactElement {
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  const sorted = useMemo(() => {
    const list = [...knowledgeBases]
    list.sort((a, b) => {
      const aTime = new Date(a.created_at).getTime()
      const bTime = new Date(b.created_at).getTime()
      return sortDir === 'asc' ? aTime - bTime : bTime - aTime
    })
    return list
  }, [knowledgeBases, sortDir])

  if (knowledgeBases.length === 0) {
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
            <th>Name</th>
            <th>Status</th>
            <th>Documents</th>
            <th
              className={styles.sortable}
              aria-sort={sortDir === 'asc' ? 'ascending' : 'descending'}
              onClick={() =>
                setSortDir((dir) => (dir === 'asc' ? 'desc' : 'asc'))
              }
              role="button"
              tabIndex={0}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  setSortDir((dir) => (dir === 'asc' ? 'desc' : 'asc'))
                }
              }}
            >
              Created
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((kb) => (
            <tr key={kb.id} data-testid="kb-row">
              <td>
                {onSelect ? (
                  <button
                    type="button"
                    className={styles.nameLink}
                    onClick={() => onSelect(kb)}
                  >
                    {kb.name}
                  </button>
                ) : (
                  kb.name
                )}
              </td>
              <td>
                <StatusBadge status={kb.status} />
              </td>
              <td>{kb.document_count}</td>
              <td>{formatDate(kb.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
