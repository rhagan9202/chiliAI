import { fireEvent, render, screen } from '@testing-library/react'
import { act } from 'react'
import { BrowserRouter, MemoryRouter, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AlertFeedPage } from '../AlertFeedPage'

const mocks = vi.hoisted(() => ({
  acknowledge: vi.fn(),
  promoteAlertToCase: vi.fn(),
  useAlerts: vi.fn(),
  useCases: vi.fn(),
}))

vi.mock('../../api/alerts', () => ({
  useAcknowledgeAlert: () => ({ isPending: false, mutate: mocks.acknowledge }),
  useAlerts: mocks.useAlerts,
}))

vi.mock('../../api/cases', () => ({
  useCases: mocks.useCases,
  usePromoteAlertToCase: () => ({ isPending: false, mutate: mocks.promoteAlertToCase }),
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
    mocks.promoteAlertToCase.mockImplementation((_variables, options) => {
      options.onSuccess()
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

  it('filters the feed and renders an empty state', () => {
    renderAlertFeed()

    fireEvent.click(screen.getByRole('button', { name: 'Critical' }))
    expect(screen.getByText('Redwood DME Group')).toBeInTheDocument()
    expect(screen.queryByText('North Harbor Imaging')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Acknowledged' }))
    expect(screen.queryByText('Redwood DME Group')).not.toBeInTheDocument()
    expect(screen.getByText('North Harbor Imaging')).toBeInTheDocument()
  })

  it('renders empty state when no alert matches the active filter', () => {
    mocks.useAlerts.mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [alertResponse.items[1]], page: { page: 1, page_size: 1, total_items: 1 } },
    })

    renderAlertFeed()
    fireEvent.click(screen.getByRole('button', { name: 'Critical' }))

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
})
