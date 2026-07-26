import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type {
  ClusterResult,
  DomainCapabilities,
  DomainConfig,
  RiskFactorResponse,
  RuntimeEntity,
} from '../../api/contracts'
import { InvestigationWorkbenchPage } from '../InvestigationWorkbenchPage'

const FULL_CAPABILITIES: DomainCapabilities = {
  timeseries: true,
  gnn: true,
  risk_scoring: true,
  rag_chat: true,
  explainability: true,
  peer_stats: false,
}

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
  alerts: [] as Array<{
    id: string
    entity_id: string
    knowledge_base_id: string
    severity: string
    evidence_pack_id: string | null
  }>,
  useAlerts: vi.fn(),
  searchItems: [] as RuntimeEntity[],
  selectedEntity: null as RuntimeEntity | null,
  navigate: vi.fn(),
  routeEntityId: null as string | null,
  riskUnavailableReason: 'No risk profile has been generated for this entity.' as string | null,
  riskAvailable: false,
  riskOverallScore: 0,
  riskLevel: 'low' as 'low' | 'medium' | 'high' | 'critical',
  riskFactors: [] as RiskFactorResponse[],
  clusters: [] as ClusterResult[],
  capabilities: { timeseries: true, gnn: true, risk_scoring: true, rag_chat: true, explainability: true, peer_stats: false } as DomainCapabilities,
  policyItems: [] as Array<{
    id: string
    knowledge_base_id: string
    rule_id: string
    target_kind: 'entity' | 'alert' | 'metric'
    target_ref: string
    severity: 'critical' | 'high' | 'medium'
    status: 'open' | 'accepted' | 'rejected' | 'deferred' | 'escalated'
    title: string
  }>,
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
    peer_stats: false,
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

vi.mock('react-router', async () => {
  const actual = await vi.importActual<typeof import('react-router')>('react-router')
  return {
    ...actual,
    useParams: () => (mocks.routeEntityId ? { entityId: mocks.routeEntityId } : {}),
    useNavigate: () => mocks.navigate,
  }
})

vi.mock('../../api/config', () => ({
  useDomainConfig: () => ({
    isLoading: false,
    isError: false,
    data: { ...domainConfig, capabilities: mocks.capabilities },
  }),
  useDomainFeatures: () => ({
    isLoading: false,
    isError: false,
    data: { capabilities: mocks.capabilities, enabled_pages: [], roles: {} },
  }),
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
  useAlerts: mocks.useAlerts,
}))

