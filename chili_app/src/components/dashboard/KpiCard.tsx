import { Skeleton } from '../common/Skeleton'
import styles from './KpiCard.module.css'

export interface KpiCardProps {
  title: string
  value: number | string | null | undefined
  icon?: string
  hint?: string
  loading?: boolean
  error?: string | null
}

function formatValue(value: number | string | null | undefined): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'number') return value.toLocaleString()
  return value
}

export function KpiCard({
  title,
  value,
  icon,
  hint,
  loading = false,
  error = null,
}: KpiCardProps): React.ReactElement {
  return (
    <div className={styles.card} data-testid="kpi-card" data-title={title}>
      <div className={styles.header}>
        <h3 className={styles.title}>{title}</h3>
        {icon ? (
          <span aria-hidden="true" className={styles.icon}>
            {icon}
          </span>
        ) : null}
      </div>
      {loading ? (
        <Skeleton width={96} height={32} ariaLabel={`${title} loading`} />
      ) : error ? (
        <span className={styles.error}>{error}</span>
      ) : (
        <span className={styles.value}>{formatValue(value)}</span>
      )}
      {hint && !loading && !error ? (
        <span className={styles.hint}>{hint}</span>
      ) : null}
    </div>
  )
}
