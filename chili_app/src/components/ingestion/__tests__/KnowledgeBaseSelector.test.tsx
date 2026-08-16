import type { ComponentProps } from 'react'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { KnowledgeBaseSummaryResponse } from '../../../api/contracts'
import { KnowledgeBaseSelector } from '../KnowledgeBaseSelector'

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

function renderSelector(
  overrides: Partial<ComponentProps<typeof KnowledgeBaseSelector>> = {},
) {
  const props: ComponentProps<typeof KnowledgeBaseSelector> = {
    activeKnowledgeBaseId: 'kb-policy',
    createDescription: '',
    createDisabled: false,
    createName: '',
    knowledgeBases,
    onCreateDescriptionChange: vi.fn(),
    onCreateNameChange: vi.fn(),
    onCreateSubmit: vi.fn(),
    onSelect: vi.fn(),
    ...overrides,
  }

  render(<KnowledgeBaseSelector {...props} />)

  return props
}

describe('KnowledgeBaseSelector', () => {
  it('selects an existing knowledge base from the list', () => {
    const props = renderSelector()
    const activeButton = screen.getByRole('button', { name: /policy corpus/i })
    const inactiveButton = screen.getByRole('button', { name: /claims review/i })

    fireEvent.click(inactiveButton)

    expect(props.onSelect).toHaveBeenCalledWith('kb-claims')
    expect(activeButton).toHaveClass('page-list-item--active')
    expect(activeButton).toHaveAttribute('aria-pressed', 'true')
    expect(inactiveButton).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByText('2 knowledge bases')).toBeInTheDocument()
    expect(screen.getByText('12 documents')).toBeInTheDocument()
    expect(screen.getByText('84 entities')).toBeInTheDocument()
  })

  it('submits controlled create fields when the name is not blank', () => {
    const props = renderSelector({
      createName: 'New corpus',
      createDescription: 'New source material',
    })

    fireEvent.change(screen.getByLabelText(/knowledge base name/i), {
      target: { value: 'Updated corpus' },
    })
    fireEvent.change(screen.getByLabelText(/description/i), {
      target: { value: 'Updated source material' },
    })
    fireEvent.click(screen.getByRole('button', { name: /create knowledge base/i }))

    expect(props.onCreateNameChange).toHaveBeenCalledWith('Updated corpus')
    expect(props.onCreateDescriptionChange).toHaveBeenCalledWith(
      'Updated source material',
    )
    expect(props.onCreateSubmit).toHaveBeenCalledTimes(1)
  })

  it('flags domain provenance per knowledge base without blocking selection', () => {
    const props = renderSelector({
      activeDomainName: 'food_supply_chain',
      knowledgeBases: [
        { ...knowledgeBases[0]!, domain: 'medicare_fraud' },
        { ...knowledgeBases[1]!, domain: null },
      ],
    })

    const mismatched = screen.getByRole('button', { name: /policy corpus/i })
    const legacy = screen.getByRole('button', { name: /claims review/i })

    expect(within(mismatched).getByTestId('kb-domain-mismatch')).toBeInTheDocument()
    expect(within(mismatched).getByText('Created under medicare_fraud')).toBeInTheDocument()
    expect(within(legacy).getByTestId('kb-domain-unknown')).toBeInTheDocument()
    expect(within(legacy).queryByTestId('kb-domain-mismatch')).not.toBeInTheDocument()

    // Warn only — a mismatched knowledge base is still selectable.
    fireEvent.click(mismatched)
    expect(props.onSelect).toHaveBeenCalledWith('kb-policy')
  })

  it('shows no domain badge when the knowledge base matches the active domain', () => {
    renderSelector({
      activeDomainName: 'medicare_fraud',
      knowledgeBases: [{ ...knowledgeBases[0]!, domain: 'medicare_fraud' }],
    })

    expect(screen.queryByTestId('kb-domain-mismatch')).not.toBeInTheDocument()
    expect(screen.queryByTestId('kb-domain-unknown')).not.toBeInTheDocument()
  })

  it('renders no domain toggle when no knowledge bases are hidden', () => {
    renderSelector()

    expect(screen.queryByTestId('kb-show-all-domains-toggle')).not.toBeInTheDocument()
  })

  it('shows the hidden-domain count on the toggle and reports toggling', () => {
    const onToggleShowAllDomains = vi.fn()
    renderSelector({ hiddenDomainCount: 3, onToggleShowAllDomains })

    const toggle = screen.getByRole('button', { name: 'Show all domains (3 hidden)' })
    expect(toggle).toHaveAttribute('aria-pressed', 'false')

    fireEvent.click(toggle)

    expect(onToggleShowAllDomains).toHaveBeenCalledTimes(1)
  })

  it('offers to scope back to the active domain when all domains are shown', () => {
    renderSelector({ hiddenDomainCount: 2, showAllDomains: true })

    const toggle = screen.getByRole('button', { name: 'Scope to active domain' })
    expect(toggle).toHaveAttribute('aria-pressed', 'true')
  })

  it('explains a scoped-empty list instead of claiming no knowledge bases exist', () => {
    renderSelector({
      activeKnowledgeBaseId: null,
      hiddenDomainCount: 2,
      knowledgeBases: [],
    })

    expect(screen.getByText('No knowledge bases in the active domain')).toBeInTheDocument()
    expect(screen.queryByText('No knowledge bases yet')).not.toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Show all domains (2 hidden)' }),
    ).toBeInTheDocument()
  })

  it('renders an empty state and keeps create disabled for blank names', () => {
    renderSelector({
      activeKnowledgeBaseId: null,
      createName: '   ',
      knowledgeBases: [],
    })

    expect(screen.getByText('No knowledge bases yet')).toBeInTheDocument()
    expect(
      within(screen.getByRole('button', { name: /create knowledge base/i })).getByText(
        /create knowledge base/i,
      ),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /create knowledge base/i })).toBeDisabled()
  })
})
