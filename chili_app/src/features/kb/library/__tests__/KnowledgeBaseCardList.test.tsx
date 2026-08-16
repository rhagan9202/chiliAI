import { fireEvent, render, screen, within } from '@testing-library/react'
import type { ComponentProps } from 'react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'

import type { KnowledgeBaseSummaryResponse } from '../../../../api/contracts'
import { KnowledgeBaseCardList } from '../KnowledgeBaseCardList'

const knowledgeBases: KnowledgeBaseSummaryResponse[] = [
  {
    id: 'kb-policy',
    name: 'Policy corpus',
    description: 'CMS policy documents',
    status: 'ready',
    document_count: 12,
    entity_count: 84,
    relationship_count: 19,
    created_at: '2026-05-01T12:00:00Z',
    updated_at: '2026-05-02T12:00:00Z',
  },
  {
    id: 'kb-claims',
    name: 'Claims review',
    description: 'Claims and investigation records',
    status: 'building',
    document_count: 4,
    entity_count: 21,
    relationship_count: 7,
    created_at: '2026-05-02T12:00:00Z',
  },
]

function renderList(overrides: Partial<ComponentProps<typeof KnowledgeBaseCardList>> = {}) {
  const props: ComponentProps<typeof KnowledgeBaseCardList> = {
    activeDomainName: null,
    hiddenDomainCount: 0,
    knowledgeBases,
    onToggleShowAllDomains: vi.fn(),
    showAllDomains: false,
    ...overrides,
  }

  render(
    <MemoryRouter>
      <KnowledgeBaseCardList {...props} />
    </MemoryRouter>,
  )

  return props
}

describe('KnowledgeBaseCardList', () => {
  it('labels the region "Choose a knowledge base" and counts the list', () => {
    renderList()

    const region = screen.getByRole('region', { name: 'Choose a knowledge base' })
    expect(within(region).getByText('2 knowledge bases')).toBeInTheDocument()
  })

  it('links each card to that knowledge base’s workspace overview', () => {
    renderList()

    const card = screen.getByRole('link', { name: /Policy corpus/ })
    expect(card).toHaveAttribute('href', '/knowledge-bases/kb-policy')
    expect(within(card).getByText('12 documents')).toBeInTheDocument()
    expect(within(card).getByText('84 entities')).toBeInTheDocument()
  })

  it('renders no domain toggle when nothing is hidden', () => {
    renderList()

    expect(screen.queryByTestId('kb-show-all-domains-toggle')).not.toBeInTheDocument()
  })

  it('shows the hidden-domain count on the toggle and reports toggling', () => {
    const onToggleShowAllDomains = vi.fn()
    renderList({ hiddenDomainCount: 3, onToggleShowAllDomains })

    const toggle = screen.getByTestId('kb-show-all-domains-toggle')
    expect(toggle).toHaveTextContent('Show all domains (3 hidden)')
    expect(toggle).toHaveAttribute('aria-pressed', 'false')

    fireEvent.click(toggle)

    expect(onToggleShowAllDomains).toHaveBeenCalledTimes(1)
  })

  it('offers to scope back to the active domain when all domains are shown', () => {
    renderList({ hiddenDomainCount: 2, showAllDomains: true })

    const toggle = screen.getByTestId('kb-show-all-domains-toggle')
    expect(toggle).toHaveTextContent('Scope to active domain')
    expect(toggle).toHaveAttribute('aria-pressed', 'true')
  })

  it('explains a scoped-empty list instead of claiming no knowledge bases exist', () => {
    renderList({ knowledgeBases: [], hiddenDomainCount: 2 })

    expect(screen.getByText('No knowledge bases in the active domain')).toBeInTheDocument()
  })

  it('explains a genuinely empty library', () => {
    renderList({ knowledgeBases: [], hiddenDomainCount: 0 })

    expect(screen.getByText('No knowledge bases yet')).toBeInTheDocument()
  })

  it('flags domain provenance per knowledge base without blocking navigation', () => {
    renderList({
      activeDomainName: 'food_supply_chain',
      knowledgeBases: [
        { ...knowledgeBases[0]!, domain: 'medicare_fraud' },
        { ...knowledgeBases[1]!, domain: null },
      ],
    })

    const mismatched = screen.getByRole('link', { name: /Policy corpus/ })
    const legacy = screen.getByRole('link', { name: /Claims review/ })

    expect(within(mismatched).getByTestId('kb-domain-mismatch')).toBeInTheDocument()
    expect(within(legacy).getByTestId('kb-domain-unknown')).toBeInTheDocument()
  })
})
