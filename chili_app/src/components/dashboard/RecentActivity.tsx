import { useRecentActivity } from '../../hooks/useRecentActivity'
import type { ActivityEvent, ActivityKind } from '../../types/dashboard'
import { Skeleton } from '../common/Skeleton'
import styles from './RecentActivity.module.css'

const KIND_ICONS: Record<ActivityKind, string> = {
  kb_created: '⛁',
  kb_updated: '✎',
  document_uploaded: '⤒',
  alert_opened: '⚑',
  analysis_completed: '✓',
}

const KIND_LABELS: Record<ActivityKind, string> = {
  kb_created: 'Knowledge base',
  kb_updated: 'Knowledge base',
  document_uploaded: 'Document',
  alert_opened: 'Alert',
  analysis_completed: 'Analysis',
}

function formatTimestamp(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString()
}

function ActivityItem({
  event,
}: {
  event: ActivityEvent
}): React.ReactElement {
  return (
    <li className={styles.item} data-testid="activity-item">
      <span aria-hidden="true" className={styles.icon}>
        {KIND_ICONS[event.kind]}
      </span>
      <span className={styles.body}>
        <span className={styles.kind}>{KIND_LABELS[event.kind]}</span>
        <span className={styles.description}>{event.description}</span>
        {event.entityType && event.entityId ? (
          <span className={styles.meta}>
            {event.entityType} · {event.entityId}
          </span>
        ) : null}
      </span>
      <span className={styles.meta}>{formatTimestamp(event.timestamp)}</span>
    </li>
  )
}

export function RecentActivity(): React.ReactElement {
  const { data, isLoading, error } = useRecentActivity()

  return (
    <section
      aria-labelledby="recent-activity-heading"
      className={styles.section}
    >
      <h2 id="recent-activity-heading" className={styles.heading}>
        Recent Activity
      </h2>
      {isLoading ? (
        <ul className={styles.list}>
          {Array.from({ length: 5 }, (_, i) => (
            <li key={i} className={styles.item}>
              <Skeleton width={28} height={28} radius="50%" />
              <span className={styles.body}>
                <Skeleton width={140} height={12} />
                <Skeleton width={220} height={14} />
              </span>
              <Skeleton width={100} height={12} />
            </li>
          ))}
        </ul>
      ) : error ? (
        <p className={styles.error}>
          Failed to load recent activity: {error.message}
        </p>
      ) : !data || data.length === 0 ? (
        <p className={styles.empty}>No recent activity to display.</p>
      ) : (
        <ul className={styles.list}>
          {data.map((event) => (
            <ActivityItem key={event.id} event={event} />
          ))}
        </ul>
      )}
    </section>
  )
}
