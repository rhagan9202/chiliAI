import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'

import type { KnowledgeBaseSummaryResponse } from '../../../../api/contracts'
import { knowledgeBaseSituation, OverviewSection } from '../OverviewSection'

const base: KnowledgeBaseSummaryResponse = {
  id: 'kb-1',
  name: 'Fraud KB',
  description: 'Active corpus',
  status: 'ready',
  document_count: 0,
  entity_count: 0,
  relationship_count: 0,
  created_at: '2026-08-01T00:00:00Z',
  updated_at: '2026-08-14T00:00:00Z',
  domain: 'medicare_fraud',
}

describe('knowledgeBaseSituation', () => {
  it('says a new knowledge base is empty and what to do about it', () => {
    expect(knowledgeBaseSituation(base)).toBe(
      'This knowledge base is empty. Add documents or structured records to start.',
    )
  })

  it('says ingested-but-not-extracted when documents produced no entities', () => {
    expect(knowledgeBaseSituation({ ...base, document_count: 3 })).toBe(
      '3 documents are ingested but produced no entities yet. Check the runs for extraction problems.',
    )
  })

  it('agrees in number for a single document', () => {
    expect(knowledgeBaseSituation({ ...base, document_count: 1 })).toBe(
      '1 document is ingested but produced no entities yet. Check the runs for extraction problems.',
    )
  })

  it('states what is queryable once entities exist', () => {
    expect(
      knowledgeBaseSituation({
        ...base,
        document_count: 8,
        entity_count: 53,
        relationship_count: 21,
      }),
    ).toBe('53 entities and 21 relationships from 8 documents are ready to investigate.')
  })
})

describe('OverviewSection', () => {
  it('offers the handoffs, disabled with a reason while there is nothing to hand off', () => {
    render(
      <MemoryRouter>
        <OverviewSection activeDomainName="medicare_fraud" knowledgeBase={base} />
      </MemoryRouter>,
    )

    expect(screen.getByRole('button', { name: 'Investigate entities' })).toBeDisabled()
    expect(
      screen.getByText('Investigating needs at least one extracted entity.'),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Add data' })).toHaveAttribute(
      'href',
      '/knowledge-bases/kb-1/add',
    )
  })

  it('enables the handoffs once entities exist and scopes them to this knowledge base', () => {
    render(
      <MemoryRouter>
        <OverviewSection
          activeDomainName="medicare_fraud"
          knowledgeBase={{ ...base, document_count: 8, entity_count: 53 }}
        />
      </MemoryRouter>,
    )

    expect(screen.getByRole('link', { name: 'Investigate entities' })).toHaveAttribute(
      'href',
      '/investigation?kb=kb-1',
    )
    expect(screen.getByRole('link', { name: 'Review alerts' })).toHaveAttribute(
      'href',
      '/alerts?kb=kb-1',
    )
    expect(screen.getByRole('link', { name: 'Ask in RAG chat' })).toHaveAttribute(
      'href',
      '/rag-chat?kb=kb-1',
    )
  })

  it('warns when the knowledge base was built under another domain', () => {
    render(
      <MemoryRouter>
        <OverviewSection activeDomainName="food_supply_chain" knowledgeBase={base} />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('kb-domain-mismatch-note')).toBeInTheDocument()
  })
})
