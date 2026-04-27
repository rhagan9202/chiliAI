import type { ChangeEvent } from 'react'

import type { AlertSeverity, AlertStatus } from '../../types/api'

import styles from './AlertTable.module.css'

const SEVERITY_OPTIONS: AlertSeverity[] = ['critical', 'high', 'medium', 'low']
const STATUS_OPTIONS: AlertStatus[] = [
  'open',
  'acknowledged',
  'investigating',
  'resolved',
  'dismissed',
]

export interface AlertFiltersValue {
  severities: AlertSeverity[]
  status: AlertStatus | ''
  entityType: string
  startDate: string
  endDate: string
}

export interface AlertFiltersProps {
  value: AlertFiltersValue
  entityTypeOptions: string[]
  onChange: (next: AlertFiltersValue) => void
}

export function AlertFilters({
  value,
  entityTypeOptions,
  onChange,
}: AlertFiltersProps): React.ReactElement {
  const toggleSeverity = (severity: AlertSeverity): void => {
    const enabled = value.severities.includes(severity)
    const next = enabled
      ? value.severities.filter((item) => item !== severity)
      : [...value.severities, severity]
    onChange({ ...value, severities: next })
  }

  const handleStatus = (event: ChangeEvent<HTMLSelectElement>): void => {
    onChange({ ...value, status: event.target.value as AlertStatus | '' })
  }

  const handleEntity = (event: ChangeEvent<HTMLSelectElement>): void => {
    onChange({ ...value, entityType: event.target.value })
  }

  const handleStart = (event: ChangeEvent<HTMLInputElement>): void => {
    onChange({ ...value, startDate: event.target.value })
  }

  const handleEnd = (event: ChangeEvent<HTMLInputElement>): void => {
    onChange({ ...value, endDate: event.target.value })
  }

  return (
    <div className={styles.filters} role="group" aria-label="Alert filters">
      <fieldset className={styles.filterGroup}>
        <legend>Severity</legend>
        <div className={styles.severityRow}>
          {SEVERITY_OPTIONS.map((severity) => (
            <label key={severity} className={styles.severityCheckbox}>
              <input
                type="checkbox"
                checked={value.severities.includes(severity)}
                onChange={() => toggleSeverity(severity)}
              />
              {severity}
            </label>
          ))}
        </div>
      </fieldset>

      <label className={styles.filterGroup}>
        <span>Status</span>
        <select value={value.status} onChange={handleStatus}>
          <option value="">All</option>
          {STATUS_OPTIONS.map((status) => (
            <option key={status} value={status}>
              {status}
            </option>
          ))}
        </select>
      </label>

      <label className={styles.filterGroup}>
        <span>Entity type</span>
        <select value={value.entityType} onChange={handleEntity}>
          <option value="">All</option>
          {entityTypeOptions.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </label>

      <label className={styles.filterGroup}>
        <span>From</span>
        <input
          type="date"
          value={value.startDate}
          onChange={handleStart}
          aria-label="Start date"
        />
      </label>

      <label className={styles.filterGroup}>
        <span>To</span>
        <input
          type="date"
          value={value.endDate}
          onChange={handleEnd}
          aria-label="End date"
        />
      </label>
    </div>
  )
}

export default AlertFilters
