import './ui.css'

type ConfidenceBarProps = {
  color?: string
  value: number
}

export function ConfidenceBar({ color = '#00d4ff', value }: ConfidenceBarProps) {
  const bounded = Math.max(0, Math.min(100, value))

  return (
    <div className="confidence-bar" aria-label={`Confidence ${bounded}%`}>
      <div className="confidence-bar__track">
        <div className="confidence-bar__fill" style={{ backgroundColor: color, width: `${bounded}%` }} />
      </div>
      <span className="confidence-bar__label">{bounded}%</span>
    </div>
  )
}