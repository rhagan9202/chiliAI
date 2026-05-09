import './ui.css'

type LoadingStateProps = {
  label?: string
}

export function LoadingState({ label = 'Loading data' }: LoadingStateProps) {
  return (
    <div className="feedback-state feedback-state--loading" role="status">
      <span className="feedback-state__spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  )
}