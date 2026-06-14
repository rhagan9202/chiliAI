import { fireEvent, render, screen } from '@testing-library/react'
import { act } from 'react'
import { BrowserRouter, MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AlertFeedPage } from '../AlertFeedPage'

const mocks = vi.hoisted(() => ({
  acknowledge: vi.fn(),
  useAlerts: vi.fn(),
}))

vi.mock('../../api/alerts', () => ({
  useAcknowledgeAlert: () => ({ isPending: false, mutate: mocks.acknowledge }),
  useAlerts: mocks.useAlerts,
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

describe('AlertFeedPage', () => {
  beforeEach(() => {
    mocks.acknowledge.mockReset()
    mocks.useAlerts.mockReset()
    mocks.useAlerts.mockImplementation(
      (filters?: { knowledgeBaseId?: string }) => ({
        isLoading: false,
        isError: false,
        data: alertsForKnowledgeBase(filters?.knowledgeBaseId),
      }),
    )
  })

  function renderAlertFeed(initialEntry = '/alerts') {
    return render(
      <MemoryRouter initialEntries={[initialEntry]}>
        <AlertFeedPage />
      </MemoryRouter>,
    )
  }

  it('renders alert feed rows and acknowledgement action', () => {
    renderAlertFeed()

    expect(screen.getByText('Alert Feed')).toBeInTheDocument()
    expect(screen.getByText('Redwood DME Group')).toBeInTheDocument()
    expect(screen.getByText('North Harbor Imaging')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Acknowledge' }))

    expect(mocks.acknowledge).toHaveBeenCalledWith('alert-1')
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
