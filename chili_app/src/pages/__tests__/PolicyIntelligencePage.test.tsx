import { act, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useAppStore } from '../../stores/appStore'
import { PolicyIntelligencePage } from '../PolicyIntelligencePage'

const mocks = vi.hoisted(() => ({
  triage: vi.fn(),
  usePolicyItems: vi.fn(),
  usePolicyItem: vi.fn(),
  useKnowledgeBases: vi.fn(),
  useDomainConfig: vi.fn(),
}))

vi.mock('../../api/knowledgebases', () => ({ useKnowledgeBases: mocks.useKnowledgeBases }))
vi.mock('../../api/config', () => ({ useDomainConfig: mocks.useDomainConfig }))
vi.mock('../../api/policy', () => ({
  usePolicyItems: mocks.usePolicyItems,
  usePolicyItem: mocks.usePolicyItem,
  useTriagePolicyItem: () => ({ mutate: mocks.triage, isPending: false }),
}))

function setup() {
  mocks.useDomainConfig.mockReturnValue({ data: { domain: { name: 'medicare_fraud' } } })
  mocks.useKnowledgeBases.mockReturnValue({ data: { items: [{ id: 'kb-1', name: 'KB 1' }] } })
  mocks.usePolicyItems.mockReturnValue({
    isLoading: false, isError: false,
    data: {
      items: [{ id: 'item-1', title: 'Claim claim-1 over threshold', severity: 'high', status: 'open', updated_at: '2026-06-04T00:00:00Z' }],
      total: 1,
      status_counts: { open: 1, escalated: 2 },
    },
  })
  mocks.usePolicyItem.mockReturnValue({
    isLoading: false, isError: false,
    data: { item: { id: 'item-1', title: 'Claim claim-1 over threshold', severity: 'high', status: 'open', updated_at: '2026-06-04T00:00:00Z' }, matched_fields: { 'properties.amount': 1500 }, citations: [] },
  })
}

describe('PolicyIntelligencePage', () => {
  beforeEach(() => {
    mocks.usePolicyItems.mockClear()
    window.localStorage.clear()
    useAppStore.setState({ activeKnowledgeBaseId: null })
  })

  it('scopes to the shared active knowledge base, not the first one listed', () => {
    setup()
    mocks.useKnowledgeBases.mockReturnValue({
      data: {
        items: [
          { id: 'kb-stale', name: 'Stale', updated_at: '2026-01-01T00:00:00Z', domain: 'medicare_fraud' },
          { id: 'kb-current', name: 'Current', updated_at: '2026-07-01T00:00:00Z', domain: 'medicare_fraud' },
        ],
      },
    })

    render(<MemoryRouter initialEntries={['/policy']}><PolicyIntelligencePage /></MemoryRouter>)

    expect(mocks.usePolicyItems).toHaveBeenCalledWith('kb-current', {
      statuses: [],
      search: '',
    })
  })

  it('lists items and triages the selected item', () => {
    setup()
    render(<MemoryRouter initialEntries={['/policy?kb=kb-1']}><PolicyIntelligencePage /></MemoryRouter>)
    expect(screen.getByText('Policy Intelligence')).toBeInTheDocument()
    expect(screen.getAllByText('Claim claim-1 over threshold').length).toBeGreaterThan(0)
    fireEvent.click(screen.getByRole('button', { name: 'Accept' }))
    expect(mocks.triage).toHaveBeenCalledWith(
      { itemId: 'item-1', payload: { action: 'accept' } }, expect.anything(),
    )
  })

  it('sends a multi-select status and search from the URL to the API (UXA-401)', () => {
    // The queue is filtered server-side, so "open OR escalated" has to reach
    // the request, not be applied to an already-narrowed page.
    setup()

    render(
      <MemoryRouter initialEntries={['/policy?kb=kb-1&status=open&status=escalated&q=upcoding']}>
        <PolicyIntelligencePage />
      </MemoryRouter>,
    )

    expect(mocks.usePolicyItems).toHaveBeenCalledWith('kb-1', {
      statuses: ['open', 'escalated'],
      search: 'upcoding',
    })
  })

  it('toggles a status into the URL so the view is shareable', () => {
    setup()
    render(<MemoryRouter initialEntries={['/policy?kb=kb-1']}><PolicyIntelligencePage /></MemoryRouter>)

    fireEvent.click(screen.getByRole('button', { name: 'Escalated, 2 matching' }))

    expect(mocks.usePolicyItems).toHaveBeenLastCalledWith('kb-1', {
      statuses: ['escalated'],
      search: '',
    })
  })

  it('shows typed text immediately but queries once typing stops', () => {
    // Each committed keystroke is a filtered SQL query, so the request waits
    // for a pause — the box must not wait with it.
    vi.useFakeTimers()
    try {
      setup()
      render(<MemoryRouter initialEntries={['/policy?kb=kb-1']}><PolicyIntelligencePage /></MemoryRouter>)
      const search = screen.getByLabelText('Search')

      fireEvent.change(search, { target: { value: 'up' } })
      fireEvent.change(search, { target: { value: 'upcoding' } })

      expect((search as HTMLInputElement).value).toBe('upcoding')
      expect(mocks.usePolicyItems).toHaveBeenLastCalledWith('kb-1', {
        statuses: [],
        search: '',
      })

      act(() => {
        vi.advanceTimersByTime(250)
      })

      expect(mocks.usePolicyItems).toHaveBeenLastCalledWith('kb-1', {
        statuses: [],
        search: 'upcoding',
      })
    } finally {
      vi.useRealTimers()
    }
  })

  it('counts every status option from the whole knowledge base, not the filtered page', () => {
    // A filtered response carries one item; the strip must still say 2
    // escalated, or selecting a filter would zero out every other option.
    setup()

    render(
      <MemoryRouter initialEntries={['/policy?kb=kb-1&status=open']}>
        <PolicyIntelligencePage />
      </MemoryRouter>,
    )

    expect(screen.getByRole('button', { name: 'Open, 1 matching' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Escalated, 2 matching' })).toBeInTheDocument()
    expect(screen.getByText('Showing 1 of 3 items')).toBeInTheDocument()
  })

  it('states the unfiltered total when no filter is set', () => {
    setup()
    render(<MemoryRouter initialEntries={['/policy?kb=kb-1']}><PolicyIntelligencePage /></MemoryRouter>)

    expect(screen.getByText('Showing all 3 items')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Clear filters' })).not.toBeInTheDocument()
  })

  it('offers Clear filters when a filter hid everything, and ingestion when nothing exists', () => {
    setup()
    mocks.usePolicyItems.mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [], total: 0, status_counts: { open: 4 } },
    })

    const filtered = render(
      <MemoryRouter initialEntries={['/policy?kb=kb-1&status=rejected']}>
        <PolicyIntelligencePage />
      </MemoryRouter>,
    )

    expect(screen.getByText('No items match these filters')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Clear filters' }).length).toBeGreaterThan(0)
    filtered.unmount()

    mocks.usePolicyItems.mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [], total: 0, status_counts: {} },
    })
    render(<MemoryRouter initialEntries={['/policy?kb=kb-1']}><PolicyIntelligencePage /></MemoryRouter>)

    expect(screen.getByText('No policy items yet')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Add data to this knowledge base' })).toBeInTheDocument()
  })
})
