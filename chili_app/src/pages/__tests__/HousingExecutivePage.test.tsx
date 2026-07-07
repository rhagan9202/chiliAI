import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type {
  HousingInstallationResponse,
  HousingInstallationsResponse,
  HousingOverviewResponse,
  KnowledgeBaseListResponse,
  ScorecardRunListResponse,
  ScorecardTemplateListResponse,
} from '../../api/contracts'
import { HousingExecutivePage } from '../HousingExecutivePage'

const mocks = vi.hoisted(() => ({
  useGenerateScorecardRun: vi.fn(),
  useHousingInstallations: vi.fn(),
  useHousingOverview: vi.fn(),
  useKnowledgeBases: vi.fn(),
  useScorecardRuns: vi.fn(),
  useScorecardTemplates: vi.fn(),
}))

vi.mock('../../api/housing', () => ({
  useHousingInstallations: mocks.useHousingInstallations,
  useHousingOverview: mocks.useHousingOverview,
}))

vi.mock('../../api/knowledgebases', () => ({
  useKnowledgeBases: mocks.useKnowledgeBases,
}))

vi.mock('../../api/scorecards', () => ({
  useGenerateScorecardRun: mocks.useGenerateScorecardRun,
  useScorecardRuns: mocks.useScorecardRuns,
  useScorecardTemplates: mocks.useScorecardTemplates,
}))

const overview: HousingOverviewResponse = {
  period_start: '2026-06-01',
  period_end: '2026-06-30',
  portfolio_summary: {
    total_installations: 2,
    installations_reporting: 2,
    open_work_orders: 139,
    overdue_work_orders: 26,
    occupancy_rate: 0.91,
    resident_satisfaction: 0.78,
  },
  executive_kpis: [
    { id: 'critical-bases', label: 'Critical bases', status: 'critical', value: 1, unit: 'count' },
    { id: 'watch-bases', label: 'Watch bases', status: 'watch', value: 1, unit: 'count' },
  ],
}

const installations: HousingInstallationsResponse = {
  period_start: '2026-06-01',
  period_end: '2026-06-30',
  total: 2,
  items: [
    {
      installation_id: 'barksdale',
      name: 'Barksdale AFB',
      majcom: 'AFGSC',
      state: 'LA',
      status: 'watch',
      open_work_orders: 44,
      occupancy_rate: 0.88,
    },
    {
      installation_id: 'edwards',
      name: 'Edwards AFB',
      majcom: 'AFMC',
      state: 'CA',
      status: 'critical',
      open_work_orders: 95,
      occupancy_rate: 0.82,
    },
  ],
  map_points: [
    {
      installation_id: 'barksdale',
      name: 'Barksdale AFB',
      latitude: 32.5018,
      longitude: -93.6627,
      status: 'watch',
    },
    {
      installation_id: 'edwards',
      name: 'Edwards AFB',
      latitude: 34.9054,
      longitude: -117.8837,
      status: 'critical',
    },
  ],
}

const filterableInstallations: HousingInstallationsResponse = {
  period_start: '2026-06-01',
  period_end: '2026-06-30',
  total: 3,
  items: [
    {
      installation_id: 'barksdale',
      name: 'Barksdale AFB',
      majcom: 'AFGSC',
      branch: 'USAF',
      state: 'LA',
      status: 'watch',
      open_work_orders: 44,
      occupancy_rate: 0.88,
    },
    {
      installation_id: 'edwards',
      name: 'Edwards AFB',
      majcom: 'AFMC',
      branch: 'USAF',
      state: 'CA',
      status: 'critical',
      open_work_orders: 95,
      occupancy_rate: 0.82,
    },
    {
      installation_id: 'patrick',
      name: 'Patrick SFB',
      majcom: 'SSC',
      branch: 'USSF',
      state: 'FL',
      status: 'ok',
      open_work_orders: 12,
      occupancy_rate: 0.93,
    },
  ],
  map_points: [
    {
      installation_id: 'barksdale',
      name: 'Barksdale AFB',
      branch: 'USAF',
      latitude: 32.5018,
      longitude: -93.6627,
      status: 'watch',
    },
    {
      installation_id: 'edwards',
      name: 'Edwards AFB',
      branch: 'USAF',
      latitude: 34.9054,
      longitude: -117.8837,
      status: 'critical',
    },
    {
      installation_id: 'patrick',
      name: 'Patrick SFB',
      branch: 'USSF',
      latitude: 28.2349,
      longitude: -80.6101,
      status: 'ok',
    },
  ],
}

