import type { KnowledgeBaseStatus } from '../../types/api'
import {
  knowledgeBaseStatusHint,
  knowledgeBaseStatusLabel,
} from '../../utils/knowledgeBaseStatus'
import styles from './KbTable.module.css'

const VARIANTS: Record<KnowledgeBaseStatus, string> = {
  active: styles.badgeActive,
  ready: styles.badgeReady,
  building: styles.badgeBuilding,
  error: styles.badgeError,
  archived: styles.badgeArchived,
}

export interface StatusBadgeProps {
  status: KnowledgeBaseStatus
}

export function StatusBadge({
  status,
}: StatusBadgeProps): React.ReactElement {
  const variantClass = VARIANTS[status] ?? styles.badgeArchived
  return (
    <span
      className={`${styles.badge} ${variantClass}`}
      data-testid="kb-status-badge"
      data-status={status}
      title={knowledgeBaseStatusHint(status)}
    >
      {knowledgeBaseStatusLabel(status)}
    </span>
  )
}
