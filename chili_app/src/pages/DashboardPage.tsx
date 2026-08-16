import { Activity, AlertTriangle, Database, ShieldCheck } from 'lucide-react'
import type { ReactNode } from 'react'
import { useState } from 'react'
import { Link } from 'react-router'

import { useAlerts } from '../api/alerts'
import { useAnalyticsOverview, useGnnClusters, useMetricTimeseries, useRiskProjections } from '../api/analytics'
import { useDomainFeatures } from '../api/config'
import { useWorkflows } from '../api/workflows'
import { TrendBars } from '../components/charts/TrendBars'
import { ChartFrame } from '../components/charts/ChartFrame'
import { Chip } from '../components/ui/Chip'
import { ConfidenceBar } from '../components/ui/ConfidenceBar'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { Card } from '../components/ui/Card'
import { KpiCard } from '../components/ui/KpiCard'
import { LoadingState } from '../components/ui/LoadingState'
import { RiskBadge } from '../components/ui/RiskBadge'
import { SectionHeader } from '../components/ui/SectionHeader'
import { StatusPill } from '../components/ui/StatusPill'
import { Tabs } from '../components/ui/Tabs'
import { statusToneForValue } from '../components/ui/statusPill'
import { useActiveKnowledgeBase } from '../hooks/useActiveKnowledgeBase'
import { flagLabelFor } from '../utils/flagLabel'
import { KNOWLEDGE_BASES_ROUTE, knowledgeBaseWorkspacePath } from '../utils/knowledgeBaseRoutes'
import { backlogTrend, queueHealth } from '../utils/queueHealth'
import { countTone } from '../utils/severity'
import { clusterColorFor } from '../utils/graphStyles'
import { triageNumeralColor } from '../utils/triage'
import './pages.css'

/** The window the backlog trend covers; stated on the chart, not implied. */
const TREND_DAYS = 30

const dashboardTabs = [
  { id: 'overview', label: 'Overview' },
  { id: 'queue', label: 'Queue Health' },
  { id: 'policy', label: 'Policy Signals' },
]

