import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type {
  AlertListResponse,
  AnalyticsOverviewResponse,
  GnnClusterResponse,
  KnowledgeBaseListResponse,
  MetricTimeseriesResponse,
  RiskScoreListResponse,
  WorkflowRunListResponse,
} from '../../api/contracts'
import { DashboardPage } from '../DashboardPage'

const mocks = vi.hoisted(() => ({
  useAlerts: vi.fn(),
  useAnalyticsOverview: vi.fn(),
  useGnnClusters: vi.fn(),
  useKnowledgeBases: vi.fn(),
  useMetricTimeseries: vi.fn(),
  useRiskScores: vi.fn(),
  useWorkflows: vi.fn(),
}))

vi.mock('../../api/alerts', () => ({ useAlerts: mocks.useAlerts }))

vi.mock('../../api/analytics', () => ({
  useAnalyticsOverview: mocks.useAnalyticsOverview,
  useGnnClusters: mocks.useGnnClusters,
  useMetricTimeseries: mocks.useMetricTimeseries,
  useRiskScores: mocks.useRiskScores,
}))

vi.mock('../../api/knowledgebases', () => ({ useKnowledgeBases: mocks.useKnowledgeBases }))

vi.mock('../../api/workflows', () => ({ useWorkflows: mocks.useWorkflows }))

const now = '2026-06-15T16:00:00.000Z'

const overview: AnalyticsOverviewResponse = {
  active_alerts: 4,
  high_risk_entities: 2,
  entities_monitored: 12,
  open_cases: 3,
}

const alerts: AlertListResponse = {
  items: [
    {
      id: 'alert-1',
      knowledge_base_id: 'kb-ready',
      entity_id: 'provider-204',
      entity_type: 'provider',
      entity_label: 'Advanced Pain Specialists',
      severity: 'high',
      status: 'open',
      title: 'Provider risk threshold exceeded',
      reasoning: 'Aggregate risk score breached configured threshold.',
      confidence: 0.85,
      evidence_pack_id: 'evidence-001',
      created_at: now,
      tags: ['provider', 'risk-spike'],
    },
    {
      id: 'alert-2',
      knowledge_base_id: 'kb-ready',
      entity_id: 'provider-300',
      entity_type: 'provider',
      entity_label: 'North Billing Group',
      severity: 'medium',
      status: 'open',
      title: 'Utilization changed',
      reasoning: 'Utilization shifted above peer baseline.',
      confidence: 0.62,
      evidence_pack_id: 'evidence-002',
      created_at: now,
      tags: [],
    },
  ],
  page: { page: 1, page_size: 2, total_items: 2 },
}

const workflows: WorkflowRunListResponse = {
  items: [
    {
      id: 'wf-queued',
      knowledge_base_id: 'kb-ready',
      workflow_type: 'ingestion',
      status: 'queued',
      current_step: 'queued',
      started_at: now,
      updated_at: now,
    },
    {
      id: 'wf-running',
      knowledge_base_id: 'kb-ready',
      workflow_type: 'analytics',
      status: 'running',
      current_step: 'risk scoring',
      started_at: now,
      updated_at: now,
    },
    {
      id: 'wf-failed',
      knowledge_base_id: 'kb-ready',
      workflow_type: 'graph_build',
      status: 'failed',
      current_step: 'graph build',
      last_error: 'Graph sync failed',
      started_at: now,
      updated_at: now,
    },
    {
      id: 'wf-completed',
      knowledge_base_id: 'kb-ready',
      workflow_type: 'monitoring',
      status: 'completed',
      current_step: 'done',
      started_at: now,
      updated_at: now,
    },
  ],
  has_more: false,
}

const knowledgeBases: KnowledgeBaseListResponse = {
  items: [
    {
      id: 'kb-draft',
      name: 'Draft KB',
      description: 'Not selected while a ready KB exists.',
      status: 'building',
      document_count: 0,
      entity_count: 0,
      relationship_count: 0,
      created_at: now,
      updated_at: now,
      pending_cleanup: false,
    },
    {
      id: 'kb-ready',
      name: 'Ready KB',
      description: 'Selected for dashboard analytics.',
      status: 'ready',
      document_count: 12,
      entity_count: 48,
      relationship_count: 96,
      created_at: now,
      updated_at: now,
      pending_cleanup: false,
    },
  ],
  total: 2,
}

const riskScores: RiskScoreListResponse = {
  knowledge_base_id: 'kb-ready',
  total: 1,
  items: [
    {
      entity_id: 'provider-204',
      entity_type: 'provider',
      overall_score: 0.91,
      risk_level: 'critical',
    },
  ],
}

const clusters: GnnClusterResponse = {
  knowledge_base_id: 'kb-ready',
  clusters: [
    {
      cluster_id: 'cluster-1',
      entity_ids: ['provider-204', 'claim-771', 'claim-772'],
      label: 'Anomalous billing cluster',
      anomaly_score: 0.73,
    },
  ],
}