const knowledgeBases: KnowledgeBaseListResponse = {
  total: 1,
  items: [
    {
      id: 'kb-housing',
      name: 'Housing KB',
      description: 'Ready housing evidence.',
      status: 'ready',
      document_count: 10,
      entity_count: 20,
      relationship_count: 30,
      created_at: '2026-06-01T00:00:00Z',
      updated_at: '2026-06-15T00:00:00Z',
      pending_cleanup: false,
    },
  ],
}

const templates: ScorecardTemplateListResponse = {
  items: [
    {
      id: 'installation-health',
      name: 'Installation Health',
      category: 'combined',
      scope: 'installation',
      period: 'monthly',
    },
  ],
}

const runs: ScorecardRunListResponse = {
  total: 1,
  limit: 5,
  offset: 0,
  items: [
    {
      id: 'run-edwards',
      knowledge_base_id: 'kb-housing',
      template_id: 'installation-health',
      template_name: 'Installation Health',
      scope_type: 'installation',
      scope_id: 'edwards',
      period_start: '2026-06-01',
      period_end: '2026-06-30',
      overall_health: 'fail',
      status: 'generated',
      source_snapshot_hash: 'snapshot-1',
      created_at: '2026-06-30T12:00:00Z',
      updated_at: '2026-06-30T12:00:00Z',
      sections: [],
    },
  ],
}

function querySuccess<T>(data: T) {
  return { isLoading: false, isError: false, data }
}

function renderPage(initialEntry = '/housing') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <HousingExecutivePage />
    </MemoryRouter>,
  )
}

