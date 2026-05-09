import './ui.css'

type ErrorStateProps = {
  description: string
  title?: string
}

export function ErrorState({ description, title = 'Unable to load section' }: ErrorStateProps) {
  return (
    <div className="feedback-state feedback-state--error" role="alert">
      <div className="feedback-state__title">{title}</div>
      <div>{description}</div>
    </div>
  )
}