const metricTimeseries: MetricTimeseriesResponse = {
  knowledge_base_id: 'kb-ready',
  metric_name: 'claim_volume',
  start: '2026-05-16T16:00:00.000Z',
  end: now,
  points: [
    { observed_at: '2026-06-01T00:00:00Z', value: 12 },
    { observed_at: '2026-06-02T00:00:00Z', value: 16 },
  ],
}

function querySuccess<T>(data: T) {
  return { isLoading: false, isError: false, data }
}

function queryLoading() {
  return { isLoading: true, isError: false, data: undefined }
}

function queryError() {
  return { isLoading: false, isError: true, data: undefined }
}

function setupDefaultMocks() {
  mocks.useAnalyticsOverview.mockReturnValue(querySuccess(overview))
  mocks.useAlerts.mockReturnValue(querySuccess(alerts))
  mocks.useWorkflows.mockReturnValue(querySuccess(workflows))
  mocks.useKnowledgeBases.mockReturnValue(querySuccess(knowledgeBases))
  mocks.useRiskScores.mockReturnValue(querySuccess(riskScores))
  mocks.useGnnClusters.mockReturnValue(querySuccess(clusters))
  mocks.useMetricTimeseries.mockReturnValue(querySuccess(metricTimeseries))
}

function renderDashboard() {
  return render(
    <MemoryRouter>
      <DashboardPage />
    </MemoryRouter>,
  )
}

function clickTab(name: RegExp) {
  fireEvent.click(screen.getByRole('tab', { name }))
}

function expectMetricRowValue(panel: HTMLElement, label: RegExp, value: string) {
  const labelElement = within(panel).getByText(label)
  const row = labelElement.closest('.metric-row')
  expect(row).not.toBeNull()
  expect(within(row as HTMLElement).getByText(value)).toBeInTheDocument()
}

