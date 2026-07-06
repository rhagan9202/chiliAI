import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type {
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
    expect(screen.getByText('Edwards AFB')).toBeInTheDocument()

    const detail = screen.getByRole('region', { name: 'Installation detail' })
    expect(within(detail).getByText('Barksdale AFB')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Select Edwards AFB on map' }))

    expect(within(detail).getByText('Edwards AFB')).toBeInTheDocument()
    expect(within(detail).getByText('AFMC')).toBeInTheDocument()

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
})
