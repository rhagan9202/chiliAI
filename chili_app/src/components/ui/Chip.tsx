import type { CSSProperties } from 'react'

import { CHIP_TONE_COLORS } from './chipTones'
import type { ChipTone } from './chipTones'
import './ui.css'

type ChipProps = {
  color?: string
  label: string
  tone?: ChipTone
}

export function Chip({ color, label, tone = 'default' }: ChipProps) {
  const resolvedColor = color ?? CHIP_TONE_COLORS[tone]
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