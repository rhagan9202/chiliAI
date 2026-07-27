import type { CSSProperties } from 'react'

import { CHIP_TONE_COLORS } from './chipTones'
import type { ChipTone } from './chipTones'
import './ui.css'

type ChipProps = {
  color?: string
  label: string
  /** Hover explanation for a label too terse to stand on its own. */
  title?: string
  tone?: ChipTone
}

export function Chip({ color, label, title, tone = 'default' }: ChipProps) {
  const resolvedColor = color ?? CHIP_TONE_COLORS[tone]
  const style = {
    '--chip-background': `${resolvedColor}12`,
    '--chip-border': `${resolvedColor}30`,
    '--chip-color': resolvedColor,
  } as CSSProperties

  return (
    <span className="ui-chip" style={style} title={title}>
      {label}
    </span>
  )
}