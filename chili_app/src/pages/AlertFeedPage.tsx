import { useState } from 'react'

import { Chip } from '../components/ui/Chip'
import { ConfidenceBar } from '../components/ui/ConfidenceBar'
import { FilterBar } from '../components/ui/FilterBar'
import { Card } from '../components/ui/Card'
import { RiskBadge } from '../components/ui/RiskBadge'
import { SectionHeader } from '../components/ui/SectionHeader'
import './pages.css'

const filters = [
  { id: 'all', label: 'All' },
  { id: 'billing', label: 'Billing' },
  { id: 'network', label: 'Network' },
  { id: 'trend', label: 'Trend' },
]

export function AlertFeedPage() {
  const [activeFilterId, setActiveFilterId] = useState('all')

  return (
    <section className="page-grid">
      <SectionHeader
        actions={<Chip label="Prototype translated to primitives" tone="info" />}
        eyebrow="Triage queue"
        subtitle="The alert feed page is now set up to compose from reusable rows, chips, risk badges, and filter controls rather than one-off JSX."
        title="Alert Feed"
      />

      <FilterBar activeFilterId={activeFilterId} filters={filters} onChange={setActiveFilterId} />

      <Card className="alert-row-card" compact>
        <div className="alert-row-card__header">
          <div>
            <div className="alert-row-card__title">Advanced Pain Specialists</div>
            <div className="alert-row-card__subtitle">Entity route will become config-driven in the next slice.</div>
          </div>
          <RiskBadge score={94} />
        </div>
        <div className="alert-row-card__meta">
          <Chip label="Billing anomaly" tone="danger" />
          <Chip label="Flagged 2d ago" tone="info" />
          <Chip label="Miami, FL" tone="default" />
        </div>
        <ConfidenceBar value={89} />
      </Card>
    </section>
  )
}