describe('DashboardPage', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(now))
    Object.values(mocks).forEach((mock) => mock.mockReset())
    setupDefaultMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders KPI cards using the api.contracts shape', () => {
    renderDashboard()

    expect(screen.getByText('Dashboard')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /active alerts/i })).toHaveAccessibleName(/4/)
  })

  it('renders KPI drilldown links', () => {
    renderDashboard()

    const activeAlertsLink = screen.getByRole('link', { name: /active alerts/i })
    expect(activeAlertsLink).toHaveAttribute('href', '/alerts')
    expect(activeAlertsLink).toHaveAccessibleName(/4/)
    expect(activeAlertsLink).toHaveStyle({ display: 'block', height: '100%' })
    expect(activeAlertsLink.firstElementChild).toHaveStyle({ display: 'grid', height: '100%' })

    const openCasesLink = screen.getByRole('link', { name: /open cases/i })
    expect(openCasesLink).toHaveAttribute('href', '/cases')
    expect(openCasesLink).toHaveAccessibleName(/3/)

    expect(screen.getByRole('link', { name: /workflow runs/i })).toHaveAttribute('href', '/knowledge-bases')
    expect(screen.getByRole('link', { name: /high-risk entities/i })).toHaveAttribute('href', '/investigation')
    expect(screen.getByRole('link', { name: /entities monitored/i })).toHaveAttribute('href', '/investigation')
  })

  it('renders the lead alert from the alerts feed', () => {
    renderDashboard()

    expect(screen.getByText('Advanced Pain Specialists')).toBeInTheDocument()
  })

  it('renders queue health counts and direct drilldown links', async () => {
    renderDashboard()

    const queueTab = screen.getByRole('tab', { name: /queue health/i })
    expect(queueTab).toHaveAttribute('id', 'dashboard-tab-queue')
    expect(queueTab).toHaveAttribute('aria-controls', 'dashboard-tabpanel-queue')
    clickTab(/queue health/i)

    const panel = screen.getByRole('tabpanel', { name: /queue health/i })
    expect(panel).toHaveAttribute('aria-labelledby', 'dashboard-tab-queue')
    expectMetricRowValue(panel, /active alerts/i, '4')
    expectMetricRowValue(panel, /open cases/i, '3')
    expectMetricRowValue(panel, /queued workflows/i, '1')
    expectMetricRowValue(panel, /running workflows/i, '1')
    expectMetricRowValue(panel, /failed workflows/i, '1')
    expectMetricRowValue(panel, /completed workflows/i, '1')
    expect(within(panel).getByRole('link', { name: /alerts feed/i })).toHaveAttribute('href', '/alerts')
    expect(within(panel).getByRole('link', { name: /case queue/i })).toHaveAttribute('href', '/cases')
    expect(within(panel).getByRole('link', { name: /knowledge bases/i })).toHaveAttribute('href', '/knowledge-bases')
  })

  it('renders policy signals from the active ready knowledge base', async () => {
    renderDashboard()

    clickTab(/policy signals/i)

    const panel = screen.getByRole('tabpanel', { name: /policy signals/i })
    expect(within(panel).getByText(/top risk entities/i)).toBeInTheDocument()
    expect(within(panel).getByText('Ready KB')).toBeInTheDocument()
    expect(within(panel).getByText('provider-204')).toBeInTheDocument()
    expect(within(panel).getByText('Provider provider-204')).toBeInTheDocument()
    expect(within(panel).getByText('91')).toBeInTheDocument()
    expect(within(panel).getByText(/graph clusters/i)).toBeInTheDocument()
    expect(within(panel).getByText('Anomalous billing cluster')).toBeInTheDocument()
    expect(within(panel).getByText(/3 entities/i)).toBeInTheDocument()
    expect(within(panel).getByText(/73 anomaly/i)).toBeInTheDocument()
    expect(within(panel).getByText(/metric trend/i)).toBeInTheDocument()
    expect(within(panel).getByText(/claim volume/i)).toBeInTheDocument()

    expect(mocks.useRiskScores).toHaveBeenCalledWith({ knowledgeBaseId: 'kb-ready', limit: 5 })
    expect(mocks.useGnnClusters).toHaveBeenCalledWith('kb-ready')
    expect(mocks.useMetricTimeseries).toHaveBeenCalledWith({
      knowledgeBaseId: 'kb-ready',
      metric: 'claim_volume',
      start: '2026-05-16T16:00:00.000Z',
      end: now,
    })
  })

  it('keeps the metric time range stable across tab updates', async () => {
    renderDashboard()

    const firstArgs = mocks.useMetricTimeseries.mock.calls.at(-1)?.[0]
    clickTab(/queue health/i)
    clickTab(/policy signals/i)
    const latestArgs = mocks.useMetricTimeseries.mock.calls.at(-1)?.[0]

    expect(latestArgs).toEqual(firstArgs)
  })

  it('supports arrow-key tab navigation', async () => {
    renderDashboard()

    const overviewTab = screen.getByRole('tab', { name: /overview/i })
    const queueTab = screen.getByRole('tab', { name: /queue health/i })
    const policyTab = screen.getByRole('tab', { name: /policy signals/i })

    overviewTab.focus()
    expect(overviewTab).toHaveFocus()
    expect(overviewTab).toHaveAttribute('tabindex', '0')
    expect(queueTab).toHaveAttribute('tabindex', '-1')

    fireEvent.keyDown(overviewTab, { key: 'ArrowRight' })
    expect(queueTab).toHaveFocus()
    expect(screen.getByRole('tabpanel', { name: /queue health/i })).toBeInTheDocument()

    fireEvent.keyDown(queueTab, { key: 'End' })
    expect(policyTab).toHaveFocus()
    expect(screen.getByRole('tabpanel', { name: /policy signals/i })).toBeInTheDocument()

    fireEvent.keyDown(policyTab, { key: 'ArrowLeft' })
    expect(queueTab).toHaveFocus()
  })

  it('shows policy signals empty state when no knowledge base exists', async () => {
    mocks.useKnowledgeBases.mockReturnValue(querySuccess({ items: [], total: 0 } satisfies KnowledgeBaseListResponse))

    renderDashboard()

    clickTab(/policy signals/i)

    expect(screen.getByRole('tabpanel', { name: /policy signals/i })).toBeInTheDocument()
    expect(screen.getByText(/no ready knowledge base selected/i)).toBeInTheDocument()
    expect(mocks.useRiskScores).toHaveBeenCalledWith(null)
    expect(mocks.useGnnClusters).toHaveBeenCalledWith(null)
    expect(mocks.useMetricTimeseries).toHaveBeenCalledWith(null)
  })

  it('shows policy signals empty state when knowledge bases are not ready', async () => {
    mocks.useKnowledgeBases.mockReturnValue(querySuccess({
      items: [knowledgeBases.items[0]],
      total: 1,
    } satisfies KnowledgeBaseListResponse))

    renderDashboard()

    clickTab(/policy signals/i)

    expect(screen.getByRole('tabpanel', { name: /policy signals/i })).toBeInTheDocument()
    expect(screen.getByText(/no ready knowledge base selected/i)).toBeInTheDocument()
    expect(mocks.useRiskScores).toHaveBeenCalledWith(null)
    expect(mocks.useGnnClusters).toHaveBeenCalledWith(null)
    expect(mocks.useMetricTimeseries).toHaveBeenCalledWith(null)
  })

  it('shows policy signals error state when secondary analytics queries fail', async () => {
    mocks.useRiskScores.mockReturnValue(queryError())

    renderDashboard()

    clickTab(/policy signals/i)

    expect(screen.getByRole('tabpanel', { name: /policy signals/i })).toBeInTheDocument()
    expect(screen.getByText(/policy signal analytics could not be loaded/i)).toBeInTheDocument()
    expect(screen.queryByText(/no risk scores/i)).not.toBeInTheDocument()
  })

  it('shows policy signals loading state while secondary analytics queries load', async () => {
    mocks.useGnnClusters.mockReturnValue(queryLoading())

    renderDashboard()

    clickTab(/policy signals/i)

    expect(screen.getByRole('tabpanel', { name: /policy signals/i })).toBeInTheDocument()
    expect(screen.getByText(/loading policy signal analytics/i)).toBeInTheDocument()
  })
})