vi.mock('../../api/analytics', () => ({
  useRiskScore: (knowledgeBaseId: string | null, entityId: string | null) => {
    analyticsCalls.risk.push([knowledgeBaseId, entityId])
    return {
      isLoading: false,
      isError: false,
      data: {
        entity_id: entityId ?? '',
        overall_score: mocks.riskOverallScore,
        risk_level: mocks.riskLevel,
        factors: mocks.riskFactors,
        availability_status: mocks.riskAvailable ? 'available' : 'unavailable',
        unavailable_reason: mocks.riskAvailable ? null : mocks.riskUnavailableReason,
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
  useGnnClusters: (knowledgeBaseId: string | null) => ({
    isLoading: false,
    isError: false,
    data: { knowledge_base_id: knowledgeBaseId ?? '', clusters: mocks.clusters },
  }),
}))

vi.mock('../../api/evidence', () => ({
  useEvidencePack: () => ({ isLoading: false, isError: false, data: undefined }),
}))

vi.mock('../../api/policy', () => ({
  usePolicyItems: () => ({
    isLoading: false,
    isError: false,
    data: { items: mocks.policyItems, total: mocks.policyItems.length },
  }),
}))

function renderInvestigationWorkbench(initialEntry = '/investigation') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <InvestigationWorkbenchPage />
    </MemoryRouter>,
  )
}

/** Select a live KB with a single loaded provider entity — the fixture shared by tests that need an entity in the dossier. */
function selectLiveProvider(): RuntimeEntity {
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
  mocks.selectedEntity = provider
  mocks.routeEntityId = 'provider-204'
  return provider
}

describe('InvestigationWorkbenchPage', () => {
  beforeEach(() => {
    mocks.knowledgeBases = []
    mocks.alerts = []
    mocks.useAlerts.mockReset()
    mocks.useAlerts.mockImplementation((filters?: { knowledgeBaseId?: string }) => {
      const items = filters?.knowledgeBaseId
        ? mocks.alerts.filter((alert) => alert.knowledge_base_id === filters.knowledgeBaseId)
        : mocks.alerts
      return {
        isLoading: false,
        isError: false,
        data: { items, page: { page: 1, page_size: items.length, total_items: items.length } },
      }
    })
    mocks.searchItems = []
    mocks.selectedEntity = null
    mocks.navigate.mockReset()
    mocks.routeEntityId = null
    mocks.riskUnavailableReason = 'No risk profile has been generated for this entity.'
    mocks.riskAvailable = false
    mocks.riskOverallScore = 0
    mocks.riskLevel = 'low'
    mocks.riskFactors = []
    mocks.clusters = []
    mocks.capabilities = { ...FULL_CAPABILITIES }
    mocks.policyItems = []
    analyticsCalls.risk = []
    analyticsCalls.timeseries = []
  })

  it('renders a live no-KB state instead of seeded graph data', () => {
    renderInvestigationWorkbench()

    expect(screen.getByText('No graph-ready knowledge base')).toBeInTheDocument()
    expect(screen.getByText(/queries the graph through a selected knowledge base/i)).toBeInTheDocument()
  })

  it('renders a Create Knowledge Base CTA on the no-KB empty state that navigates to /knowledge-bases', async () => {
    renderInvestigationWorkbench()

    const cta = await screen.findByRole('button', {
      name: /create knowledge base/i,
    })
    expect(cta).toBeInTheDocument()

    await userEvent.click(cta)

    expect(mocks.navigate).toHaveBeenCalledWith('/knowledge-bases')
  })

  it('searches a selected KB and renders config-derived entity details', async () => {
    const provider = selectLiveProvider()
    mocks.searchItems = [provider]

    renderInvestigationWorkbench()

    await userEvent.type(screen.getByRole('searchbox', { name: 'Entity search' }), '123')
    await userEvent.click(await screen.findByRole('button', { name: /1234567890/i }))

    expect(mocks.navigate).toHaveBeenCalledWith(
      {
        pathname: '/investigation/provider-204',
        search: 'kb=kb-live',
      },
      { preventScrollReset: true },
    )
    // The entity title and type/subtitle line now render inside the
    // EntityDossierHeader (data-testid="entity-dossier-header") rather than
    // a standalone Card — the plain page-wide `getByRole('heading', ...)`
    // query from before the restructure would now match twice (SectionHeader
    // also shows the entity title per design §4.1), so this scopes to the
    // dossier header specifically.
    const dossierHeader = screen.getByTestId('entity-dossier-header')
    expect(within(dossierHeader).getByRole('heading', { name: '1234567890' })).toBeInTheDocument()
    // Old: separate `getByText('Provider')` + `getByText('Pain Management')`
    // assertions matched two standalone elements (a Chip and a <p>). The
    // dossier header now renders type label + subtitle joined in one
    // flag-label line, so this asserts the combined text instead.
    expect(within(dossierHeader).getByText('Provider · Pain Management')).toBeInTheDocument()
    expect(screen.getByText('state: WA')).toBeInTheDocument()
  })

  it('passes active knowledge base scope into analytics queries', () => {
    selectLiveProvider()

    renderInvestigationWorkbench()

    expect(analyticsCalls.risk.at(-1)).toEqual(['kb-live', 'provider-204'])
    expect(analyticsCalls.timeseries.at(-1)).toEqual(['kb-live', 'provider-204'])
    // The unavailable reason now surfaces in two places by design: the
    // dossier header's sub-line (EntityDossierHeader) and the SIGNALS tab's
    // factor-detail EmptyState — `getByText` (singular) would throw on the
    // duplicate, so this asserts presence via `getAllByText`.
    expect(screen.getAllByText(/No risk profile has been generated/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/No time series has been generated/i)).toBeInTheDocument()
    expect(screen.queryByText('Risk pressure trend')).not.toBeInTheDocument()
  })

  it('renders unavailable risk analytics without a reason as the fallback empty state', () => {
    selectLiveProvider()
    mocks.riskUnavailableReason = null

    renderInvestigationWorkbench()

    expect(screen.getByText(/Risk scoring is unavailable until an entity is selected and analytics respond/i)).toBeInTheDocument()
    // "Composite risk" was the old metric-row label for the RiskBadge in the
    // pre-restructure entity Card; it no longer exists anywhere on the page
    // (the dossier header shows a risk numeral instead) so this assertion is
    // now unconditionally true, not just true-when-unavailable. Kept as a
    // regression guard against the label being reintroduced.
    expect(screen.queryByText('Composite risk')).not.toBeInTheDocument()
  })

  it('selects the knowledge base from the incoming kb query parameter', () => {
    mocks.knowledgeBases = [
      {
        id: 'kb-first',
        name: 'First KB',
        description: 'Default fallback',
        status: 'ready',
        document_count: 1,
        entity_count: 1,
        relationship_count: 0,
        created_at: '2026-05-10T00:00:00Z',
      },
      {
        id: 'kb-claims',
        name: 'Claims KB',
        description: 'Query-selected KB',
        status: 'ready',
        document_count: 2,
        entity_count: 3,
        relationship_count: 1,
        created_at: '2026-05-11T00:00:00Z',
      },
    ]

    renderInvestigationWorkbench('/investigation?kb=kb-claims')

    expect(screen.getByLabelText('Knowledge base')).toHaveValue('kb-claims')
  })

  it('launches Ask AI with the selected entity context', async () => {
    selectLiveProvider()
    mocks.alerts = [
      {
        id: 'alert-1',
        entity_id: 'provider-204',
        knowledge_base_id: 'kb-live',
        severity: 'critical',
        evidence_pack_id: 'evidence-1',
      },
    ]

    renderInvestigationWorkbench('/investigation/provider-204?kb=kb-live')

    await userEvent.click(screen.getByRole('button', { name: 'Ask AI' }))

    expect(mocks.navigate).toHaveBeenCalledWith(
      '/rag-chat?kb=kb-live&source=entity&alert=alert-1&entity=provider-204&evidence=evidence-1&q=Why+is+this+high+risk%3F',
    )
  })

  it('loads alerts in the active knowledge base scope for entity Ask AI context', () => {
    selectLiveProvider()
    mocks.alerts = [
      {
        id: 'alert-other-kb',
        entity_id: 'provider-204',
        knowledge_base_id: 'kb-other',
        severity: 'critical',
        evidence_pack_id: 'evidence-other',
      },
      {
        id: 'alert-live',
        entity_id: 'provider-204',
        knowledge_base_id: 'kb-live',
        severity: 'high',
        evidence_pack_id: 'evidence-live',
      },
    ]

    renderInvestigationWorkbench('/investigation/provider-204?kb=kb-live')

    expect(mocks.useAlerts).toHaveBeenCalledWith({ knowledgeBaseId: 'kb-live' })
  })

  it('renders Signals, Network, Policy, and Evidence tabs when all capabilities are enabled', () => {
    selectLiveProvider()

    renderInvestigationWorkbench()

    const tabLabels = screen.getAllByRole('tab').map((tab) => tab.textContent)
    expect(tabLabels).toEqual(['Signals', 'Network', 'Policy', 'Evidence'])
  })

  it('collapses the tab strip to Signals and Network when explainability is disabled', () => {
    selectLiveProvider()
    mocks.capabilities = { ...mocks.capabilities, explainability: false }

    renderInvestigationWorkbench()

    const tabLabels = screen.getAllByRole('tab').map((tab) => tab.textContent)
    expect(tabLabels).toEqual(['Signals', 'Network'])
    expect(screen.queryByRole('tab', { name: 'Policy' })).not.toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Evidence' })).not.toBeInTheDocument()
  })

  it('renders no tab strip and shows the Network panel directly when signals, policy, and evidence are all gated off', () => {
    selectLiveProvider()
    mocks.capabilities = {
      ...mocks.capabilities,
      risk_scoring: false,
      timeseries: false,
      explainability: false,
    }

    renderInvestigationWorkbench()

    expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
    expect(screen.queryAllByRole('tab')).toHaveLength(0)
    expect(screen.getByTestId('investigation-graph-canvas')).toBeInTheDocument()
    expect(screen.getByLabelText('Depth')).toBeInTheDocument()
  })

  it('renders the AI signal band listing factor names when risk is available', () => {
    selectLiveProvider()
    mocks.riskAvailable = true
    mocks.riskOverallScore = 0.82
    mocks.riskLevel = 'high'
    mocks.riskFactors = [
      {
        factor_name: 'weekly_carrier_billing_self',
        contribution: 0.42,
        rationale: 'self-history anomaly z=4.5',
      },
    ]

    renderInvestigationWorkbench()

    const band = screen.getByTestId('signal-band')
    expect(within(band).getByText(/AI ANALYSIS · 1 RISK SIGNAL\b/)).toBeInTheDocument()
    expect(within(band).getByText('weekly carrier billing self')).toBeInTheDocument()
  })

  it('hides the signal band when risk is unavailable, even with factors on the raw payload', () => {
    // Distinct from the empty-factors case: this pins that the band is
    // hidden specifically because availability_status is 'unavailable',
    // not merely because the factor list happens to be empty.
    selectLiveProvider()
    mocks.riskAvailable = false
    mocks.riskUnavailableReason = 'Risk scoring has been retracted for this entity.'
    mocks.riskFactors = [
      {
        factor_name: 'weekly_carrier_billing_self',
        contribution: 0.42,
        rationale: 'self-history anomaly z=4.5',
      },
    ]

    renderInvestigationWorkbench()

    expect(screen.queryByTestId('signal-band')).not.toBeInTheDocument()
  })

  it('omits the anomaly trend panel entirely when the timeseries capability is disabled', () => {
    selectLiveProvider()
    mocks.capabilities = { ...mocks.capabilities, timeseries: false }

    renderInvestigationWorkbench()

    expect(screen.queryByText('No time series')).not.toBeInTheDocument()
    expect(screen.queryByText(/No time series has been generated/i)).not.toBeInTheDocument()
  })

  it('reveals the graph neighborhood canvas under the Network tab', async () => {
    selectLiveProvider()

    renderInvestigationWorkbench()
    await userEvent.click(screen.getByRole('tab', { name: 'Network' }))

    expect(screen.getByTestId('investigation-graph-canvas')).toBeInTheDocument()
    expect(screen.getByLabelText('Depth')).toBeInTheDocument()
  })

  it('shows an evidence empty state linking to the Alert Feed when no pack is linked', async () => {
    selectLiveProvider()

    renderInvestigationWorkbench()
    await userEvent.click(screen.getByRole('tab', { name: 'Evidence' }))

    expect(screen.getByText('No evidence available')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open Alert Feed' })).toHaveAttribute('href', '/alerts')
  })

  it('shows the policy panel empty state under the Policy tab when no items reference the entity', async () => {
    selectLiveProvider()

    renderInvestigationWorkbench()
    await userEvent.click(screen.getByRole('tab', { name: 'Policy' }))

    expect(screen.getByText('No policy signals')).toBeInTheDocument()
  })
})
