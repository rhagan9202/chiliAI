import {
  AlertTriangle,
  CheckCircle2,
  Circle,
  CircleDot,
  Info,
  Network,
} from 'lucide-react'
import type { CSSProperties } from 'react'

import { CHIP_TONE_COLORS } from './chipTones'
import type { StatusPillTone } from './statusPill'
import './ui.css'

type StatusPillProps = {
  className?: string
  compact?: boolean
  context?: string
  label: string
  tone?: StatusPillTone
}

const TONE_ICONS = {
  danger: AlertTriangle,
  default: Circle,
  info: Info,
  network: Network,
  success: CheckCircle2,
  warning: CircleDot,
} as const satisfies Record<StatusPillTone, typeof Circle>

export function StatusPill({
  className,
  compact = false,
  context,
  label,
  tone = 'default',
}: StatusPillProps) {
  const color = CHIP_TONE_COLORS[tone]
  const Icon = TONE_ICONS[tone]
  const classes = ['status-pill', `status-pill--${tone}`]
  if (compact) {
    classes.push('status-pill--compact')
  }
  if (className) {
    classes.push(className)
  }
  const style = {
    '--status-pill-background': `${color}12`,
    '--status-pill-border': `${color}38`,
    '--status-pill-color': color,
  } as CSSProperties

  return (
    <span
      aria-label={context ? `${context}: ${label}` : label}
      className={classes.join(' ')}
      style={style}
    >
      <Icon aria-hidden="true" className="status-pill__icon" data-testid="status-pill-icon" />
      <span className="status-pill__label">{label}</span>
    </span>
  )
}
