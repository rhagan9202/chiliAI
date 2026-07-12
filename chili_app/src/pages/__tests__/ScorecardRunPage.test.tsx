import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { HousingInstallationsResponse, ScorecardRunResponse } from '../../api/contracts'
import { ApiError } from '../../lib/apiClient'
import { ScorecardRunPage } from '../ScorecardRunPage'

const mocks = vi.hoisted(() => ({
  exportScorecardRun: vi.fn(),
  useHousingInstallations: vi.fn(),
  useScorecardRun: vi.fn(),
}))

vi.mock('../../api/scorecards', () => ({
  exportScorecardRun: mocks.exportScorecardRun,
  useScorecardRun: mocks.useScorecardRun,
}))

vi.mock('../../api/housing', () => ({
  useHousingInstallations: mocks.useHousingInstallations,
}))

const installations: HousingInstallationsResponse = {
  period_start: '2026-06-01',
  period_end: '2026-06-30',
  total: 1,
  items: [
    {
      installation_id: 'edwards',
      name: 'Edwards AFB',
      majcom: 'AFMC',
      state: 'CA',
      status: 'critical',
      open_work_orders: 95,
      overdue_work_orders: 30,
      satisfaction_survey_count: 1,
      uh_authorized_units: 1200,
      mfh_authorized_units: 800,
      occupancy_rate: 0.82,
    },
  ],
  map_points: [],
}

const run: ScorecardRunResponse = {
  id: 'run-edwards',
  knowledge_base_id: 'kb-housing',
  template_id: 'installation-health',
  template_name: 'Installation Health',
  scope_type: 'installation',
  scope_id: 'edwards',
  period_start: '2026-06-01',
  period_end: '2026-06-30',
  overall_health: 'warn',
  status: 'generated',
  source_snapshot_hash: 'snapshot-1',
  created_at: '2026-06-30T12:00:00Z',
  updated_at: '2026-06-30T12:00:00Z',
  sections: [
    {
      id: 'occupancy',
      label: 'Occupancy & utilization',
      metrics: [
        {
          metric_id: 'occupancy-rate',
          label: 'Occupancy rate',
          value: 0.82,
          unit: 'percent',
          health: 'warn',
          completeness: 'complete',
          housing_category: 'MFH',
          description: 'Occupied units divided by total available units.',
          citations: [
            {
              citation_id: 'cit-1',
              feed_name: 'umd_feed',
              record_id: 'rec-42',
              field: 'occupied_units',
            },
          ],
          warnings: [],
        },
        {
          metric_id: 'work-order-backlog',
          label: 'Work order backlog',
          value: null,
          unit: 'count',
          health: 'incomplete',
          completeness: 'missing_source',
          housing_category: 'UH',
          description: '',
          citations: [],
          warnings: ['Work order feed has no rows for this period.'],
        },
      ],
    },
  ],
}

function querySuccess<T>(data: T) {
  return { isLoading: false, isError: false, error: null, data }
}

function renderPage(initialEntry = '/scorecards/run-edwards?kb=kb-housing') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route element={<ScorecardRunPage />} path="/scorecards/:runId" />
      </Routes>
    </MemoryRouter>,
  )
}