function formatEntityType(entityType: string) {
  return entityType
    .split(/[_-]/g)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

function formatRiskEntityLabel(entityType: string, entityId: string) {
  return `${formatEntityType(entityType) || 'Entity'} ${entityId}`
}

function formatProjectionStatus(status: string) {
  return status
    .split(/[_-]/g)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

function formatRiskProjectionLabel({
  entityType,
  entityId,
  status,
  scoredAt,
  typologyIds,
}: {
  entityType: string
  entityId: string
  status: string
  scoredAt: string
  typologyIds?: string[]
}) {
  const parts = [
    formatRiskEntityLabel(entityType, entityId),
    formatProjectionStatus(status),
    typologyIds?.[0],
    `Scored ${new Date(scoredAt).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}`,
  ].filter(Boolean)
  return parts.join(' · ')
}

// Ordered by what the headline should tell an operator, which is not the same
// as the lifecycle order. `awaiting_approval` sits above `queued` because a
// parked run is blocked on a *person* — plausibly the one reading this — while
// a queued run is merely waiting on a worker and needs nobody.
function primaryWorkflowState(workflows: { status: string }[]): string {
  if (workflows.some((workflow) => workflow.status === 'running')) return 'running'
  if (workflows.some((workflow) => workflow.status === 'failed')) return 'failed'
  if (workflows.some((workflow) => workflow.status === 'awaiting_approval')) {
    return 'awaiting_approval'
  }
  if (workflows.some((workflow) => workflow.status === 'queued')) return 'queued'
  return workflows[0]?.status ?? 'idle'
}

function DashboardTabPanel({
  children,
  tabId,
  title,
}: {
  children: ReactNode
  tabId: string
  title: string
}) {
  const tabElementId = `dashboard-tab-${tabId}`
  return (
    <div
      aria-labelledby={tabElementId}
      className="dashboard-tabpanel"
      id={`dashboard-tabpanel-${tabId}`}
      role="tabpanel"
    >
      <h3 className="dashboard-tabpanel__title">
        {title}
      </h3>
      {children}
    </div>
  )
}

export function DashboardPage() {
  const [activeTabId, setActiveTabId] = useState('overview')
  const [metricRange] = useState(() => {
    const end = new Date().toISOString()
    const start = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString()
    return { start, end }
  })
  const {
    activeKnowledgeBaseId,
    knowledgeBases,
    isLoading: knowledgeBasesLoading,
    isError: knowledgeBasesError,
  } = useActiveKnowledgeBase()
  // Scoped to the workspace KB (UXA-408) so the KPI tiles report the same
  // corpus as every other panel on the page, and refetch when it changes.
  const overviewQuery = useAnalyticsOverview(activeKnowledgeBaseId)
  const alertsQuery = useAlerts({ knowledgeBaseId: activeKnowledgeBaseId ?? undefined })
  const workflowsQuery = useWorkflows()
  const domainFeaturesQuery = useDomainFeatures()
  const capabilities = domainFeaturesQuery.data?.capabilities
  // Domain scoping and the ready-KB preference now live in the shared workspace
  // resolver, so every page agrees on which knowledge base is being read.
  // The workspace may legitimately point at a knowledge base that is still
  // building — you can still browse its cases and alerts. The analytics panels
  // below cannot: risk projections, clusters and timeseries only exist once ingestion
  // has finished, so they stay empty until the active KB is ready.
  const workspaceKnowledgeBase =
    knowledgeBases.find((kb) => kb.id === activeKnowledgeBaseId) ?? null
  const activeKnowledgeBase =
    workspaceKnowledgeBase?.status === 'ready' ? workspaceKnowledgeBase : null
  const riskProjectionsQuery = useRiskProjections(
    activeKnowledgeBase ? { knowledgeBaseId: activeKnowledgeBase.id, limit: 5, offset: 0 } : null,
  )
  const gnnClustersQuery = useGnnClusters(activeKnowledgeBase?.id ?? null)
  const metricTimeseriesQuery = useMetricTimeseries(
    activeKnowledgeBase
      ? {
          knowledgeBaseId: activeKnowledgeBase.id,
          metric: 'claim_volume',
          start: metricRange.start,
          end: metricRange.end,
        }
      : null,
  )

  if (overviewQuery.isLoading || alertsQuery.isLoading || workflowsQuery.isLoading || knowledgeBasesLoading) {
    return <LoadingState label="Loading dashboard telemetry" />
  }

  if (overviewQuery.isError || alertsQuery.isError || workflowsQuery.isError || knowledgeBasesError) {
    return <ErrorState description="Dashboard metrics could not be loaded from the API." />
  }

  if (!overviewQuery.data || !alertsQuery.data || !workflowsQuery.data) {
    return <LoadingState label="Waiting for dashboard data" />
  }

  const overview = overviewQuery.data
  const alerts = alertsQuery.data.items
  const workflows = workflowsQuery.data.items
  const workflowCounts = {
    queued: workflows.filter((workflow) => workflow.status === 'queued').length,
    running: workflows.filter((workflow) => workflow.status === 'running').length,
    failed: workflows.filter((workflow) => workflow.status === 'failed').length,
    completed: workflows.filter((workflow) => workflow.status === 'completed').length,
    awaitingApproval: workflows.filter(
      (workflow) => workflow.status === 'awaiting_approval',
    ).length,
  }
  const workflowState = primaryWorkflowState(workflows)
  const riskProjections = riskProjectionsQuery.data?.items ?? []
  const clusters = gnnClustersQuery.data?.clusters ?? []
  const metricTrend = (metricTimeseriesQuery.data?.points ?? []).map((point) => ({
    label: new Date(point.observed_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
    value: point.value,
  }))
  const policySignalsLoading = Boolean(activeKnowledgeBase) && (
    riskProjectionsQuery.isLoading || gnnClustersQuery.isLoading || metricTimeseriesQuery.isLoading
  )
  const policySignalsError = Boolean(activeKnowledgeBase) && (
    riskProjectionsQuery.isError || gnnClustersQuery.isError || metricTimeseriesQuery.isError
  )
  const health = queueHealth(alerts)
  const trend = backlogTrend(alerts, new Date(), TREND_DAYS)
  const leadAlert = alerts[0]
  const severityTrend = ['critical', 'high', 'medium', 'low'].map((severity) => ({
    label: severity.toUpperCase(),
    value: alerts.filter((alert) => alert.severity === severity).length,
  }))

  return (
    <section className="page-grid">
      <SectionHeader
        actions={
          // The domain title is already the top bar's h1. What an analyst
          // cannot otherwise tell is *which* knowledge base these numbers
          // describe (UXA-305).
          <Chip
            label={workspaceKnowledgeBase?.name ?? 'No knowledge base'}
            testId="dashboard-scope"
            title={workspaceKnowledgeBase ? 'These figures cover this knowledge base.' : undefined}
            tone={workspaceKnowledgeBase ? 'info' : 'default'}
          />
        }
        eyebrow="Operational overview"
        subtitle="Where the queue stands right now, what ingestion is doing, and which entities are drawing the most attention."
        title="Dashboard"
      />

      <div className="page-toolbar">
        <Tabs
          activeTabId={activeTabId}
          ariaControlsPrefix="dashboard-tabpanel"
          idPrefix="dashboard-tab"
          onChange={setActiveTabId}
          tabs={dashboardTabs}
        />
      </div>

      <div className="dashboard-kpis">
        <KpiCard color="#00d4ff" icon={AlertTriangle} label="Active alerts" sublabel="Across triage queues and evidence review" to="/alerts" value={String(overview.active_alerts)} />
        <KpiCard color="#f59e0b" icon={ShieldCheck} label="High-risk entities" sublabel="Entities currently above high-risk thresholds" to="/investigation" value={String(overview.high_risk_entities)} />
        <KpiCard color="#00e676" icon={Database} label="Entities monitored" sublabel="Entities available in the active investigation graph" to="/investigation" value={String(overview.entities_monitored)} />
        <KpiCard color="#a855f7" icon={Activity} label="Workflow runs" sublabel="Recent ingestion and analytics pipeline activity" to={activeKnowledgeBaseId ? knowledgeBaseWorkspacePath(activeKnowledgeBaseId, 'runs') : KNOWLEDGE_BASES_ROUTE} value={String(workflows.length)} />
      </div>

      {activeTabId === 'overview' ? (
        <DashboardTabPanel tabId="overview" title="Overview">
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
                  <StatusPill
                    context="Workflow state"
                    label={workflowState.replace(/_/g, ' ')}
                    tone={statusToneForValue(workflowState)}
                  />
                </div>
                <Link className="metric-row" style={{ color: 'inherit', textDecoration: 'none' }} to="/cases">
                  <span className="metric-row__label">Open cases</span>
                  <Chip label={String(overview.open_cases)} tone="network" />
                </Link>
              </div>
            </Card>
          </div>

          {leadAlert ? (
            <Card>
              <div className="triage-row">
                <div
                  className="triage-row__numeral"
                  data-testid="triage-numeral"
                  style={{ color: triageNumeralColor(leadAlert.severity) }}
                >
                  {Math.round(leadAlert.confidence * 100)}
                </div>
                <div className="metric-stack">
                  <div className="metric-row metric-row--stacked">
                    <strong>{leadAlert.entity_label}</strong>
                    <span className="flag-label">
                      {flagLabelFor({ tags: leadAlert.tags ?? [], severity: leadAlert.severity })}
                    </span>
                    <span className="metric-row__label">{leadAlert.reasoning}</span>
                  </div>
                  <div className="alert-row-card__meta">
                    {(leadAlert.tags ?? []).map((tag) => (
                      <Chip key={tag} label={tag.replace(/-/g, ' ')} tone="info" />
                    ))}
                  </div>
                  <Link
                    aria-label={`Investigate ${leadAlert.entity_label}`}
                    className="page-button page-button--sm page-button--secondary"
                    to={`/investigation/${encodeURIComponent(leadAlert.entity_id)}?kb=${encodeURIComponent(leadAlert.knowledge_base_id)}`}
                  >
                    Investigate
                  </Link>
                </div>
              </div>
            </Card>
          ) : (
            <EmptyState description="Nothing has been flagged in this knowledge base yet." title="Queue is empty" />
          )}
        </DashboardTabPanel>
      ) : null}

      {activeTabId === 'queue' ? (
        <DashboardTabPanel tabId="queue" title="Queue Health">
          <div className="dashboard-panels">
            <Card>
              <div className="metric-stack">
                {/* Counts alone never answered "is the queue keeping up?"
                    (UXA-402). The rows that merely repeated the KPI band and
                    the unexplained "Open" service words are gone. */}
                <h4 className="dashboard-panel__heading">Is the queue keeping up?</h4>
                <div className="metric-row">
                  <span className="metric-row__label">Waiting on triage</span>
                  <Chip
                    label={String(health.openCount)}
                    title="Alerts still open or under investigation."
                    tone={countTone(health.openCount, 'warning')}
                  />
                </div>
                <div className="metric-row">
                  <span className="metric-row__label">Oldest still waiting</span>
                  <Chip
                    label={health.oldestOpenAge ?? 'Nothing waiting'}
                    title="How long the least-recently raised untouched alert has been in the queue."
                    tone={health.oldestOpenAge ? 'warning' : 'success'}
                  />
                </div>
                <div className="metric-row">
                  <span className="metric-row__label">Median time to acknowledge</span>
                  <Chip
                    label={health.medianTimeToAcknowledge ?? 'Not yet measurable'}
                    title="Median, so one stale outlier does not move the typical figure."
                    tone="info"
                  />
                </div>
                <div className="metric-row">
                  <span className="metric-row__label">Dispositioned (last 24h)</span>
                  <Chip
                    label={String(health.dispositionedLastDay)}
                    title="Alerts acknowledged, resolved or dismissed in the last day."
                    tone={countTone(health.dispositionedLastDay, 'success')}
                  />
                </div>
                <ChartFrame
                  eyebrow={`Alerts raised · last ${TREND_DAYS} days`}
                  title="Backlog trend"
                >
                  <TrendBars color="#00d4ff" data={trend} />
                </ChartFrame>
              </div>
            </Card>

            <Card>
              <div className="metric-stack">
                <h4 className="dashboard-panel__heading">Pipeline activity</h4>
                <div className="metric-row">
                  <span className="metric-row__label">Queued workflows</span>
                  <StatusPill context="Queued workflows" label={String(workflowCounts.queued)} tone="default" />
                </div>
                <div className="metric-row">
                  <span className="metric-row__label">Awaiting approval</span>
                  <StatusPill context="Awaiting approval" label={String(workflowCounts.awaitingApproval)} tone={countTone(workflowCounts.awaitingApproval, 'info')} />
                </div>
                <div className="metric-row">
                  <span className="metric-row__label">Running workflows</span>
                  <StatusPill context="Running workflows" label={String(workflowCounts.running)} tone={countTone(workflowCounts.running, 'warning')} />
                </div>
                <div className="metric-row">
                  <span className="metric-row__label">Failed workflows</span>
                  <StatusPill context="Failed workflows" label={String(workflowCounts.failed)} tone={countTone(workflowCounts.failed, 'danger')} />
                </div>
                <div className="metric-row">
                  <span className="metric-row__label">Completed workflows</span>
                  <StatusPill context="Completed workflows" label={String(workflowCounts.completed)} tone={countTone(workflowCounts.completed, 'success')} />
                </div>
              </div>
            </Card>
          </div>
        </DashboardTabPanel>
      ) : null}

      {activeTabId === 'policy' ? (
        <DashboardTabPanel tabId="policy" title="Policy Signals">
          {!activeKnowledgeBase ? (
            <EmptyState description="Create or finish syncing a knowledge base to populate risk, graph, and metric summaries." title="No ready knowledge base selected" />
          ) : policySignalsLoading ? (
            <LoadingState label="Loading policy signal analytics" />
          ) : policySignalsError ? (
            <ErrorState description="Policy signal analytics could not be loaded from the API." />
          ) : (
          <div className="dashboard-panels">
            <Card>
              <div className="metric-stack">
                <div className="metric-row metric-row--stacked">
                  <strong>Top risk entities</strong>
                  <span className="metric-row__label">{activeKnowledgeBase.name}</span>
                </div>
                {riskProjections.map((riskProjection) => (
                  <div className="dashboard-summary-row" key={riskProjection.entity_id}>
                    <span>
                      <strong>{riskProjection.entity_id}</strong>
                      <span className="metric-row__label">
                        {formatRiskProjectionLabel({
                          entityType: riskProjection.entity_type,
                          entityId: riskProjection.entity_id,
                          status: riskProjection.status,
                          scoredAt: riskProjection.scored_at,
                          typologyIds: riskProjection.top_typology_ids,
                        })}
                      </span>
                    </span>
                    <RiskBadge score={Math.round(riskProjection.overall_score * 100)} />
                  </div>
                ))}
                {riskProjections.length === 0 ? <EmptyState description="No ranked risk entities are available for this knowledge base." title="No risk projections" /> : null}
              </div>
            </Card>

            {capabilities?.gnn ? (
              <Card>
                <div className="metric-stack">
                  <div className="metric-row metric-row--stacked">
                    <strong>Graph clusters</strong>
                    <span className="metric-row__label">Entities that behave alike</span>
                  </div>
                  {clusters.map((cluster) => {
                    const firstMember = cluster.entity_ids?.[0]
                    return (
                      <div className="dashboard-summary-row" key={cluster.cluster_id}>
                        <span
                          className="cluster-swatch"
                          data-testid="cluster-swatch"
                          style={{ background: clusterColorFor(cluster.cluster_id) }}
                        />
                        <span>
                          <strong>{cluster.label ?? cluster.cluster_id}</strong>
                          <span className="metric-row__label">{cluster.entity_ids?.length ?? 0} entities</span>
                        </span>
                        <span>
                          <Chip label={`${Math.round(cluster.anomaly_score * 100)} anomaly`} tone="warning" />
                          {firstMember ? (
                            <Link
                              to={`/investigation/${encodeURIComponent(firstMember)}?kb=${encodeURIComponent(activeKnowledgeBase.id)}`}
                            >
                              Open in workbench
                            </Link>
                          ) : null}
                        </span>
                      </div>
                    )
                  })}
                  {clusters.length === 0 ? <EmptyState description="No graph clusters are available for this knowledge base." title="No graph clusters" /> : null}
                </div>
              </Card>
            ) : null}
            {metricTrend.length > 0 ? (
              <ChartFrame
                eyebrow="Policy analytics"
                subtitle="Claim volume over the selected 30-day dashboard window."
                title="Metric Trend"
              >
                <TrendBars color="#00e676" data={metricTrend} />
              </ChartFrame>
            ) : null}
          </div>
          )}
        </DashboardTabPanel>
      ) : null}
    </section>
  )
}
