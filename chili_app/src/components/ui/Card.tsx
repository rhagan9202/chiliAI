import type { CSSProperties, PropsWithChildren } from 'react'

import './ui.css'

type CardProps = PropsWithChildren<{
  accentColor?: string
  className?: string
  compact?: boolean
}>

export function Card({ accentColor, children, className, compact = false }: CardProps) {
  const style = accentColor
    ? ({ '--card-accent': accentColor } as CSSProperties)
    : undefined

  const classes = ['ui-card']
  if (compact) {
    classes.push('ui-card--compact')
  }
  if (accentColor) {
    classes.push('ui-card--accented')
  }
  if (className) {
    classes.push(className)
  }

  return (
    <section className={classes.join(' ')} style={style}>
      {children}
    </section>
  )
}