import { Activity, AlertTriangle, Database, ShieldCheck } from 'lucide-react'
import { useState } from 'react'

import { useAlerts } from '../api/alerts'
import { useAnalyticsOverview } from '../api/analytics'
import { useWorkflows } from '../api/workflows'
import { TrendBars } from '../components/charts/TrendBars'
import { ChartFrame } from '../components/charts/ChartFrame'
import { Chip } from '../components/ui/Chip'
import { ConfidenceBar } from '../components/ui/ConfidenceBar'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { FilterBar } from '../components/ui/FilterBar'
import { Card } from '../components/ui/Card'
import { KpiCard } from '../components/ui/KpiCard'
import { LoadingState } from '../components/ui/LoadingState'
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

export function DashboardPage() {
  const [activeTabId, setActiveTabId] = useState('overview')
  const [activeFilterId, setActiveFilterId] = useState('all')
  const overviewQuery = useAnalyticsOverview()
  const alertsQuery = useAlerts()
  const workflowsQuery = useWorkflows()

  if (overviewQuery.isLoading || alertsQuery.isLoading || workflowsQuery.isLoading) {
    return <LoadingState label="Loading dashboard telemetry" />
  }

  if (overviewQuery.isError || alertsQuery.isError || workflowsQuery.isError) {
    return <ErrorState description="Dashboard metrics could not be loaded from the API." />
  }

  if (!overviewQuery.data || !alertsQuery.data || !workflowsQuery.data) {
    return <LoadingState label="Waiting for dashboard data" />
  }

  const overview = overviewQuery.data
  const alerts = alertsQuery.data.items
  const workflows = workflowsQuery.data.items
  const leadAlert = alerts[0]
  const severityTrend = ['critical', 'high', 'medium', 'low'].map((severity) => ({
    label: severity.toUpperCase(),
    value: alerts.filter((alert) => alert.severity === severity).length,
  }))

  return (
    <section className="page-grid">
      <SectionHeader
        actions={<Chip label="Phase 5 data live" tone="info" />}
        eyebrow="Operational overview"
        subtitle="The dashboard now reads live backend overview, alert, and workflow summaries instead of implementation fixtures."
        title="Dashboard"
      />

      <div className="page-toolbar">
        <Tabs activeTabId={activeTabId} onChange={setActiveTabId} tabs={dashboardTabs} />
        <FilterBar activeFilterId={activeFilterId} filters={dashboardFilters} onChange={setActiveFilterId} />
      </div>

      <div className="dashboard-kpis">
        <KpiCard color="#00d4ff" icon={AlertTriangle} label="Active alerts" sublabel="Across triage queues and evidence review" value={String(overview.active_alerts)} />
        <KpiCard color="#f59e0b" icon={ShieldCheck} label="High-risk entities" sublabel="Entities currently above high-risk thresholds" value={String(overview.high_risk_entities)} />
        <KpiCard color="#00e676" icon={Database} label="Entities monitored" sublabel="Entities available in the seeded investigation graph" value={String(overview.entities_monitored)} />
        <KpiCard color="#a855f7" icon={Activity} label="Workflow runs" sublabel="Recent ingestion and analytics pipeline activity" value={String(workflows.length)} />
      </div>

      <div className="dashboard-panels">
        <ChartFrame
          eyebrow="Alert operations"
          footer={<Chip label={`${leadAlert?.entity_label ?? 'No alerts'} lead entity`} tone="default" />}
          subtitle="Current queue composition by severity from the alerts API."
          title="Severity Mix"
        >
          <TrendBars color="#00d4ff" data={severityTrend} />
        </ChartFrame>

        <Card>
          <div className="metric-stack">
            <div className="metric-row">
              <span className="metric-row__label">Lead queue item</span>
              {leadAlert ? <RiskBadge score={Math.round(leadAlert.confidence * 100)} /> : <Chip label="No alerts" tone="default" />}
            </div>
            <ConfidenceBar color="#ff4040" value={leadAlert ? Math.round(leadAlert.confidence * 100) : 0} />
            <div className="metric-row">
              <span className="metric-row__label">Workflow state</span>
              <Chip label={workflows[0]?.status ?? 'idle'} tone={workflows[0]?.status === 'running' ? 'warning' : 'success'} />
            </div>
            <div className="metric-row">
              <span className="metric-row__label">Open cases</span>
              <Chip label={String(overview.open_cases)} tone="network" />
            </div>
          </div>
        </Card>
      </div>

      {leadAlert ? (
        <Card>
          <div className="metric-stack">
            <div className="metric-row metric-row--stacked">
              <strong>{leadAlert.entity_label}</strong>
              <span className="metric-row__label">{leadAlert.reasoning}</span>
            </div>
            <div className="alert-row-card__meta">
              {leadAlert.tags.map((tag) => (
                <Chip key={tag} label={tag.replace(/-/g, ' ')} tone="info" />
              ))}
            </div>
          </div>
        </Card>
      ) : (
        <EmptyState description="No alerts are currently available from the backend feed." title="Queue is empty" />
      )}
    </section>
  )
}