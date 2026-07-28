import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { act } from 'react'
import { BrowserRouter, MemoryRouter, useLocation } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { DomainCapabilities, DomainConfig } from '../../api/contracts'
import { useToastStore } from '../../components/common/toastStore'
import { AlertFeedPage } from '../AlertFeedPage'

const mocks = vi.hoisted(() => ({
  acknowledge: vi.fn(),
  promoteAlertToCase: vi.fn(),
  attachAlertToCase: vi.fn(),
  useAlerts: vi.fn(),
  useCases: vi.fn(),
  capabilities: {
    timeseries: true,
    gnn: true,
    risk_scoring: true,
    rag_chat: true,
    explainability: true,
    peer_stats: false,
  } as DomainCapabilities,
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

const domainConfig: DomainConfig = {
  domain: {
    name: 'medicare_fraud',
    display_name: 'Medicare Fraud Detection',
    description: 'Fraud investigation domain',
  },
  entities: [
    { name: 'provider', display_label: 'Provider', properties: {} },
  ],
  relationships: [],
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
  ui: {},
}

vi.mock('../../api/alerts', () => ({
  useAcknowledgeAlert: () => ({ isPending: false, mutate: mocks.acknowledge }),
  useAlerts: mocks.useAlerts,
}))

vi.mock('../../api/cases', () => ({
  useCases: mocks.useCases,
  usePromoteAlertToCase: () => ({ isPending: false, mutate: mocks.promoteAlertToCase }),
  useAttachAlertToCase: () => ({ isPending: false, mutate: mocks.attachAlertToCase }),
}))

vi.mock('../../api/config', () => ({
  useDomainConfig: () => ({
    isLoading: false,
    isError: false,
    data: domainConfig,
  }),
  useDomainFeatures: () => ({
    isLoading: false,
    isError: false,
    data: { capabilities: mocks.capabilities, enabled_pages: [], roles: {} },
  }),
}))

vi.mock('../../api/investigation', () => ({
  useInvestigationNeighborhood: () => ({
    isLoading: false,
    isError: false,
    data: undefined,
  }),
}))

vi.mock('../../api/policy', () => ({
  usePolicyItems: () => ({
    isLoading: false,
    isError: false,
    data: { items: mocks.policyItems, total: mocks.policyItems.length },
  }),
}))

vi.mock('../../api/evidence', () => ({
  useEvidencePack: (evidencePackId: string | null) => ({
    isLoading: false,
    data: evidencePackId
      ? {
          id: evidencePackId,
          knowledge_base_id: 'kb-redwood',
          alert_id: 'alert-1',
          entity_id: 'provider-204',
          reasoning: 'Evidence for Redwood DME Group.',
          confidence: 0.96,
          citations: [],
          subgraph: { nodes: [], edges: [] },
          created_at: '2026-05-12T00:00:00Z',
        }
      : undefined,
  }),
}))

const alertResponse = {
  items: [
    {
      id: 'alert-1',
      entity_id: 'provider-204',
      entity_type: 'provider',
      entity_label: 'Redwood DME Group',
      severity: 'critical',
      status: 'open',
      title: 'Outlier billing concentration',
      reasoning: 'Provider activity is materially above peers.',
      confidence: 0.96,
      evidence_pack_id: 'evidence-1',
      knowledge_base_id: 'kb-redwood',
      created_at: '2026-05-12T00:00:00Z',
      tags: ['billing', 'peer-deviation'],
    },
    {
      id: 'alert-2',
      entity_id: 'provider-118',
      entity_type: 'provider',
      entity_label: 'North Harbor Imaging',
      severity: 'high',
      status: 'acknowledged',
      title: 'Referral concentration anomaly',
      reasoning: 'Referral traffic is concentrated outside norms.',
      confidence: 0.84,
      evidence_pack_id: null,
      knowledge_base_id: 'kb-harbor',
      created_at: '2026-05-12T00:00:00Z',
      tags: ['network'],
    },
  ],
  page: { page: 1, page_size: 2, total_items: 2 },
}

function alertsForKnowledgeBase(knowledgeBaseId: string | undefined) {
  if (!knowledgeBaseId) {
    return alertResponse
  }
  const items = alertResponse.items.filter(
    (alert) => alert.knowledge_base_id === knowledgeBaseId,
  )
  return {
    items,
    page: { page: 1, page_size: items.length, total_items: items.length },
  }
}

function LocationProbe({ onChange }: { onChange: (location: string) => void }) {
  const location = useLocation()
  onChange(`${location.pathname}${location.search}`)
  return null
}

describe('AlertFeedPage', () => {
  beforeEach(() => {
    mocks.acknowledge.mockReset()
    mocks.promoteAlertToCase.mockReset()
    mocks.useAlerts.mockReset()
    mocks.useCases.mockReset()
    mocks.useAlerts.mockImplementation(
      (filters?: { knowledgeBaseId?: string }) => ({
        isLoading: false,
        isError: false,
        data: alertsForKnowledgeBase(filters?.knowledgeBaseId),
      }),
    )
    mocks.useCases.mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [], page: { page: 1, page_size: 0, total_items: 0 } },
    })
    mocks.capabilities = {
      timeseries: true,
      gnn: true,
      risk_scoring: true,
      rag_chat: true,
      explainability: true,
      peer_stats: false,
    }
    mocks.policyItems = []
    useToastStore.getState().clear()
  })

  function renderAlertFeed(initialEntry = '/alerts') {
    return render(
      <MemoryRouter initialEntries={[initialEntry]}>
        <AlertFeedPage />
      </MemoryRouter>,
    )
  }

  function renderAlertFeedWithLocationProbe(initialEntry = '/alerts') {
    const locations: string[] = []
    render(
      <MemoryRouter initialEntries={[initialEntry]}>
        <AlertFeedPage />
        <LocationProbe onChange={(location) => locations.push(location)} />
      </MemoryRouter>,
    )
    return locations
  }

  it('links the promote toast to the case it just created', () => {
    // Promotion succeeded with a well-worded toast that led nowhere, so the
    // artifact the analyst had just made was unreachable (UXA-405).
    mocks.promoteAlertToCase.mockImplementation((_payload, options) => {
      options.onSuccess({ case: { id: 'case-new', knowledge_base_id: 'kb-redwood' } })
    })

    renderAlertFeed()
    fireEvent.click(screen.getByRole('button', { name: 'Promote Redwood DME Group to case' }))

    const [toast] = useToastStore.getState().toasts
    expect(toast?.action).toEqual({
      label: 'Open case',
      to: '/cases?kb=kb-redwood&case=case-new',
    })
  })

  it('reflects the promotion on the alert and refuses a second one', () => {
    mocks.promoteAlertToCase.mockImplementation((_payload, options) => {
      options.onSuccess({ case: { id: 'case-new', knowledge_base_id: 'kb-redwood' } })
    })

    renderAlertFeed()
    const promote = screen.getByRole('button', { name: 'Promote Redwood DME Group to case' })
    fireEvent.click(promote)

    const promoted = screen.getByRole('button', { name: 'Promoted Redwood DME Group to case' })
    expect(promoted).toBeDisabled()

    fireEvent.click(promoted)
    expect(mocks.promoteAlertToCase).toHaveBeenCalledTimes(1)
  })

  it('acknowledges a selected set in one action', async () => {
    // Every alert had to be acknowledged one at a time (UXA-406).
    renderAlertFeed()

    fireEvent.click(screen.getByRole('checkbox', { name: 'Select Outlier billing concentration' }))
    fireEvent.click(screen.getByRole('checkbox', { name: 'Select Referral concentration anomaly' }))

    expect(screen.getByText('2 alerts selected')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Acknowledge 2 alerts' }))
    // Scoped to the dialog: each row also has its own Acknowledge button.
    await userEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: 'Acknowledge' }),
    )

    expect(mocks.acknowledge).toHaveBeenCalledTimes(2)
  })

  it('selects every alert the current filter shows, not the whole queue', () => {
    renderAlertFeed('/alerts?severity=critical')

    fireEvent.click(screen.getByRole('checkbox', { name: 'Select all alerts in view' }))

    expect(screen.getByText('1 alert selected')).toBeInTheDocument()
  })

  it('states the exact count in the confirmation', () => {
    renderAlertFeed()

    fireEvent.click(screen.getByRole('checkbox', { name: 'Select Outlier billing concentration' }))
    fireEvent.click(screen.getByRole('button', { name: 'Acknowledge 1 alert' }))

    expect(screen.getByRole('dialog')).toHaveTextContent(
      'This marks 1 alert as seen. It cannot be undone from here.',
    )
  })

  it('clears the selection without acting on it', () => {
    renderAlertFeed()

    fireEvent.click(screen.getByRole('checkbox', { name: 'Select Outlier billing concentration' }))
    fireEvent.click(screen.getByRole('button', { name: 'Clear selection' }))

    expect(screen.queryByText(/alerts? selected/)).not.toBeInTheDocument()
    expect(mocks.acknowledge).not.toHaveBeenCalled()
  })

  it('expresses critical AND unacknowledged in one view', () => {
    // The single-select chip row conflated severity and status, so the
    // product's most common triage filter could not be stated (UXA-401).
    renderAlertFeed('/alerts?severity=critical&status=open')

    expect(screen.getByText('Outlier billing concentration')).toBeInTheDocument()
    expect(screen.queryByText('Referral concentration anomaly')).not.toBeInTheDocument()
  })

  it('reflects a filter toggle in the URL so the view is shareable', async () => {
    const locations = renderAlertFeedWithLocationProbe('/alerts')

    fireEvent.click(screen.getByRole('button', { name: /^Critical, \d+ matching$/ }))

    expect(locations.at(-1)).toContain('severity=critical')
  })

  it('shows a count on every filter option', () => {
    renderAlertFeed()

    expect(screen.getByRole('button', { name: 'Critical, 1 matching' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'High, 1 matching' })).toBeInTheDocument()
  })

  it('offers every configured severity, not a hardcoded subset', () => {
    // Medium and Low were charted by the Severity Mix panel but unfilterable.
    renderAlertFeed()

    const severities = screen.getByRole('group', { name: 'Severity' })
    expect(within(severities).getAllByRole('button').map((b) => b.textContent)).toEqual([
      'Critical1',
      'High1',
      'Medium0',
      'Low0',
    ])
  })

  it('states what is being shown', () => {
    renderAlertFeed()

    expect(screen.getByText('Showing all 2 alerts')).toBeInTheDocument()
  })

  it('states how much of the queue a filter is hiding', () => {
    renderAlertFeed('/alerts?severity=critical')

    expect(screen.getByText('Showing 1 of 2 alerts')).toBeInTheDocument()
  })

  it('searches entity label and alert title', () => {
    renderAlertFeed('/alerts?q=harbor')

    expect(screen.getByText('North Harbor Imaging')).toBeInTheDocument()
    expect(screen.queryByText('Redwood DME Group')).not.toBeInTheDocument()
  })

  it('leads each card with what is wrong, not only who it happened to', () => {
    renderAlertFeed()

    // The API returns `title`; the card used to render only `entity_label`,
    // so an analyst saw the subject but never the finding (UXA-303).
    const headline = screen.getByText('Outlier billing concentration')
    expect(headline).toHaveClass('alert-row-card__title')
    expect(screen.getByText('Redwood DME Group')).toHaveClass('alert-row-card__subject')
  })

  it('shows how old each alert is, with the exact time on hover', () => {
    renderAlertFeed()

    const age = screen.getAllByTestId('alert-age')[0]
    expect(age).toHaveTextContent(/ago$/)
    expect(age).toHaveAttribute('title', 'May 12, 2026, 00:00 UTC')
  })

  it('labels the confidence numeral and does not repeat it unlabeled', () => {
    renderAlertFeed()

    expect(screen.getAllByTestId('triage-numeral')[0]).toHaveTextContent('96')
    expect(screen.getAllByText('confidence')[0]).toBeInTheDocument()
    // The ConfidenceBar rendered the same 96% a second time, unexplained.
    expect(document.querySelector('.alert-row-card .confidence-bar')).toBeNull()
  })

  it('renders each tag once', () => {
    renderAlertFeed()

    // `flagLabelFor` already puts the leading tag in the mono eyebrow; the
    // card also mapped every tag to a chip, so "BILLING" appeared twice.
    expect(screen.queryByText('peer deviation')).not.toBeInTheDocument()
    expect(screen.getAllByText('BILLING · PEER-DEVIATION')).toHaveLength(1)
  })

  it('makes one action primary and demotes the rest', () => {
    renderAlertFeed()

    const investigate = screen.getAllByRole('link', { name: /^Investigate / })[0]
    expect(investigate).toHaveClass('page-button--primary')
    expect(screen.getByRole('button', { name: 'Acknowledge' })).not.toHaveClass(
      'page-button--primary',
    )
  })

  it('renders alert feed rows and acknowledgement action', () => {
    renderAlertFeed()

    expect(screen.getByText('Alert Feed')).toBeInTheDocument()
    expect(screen.getByText('Redwood DME Group')).toBeInTheDocument()
    expect(screen.getByText('North Harbor Imaging')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Acknowledge' }))

    expect(mocks.acknowledge).toHaveBeenCalledWith('alert-1')
  })

  it('promotes the selected alert row to a case', () => {
    renderAlertFeed()

    fireEvent.click(screen.getByRole('button', { name: 'Promote North Harbor Imaging to case' }))

    expect(mocks.promoteAlertToCase).toHaveBeenCalledWith(
      { knowledgeBaseId: 'kb-harbor', alertId: 'alert-2' },
      expect.objectContaining({
        onSuccess: expect.any(Function),
        onError: expect.any(Function),
      }),
    )
  })

  it('disables a promoted alert row after promotion succeeds', () => {
    // The real mutation always hands onSuccess a CaseDetailResponse; a mock
    // that calls it bare lies about the contract and hid a crash in the
    // promote handler until CI surfaced it as an unhandled error.
    mocks.promoteAlertToCase.mockImplementation((_variables, options) => {
      options.onSuccess({ case: { id: 'case-harbor', knowledge_base_id: 'kb-harbor' } })
    })
    renderAlertFeed()

    const promoteButton = screen.getByRole('button', {
      name: 'Promote North Harbor Imaging to case',
    })

    fireEvent.click(promoteButton)

    const promotedButton = screen.getByRole('button', {
      name: 'Promoted North Harbor Imaging to case',
    })
    expect(promotedButton).toBeDisabled()

    fireEvent.click(promotedButton)

    expect(mocks.promoteAlertToCase).toHaveBeenCalledTimes(1)
  })

  it('disables an alert row already represented by an existing case in the selected knowledge base', () => {
    mocks.useCases.mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        items: [
          {
            id: 'case-2',
            knowledge_base_id: 'kb-harbor',
            title: 'North Harbor Imaging escalation',
            status: 'open',
            priority: 'high',
            assignee: null,
            alert_ids: ['alert-2'],
            updated_at: '2026-05-12T00:00:00Z',
          },
        ],
        page: { page: 1, page_size: 1, total_items: 1 },
      },
    })

    renderAlertFeed('/alerts?kb=kb-harbor')

    expect(mocks.useCases).toHaveBeenCalledWith('kb-harbor')

    const promotedButton = screen.getByRole('button', {
      name: 'Promoted North Harbor Imaging to case',
    })
    expect(promotedButton).toBeDisabled()

    fireEvent.click(promotedButton)

    expect(mocks.promoteAlertToCase).not.toHaveBeenCalled()
  })

  it('links each alert row to the entity investigation view with unique labels', () => {
    renderAlertFeed()

    const redwoodLink = screen.getByRole('link', { name: 'Investigate Redwood DME Group' })
    const harborLink = screen.getByRole('link', { name: 'Investigate North Harbor Imaging' })

    expect(redwoodLink).toHaveAttribute('href', '/investigation/provider-204?kb=kb-redwood')
    expect(harborLink).toHaveAttribute('href', '/investigation/provider-118?kb=kb-harbor')
  })

  it('launches Ask AI with the selected alert context', () => {
    const locations = renderAlertFeedWithLocationProbe()

    fireEvent.click(screen.getByRole('button', { name: 'Ask AI for Redwood DME Group' }))

    expect(locations.at(-1)).toBe(
      '/rag-chat?kb=kb-redwood&source=alert&alert=alert-1&entity=provider-204&evidence=evidence-1&q=Why+is+this+high+risk%3F',
    )
  })

  it('filters the feed by each dimension independently', () => {
    renderAlertFeed('/alerts?severity=critical')
    expect(screen.getByText('Redwood DME Group')).toBeInTheDocument()
    expect(screen.queryByText('North Harbor Imaging')).not.toBeInTheDocument()

    cleanup()
    renderAlertFeed('/alerts?status=acknowledged')
    expect(screen.queryByText('Redwood DME Group')).not.toBeInTheDocument()
    expect(screen.getByText('North Harbor Imaging')).toBeInTheDocument()
  })

  it('renders an empty state when no alert matches the active filter', () => {
    mocks.useAlerts.mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [alertResponse.items[1]], page: { page: 1, page_size: 1, total_items: 1 } },
    })

    renderAlertFeed('/alerts?severity=critical')

    expect(screen.getByText('No matching alerts')).toBeInTheDocument()
  })

  it('filters alerts by the incoming knowledge base query parameter', () => {
    renderAlertFeed('/alerts?kb=kb-harbor')

    expect(mocks.useAlerts).toHaveBeenCalledWith({ knowledgeBaseId: 'kb-harbor' })
    expect(screen.queryByText('Redwood DME Group')).not.toBeInTheDocument()
    expect(screen.getByText('North Harbor Imaging')).toBeInTheDocument()
  })

  it('hides selected evidence when the selected alert is outside the active knowledge base', async () => {
    window.history.pushState({}, '', '/alerts')
    render(
      <BrowserRouter>
        <AlertFeedPage />
      </BrowserRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'View evidence' }))
    expect(await screen.findByText('Evidence for Redwood DME Group.')).toBeInTheDocument()

    act(() => {
      window.history.pushState({}, '', '/alerts?kb=kb-harbor')
      window.dispatchEvent(new PopStateEvent('popstate'))
    })

    expect(screen.queryByText('Redwood DME Group')).not.toBeInTheDocument()
    expect(screen.queryByText('Evidence for Redwood DME Group.')).not.toBeInTheDocument()
    expect(screen.getByText('North Harbor Imaging')).toBeInTheDocument()
  })

  it('renders a risk-ranked triage numeral and flag label on each row', () => {
    renderAlertFeed()

    const numerals = screen.getAllByTestId('triage-numeral')
    expect(numerals[0]).toHaveTextContent('96')
    expect(numerals[1]).toHaveTextContent('84')

    expect(screen.getByText('BILLING · PEER-DEVIATION')).toBeInTheDocument()
    expect(screen.getByText('NETWORK')).toBeInTheDocument()
  })

  it('falls back to the severity word for the flag label when an alert has no tags', () => {
    mocks.useAlerts.mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        items: [{ ...alertResponse.items[0], tags: [] }],
        page: { page: 1, page_size: 1, total_items: 1 },
      },
    })

    renderAlertFeed()

    expect(screen.getByText('CRITICAL')).toBeInTheDocument()
  })

  it('shows a policy chip when policy items reference the alert or its entity', () => {
    mocks.policyItems = [
      {
        id: 'policy-1',
        knowledge_base_id: 'kb-redwood',
        rule_id: 'rule-1',
        target_kind: 'alert',
        target_ref: 'alert-1',
        severity: 'high',
        status: 'open',
        title: 'Outlier billing concentration under review',
      },
    ]

    renderAlertFeed()

    expect(screen.getByText('policy')).toBeInTheDocument()
  })

  it('hides the policy chip and the evidence action when explainability is disabled', () => {
    mocks.capabilities = { ...mocks.capabilities, explainability: false }
    mocks.policyItems = [
      {
        id: 'policy-1',
        knowledge_base_id: 'kb-redwood',
        rule_id: 'rule-1',
        target_kind: 'alert',
        target_ref: 'alert-1',
        severity: 'high',
        status: 'open',
        title: 'Outlier billing concentration under review',
      },
    ]

    renderAlertFeed()

    expect(screen.queryByText('policy')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'View evidence' })).not.toBeInTheDocument()
  })
})
