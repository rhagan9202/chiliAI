import './ui.css'

type RiskBadgeProps = {
  score: number
}

type RiskLevel = {
  color: string
  label: 'HIGH' | 'MED' | 'LOW'
}

function getRiskLevel(score: number): RiskLevel {
  if (score >= 90) {
    return { color: '#ff4040', label: 'HIGH' }
  }
  if (score >= 75) {
    return { color: '#f59e0b', label: 'MED' }
  }
  return { color: '#00e676', label: 'LOW' }
}

export function RiskBadge({ score }: RiskBadgeProps) {
  const { color, label } = getRiskLevel(score)

  return (
    <span className="risk-badge">
      <span className="risk-badge__dot" style={{ backgroundColor: color, boxShadow: `0 0 8px ${color}` }} />
      <span className="risk-badge__score" style={{ color }}>
        {score}
      </span>
      <span className="risk-badge__label">{label}</span>
    </span>
  )
}