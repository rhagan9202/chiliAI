import type { ConnectionStatus as Status } from '../../types/wsEvents'

import styles from './ConnectionStatus.module.css'

export interface ConnectionStatusProps {
  status: Status
  label?: string
}

const STATUS_TEXT: Record<Status, string> = {
  open: 'Live',
  connecting: 'Connecting',
  reconnecting: 'Reconnecting',
  closed: 'Disconnected',
}

export function ConnectionStatus({
  status,
  label,
}: ConnectionStatusProps): React.ReactElement {
  const text = label ?? STATUS_TEXT[status]
  return (
    <span
      className={`${styles.badge} ${styles[status]}`}
      role="status"
      aria-live="polite"
      data-testid="connection-status"
      data-status={status}
    >
      <span className={styles.dot} aria-hidden="true" />
      {text}
    </span>
  )
}

export default ConnectionStatus
