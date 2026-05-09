import './ui.css'

type EmptyStateProps = {
  description: string
  title?: string
}

export function EmptyState({ description, title = 'No data yet' }: EmptyStateProps) {
  return (
    <div className="feedback-state feedback-state--empty">
      <div className="feedback-state__title">{title}</div>
      <div>{description}</div>
    </div>
  )
}