describe('ScorecardRunPage', () => {
  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset())
    mocks.useScorecardRun.mockReturnValue(querySuccess(run))
    mocks.useHousingInstallations.mockReturnValue(querySuccess(installations))
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders the run header, sections, metric values, citations, and description affordance', () => {
    renderPage()

    expect(screen.getByRole('heading', { name: 'Installation Health' })).toBeInTheDocument()
    expect(mocks.useScorecardRun).toHaveBeenCalledWith('kb-housing', 'run-edwards')
    // Installation name resolved from scope_id in header subtitle and summary.
    const summary = screen.getByRole('region', { name: 'Run summary' })
    expect(within(summary).getByText('Edwards AFB')).toBeInTheDocument()
    expect(within(summary).getByText('overall warn')).toBeInTheDocument()
    expect(within(summary).getByText('generated')).toBeInTheDocument()
    expect(within(summary).getByText('Jun 1, 2026 – Jun 30, 2026')).toBeInTheDocument()

    const section = screen.getByRole('region', { name: 'Occupancy & utilization' })
    expect(within(section).getByText('2 metrics')).toBeInTheDocument()
    expect(within(section).getByText('Occupancy rate')).toBeInTheDocument()
    expect(within(section).getByText('82%')).toBeInTheDocument()
    expect(within(section).getByText('Military family housing')).toBeInTheDocument()

    const citations = within(section).getByRole('list', { name: 'Citations for Occupancy rate' })
    expect(within(citations).getByText('umd_feed')).toBeInTheDocument()
    expect(within(citations).getByText('rec-42 · occupied_units')).toBeInTheDocument()

    const description = within(section).getByText('How this metric is computed')
    fireEvent.click(description)
    expect(
      within(section).getByText('Occupied units divided by total available units.'),
    ).toBeInTheDocument()

    const backLink = screen.getByRole('link', { name: 'Back to Edwards AFB' })
    expect(backLink).toHaveAttribute('href', '/housing?installation=edwards')
  })

  it('marks incomplete metrics visibly with a nullable-safe value', () => {
    renderPage()

    const section = screen.getByRole('region', { name: 'Occupancy & utilization' })
    expect(within(section).getByText('Work order backlog')).toBeInTheDocument()
    expect(within(section).getByText('n/a')).toBeInTheDocument()
    expect(within(section).getByText('source missing')).toBeInTheDocument()
    expect(within(section).getByText('incomplete')).toBeInTheDocument()

    const warnings = within(section).getByRole('list', { name: 'Warnings for Work order backlog' })
    expect(
      within(warnings).getByText('Work order feed has no rows for this period.'),
    ).toBeInTheDocument()
    expect(within(section).getByText('No citations recorded')).toBeInTheDocument()
  })

  it('renders a failed run honestly with a prominent alert', () => {
    mocks.useScorecardRun.mockReturnValue(
      querySuccess({ ...run, status: 'failed' as const, overall_health: 'incomplete' as const, sections: [] }),
    )

    renderPage()

    const banner = screen.getByRole('alert')
    expect(within(banner).getByText('This scorecard run failed')).toBeInTheDocument()
    const summary = screen.getByRole('region', { name: 'Run summary' })
    expect(within(summary).getByText('failed')).toBeInTheDocument()
    expect(screen.getByText('The failed run recorded no metric sections.')).toBeInTheDocument()
  })

  it('flags superseded runs', () => {
    mocks.useScorecardRun.mockReturnValue(querySuccess({ ...run, status: 'superseded' as const }))

    renderPage()

    expect(screen.getByText('Superseded run')).toBeInTheDocument()
    expect(
      screen.getByText('A newer run replaces this scorecard for the same scope and period.'),
    ).toBeInTheDocument()
  })

  it('downloads exports through the export endpoint as client-side files', async () => {
    mocks.exportScorecardRun.mockResolvedValue({
      run_id: 'run-edwards',
      format: 'markdown',
      content: '# Installation Health',
    })
    const createObjectURL = vi.fn(() => 'blob:scorecard')
    const revokeObjectURL = vi.fn()
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectURL })
    const anchorClick = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => undefined)

    renderPage()

    fireEvent.click(screen.getByRole('button', { name: 'Download Markdown' }))

    await waitFor(() => {
      expect(mocks.exportScorecardRun).toHaveBeenCalledWith('kb-housing', 'run-edwards', 'markdown')
    })
    await waitFor(() => {
      expect(anchorClick).toHaveBeenCalledTimes(1)
    })
    expect(createObjectURL).toHaveBeenCalledTimes(1)
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:scorecard')
  })

  it('requests JSON exports with the json format', async () => {
    mocks.exportScorecardRun.mockResolvedValue({
      run_id: 'run-edwards',
      format: 'json',
      content: '{}',
    })
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:json') })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)

    renderPage()

    fireEvent.click(screen.getByRole('button', { name: 'Download JSON' }))

    await waitFor(() => {
      expect(mocks.exportScorecardRun).toHaveBeenCalledWith('kb-housing', 'run-edwards', 'json')
    })
  })

  it('guides the user when the knowledge base context is missing', () => {
    renderPage('/scorecards/run-edwards')

    expect(screen.getByText('Missing knowledge base context')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back to housing dashboard' })).toHaveAttribute(
      'href',
      '/housing',
    )
    expect(mocks.useScorecardRun).toHaveBeenCalledWith(null, 'run-edwards')
  })

  it('renders a not-found state for unknown runs', () => {
    mocks.useScorecardRun.mockReturnValue({
      isLoading: false,
      isError: true,
      error: new ApiError(404, 'run not found', null),
      data: undefined,
    })

    renderPage()

    expect(screen.getByText('Scorecard run not found')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back to housing dashboard' })).toBeInTheDocument()
  })

  it('renders loading and error states per app idiom', () => {
    mocks.useScorecardRun.mockReturnValue({
      isLoading: true,
      isError: false,
      error: null,
      data: undefined,
    })
    const { unmount } = renderPage()
    expect(screen.getByText('Loading scorecard run')).toBeInTheDocument()
    unmount()

    mocks.useScorecardRun.mockReturnValue({
      isLoading: false,
      isError: true,
      error: new ApiError(500, 'boom', null),
      data: undefined,
    })
    renderPage()
    expect(
      screen.getByText('The scorecard run could not be loaded from the API.'),
    ).toBeInTheDocument()
  })
})
