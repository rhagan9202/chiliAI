import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useAppStore } from '../../stores/appStore'

import type {
  ClusterResult,
  DomainCapabilities,
  DomainConfig,
  EntityFeatureValueResponse,
  EvidencePackResponse,
  FeatureCatalogResponse,
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
    updated_at?: string | null
  }>,
  alerts: [] as Array<{
    id: string
    entity_id: string
    knowledge_base_id: string
    severity: string
    evidence_pack_id: string | null
  }>,
  useAlerts: vi.fn(),
  useCase: vi.fn(),
  evidencePacks: {} as Record<string, EvidencePackResponse>,
  searchItems: [] as RuntimeEntity[],
  selectedEntity: null as RuntimeEntity | null,
  navigate: vi.fn(),
  routeEntityId: null as string | null,
  entityLocations: [] as Array<{ knowledge_base_id: string; knowledge_base_name: string }>,
  entityLoadFailed: false,
  riskUnavailableReason: 'No risk profile has been generated for this entity.' as string | null,
  riskAvailable: false,
  riskOverallScore: 0,
  riskLevel: 'low' as 'low' | 'medium' | 'high' | 'critical',
  riskFactors: [] as RiskFactorResponse[],
  featureCatalog: null as FeatureCatalogResponse | null,
  featureValues: [] as EntityFeatureValueResponse[],
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
  featureCatalog: [] as Array<[string | null]>,
  featureValues: [] as Array<[string | null, string | null, string | null]>,
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
    isError: mocks.entityLoadFailed,
    data:
      entityId && mocks.selectedEntity && !mocks.entityLoadFailed
        ? { entity: mocks.selectedEntity }
        : undefined,
  }),
  useEntityLocations: () => ({
    isLoading: false,
    isError: false,
    data: { items: mocks.entityLocations },
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

vi.mock('../../api/cases', () => ({
  useCase: mocks.useCase,
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

vi.mock('../../api/features', () => ({
  useFeatureCatalog: (knowledgeBaseId: string | null) => {
    analyticsCalls.featureCatalog.push([knowledgeBaseId])
    return {
      isLoading: false,
      isError: false,
      data: mocks.featureCatalog ?? undefined,
    }
  },
  useEntityFeatureValues: (
    knowledgeBaseId: string | null,
    entityType: string | null,
    entityId: string | null,
  ) => {
    analyticsCalls.featureValues.push([knowledgeBaseId, entityType, entityId])
    return {
      isLoading: false,
      isError: false,
      data: {
        knowledge_base_id: knowledgeBaseId ?? '',
        entity_type: entityType ?? '',
        entity_id: entityId ?? '',
        items: mocks.featureValues,
      },
    }
  },
}))

vi.mock('../../api/evidence', () => ({
  useEvidencePack: (evidencePackId: string | null) => ({
    isLoading: false,
    isError: false,
    data: evidencePackId ? mocks.evidencePacks[evidencePackId] : undefined,
  }),
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

function evidencePack(id: string, alertId: string, reasoning: string): EvidencePackResponse {
  return {
    id,
    alert_id: alertId,
    reasoning,
    confidence: 0.91,
    created_at: '2026-08-02T12:00:00Z',
    items: [],
    policy_citations: [],
    scores: {},
    source_documents: [],
    subgraph_edge_ids: [],
    subgraph_node_ids: ['provider-204'],
  }
}

describe('InvestigationWorkbenchPage', () => {
  beforeEach(() => {
    // The active knowledge base is remembered across pages; reset it so one
    // test's selection cannot leak into the next.
    window.localStorage.clear()
    useAppStore.setState({ activeKnowledgeBaseId: null })
    mocks.knowledgeBases = []
    mocks.alerts = []
    mocks.useAlerts.mockReset()
    mocks.useCase.mockReset()
    mocks.evidencePacks = {}
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
    mocks.useCase.mockReturnValue({
      isLoading: false,
      isError: false,
      data: undefined,
    })
    mocks.searchItems = []
    mocks.selectedEntity = null
    mocks.navigate.mockReset()
    mocks.routeEntityId = null
    mocks.entityLocations = []
    mocks.entityLoadFailed = false
    mocks.riskUnavailableReason = 'No risk profile has been generated for this entity.'
    mocks.riskAvailable = false
    mocks.riskOverallScore = 0
    mocks.riskLevel = 'low'
    mocks.riskFactors = []
    mocks.featureCatalog = null
    mocks.featureValues = []
    mocks.clusters = []
    mocks.capabilities = { ...FULL_CAPABILITIES }
    mocks.policyItems = []
    analyticsCalls.risk = []
    analyticsCalls.timeseries = []
    analyticsCalls.featureCatalog = []
    analyticsCalls.featureValues = []
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
    // Properties render as labeled facts (UXA-302), not `key: value` chips.
    expect(within(dossierHeader).getByText('State')).toBeInTheDocument()
    expect(within(dossierHeader).getByText('WA')).toBeInTheDocument()
  })

  it('offers flagged subjects as starting points instead of a bare search box', () => {
    // The landing state was a ~300px search card in a 1440px viewport with no
    // graph, no recent entities and no suggested starting points (UXA-305).
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
    mocks.alerts = [
      {
        id: 'alert-1',
        entity_id: 'provider-204',
        knowledge_base_id: 'kb-live',
        severity: 'critical',
        evidence_pack_id: null,
      },
    ]

    renderInvestigationWorkbench()

    const suggestions = screen.getByRole('group', { name: 'Flagged subjects' })
    expect(within(suggestions).getByRole('button', { name: /provider-204/ })).toBeInTheDocument()
  })

  it('opens a suggested subject on click', async () => {
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
    mocks.alerts = [
      {
        id: 'alert-1',
        entity_id: 'provider-204',
        knowledge_base_id: 'kb-live',
        severity: 'critical',
        evidence_pack_id: null,
      },
    ]

    renderInvestigationWorkbench()
    await userEvent.click(screen.getByRole('button', { name: /provider-204/ }))

    expect(mocks.navigate).toHaveBeenCalledWith(
      expect.objectContaining({ pathname: '/investigation/provider-204' }),
      { preventScrollReset: true },
    )
  })

  it('offers a switch when the entity lives in another knowledge base', () => {
    // A deep link with no ?kb= resolved against whatever the workspace pointed
    // at and dead-ended with "could not be loaded" (UXA-104).
    selectLiveProvider()
    mocks.entityLoadFailed = true
    mocks.entityLocations = [{ knowledge_base_id: 'kb-other', knowledge_base_name: 'Claims 2026' }]

    renderInvestigationWorkbench()

    expect(screen.getByText('This entity is in another knowledge base')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Switch to Claims 2026' })).toHaveAttribute(
      'href',
      '/investigation/provider-204?kb=kb-other',
    )
  })

  it('says plainly when the entity exists nowhere, rather than "could not be loaded"', () => {
    selectLiveProvider()
    mocks.entityLoadFailed = true
    mocks.entityLocations = []

    renderInvestigationWorkbench()

    expect(screen.getByText('This entity no longer exists')).toBeInTheDocument()
    expect(
      screen.queryByText(/could not be loaded from the active knowledge base/i),
    ).not.toBeInTheDocument()
  })

  it('states an unavailable risk profile once, not three times', () => {
    // The reason appeared as dossier body copy, again as the Signals-tab
    // empty-state description, and a third time as its "No risk score"
    // eyebrow — all above a CRITICAL badge (UXA-305).
    // riskAvailable defaults to false in beforeEach.
    selectLiveProvider()

    renderInvestigationWorkbench()

    expect(screen.getAllByText(/no risk profile has been generated/i)).toHaveLength(1)
  })

  it('does not tell an analyst to select an entity while one is selected', () => {
    selectLiveProvider()

    renderInvestigationWorkbench()

    expect(screen.queryByText(/select an entity to load its trend/i)).not.toBeInTheDocument()
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

  it('renders unavailable risk analytics with a next step, not a restated reason', () => {
    selectLiveProvider()
    mocks.riskUnavailableReason = null

    renderInvestigationWorkbench()

    // The panel offers what to do about it; the reason (when there is one)
    // lives once in the dossier header (UXA-305).
    expect(screen.getByText(/Risk factors appear once analytics have scored this entity/i)).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: 'Add data to this knowledge base' }),
    ).toBeInTheDocument()
    // "Composite risk" was the old metric-row label for the RiskBadge in the
    // pre-restructure entity Card; it no longer exists anywhere on the page
    // (the dossier header shows a risk numeral instead) so this assertion is
    // now unconditionally true, not just true-when-unavailable. Kept as a
    // regression guard against the label being reintroduced.
    expect(screen.queryByText('Composite risk')).not.toBeInTheDocument()
  })

  it('defaults to the most recently updated knowledge base, not the first listed', () => {
    mocks.knowledgeBases = [
      {
        id: 'kb-stale',
        name: 'Stale KB',
        description: 'Listed first but long untouched',
        status: 'ready',
        document_count: 1,
        entity_count: 1,
        relationship_count: 0,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
      {
        id: 'kb-current',
        name: 'Current KB',
        description: 'Most recently updated',
        status: 'ready',
        document_count: 2,
        entity_count: 2,
        relationship_count: 1,
        created_at: '2026-02-01T00:00:00Z',
        updated_at: '2026-07-01T00:00:00Z',
      },
    ]

    renderInvestigationWorkbench('/investigation')

    expect(screen.getByLabelText('Knowledge base')).toHaveValue('kb-current')
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

  it('honors explicit alert, case, and evidence cockpit state from the URL', async () => {
    selectLiveProvider()
    mocks.alerts = [
      {
        id: 'alert-fallback',
        entity_id: 'provider-204',
        knowledge_base_id: 'kb-live',
        severity: 'critical',
        evidence_pack_id: 'evidence-fallback',
      },
      {
        id: 'alert-live',
        entity_id: 'provider-204',
        knowledge_base_id: 'kb-live',
        severity: 'high',
        evidence_pack_id: 'evidence-live',
      },
    ]
    mocks.evidencePacks = {
      'evidence-live': evidencePack('evidence-live', 'alert-live', 'Explicit cockpit evidence.'),
      'evidence-fallback': evidencePack('evidence-fallback', 'alert-fallback', 'Fallback evidence.'),
    }
    mocks.useCase.mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        case: {
          id: 'case-1',
          knowledge_base_id: 'kb-live',
          title: 'Case #1',
          status: 'open',
          priority: 'high',
          assignee: null,
          alert_ids: ['alert-live'],
          evidence_pack_id: 'evidence-live',
          updated_at: '2026-08-02T12:00:00Z',
        },
        alerts: [],
        entity_timeline: [],
        feedback_history: [],
        evidence_pack: null,
      },
    })

    renderInvestigationWorkbench(
      '/investigation/provider-204?kb=kb-live&alert=alert-live&case=case-1&evidence=evidence-live',
    )

    expect(mocks.useCase).toHaveBeenCalledWith('kb-live', 'case-1')
    const state = screen.getByRole('group', { name: 'Cockpit state' })
    expect(within(state).getByText('Cockpit state')).toBeInTheDocument()
    expect(within(state).getByText('alert-live')).toBeInTheDocument()
    expect(within(state).getByText('Case #1')).toBeInTheDocument()
    expect(within(state).getByText('evidence-live')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('tab', { name: 'Evidence' }))

    expect(screen.getByText('Explicit cockpit evidence.')).toBeInTheDocument()
    expect(screen.queryByText('Fallback evidence.')).not.toBeInTheDocument()
  })

  it('renders cockpit actions only for validated alert, case, and evidence context', async () => {
    selectLiveProvider()
    mocks.alerts = [
      {
        id: 'alert-live',
        entity_id: 'provider-204',
        knowledge_base_id: 'kb-live',
        severity: 'high',
        evidence_pack_id: 'evidence-live',
      },
    ]
    mocks.evidencePacks = {
      'evidence-live': evidencePack('evidence-live', 'alert-live', 'Action rail evidence.'),
    }
    mocks.useCase.mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        case: {
          id: 'case-1',
          knowledge_base_id: 'kb-live',
          title: 'Case #1',
          status: 'open',
          priority: 'high',
          assignee: null,
          alert_ids: ['alert-live'],
          evidence_pack_id: 'evidence-live',
          updated_at: '2026-08-02T12:00:00Z',
        },
        alerts: [],
        entity_timeline: [],
        feedback_history: [],
        evidence_pack: null,
      },
    })

    renderInvestigationWorkbench(
      '/investigation/provider-204?kb=kb-live&alert=alert-live&case=case-1&evidence=evidence-live',
    )

    expect(screen.getByRole('link', { name: 'Open alert' })).toHaveAttribute(
      'href',
      '/alerts?kb=kb-live&alert=alert-live',
    )
    expect(screen.getByRole('link', { name: 'Open case' })).toHaveAttribute(
      'href',
      '/cases?kb=kb-live&case=case-1',
    )

    await userEvent.click(screen.getByRole('button', { name: 'View cockpit evidence' }))

    expect(screen.getByText('Action rail evidence.')).toBeInTheDocument()
  })

  it('summarizes risk, graph, case, and evidence in the first-viewport cockpit overview', () => {
    selectLiveProvider()
    mocks.riskAvailable = true
    mocks.riskOverallScore = 0.82
    mocks.riskLevel = 'high'
    mocks.alerts = [
      {
        id: 'alert-live',
        entity_id: 'provider-204',
        knowledge_base_id: 'kb-live',
        severity: 'high',
        evidence_pack_id: 'evidence-live',
      },
    ]
    mocks.evidencePacks = {
      'evidence-live': evidencePack('evidence-live', 'alert-live', 'Overview evidence.'),
    }
    mocks.useCase.mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        case: {
          id: 'case-1',
          knowledge_base_id: 'kb-live',
          title: 'Case #1',
          status: 'open',
          priority: 'high',
          assignee: null,
          alert_ids: ['alert-live'],
          evidence_pack_id: 'evidence-live',
          updated_at: '2026-08-02T12:00:00Z',
        },
        alerts: [],
        entity_timeline: [],
        feedback_history: [],
        evidence_pack: null,
      },
    })

    renderInvestigationWorkbench(
      '/investigation/provider-204?kb=kb-live&alert=alert-live&case=case-1&evidence=evidence-live',
    )

    const overview = screen.getByRole('group', { name: 'Cockpit overview' })
    expect(within(overview).getByText('82')).toBeInTheDocument()
    expect(within(overview).getByText('high risk')).toBeInTheDocument()
    expect(within(overview).getByText('1 entity · 0 relationships')).toBeInTheDocument()
    expect(within(overview).getByText('Case #1')).toBeInTheDocument()
    expect(within(overview).getByText('evidence-live')).toBeInTheDocument()
  })

  it('launches Ask AI with explicit cockpit state instead of the fallback entity alert', async () => {
    selectLiveProvider()
    mocks.alerts = [
      {
        id: 'alert-fallback',
        entity_id: 'provider-204',
        knowledge_base_id: 'kb-live',
        severity: 'critical',
        evidence_pack_id: 'evidence-fallback',
      },
      {
        id: 'alert-live',
        entity_id: 'provider-204',
        knowledge_base_id: 'kb-live',
        severity: 'high',
        evidence_pack_id: 'evidence-live',
      },
    ]
    mocks.evidencePacks = {
      'evidence-live': evidencePack('evidence-live', 'alert-live', 'Explicit cockpit evidence.'),
    }
    mocks.useCase.mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        case: {
          id: 'case-1',
          knowledge_base_id: 'kb-live',
          title: 'Case #1',
          status: 'open',
          priority: 'high',
          assignee: null,
          alert_ids: ['alert-live'],
          evidence_pack_id: 'evidence-live',
          updated_at: '2026-08-02T12:00:00Z',
        },
        alerts: [],
        entity_timeline: [],
        feedback_history: [],
        evidence_pack: null,
      },
    })

    renderInvestigationWorkbench(
      '/investigation/provider-204?kb=kb-live&alert=alert-live&case=case-1&evidence=evidence-live',
    )

    await userEvent.click(screen.getByRole('button', { name: 'Ask AI' }))

    expect(mocks.navigate).toHaveBeenCalledWith(
      '/rag-chat?kb=kb-live&source=entity&alert=alert-live&entity=provider-204&case=case-1&evidence=evidence-live&q=Why+is+this+high+risk%3F',
    )
  })

  it('marks an invalid explicit alert and does not silently launch AI against a fallback alert', async () => {
    selectLiveProvider()
    mocks.alerts = [
      {
        id: 'alert-fallback',
        entity_id: 'provider-204',
        knowledge_base_id: 'kb-live',
        severity: 'critical',
        evidence_pack_id: 'evidence-fallback',
      },
    ]

    renderInvestigationWorkbench('/investigation/provider-204?kb=kb-live&alert=alert-missing')

    expect(screen.getByText('alert-missing')).toBeInTheDocument()
    expect(screen.getByText('Requested context could not be loaded.')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Ask AI' }))

    expect(mocks.navigate).toHaveBeenCalledWith(
      '/rag-chat?kb=kb-live&source=entity&entity=provider-204&q=Why+is+this+high+risk%3F',
    )
  })

  it('drops an invalid explicit evidence pack from AI handoff', async () => {
    selectLiveProvider()
    mocks.alerts = [
      {
        id: 'alert-live',
        entity_id: 'provider-204',
        knowledge_base_id: 'kb-live',
        severity: 'high',
        evidence_pack_id: 'evidence-live',
      },
    ]

    renderInvestigationWorkbench(
      '/investigation/provider-204?kb=kb-live&alert=alert-live&evidence=evidence-missing',
    )

    expect(screen.getByText('evidence-missing')).toBeInTheDocument()
    expect(screen.getByText('Requested context could not be loaded.')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Ask AI' }))

    expect(mocks.navigate).toHaveBeenCalledWith(
      '/rag-chat?kb=kb-live&source=entity&alert=alert-live&entity=provider-204&q=Why+is+this+high+risk%3F',
    )
  })

  it('drops an invalid case from AI handoff', async () => {
    selectLiveProvider()
    mocks.alerts = [
      {
        id: 'alert-live',
        entity_id: 'provider-204',
        knowledge_base_id: 'kb-live',
        severity: 'high',
        evidence_pack_id: null,
      },
    ]
    mocks.useCase.mockReturnValue({
      isLoading: false,
      isError: true,
      data: undefined,
    })

    renderInvestigationWorkbench(
      '/investigation/provider-204?kb=kb-live&alert=alert-live&case=case-missing',
    )

    expect(screen.getByText('case-missing')).toBeInTheDocument()
    expect(screen.getByText('Requested context could not be loaded.')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Ask AI' }))

    expect(mocks.navigate).toHaveBeenCalledWith(
      '/rag-chat?kb=kb-live&source=entity&alert=alert-live&entity=provider-204&q=Why+is+this+high+risk%3F',
    )
  })

  it('clears alert, case, and evidence context when switching knowledge bases', async () => {
    selectLiveProvider()
    mocks.knowledgeBases.push({
      id: 'kb-other',
      name: 'Other KB',
      description: 'Other KB',
      status: 'ready',
      document_count: 1,
      entity_count: 1,
      relationship_count: 0,
      created_at: '2026-05-11T00:00:00Z',
    })

    renderInvestigationWorkbench(
      '/investigation/provider-204?kb=kb-live&alert=alert-live&case=case-1&evidence=evidence-live',
    )

    await userEvent.selectOptions(screen.getByLabelText('Knowledge base'), 'kb-other')

    expect(mocks.navigate).toHaveBeenCalledWith({
      pathname: '/investigation',
      search: 'kb=kb-other',
    })
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

  it('shows catalog feature labels and typologies in the Signals tab', () => {
    selectLiveProvider()
    mocks.riskAvailable = true
    mocks.riskFactors = [
      {
        factor_name: 'weekly_provider_billing_zscore',
        contribution: 0.42,
        rationale: 'self-history anomaly z=4.5',
      },
    ]
    mocks.featureCatalog = {
      knowledge_base_id: 'kb-live',
      catalog_version: 'cms-fraud-features-v1',
      typologies: [
        {
          id: 'billing_spike',
          label: 'Billing spike',
          description: 'Unexpected billing acceleration.',
          entity_types: ['provider'],
          feature_ids: ['weekly_provider_billing_zscore'],
          policy_rule_ids: [],
          playbook_ids: [],
          severity_hint: 'high',
        },
      ],
      features: [
        {
          id: 'weekly_provider_billing_zscore',
          label: 'Weekly provider billing z-score',
          description: 'Provider billing deviation from baseline.',
          entity_types: ['provider'],
          typology_ids: ['billing_spike'],
          value_type: 'decimal',
          transformation_version: 'peerstats-zscore-v1',
          source_mappings: [],
          peer_dimensions: ['specialty'],
          threshold_hints: { high: 0.8 },
        },
      ],
    }
    mocks.featureValues = [
      {
        entity_type: 'provider',
        entity_id: 'provider-204',
        feature_id: 'weekly_provider_billing_zscore',
        value: 4.2,
        normalized_value: 0.84,
        catalog_version: 'cms-fraud-features-v1',
        transformation_version: 'peerstats-zscore-v1',
        source_refs: ['entity_derived_signals.weekly_provider_billing'],
        observed_at: '2026-08-02T12:00:00Z',
        score_run_id: 'score-run-1',
      },
    ]

    renderInvestigationWorkbench('/investigation/provider-204?kb=kb-live')

    expect(analyticsCalls.featureCatalog.at(-1)).toEqual(['kb-live'])
    expect(analyticsCalls.featureValues.at(-1)).toEqual(['kb-live', 'provider', 'provider-204'])
    expect(screen.getByText('Feature values')).toBeInTheDocument()
    expect(screen.getByText('Weekly provider billing z-score')).toBeInTheDocument()
    expect(screen.getByText('Billing spike')).toBeInTheDocument()
    expect(screen.getByText('84%')).toBeInTheDocument()
    expect(screen.getByText('entity_derived_signals.weekly_provider_billing')).toBeInTheDocument()
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
