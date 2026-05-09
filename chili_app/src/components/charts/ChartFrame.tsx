import type { PropsWithChildren, ReactNode } from 'react'

import { Card } from '../ui/Card'
import './charts.css'

type ChartFrameProps = PropsWithChildren<{
  eyebrow?: string
  footer?: ReactNode
  subtitle?: string
  title: string
}>

export function ChartFrame({ children, eyebrow, footer, subtitle, title }: ChartFrameProps) {
  return (
    <Card className="chart-frame">
      {eyebrow ? <div className="chart-frame__eyebrow">{eyebrow}</div> : null}
      <div className="chart-frame__title">{title}</div>
      {subtitle ? <div className="chart-frame__subtitle">{subtitle}</div> : null}
      <div className="chart-frame__canvas">{children}</div>
      {footer ? <div className="chart-frame__footer">{footer}</div> : null}
    </Card>
  )
}