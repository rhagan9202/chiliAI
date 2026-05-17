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
    deleteDisabled: false,
    knowledgeBases,
    onCreateDescriptionChange: vi.fn(),
    onCreateNameChange: vi.fn(),
    onCreateSubmit: vi.fn(),
    onDelete: vi.fn(),
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
    expect(screen.getByText('12 docs')).toBeInTheDocument()
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

  it('deletes the active knowledge base when delete is available', () => {
    const props = renderSelector()

    fireEvent.click(screen.getByRole('button', { name: /delete selected knowledge base/i }))

    expect(props.onDelete).toHaveBeenCalledWith('kb-policy')
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
    expect(
      screen.queryByRole('button', { name: /delete selected knowledge base/i }),
    ).not.toBeInTheDocument()
  })
})
