import { Activity, AlertTriangle, Database, ShieldCheck } from 'lucide-react'
import { useState } from 'react'

import { TrendBars } from '../components/charts/TrendBars'
import { ChartFrame } from '../components/charts/ChartFrame'
import { Chip } from '../components/ui/Chip'
import { ConfidenceBar } from '../components/ui/ConfidenceBar'
import { EmptyState } from '../components/ui/EmptyState'
import { FilterBar } from '../components/ui/FilterBar'
import { Card } from '../components/ui/Card'
import { KpiCard } from '../components/ui/KpiCard'
import { RiskBadge } from '../components/ui/RiskBadge'
import { SectionHeader } from '../components/ui/SectionHeader'
import { Tabs } from '../components/ui/Tabs'
import './pages.css'

const dashboardTabs = [
  { id: 'overview', label: 'Overview' },
  { id: 'queue', label: 'Queue Health' },
  { id: 'policy', label: 'Policy Signals' },
]

const dashboardFilters = [
  { id: 'all', label: 'All Programs' },
  { id: 'medicare', label: 'Medicare FFS' },
  { id: 'medicaid', label: 'Medicaid' },
]

const alertTrend = [
  { label: 'Mon', value: 14 },
  { label: 'Tue', value: 18 },
  { label: 'Wed', value: 22 },
  { label: 'Thu', value: 19 },
  { label: 'Fri', value: 27 },
  { label: 'Sat', value: 13 },
]

export function DashboardPage() {
  const [activeTabId, setActiveTabId] = useState('overview')
  const [activeFilterId, setActiveFilterId] = useState('all')

  return (
    <section className="page-grid">
      <SectionHeader
        actions={<Chip label="Phase 2 primitives live" tone="info" />}
        eyebrow="Phase 2 composition"
        subtitle="The dashboard now uses reusable KPI, chart, filter, tab, and feedback-state components. These are the building blocks for the production page rebuilds."
        title="Dashboard"
      />

      <div className="page-toolbar">
        <Tabs activeTabId={activeTabId} onChange={setActiveTabId} tabs={dashboardTabs} />
        <FilterBar activeFilterId={activeFilterId} filters={dashboardFilters} onChange={setActiveFilterId} />
      </div>

      <div className="dashboard-kpis">
        <KpiCard color="#00d4ff" icon={AlertTriangle} label="Active alerts" sublabel="Across triage queues and evidence review" trend="+12% week over week" value="142" />
        <KpiCard color="#f59e0b" icon={ShieldCheck} label="At-risk exposure" sublabel="Estimated recoverable overpayment" trend="+4.8%" value="$3.8M" />
        <KpiCard color="#00e676" icon={Database} label="Knowledge bases" sublabel="Domains and corpora currently searchable" value="06" />
        <KpiCard color="#a855f7" icon={Activity} label="Workflows running" sublabel="Event-driven ingestion and scoring pipelines" value="11" />
      </div>

      <div className="dashboard-panels">
        <ChartFrame
          eyebrow="Alert operations"
          footer={<Chip label="Realtime feed planned in Phase 13" tone="default" />}
          subtitle="Reusable chart framing for trends, policy signals, and queue health views."
          title="Alert Volume Trend"
        >
          <TrendBars color="#00d4ff" data={alertTrend} />
        </ChartFrame>

        <Card>
          <div className="metric-stack">
            <div className="metric-row">
              <span className="metric-row__label">High severity queue</span>
              <RiskBadge score={94} />
            </div>
            <ConfidenceBar color="#ff4040" value={91} />
            <div className="metric-row">
              <span className="metric-row__label">Supervisor review lane</span>
              <Chip label="Needs attention" tone="danger" />
            </div>
            <div className="metric-row">
              <span className="metric-row__label">Entity display model</span>
              <Chip label="Generic contracts" tone="network" />
            </div>
          </div>
        </Card>
      </div>

      <EmptyState
        description="Dashboard widgets are still using implementation fixtures. Phase 3 will replace these with backend-backed read models and domain-config-driven summaries."
        title="Production shell ready for data wiring"
      />
    </section>
  )
}