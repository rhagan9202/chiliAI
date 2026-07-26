import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type {
  HousingInstallationResponse,
  HousingInstallationsResponse,
  KnowledgeBaseListResponse,
  ScorecardRunListResponse,
} from '../../api/contracts'
import { HousingExecutivePage } from '../HousingExecutivePage'

const mocks = vi.hoisted(() => ({
  useHousingInstallations: vi.fn(),
  useKnowledgeBases: vi.fn(),
  useScorecardRuns: vi.fn(),
}))

vi.mock('../../api/housing', () => ({
  useHousingInstallations: mocks.useHousingInstallations,
}))

vi.mock('../../api/knowledgebases', () => ({
  useKnowledgeBases: mocks.useKnowledgeBases,
}))

vi.mock('../../api/scorecards', () => ({
  useScorecardRuns: mocks.useScorecardRuns,
}))

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
      overdue_work_orders: 6,
      satisfaction_survey_count: 0,
      uh_authorized_units: 900,
      mfh_authorized_units: 700,
      occupancy_rate: 0.88,
    },
    {
      installation_id: 'edwards',
      name: 'Edwards AFB',
      majcom: 'AFMC',
      state: 'CA',
      status: 'critical',
      open_work_orders: 95,
      overdue_work_orders: 30,
      satisfaction_survey_count: 0,
      uh_authorized_units: 1200,
      mfh_authorized_units: 800,
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

/**
 * Fully reported aggregate inputs so the summary band's filter-driven math is
 * assertable: unfiltered occupancy (0.88·500 + 0.82·1000 + 0.93·200) / 1700 =
 * 85%, UH supply (360+500+275)/(400+1000+250) = 0.69; critical-only (Edwards)
 * occupancy 82%, UH supply 0.50.
 */
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
      overdue_work_orders: 6,
      occupancy_rate: 0.88,
      occupancy_unit_weight: 500,
      condition_index: 82,
      condition_unit_weight: 400,
      resident_satisfaction: 74,
      satisfaction_survey_count: 2,
      uh_available_units: 360,
      uh_authorized_units: 400,
      mfh_available_units: 300,
      mfh_authorized_units: 300,
    },
    {
      installation_id: 'edwards',
      name: 'Edwards AFB',
      majcom: 'AFMC',
      branch: 'USAF',
      state: 'CA',
      status: 'critical',
      open_work_orders: 95,
      overdue_work_orders: 30,
      occupancy_rate: 0.82,
      occupancy_unit_weight: 1000,
      condition_index: 68,
      condition_unit_weight: 800,
      resident_satisfaction: 58,
      satisfaction_survey_count: 1,
      uh_available_units: 500,
      uh_authorized_units: 1000,
      mfh_available_units: 350,
      mfh_authorized_units: 500,
    },
    {
      installation_id: 'patrick',
      name: 'Patrick SFB',
      majcom: 'SSC',
      branch: 'USSF',
      state: 'FL',
      status: 'ok',
      open_work_orders: 12,
      overdue_work_orders: 0,
      occupancy_rate: 0.93,
      occupancy_unit_weight: 200,
      condition_index: 90,
      condition_unit_weight: 200,
      resident_satisfaction: 85,
      satisfaction_survey_count: 1,
      uh_available_units: 275,
      uh_authorized_units: 250,
      mfh_available_units: 150,
      mfh_authorized_units: 150,
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

/** The <strong> value rendered in the summary band card with the given label. */
function bandValue(label: string): string | null {
  const band = screen.getByRole('group', { name: 'Housing portfolio summary' })
  const labelElement = within(band).getByText(label)
  return labelElement.parentElement?.querySelector('strong')?.textContent ?? null
}

describe('HousingExecutivePage', () => {
  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset())
    mocks.useHousingInstallations.mockReturnValue(querySuccess(installations))
    mocks.useKnowledgeBases.mockReturnValue(querySuccess(knowledgeBases))
    mocks.useScorecardRuns.mockReturnValue(querySuccess(runs))
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

  it('retires the scorecard readiness panel while keeping the run viewer reachable', () => {
    renderPage('/housing?installation=edwards')

    // The mid-page readiness panel (Ready KB / Templates / run summary /
    // Generate scorecard) is gone — generation stays API-side.
    expect(screen.queryByText('Ready KB')).not.toBeInTheDocument()
    expect(screen.queryByText('Templates')).not.toBeInTheDocument()
    expect(screen.queryByText('Runs generated')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /generate scorecard/i })).not.toBeInTheDocument()

    // The scorecard viewer entry point survives on the installation detail card.
    const detail = screen.getByRole('region', { name: 'Installation detail' })
    const runLink = within(detail).getByRole('link', {
      name: 'View Installation Health scorecard for Edwards AFB, overall fail',
    })
    expect(runLink).toHaveAttribute('href', '/scorecards/run-edwards?kb=kb-housing')
  })

  it('omits KB context from RAG launches when no ready or active knowledge base exists', () => {
    const processingKb: KnowledgeBaseListResponse = {
      total: 1,
      items: [{ ...knowledgeBases.items[0], status: 'building' }],
    }
    mocks.useKnowledgeBases.mockReturnValue(querySuccess(processingKb))

    renderPage('/housing?installation=edwards')

    const detail = screen.getByRole('region', { name: 'Installation detail' })
    const ragLink = within(detail).getByRole('link', { name: /ask ai about edwards afb/i })
    expect(ragLink).toHaveAttribute('href', expect.not.stringContaining('kb='))
  })

  it('resolves KB context from a records-only (active) knowledge base', () => {
    // Records-only KBs land feed rows but never transition to "ready" (no
    // document pipeline). The page must mirror the backend read model and
    // accept them, or the live demo's run links and RAG launches lose the KB.
    const recordsOnlyKb: KnowledgeBaseListResponse = {
      total: 1,
      items: [{ ...knowledgeBases.items[0], status: 'active' }],
    }
    mocks.useKnowledgeBases.mockReturnValue(querySuccess(recordsOnlyKb))

    renderPage('/housing?installation=edwards')

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
          overdue_work_orders: 0,
          satisfaction_survey_count: 0,
          uh_authorized_units: 0,
          mfh_authorized_units: 0,
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
          overdue_work_orders: 0,
          satisfaction_survey_count: 0,
          uh_authorized_units: 0,
          mfh_authorized_units: 0,
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
          overdue_work_orders: 0,
          satisfaction_survey_count: 0,
          uh_authorized_units: 0,
          mfh_authorized_units: 0,
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

  it('renders the summary band above the map with every aggregate card', () => {
    mocks.useHousingInstallations.mockReturnValue(querySuccess(filterableInstallations))

    renderPage()

    const band = screen.getByRole('group', { name: 'Housing portfolio summary' })
    const map = screen.getByLabelText('Installation health map')
    // The band precedes the map in DOM order — all summary cards live above it.
    expect(band.compareDocumentPosition(map) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()

    expect(bandValue('Reporting')).toBe('3/3')
    expect(bandValue('Open WOs')).toBe('151')
    expect(bandValue('Critical')).toBe('1')
    // Unit-weighted: (0.88·500 + 0.82·1000 + 0.93·200) / 1700 = 85%.
    expect(bandValue('Occupancy')).toBe('85%')
    // (82·400 + 68·800 + 90·200) / 1400 = 75.1.
    expect(bandValue('Condition index')).toBe('75.1')
    // Survey-count weighted: (74·2 + 58 + 85) / 4 = 72.8.
    expect(bandValue('Satisfaction')).toBe('72.8')
    // 36 overdue / 151 open = 24%.
    expect(bandValue('Overdue WO rate')).toBe('24%')
    // (360 + 500 + 275) / (400 + 1000 + 250) = 0.69.
    expect(bandValue('UH supply ratio')).toBe('0.69')
    // (300 + 350 + 150) / (300 + 500 + 150) = 0.84.
    expect(bandValue('MFH supply ratio')).toBe('0.84')
  })

  it('drives every summary band aggregate from the active filters', () => {
    mocks.useHousingInstallations.mockReturnValue(querySuccess(filterableInstallations))

    renderPage()

    const statusGroup = screen.getByRole('group', { name: 'Filter by status' })
    fireEvent.click(within(statusGroup).getByRole('button', { name: 'critical' }))

    // Only Edwards remains: its own numbers, not the portfolio's.
    expect(bandValue('Reporting')).toBe('1/1')
    expect(bandValue('Open WOs')).toBe('95')
    expect(bandValue('Critical')).toBe('1')
    expect(bandValue('Occupancy')).toBe('82%')
    expect(bandValue('UH supply ratio')).toBe('0.50')

    fireEvent.click(within(statusGroup).getByRole('button', { name: 'critical' }))
    fireEvent.click(within(statusGroup).getByRole('button', { name: 'ok' }))

    // Only Patrick remains: zero critical is an honest zero, not "n/a".
    expect(bandValue('Critical')).toBe('0')
    expect(bandValue('Occupancy')).toBe('93%')
    expect(bandValue('UH supply ratio')).toBe('1.10')

    fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }))

    expect(bandValue('Occupancy')).toBe('85%')
    expect(bandValue('Critical')).toBe('1')
  })

  it('shows honest n/a in the band when the subset reports no data for a metric', () => {
    // The base fixture carries no occupancy weights, condition, satisfaction,
    // or available-unit inventory — every derived metric must read "n/a",
    // never 0 and never NaN.
    renderPage()

    expect(bandValue('Occupancy')).toBe('n/a')
    expect(bandValue('Condition index')).toBe('n/a')
    expect(bandValue('Satisfaction')).toBe('n/a')
    expect(bandValue('UH supply ratio')).toBe('n/a')
    expect(bandValue('MFH supply ratio')).toBe('n/a')
    // Open work orders exist, so the overdue rate is a real number.
    expect(bandValue('Overdue WO rate')).toBe('26%')
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

  it('narrows the status strip alongside the filtered band', () => {
    mocks.useHousingInstallations.mockReturnValue(querySuccess(filterableInstallations))

    renderPage()

    expect(bandValue('Critical')).toBe('1')

    // Filter to ok-only: the filtered set has no critical installation, and
    // the band follows the filters (superseding the portfolio-pinned rule).
    const statusGroup = screen.getByRole('group', { name: 'Filter by status' })
    fireEvent.click(within(statusGroup).getByRole('button', { name: 'ok' }))

    expect(bandValue('Critical')).toBe('0')

    const counts = screen.getByRole('group', { name: 'Status counts' })
    // Strip reflects the filtered set: ok 1, critical/watch/unknown 0.
    expect(within(counts).getByText('1')).toBeInTheDocument()
    expect(within(counts).getAllByText('0')).toHaveLength(3)
  })

  it('renders a public installation reference layer when live housing feeds are empty', () => {
    mocks.useHousingInstallations.mockReturnValue(querySuccess({
      period_start: '2026-06-01',
      period_end: '2026-06-30',
      total: 0,
      items: [],
      map_points: [],
    }))

    renderPage()

    expect(screen.getAllByText('Public installation reference')).toHaveLength(2)
    expect(screen.getAllByText('Live feeds required')).toHaveLength(2)
    expect(screen.getByText('Edwards AFB')).toBeInTheDocument()
    expect(screen.getByRole('button', {
      name: 'Select Edwards AFB on map, public reference location, live housing status pending, USAF',
    })).toBeInTheDocument()
    expect(screen.getByText('Public CONUS base locations are shown until UMD, BAH, inventory, market, and demographics feeds are loaded.')).toBeInTheDocument()

    // The band keeps its placeholder cards — no fabricated aggregates.
    const band = screen.getByRole('group', { name: 'Housing portfolio summary' })
    expect(within(band).getByText('Public locations')).toBeInTheDocument()
    expect(within(band).getByText('Scorecards')).toBeInTheDocument()
    expect(within(band).getByText('pending')).toBeInTheDocument()
    expect(within(band).queryByText('Occupancy')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /generate scorecard/i })).not.toBeInTheDocument()
  })
})
