import type { ReactNode } from 'react'

import './ui.css'

type SectionHeaderProps = {
  actions?: ReactNode
  eyebrow?: string
  subtitle?: string
  title: string
}

export function SectionHeader({ actions, eyebrow, subtitle, title }: SectionHeaderProps) {
  return (
    <header className="section-header">
      <div>
        {eyebrow ? <div className="section-header__eyebrow">{eyebrow}</div> : null}
        <h2 className="section-header__title">{title}</h2>
        {subtitle ? <p className="section-header__subtitle">{subtitle}</p> : null}
      </div>
      {actions ? <div className="section-header__actions">{actions}</div> : null}
    </header>
  )
}