describe('HousingExecutivePage', () => {
  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset())
    mocks.useHousingOverview.mockReturnValue(querySuccess(overview))
    mocks.useHousingInstallations.mockReturnValue(querySuccess(installations))
    mocks.useKnowledgeBases.mockReturnValue(querySuccess(knowledgeBases))
    mocks.useScorecardTemplates.mockReturnValue(querySuccess(templates))
    mocks.useScorecardRuns.mockReturnValue(querySuccess(runs))
    mocks.useGenerateScorecardRun.mockReturnValue({ isPending: false, mutate: vi.fn() })
  })

  it('renders the map-led housing operating picture with contextual RAG launch', () => {
    renderPage()

    expect(screen.getByRole('heading', { name: 'Housing Supply Health' })).toBeInTheDocument()
    expect(screen.getByLabelText('Installation health map')).toBeInTheDocument()
    expect(screen.getAllByText('Edwards AFB').length).toBeGreaterThan(0)

    const detail = screen.getByRole('region', { name: 'Installation detail' })
    expect(within(detail).getByText('Barksdale AFB')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', {
      name: 'Select Edwards AFB on map, critical status, 95 open work orders',
    }))

    expect(within(detail).getByText('Edwards AFB')).toBeInTheDocument()
    expect(within(detail).getByText('AFMC')).toBeInTheDocument()
    expect(screen.getAllByText('Jun 1 - Jun 30').length).toBeGreaterThan(0)

    const ragLink = within(detail).getByRole('link', { name: /ask ai about edwards afb/i })
    expect(ragLink).toHaveAttribute('href', expect.stringContaining('/rag-chat?'))
    expect(ragLink).toHaveAttribute('href', expect.stringContaining('source=housing'))
    expect(ragLink).toHaveAttribute('href', expect.stringContaining('installation=edwards'))
    expect(ragLink).toHaveAttribute('href', expect.stringContaining('kb=kb-housing'))
  })

  it('uses route-backed installation context when present', () => {
    renderPage('/housing?installation=edwards')

    const detail = screen.getByRole('region', { name: 'Installation detail' })
    expect(within(detail).getByText('Edwards AFB')).toBeInTheDocument()
  })

  it('disables generation and omits KB context when no ready or active knowledge base exists', () => {
    const processingKb: KnowledgeBaseListResponse = {
      total: 1,
      items: [{ ...knowledgeBases.items[0], status: 'building' }],
    }
    mocks.useKnowledgeBases.mockReturnValue(querySuccess(processingKb))

    renderPage('/housing?installation=edwards')

    expect(screen.getByText('Unavailable')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Generate scorecard' })).toBeDisabled()

    const detail = screen.getByRole('region', { name: 'Installation detail' })
    const ragLink = within(detail).getByRole('link', { name: /ask ai about edwards afb/i })
    expect(ragLink).toHaveAttribute('href', expect.not.stringContaining('kb='))
  })

  it('enables generation against a records-only (active) knowledge base', () => {
    // Records-only KBs land feed rows but never transition to "ready" (no
    // document pipeline). The page must mirror the backend read model and
    // accept them, or the live demo's generate button stays dead.
    const recordsOnlyKb: KnowledgeBaseListResponse = {
      total: 1,
      items: [{ ...knowledgeBases.items[0], status: 'active' }],
    }
    mocks.useKnowledgeBases.mockReturnValue(querySuccess(recordsOnlyKb))

    renderPage('/housing?installation=edwards')

    expect(screen.getByText('Housing KB')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Generate scorecard' })).toBeEnabled()

    const detail = screen.getByRole('region', { name: 'Installation detail' })
    const ragLink = within(detail).getByRole('link', { name: /ask ai about edwards afb/i })
    expect(ragLink).toHaveAttribute('href', expect.stringContaining('kb=kb-housing'))
  })

  it('prefers a ready knowledge base over a newer active one, excluding pending cleanup', () => {
    const mixedKbs: KnowledgeBaseListResponse = {
      total: 3,
      items: [
        {
          ...knowledgeBases.items[0],
          id: 'kb-newer-active',
          name: 'Newer Active KB',
          status: 'active',
          created_at: '2026-07-01T00:00:00Z',
        },
        {
          ...knowledgeBases.items[0],
          id: 'kb-older-ready',
          name: 'Older Ready KB',
          status: 'ready',
          created_at: '2026-05-01T00:00:00Z',
        },
        {
          ...knowledgeBases.items[0],
          id: 'kb-cleanup-ready',
          name: 'Cleanup Ready KB',
          status: 'ready',
          created_at: '2026-06-20T00:00:00Z',
          pending_cleanup: true,
        },
      ],
    }
    mocks.useKnowledgeBases.mockReturnValue(querySuccess(mixedKbs))

    renderPage('/housing?installation=edwards')

    expect(screen.getByText('Older Ready KB')).toBeInTheDocument()
    expect(screen.queryByText('Newer Active KB')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Generate scorecard' })).toBeEnabled()

    const detail = screen.getByRole('region', { name: 'Installation detail' })
    const ragLink = within(detail).getByRole('link', { name: /ask ai about edwards afb/i })
    expect(ragLink).toHaveAttribute('href', expect.stringContaining('kb=kb-older-ready'))
  })

  it('surfaces installations without map coordinates as location pending and selectable', () => {
    mocks.useHousingInstallations.mockReturnValue(querySuccess({
      ...installations,
      total: 3,
      items: [
        ...installations.items,
        {
          installation_id: 'holloman',
          name: 'Holloman AFB',
          majcom: 'ACC',
          state: 'NM',
          status: 'unknown' as const,
          open_work_orders: 12,
          occupancy_rate: null,
        },
      ],
    }))

    renderPage()

    const pending = screen.getByRole('group', { name: 'Installations with location pending' })
    expect(within(pending).getByText('Location pending (1)')).toBeInTheDocument()

    fireEvent.click(within(pending).getByRole('button', { name: /holloman afb/i }))

    const detail = screen.getByRole('region', { name: 'Installation detail' })
    expect(within(detail).getByText('Holloman AFB')).toBeInTheDocument()
    expect(within(detail).getByText('ACC')).toBeInTheDocument()
  })

  it('explains the selected installation with rank, status drivers, and scorecard links', () => {
    const items: HousingInstallationResponse[] = [
      { ...installations.items[0] },
      {
        ...installations.items[1],
        open_work_orders_rank: 1,
        status_reasons: ['Open work orders far above portfolio median'],
      },
    ]
    mocks.useHousingInstallations.mockReturnValue(querySuccess({ ...installations, items }))

    renderPage('/housing?installation=edwards')

    const detail = screen.getByRole('region', { name: 'Installation detail' })
    expect(within(detail).getByText('#1 of 2 reporting by open work orders')).toBeInTheDocument()
    expect(within(detail).getByText('Why this status')).toBeInTheDocument()
    expect(
      within(detail).getByText('Open work orders far above portfolio median'),
    ).toBeInTheDocument()

    const runLink = within(detail).getByRole('link', {
      name: 'View Installation Health scorecard for Edwards AFB, overall fail',
    })
    expect(runLink).toHaveAttribute('href', '/scorecards/run-edwards?kb=kb-housing')
  })

  it('renders honest fallbacks when reasons and runs are absent for the selection', () => {
    renderPage('/housing?installation=barksdale')

    const detail = screen.getByRole('region', { name: 'Installation detail' })
    expect(within(detail).getByText('#2 of 2 reporting by open work orders')).toBeInTheDocument()
    expect(
      within(detail).getByText('No status drivers reported for this period.'),
    ).toBeInTheDocument()
    expect(
      within(detail).getByText('No scorecard runs for this installation yet.'),
    ).toBeInTheDocument()
  })

  it('excludes non-reporting installations from the rank denominator', () => {
    mocks.useHousingInstallations.mockReturnValue(querySuccess({
      ...installations,
      total: 3,
      items: [
        ...installations.items,
        {
          installation_id: 'silent',
          name: 'Silent AFB',
          majcom: 'ACC',
          state: 'TX',
          status: 'unknown' as const,
          open_work_orders: 0,
          open_work_orders_rank: null,
          occupancy_rate: null,
        },
      ],
    }))

    renderPage('/housing?installation=edwards')

    const detail = screen.getByRole('region', { name: 'Installation detail' })
    // 3 loaded, but Silent AFB reports nothing — the denominator stays at 2.
    expect(within(detail).getByText('#1 of 2 reporting by open work orders')).toBeInTheDocument()
  })

  it('renders no rank line for a non-reporting installation', () => {
    mocks.useHousingInstallations.mockReturnValue(querySuccess({
      ...installations,
      total: 3,
      items: [
        ...installations.items,
        {
          installation_id: 'silent',
          name: 'Silent AFB',
          majcom: 'ACC',
          state: 'TX',
          status: 'unknown' as const,
          open_work_orders: 0,
          open_work_orders_rank: null,
          occupancy_rate: null,
        },
      ],
    }))

    renderPage('/housing?installation=silent')

    const detail = screen.getByRole('region', { name: 'Installation detail' })
    expect(within(detail).getByText('Silent AFB')).toBeInTheDocument()
    expect(within(detail).queryByText(/by open work orders/)).not.toBeInTheDocument()
  })

  it('links readiness panel run entries into the scorecard viewer', () => {
    renderPage('/housing?installation=edwards')

    const selectedRunLink = screen.getByRole('link', {
      name: 'View Installation Health scorecard run for Edwards AFB',
    })
    expect(selectedRunLink).toHaveAttribute('href', '/scorecards/run-edwards?kb=kb-housing')

    const recentRunLink = screen.getByRole('link', {
      name: 'View Installation Health scorecard run for Edwards AFB, overall fail',
    })
    expect(recentRunLink).toHaveAttribute('href', '/scorecards/run-edwards?kb=kb-housing')
  })

  it('filters the map, ranking table, and status counts together', () => {
    mocks.useHousingInstallations.mockReturnValue(querySuccess(filterableInstallations))

    renderPage()

    const statusGroup = screen.getByRole('group', { name: 'Filter by status' })
    fireEvent.click(within(statusGroup).getByRole('button', { name: 'critical' }))

    expect(screen.getByText('Showing 1 of 3 installations')).toBeInTheDocument()

    const table = screen.getByRole('table')
    expect(within(table).getByText('Edwards AFB')).toBeInTheDocument()
    expect(within(table).queryByText('Barksdale AFB')).not.toBeInTheDocument()
    expect(within(table).queryByText('Patrick SFB')).not.toBeInTheDocument()

    expect(
      screen.getByRole('button', { name: /select edwards afb on map/i }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /select barksdale afb on map/i }),
    ).not.toBeInTheDocument()

    const counts = screen.getByRole('group', { name: 'Status counts' })
    expect(within(counts).getByText('1')).toBeInTheDocument()
    expect(within(counts).getAllByText('0')).toHaveLength(3)
  })

  it('combines branch and command filters, handles empty results, and clears all', () => {
    mocks.useHousingInstallations.mockReturnValue(querySuccess(filterableInstallations))

    renderPage()

    const branchGroup = screen.getByRole('group', { name: 'Filter by branch' })
    fireEvent.click(within(branchGroup).getByRole('button', { name: 'USSF' }))

    const table = screen.getByRole('table')
    expect(screen.getByText('Showing 1 of 3 installations')).toBeInTheDocument()
    expect(within(table).getByText('Patrick SFB')).toBeInTheDocument()
    expect(within(table).queryByText('Edwards AFB')).not.toBeInTheDocument()

    const commandGroup = screen.getByRole('group', { name: 'Filter by command' })
    fireEvent.click(within(commandGroup).getByRole('button', { name: 'AFMC' }))

    // USSF branch AND AFMC command match nothing — both panels degrade gracefully.
    expect(screen.getByText('Showing 0 of 3 installations')).toBeInTheDocument()
    expect(screen.getAllByText('No matching installations')).toHaveLength(2)
    expect(screen.queryByRole('table')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }))

    expect(screen.getByText('Showing all 3 installations')).toBeInTheDocument()
    expect(within(screen.getByRole('table')).getByText('Barksdale AFB')).toBeInTheDocument()
  })

  it('falls back to the first visible installation when filters exclude the selection and restores it on clear', () => {
    mocks.useHousingInstallations.mockReturnValue(querySuccess(filterableInstallations))

    renderPage('/housing?installation=edwards')

    const detail = screen.getByRole('region', { name: 'Installation detail' })
    expect(within(detail).getByText('Edwards AFB')).toBeInTheDocument()

    const statusGroup = screen.getByRole('group', { name: 'Filter by status' })
    fireEvent.click(within(statusGroup).getByRole('button', { name: 'ok' }))

    expect(within(detail).getByText('Patrick SFB')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }))

    expect(within(detail).getByText('Edwards AFB')).toBeInTheDocument()
  })

  it('keeps all four KPI cards portfolio-wide while filters narrow the status strip', () => {
    mocks.useHousingInstallations.mockReturnValue(querySuccess(filterableInstallations))

    renderPage()

    const criticalKpi = screen.getByText('Critical').parentElement
    expect(criticalKpi).not.toBeNull()
    expect(within(criticalKpi as HTMLElement).getByText('1')).toBeInTheDocument()

    // Filter to ok-only: the portfolio has 1 critical installation but the
    // filtered set has none — the KPI card must not follow the filter.
    const statusGroup = screen.getByRole('group', { name: 'Filter by status' })
    fireEvent.click(within(statusGroup).getByRole('button', { name: 'ok' }))

    expect(within(criticalKpi as HTMLElement).getByText('1')).toBeInTheDocument()

    const counts = screen.getByRole('group', { name: 'Status counts' })
    // Strip reflects the filtered set: ok 1, critical/watch/unknown 0.
    expect(within(counts).getByText('1')).toBeInTheDocument()
    expect(within(counts).getAllByText('0')).toHaveLength(3)
  })

  it('reports the exact run total beyond the fetched page in the readiness panel', () => {
    mocks.useScorecardRuns.mockReturnValue(querySuccess({ ...runs, total: 640 }))

    renderPage()

    const runsRow = screen.getByText('Runs generated').parentElement
    expect(runsRow).not.toBeNull()
    expect(within(runsRow as HTMLElement).getByText('640')).toBeInTheDocument()
  })

  it('renders a public installation reference layer when live housing feeds are empty', () => {
    mocks.useHousingOverview.mockReturnValue(querySuccess({
      ...overview,
      portfolio_summary: {
        total_installations: 0,
        installations_reporting: 0,
        open_work_orders: 0,
        overdue_work_orders: 0,
        occupancy_rate: null,
        resident_satisfaction: null,
      },
      executive_kpis: [],
    }))
    mocks.useHousingInstallations.mockReturnValue(querySuccess({
      period_start: '2026-06-01',
      period_end: '2026-06-30',
      total: 0,
      items: [],
      map_points: [],
    }))
    mocks.useScorecardTemplates.mockReturnValue(querySuccess({ items: [] }))

    renderPage()

    expect(screen.getAllByText('Public installation reference')).toHaveLength(2)
    expect(screen.getAllByText('Live feeds required')).toHaveLength(3)
    expect(screen.getByText('Edwards AFB')).toBeInTheDocument()
    expect(screen.getByRole('button', {
      name: 'Select Edwards AFB on map, public reference location, live housing status pending, USAF',
    })).toBeInTheDocument()
    expect(screen.getByText('Public CONUS base locations are shown until UMD, BAH, inventory, market, and demographics feeds are loaded.')).toBeInTheDocument()
    expect(screen.getByText('Live evidence pending')).toBeInTheDocument()
    expect(screen.queryByText('Housing KB')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Generate scorecard' })).toBeDisabled()
  })
})
