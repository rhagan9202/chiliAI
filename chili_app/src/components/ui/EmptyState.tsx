import type { ReactNode } from 'react'

import './ui.css'

type EmptyStateProps = {
  description: string
  title?: string
  action?: ReactNode
}

export function EmptyState({
  action,
  description,
  title = 'No data yet',
}: EmptyStateProps) {
  return (
    <div className="feedback-state feedback-state--empty">
      <div className="feedback-state__title">{title}</div>
      <div>{description}</div>
      {action ? <div className="feedback-state__action">{action}</div> : null}
    </div>
  )
}