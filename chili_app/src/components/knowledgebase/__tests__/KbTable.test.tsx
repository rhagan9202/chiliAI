import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { KnowledgeBase } from '../../../types/api'
import { KbTable } from '../KbTable'

const sampleKbs: KnowledgeBase[] = [
  {
    id: 'kb-1',
    name: 'Alpha Cases',
    description: '',
    entity_count: 10,
    relationship_count: 5,
    document_count: 3,
    status: 'active',
    created_at: '2026-04-01T00:00:00Z',
  },
  {
    id: 'kb-2',
    name: 'Beta Cases',
    description: '',
    entity_count: 0,
    relationship_count: 0,
    document_count: 0,
    status: 'building',
    created_at: '2026-04-20T00:00:00Z',
  },
]

describe('KbTable', () => {
  it('renders rows with name, status badge, document count, and date columns', () => {
    render(<KbTable knowledgeBases={sampleKbs} />)
    expect(screen.getByText('Alpha Cases')).toBeInTheDocument()
    expect(screen.getByText('Beta Cases')).toBeInTheDocument()
    expect(screen.getAllByTestId('kb-status-badge')).toHaveLength(2)
    const rows = screen.getAllByTestId('kb-row')
    expect(rows).toHaveLength(2)
  })

  it('shows the empty state when there are no knowledge bases', () => {
    render(<KbTable knowledgeBases={[]} />)
    expect(screen.getByText(/no knowledge bases/i)).toBeInTheDocument()
  })

  it('toggles the created column sort direction when clicked', () => {
    render(<KbTable knowledgeBases={sampleKbs} />)
    const header = screen.getByRole('button', { name: /Created/i })
    expect(header).toHaveAttribute('aria-sort', 'descending')
    fireEvent.click(header)
    expect(header).toHaveAttribute('aria-sort', 'ascending')
  })

  it('invokes onSelect when a name is clicked', () => {
    const onSelect = vi.fn()
    render(<KbTable knowledgeBases={sampleKbs} onSelect={onSelect} />)
    fireEvent.click(screen.getByText('Alpha Cases'))
    expect(onSelect).toHaveBeenCalledWith(sampleKbs[0])
  })
})
