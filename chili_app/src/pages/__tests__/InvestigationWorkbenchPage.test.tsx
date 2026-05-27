import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { DomainConfig, RuntimeEntity } from '../../api/contracts'
import { InvestigationWorkbenchPage } from '../InvestigationWorkbenchPage'

const mocks = vi.hoisted(() => ({
  knowledgeBases: [] as Array<{
    id: string
    name: string
    description: string
    status: string
    document_count: number
    entity_count: number
    relationship_count: number
    created_at: string
  }>,
  searchItems: [] as RuntimeEntity[],
  selectedEntity: null as RuntimeEntity | null,
  navigate: vi.fn(),
  routeEntityId: null as string | null,
  riskUnavailableReason: 'No risk profile has been generated for this entity.' as string | null,
  setSearchParams: vi.fn(),
  searchParams: new URLSearchParams(),
}))

const analyticsCalls = vi.hoisted(() => ({
  risk: [] as Array<[string | null, string | null]>,
  timeseries: [] as Array<[string | null, string | null]>,
}))

const domainConfig: DomainConfig = {
  domain: {
    name: 'medicare_fraud',
    display_name: 'Medicare Fraud Detection',
    description: 'Fraud investigation domain',
  },
  entities: [
    {
      name: 'provider',
      display_label: 'Provider',
      properties: {
        npi: { type: 'string', display: 'NPI' },
        specialty: { type: 'string', display: 'Specialty' },
        state: { type: 'string', display: 'State' },
      },
    },
  ],
  relationships: [
    {
      name: 'submitted_by',
      display_label: 'Submitted By',
      source: 'claim',
      target: 'provider',
    },
  ],
  capabilities: {
    timeseries: true,
    gnn: true,
    risk_scoring: true,
    rag_chat: true,
    explainability: true,
  },
  ingestion: {},
  alerts: { thresholds: {} },
  ui: {
    display_fields: {
      provider: {
        title: 'npi',
        subtitle: 'specialty',
        chips: ['state'],
      },
    },
  },
}

vi.mock('react-router-dom', () => ({
  useParams: () => (mocks.routeEntityId ? { entityId: mocks.routeEntityId } : {}),
  useNavigate: () => mocks.navigate,
  useSearchParams: () => [mocks.searchParams, mocks.setSearchParams],
}))

vi.mock('../../api/config', () => ({
  useDomainConfig: () => ({ isLoading: false, isError: false, data: domainConfig }),
}))

vi.mock('../../api/knowledgebases', () => ({
  useKnowledgeBases: () => ({
    isLoading: false,
    isError: false,
    data: { items: mocks.knowledgeBases, total: mocks.knowledgeBases.length },
  }),
}))

vi.mock('../../api/investigation', () => ({
  useInvestigationEntitySearch: (_knowledgeBaseId: string | null, query: string) => ({
    isLoading: false,
    isError: false,
    data: query.trim().length > 0 ? { items: mocks.searchItems, total: mocks.searchItems.length } : undefined,
  }),
  useInvestigationEntity: (_knowledgeBaseId: string | null, entityId: string | null) => ({
    isLoading: false,
    isError: false,
    data: entityId && mocks.selectedEntity ? { entity: mocks.selectedEntity } : undefined,
  }),
  useInvestigationNeighborhood: (_knowledgeBaseId: string | null, entityId: string | null) => ({
    isLoading: false,
    isError: false,
    data: entityId && mocks.selectedEntity
      ? {
          center_entity_id: mocks.selectedEntity.id,
          entities: [mocks.selectedEntity],
          relationships: [],
        }
      : undefined,
  }),
}))

vi.mock('../../api/alerts', () => ({
  useAlerts: () => ({
    isLoading: false,
    isError: false,
    data: { items: [], page: { page: 1, page_size: 0, total_items: 0 } },
  }),
}))

vi.mock('../../api/analytics', () => ({
  useRiskScore: (knowledgeBaseId: string | null, entityId: string | null) => {
    analyticsCalls.risk.push([knowledgeBaseId, entityId])
    return {
      isLoading: false,
      isError: false,
      data: {
        entity_id: entityId ?? '',
        overall_score: 0,
        risk_level: 'low',
        factors: [],
        availability_status: 'unavailable',
        unavailable_reason: mocks.riskUnavailableReason,
      },
    }
  },
  useTimeseries: (knowledgeBaseId: string | null, entityId: string | null) => {
    analyticsCalls.timeseries.push([knowledgeBaseId, entityId])
    return {
      isLoading: false,
      isError: false,
      data: {
        entity_id: entityId ?? '',
        metric_name: 'normalized_alert_pressure',
        points: [],
        availability_status: 'unavailable',
        unavailable_reason: 'No time series has been generated for this entity.',
      },
    }
  },
}))

vi.mock('../../api/evidence', () => ({
  useEvidencePack: () => ({ isLoading: false, isError: false, data: undefined }),
}))

