import { ArrowUpRight } from 'lucide-react'
import type { ComponentType } from 'react'
import { Link } from 'react-router-dom'

import { Card } from './Card'
import './ui.css'

type KpiCardProps = {
  ariaLabel?: string
  color: string
  icon: ComponentType<{ size?: number }>
  label: string
  sublabel?: string
  to?: string
  trend?: string
  value: string
}

export function KpiCard({ ariaLabel, color, icon: Icon, label, sublabel, to, trend, value }: KpiCardProps) {
  const card = (
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

  if (!to) {
    return card
  }

  return (
    <Link
      aria-label={ariaLabel}
      style={{ color: 'inherit', display: 'block', height: '100%', textDecoration: 'none' }}
      to={to}
    >
      <div style={{ display: 'grid', height: '100%' }}>{card}</div>
    </Link>
  )
}
