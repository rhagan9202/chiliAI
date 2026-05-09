import { ArrowUpRight } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

import { Card } from './Card'
import './ui.css'

type KpiCardProps = {
  color: string
  icon: LucideIcon
  label: string
  sublabel?: string
  trend?: string
  value: string
}

export function KpiCard({ color, icon: Icon, label, sublabel, trend, value }: KpiCardProps) {
  return (
    <Card accentColor={color} className="kpi-card">
      <div className="kpi-card__header">
        <div className="kpi-card__icon" style={{ backgroundColor: `${color}15`, color }}>
          <Icon size={18} />
        </div>
        {trend ? (
          <div className="kpi-card__trend">
            <ArrowUpRight size={12} />
            <span>{trend}</span>
          </div>
        ) : null}
      </div>
      <div className="kpi-card__value">{value}</div>
      <div className="kpi-card__label">{label}</div>
      {sublabel ? <div className="kpi-card__sublabel">{sublabel}</div> : null}
    </Card>
  )
}