describe('InvestigationWorkbenchPage', () => {
  beforeEach(() => {
    mocks.knowledgeBases = []
    mocks.searchItems = []
    mocks.selectedEntity = null
    mocks.navigate.mockReset()
    mocks.routeEntityId = null
    mocks.riskUnavailableReason = 'No risk profile has been generated for this entity.'
    mocks.setSearchParams.mockReset()
    mocks.searchParams = new URLSearchParams()
    analyticsCalls.risk = []
    analyticsCalls.timeseries = []
  })

  it('renders a live no-KB state instead of seeded graph data', () => {
    render(<InvestigationWorkbenchPage />)

    expect(screen.getByText('No graph-ready knowledge base')).toBeInTheDocument()
    expect(screen.getByText(/queries the graph through a selected knowledge base/i)).toBeInTheDocument()
  })

  it('renders a Create Knowledge Base CTA on the no-KB empty state that navigates to /knowledge-bases', async () => {
    render(<InvestigationWorkbenchPage />)

    const cta = await screen.findByRole('button', {
      name: /create knowledge base/i,
    })
    expect(cta).toBeInTheDocument()

    await userEvent.click(cta)

    expect(mocks.navigate).toHaveBeenCalledWith('/knowledge-bases')
  })

  it('searches a selected KB and renders config-derived entity details', async () => {
    const provider: RuntimeEntity = {
      id: 'provider-204',
      type: 'provider',
      properties: {
        npi: '1234567890',
        specialty: 'Pain Management',
        state: 'WA',
      },
      metadata: {},
      created_at: '2026-05-10T00:00:00Z',
      updated_at: null,
      version: 1,
    }
    mocks.knowledgeBases = [
      {
        id: 'kb-live',
        name: 'Live Fraud KB',
        description: 'Live KB',
        status: 'ready',
        document_count: 1,
        entity_count: 1,
        relationship_count: 0,
        created_at: '2026-05-10T00:00:00Z',
      },
    ]
    mocks.searchItems = [provider]
    mocks.selectedEntity = provider
    mocks.routeEntityId = 'provider-204'

    render(<InvestigationWorkbenchPage />)

    await userEvent.type(screen.getByRole('searchbox', { name: 'Entity search' }), '123')
    await userEvent.click(await screen.findByRole('button', { name: /1234567890/i }))

    expect(mocks.navigate).toHaveBeenCalledWith({
      pathname: '/investigation/provider-204',
      search: 'kb=kb-live',
    })
    expect(screen.getByRole('heading', { name: '1234567890' })).toBeInTheDocument()
    expect(screen.getByText('Provider')).toBeInTheDocument()
    expect(screen.getByText('state: WA')).toBeInTheDocument()
    expect(screen.getByText('Pain Management')).toBeInTheDocument()
  })

  it('passes active knowledge base scope into analytics queries', () => {
    const provider: RuntimeEntity = {
      id: 'provider-204',
      type: 'provider',
      properties: { npi: '1234567890' },
      metadata: {},
      created_at: '2026-05-10T00:00:00Z',
      updated_at: null,
      version: 1,
    }
    mocks.knowledgeBases = [
      {
        id: 'kb-live',
        name: 'Live Fraud KB',
        description: 'Live KB',
        status: 'ready',
        document_count: 1,
        entity_count: 1,
        relationship_count: 0,
        created_at: '2026-05-10T00:00:00Z',
      },
    ]
    mocks.selectedEntity = provider
    mocks.routeEntityId = 'provider-204'

    render(<InvestigationWorkbenchPage />)

    expect(analyticsCalls.risk.at(-1)).toEqual(['kb-live', 'provider-204'])
    expect(analyticsCalls.timeseries.at(-1)).toEqual(['kb-live', 'provider-204'])
    expect(screen.getByText(/No risk profile has been generated/i)).toBeInTheDocument()
  })

  it('renders unavailable risk analytics without a reason as the fallback empty state', () => {
    const provider: RuntimeEntity = {
      id: 'provider-204',
      type: 'provider',
      properties: { npi: '1234567890' },
      metadata: {},
      created_at: '2026-05-10T00:00:00Z',
      updated_at: null,
      version: 1,
    }
    mocks.knowledgeBases = [
      {
        id: 'kb-live',
        name: 'Live Fraud KB',
        description: 'Live KB',
        status: 'ready',
        document_count: 1,
        entity_count: 1,
        relationship_count: 0,
        created_at: '2026-05-10T00:00:00Z',
      },
    ]
    mocks.selectedEntity = provider
    mocks.routeEntityId = 'provider-204'
    mocks.riskUnavailableReason = null

    render(<InvestigationWorkbenchPage />)

    expect(screen.getByText(/Risk scoring is unavailable until an entity is selected and analytics respond/i)).toBeInTheDocument()
    expect(screen.queryByText('Composite risk')).not.toBeInTheDocument()
  })
})
