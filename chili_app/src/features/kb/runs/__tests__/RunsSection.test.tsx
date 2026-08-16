import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { RunsSection } from '../RunsSection'

function renderSection(entityCount: number) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    )
  }

  return render(<RunsSection knowledgeBaseId="kb-1" entityCount={entityCount} />, {
    wrapper: Wrapper,
  })
}

const workflow = {
  id: 'wf-1',
  workflow_type: 'ingestion',
  status: 'completed',
  knowledge_base_id: 'kb-1',
  created_at: '2026-08-15T12:00:00Z',
  updated_at: '2026-08-15T12:01:00Z',
  steps: [],
  metadata: {},
  receipt: null,
}

const originalFetch = globalThis.fetch

let workflowItems: unknown[] = [workflow]

beforeEach(() => {
  workflowItems = [workflow]
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString()
    if (url.includes('/workflows')) {
      return new Response(JSON.stringify({ items: workflowItems, total: workflowItems.length }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    }
    if (url.includes('/score-runs')) {
      return new Response(JSON.stringify({ items: [], total: 0 }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    }
    throw new Error(`unexpected request: ${url}`)
  }) as unknown as typeof fetch
})

afterEach(() => {
  globalThis.fetch = originalFetch
  vi.restoreAllMocks()
})

describe('RunsSection', () => {
  it('renders the runs the server reports', async () => {
    renderSection(12)

    await waitFor(() => {
      expect(screen.getByText('ingestion')).toBeInTheDocument()
    })
  })

  it('disables the score run start and names the blocker when there are no entities', async () => {
    renderSection(0)

    const start = await screen.findByRole('button', { name: 'Start score-all' })
    expect(start).toBeDisabled()
    expect(
      screen.getByText('Start requires ingested entities in this knowledge base.'),
    ).toBeInTheDocument()
  })

  it('enables the score run start once the knowledge base has entities', async () => {
    renderSection(12)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Start score-all' })).toBeEnabled()
    })
    expect(
      screen.queryByText('Start requires ingested entities in this knowledge base.'),
    ).not.toBeInTheDocument()
  })

  // Moved from KnowledgeBaseManagerPage.test.tsx: the page used to hide the
  // run timeline card entirely when a knowledge base had no workflows
  // (UXA-305, deduplicating stacked "nothing here yet" cards). Now that the
  // timeline lives in its own section, it always renders — with an empty
  // state when there is nothing to show — matching the section's role as a
  // standalone route rather than one of several stacked aside cards.
  it('shows an empty state instead of the timeline when there are no workflows', async () => {
    workflowItems = []
    renderSection(12)

    expect(
      await screen.findByText('Submitting documents or records starts a run, and it appears here.'),
    ).toBeInTheDocument()
    expect(screen.getByText('No runs yet')).toBeInTheDocument()
  })
})
