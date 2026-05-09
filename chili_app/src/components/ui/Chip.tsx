import type { CSSProperties } from 'react'

import { colors } from '../../theme/tokens'
import './ui.css'

type ChipTone = 'default' | 'info' | 'success' | 'warning' | 'danger' | 'network'

type ChipProps = {
  color?: string
  label: string
  tone?: ChipTone
}

const toneColors: Record<ChipTone, string> = {
  default: colors.b1,
  info: colors.cyan,
  success: colors.green,
  warning: colors.amber,
  danger: colors.red,
  network: colors.purple,
}

export function Chip({ color, label, tone = 'default' }: ChipProps) {
  const resolvedColor = color ?? toneColors[tone]
  const style = {
    '--chip-background': `${resolvedColor}12`,
    '--chip-border': `${resolvedColor}30`,
    '--chip-color': resolvedColor,
  } as CSSProperties

  return (
    <span className="ui-chip" style={style}>
      {label}
    </span>
  )
}