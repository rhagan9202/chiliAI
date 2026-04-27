import { useMemo } from 'react'

import type { Alert } from '../../types/api'

import styles from './AlertTable.module.css'

export type SortField = 'severity' | 'created_at' | 'status' | 'entity_type'
export type SortDirection = 'asc' | 'desc'

const SEVERITY_RANK: Record<string, number> = {
  critical: 4,
  high: 3,
  medium: 2,
  low: 1,
}

export interface AlertTableProps {
  alerts: Alert[]
  selectedIds: Set<string>
  onSelectionChange: (next: Set<string>) => void
  onRowClick: (alert: Alert) => void
  sortField: SortField
  sortDirection: SortDirection
  onSortChange: (field: SortField) => void
}

function compareAlerts(
  a: Alert,
  b: Alert,
  field: SortField,
  direction: SortDirection,
): number {
  let cmp = 0
  switch (field) {
    case 'severity': {
      const aRank = SEVERITY_RANK[a.severity] ?? 0
      const bRank = SEVERITY_RANK[b.severity] ?? 0
      cmp = aRank - bRank
      break
    }
    case 'created_at': {
      cmp = a.created_at.localeCompare(b.created_at)
      break
    }
    case 'status': {
      cmp = a.status.localeCompare(b.status)
      break
    }
    case 'entity_type': {
      cmp = a.entity_type.localeCompare(b.entity_type)
      break
    }
  }
  return direction === 'asc' ? cmp : -cmp
}

export function AlertTable({
  alerts,
  selectedIds,
  onSelectionChange,
  onRowClick,
  sortField,
  sortDirection,
  onSortChange,
}: AlertTableProps): React.ReactElement {
  const sorted = useMemo(() => {
    const copy = [...alerts]
    copy.sort((a, b) => compareAlerts(a, b, sortField, sortDirection))
    return copy
  }, [alerts, sortField, sortDirection])

  const allSelected = sorted.length > 0 && sorted.every((alert) => selectedIds.has(alert.id))

  const toggleAll = (): void => {
    if (allSelected) {
      onSelectionChange(new Set())
    } else {
      onSelectionChange(new Set(sorted.map((alert) => alert.id)))
    }
  }

  const toggleRow = (alertId: string): void => {
    const next = new Set(selectedIds)
    if (next.has(alertId)) {
      next.delete(alertId)
    } else {
      next.add(alertId)
    }
    onSelectionChange(next)
  }

  const renderSortIndicator = (field: SortField): React.ReactElement | null => {
    if (sortField !== field) {
      return null
    }
    return (
      <span className={styles.sortIndicator} aria-hidden="true">
        {sortDirection === 'asc' ? '▲' : '▼'}
      </span>
    )
  }

  if (sorted.length === 0) {
    return <div className={styles.empty}>No alerts match the current filters.</div>
  }

  return (
    <div className={styles.tableWrap}>
      <table className={styles.table} data-testid="alert-table">
        <thead>
          <tr>
            <th scope="col">
              <input
                type="checkbox"
                checked={allSelected}
                onChange={toggleAll}
                aria-label="Select all alerts"
              />
            </th>
            <th
              scope="col"
              className={styles.sortable}
              onClick={() => onSortChange('severity')}
            >
              Severity{renderSortIndicator('severity')}
            </th>
            <th
              scope="col"
              className={styles.sortable}
              onClick={() => onSortChange('status')}
            >
              Status{renderSortIndicator('status')}
            </th>
            <th
              scope="col"
              className={styles.sortable}
              onClick={() => onSortChange('entity_type')}
            >
              Entity{renderSortIndicator('entity_type')}
            </th>
            <th scope="col">Title</th>
            <th
              scope="col"
              className={styles.sortable}
              onClick={() => onSortChange('created_at')}
            >
              Created{renderSortIndicator('created_at')}
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((alert) => {
            const checked = selectedIds.has(alert.id)
            const severityClass =
              styles[alert.severity as keyof typeof styles] ?? ''
            return (
              <tr
                key={alert.id}
                className={styles.row}
                data-alert-id={alert.id}
                onClick={() => onRowClick(alert)}
              >
                <td onClick={(event) => event.stopPropagation()}>
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggleRow(alert.id)}
                    aria-label={`Select alert ${alert.id}`}
                  />
                </td>
                <td>
                  <span
                    className={`${styles.severityBadge} ${severityClass}`}
                  >
                    {alert.severity}
                  </span>
                </td>
                <td>
                  <span className={styles.statusPill}>{alert.status}</span>
                </td>
                <td>{alert.entity_type}</td>
                <td>{alert.title}</td>
                <td>{new Date(alert.created_at).toLocaleString()}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export default AlertTable
