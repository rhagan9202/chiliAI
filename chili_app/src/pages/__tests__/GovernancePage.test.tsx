import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { GovernanceReportResponse } from '../../api/contracts'
import { useAppStore } from '../../stores/appStore'
import { GovernancePage } from '../GovernancePage'

const mocks = vi.hoisted(() => ({
  useDomainConfig: vi.fn(),
  useGovernanceReport: vi.fn(),
  useKnowledgeBases: vi.fn(),
}))

vi.mock('../../api/config', () => ({ useDomainConfig: mocks.useDomainConfig }))
vi.mock('../../api/governance', () => ({ useGovernanceReport: mocks.useGovernanceReport }))
vi.mock('../../api/knowledgebases', () => ({ useKnowledgeBases: mocks.useKnowledgeBases }))

const report: GovernanceReportResponse = {
  knowledge_base_id: 'kb-1',
  domain_name: 'medicare_fraud',
  generated_at: '2026-08-05T18:00:00Z',
  release_ready: false,
  production_versions: [
    {
      component_kind: 'playbook',
      component_id: 'billing-review',
      version: 'v1',
      status: 'published',
      source: 'api_publish',
      approved_by: 'supervisor-1',
      approved_at: '2026-08-05T17:00:00Z',
    },
    {
      component_kind: 'workflow_definition',
      component_id: 'provider-review',
      version: 'v2',
      status: 'approved',
      source: 'workflow_definition',
      approved_by: 'supervisor-1',
      approved_at: '2026-08-05T17:30:00Z',
    },
  ],
  pending_approvals: [
    {
      approval_kind: 'workflow_definition',
      resource_id: 'release-candidate',
      version: 'v3',
      status: 'draft',
      requested_by: 'analyst-1',
      updated_at: '2026-08-05T17:45:00Z',
    },
  ],
  feedback_trends: {
    total_reviews: 7,
    challenged_reviews: 2,
    approved_reviews: 3,
    state_counts: { approved: 3, misleading: 1, unsupported: 1, useful: 2 },
  },
  eval_runs: [
    {
      run_id: 'kb-1:model:risk-scorer:candidate-v2:tn-demo-1pct',
      knowledge_base_id: 'kb-1',
      artifact_kind: 'model',
      artifact_id: 'risk-scorer',
      artifact_version: 'candidate-v2',
      baseline_version: 'prod-v1',
      dataset_id: 'tn-demo-1pct',
      status: 'candidate',
      metrics: [
        {
          name: 'precision',
          baseline_value: 0.72,
          candidate_value: 0.78,
          threshold: 0,
          direction: 'higher',
          delta: 0.06,
          passed: true,
        },
      ],
      drift_summary: {
        metric_count: 1,
        failed_metric_count: 0,
        max_abs_delta: 0.06,
      },
      affected_alert_ids: ['alert-1'],
      affected_case_ids: ['case-1'],
      created_by: 'model-owner-1',
      created_at: '2026-08-05T17:50:00Z',
      approval: null,
    },
  ],
  release_blockers: [
    {
      severity: 'blocking',
      code: 'pending_workflow_approval',
      message: 'Approve or retire workflow definition release-candidate:v3 before release.',
      resource_type: 'workflow_definition',
      resource_id: 'release-candidate:v3',
    },
    {
      severity: 'warning',
      code: 'challenged_explanations',
      message: '2 challenged explanation review(s) should be reviewed before release.',
      resource_type: 'evidence_review',
      resource_id: 'kb-1',
    },
  ],
}

function setup() {
  mocks.useDomainConfig.mockReturnValue({ data: { domain: { name: 'medicare_fraud' } } })
  mocks.useKnowledgeBases.mockReturnValue({
    data: {
      items: [
        {
          id: 'kb-1',
          name: 'Governance KB',
          domain: 'medicare_fraud',
          status: 'ready',
          updated_at: '2026-08-05T18:00:00Z',
        },
      ],
    },
    isError: false,
    isLoading: false,
  })
  mocks.useGovernanceReport.mockReturnValue({
    data: report,
    isError: false,
    isLoading: false,
  })
}

function renderPage(route = '/governance?kb=kb-1') {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <GovernancePage />
    </MemoryRouter>,
  )
}

describe('GovernancePage', () => {
  beforeEach(() => {
    window.localStorage.clear()
    useAppStore.setState({ activeKnowledgeBaseId: null })
    vi.clearAllMocks()
    setup()
  })

  it('renders no-KB state', () => {
    mocks.useKnowledgeBases.mockReturnValue({
      data: { items: [] },
      isError: false,
      isLoading: false,
    })

    renderPage('/governance')

    expect(screen.getByText('No knowledge base selected')).toBeInTheDocument()
    expect(mocks.useGovernanceReport).toHaveBeenCalledWith(null)
  })

  it('renders loading and error states', () => {
    mocks.useGovernanceReport.mockReturnValue({
      data: undefined,
      isError: false,
      isLoading: true,
    })
    const loading = renderPage()
    expect(screen.getByRole('status')).toHaveTextContent('Loading governance report')
    loading.unmount()

    mocks.useGovernanceReport.mockReturnValue({
      data: undefined,
      isError: true,
      isLoading: false,
    })
    renderPage()
    expect(screen.getByRole('alert')).toHaveTextContent('Governance report could not be loaded')
  })

  it('renders release readiness, versions, approvals, feedback, and blockers', () => {
    renderPage()

    expect(screen.getByRole('heading', { name: 'Governance' })).toBeInTheDocument()
    expect(screen.getByLabelText('Release readiness: blocked')).toBeInTheDocument()
    expect(screen.getByLabelText('Published versions: 2')).toBeInTheDocument()
    expect(screen.getByLabelText('Pending approvals: 1')).toBeInTheDocument()
    expect(screen.getByLabelText('Challenged explanations: 2')).toBeInTheDocument()
    expect(screen.getByLabelText('Evaluation runs: 1')).toBeInTheDocument()

    const versions = screen.getByRole('region', { name: 'Production versions' })
    expect(within(versions).getByText('billing-review')).toBeInTheDocument()
    expect(within(versions).getByText('provider-review')).toBeInTheDocument()

    const approvals = screen.getByRole('region', { name: 'Pending approvals' })
    expect(within(approvals).getByText('release-candidate')).toBeInTheDocument()

    const blockers = screen.getByRole('region', { name: 'Release blockers' })
    expect(within(blockers).getByText('pending_workflow_approval')).toBeInTheDocument()
    expect(within(blockers).getByText('challenged_explanations')).toBeInTheDocument()

    const evaluations = screen.getByRole('region', { name: 'Evaluation runs' })
    expect(within(evaluations).getByText('risk-scorer')).toBeInTheDocument()
    expect(within(evaluations).getByText('candidate-v2 vs prod-v1')).toBeInTheDocument()
    expect(within(evaluations).getByText('precision')).toBeInTheDocument()
    expect(within(evaluations).getAllByText('+0.060')).toHaveLength(2)
  })
})
