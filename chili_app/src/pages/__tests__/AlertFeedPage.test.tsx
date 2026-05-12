import { fireEvent, render, screen } from '@testing-library/react'
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
      created_at: '2026-05-12T00:00:00Z',
      tags: ['network'],
    },
  ],
  page: { page: 1, page_size: 2, total_items: 2 },
}

describe('AlertFeedPage', () => {
  beforeEach(() => {
    mocks.acknowledge.mockReset()
    mocks.useAlerts.mockReturnValue({ isLoading: false, isError: false, data: alertResponse })
  })

  it('renders alert feed rows and acknowledgement action', () => {
    render(<AlertFeedPage />)

    expect(screen.getByText('Alert Feed')).toBeInTheDocument()
    expect(screen.getByText('Redwood DME Group')).toBeInTheDocument()
    expect(screen.getByText('North Harbor Imaging')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Acknowledge' }))

    expect(mocks.acknowledge).toHaveBeenCalledWith('alert-1')
  })

  it('filters the feed and renders an empty state', () => {
    render(<AlertFeedPage />)

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

    render(<AlertFeedPage />)
    fireEvent.click(screen.getByRole('button', { name: 'Critical' }))

    expect(screen.getByText('No matching alerts')).toBeInTheDocument()
  })
})
