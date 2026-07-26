import { fireEvent, render, screen } from '@testing-library/react'
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
    data: { items: [{ id: 'item-1', title: 'Claim claim-1 over threshold', severity: 'high', status: 'open', updated_at: '2026-06-04T00:00:00Z' }], total: 1 },
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

    expect(mocks.usePolicyItems).toHaveBeenCalledWith('kb-current', undefined)
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
})
