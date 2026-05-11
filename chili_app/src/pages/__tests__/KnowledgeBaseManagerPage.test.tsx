import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { KnowledgeBaseManagerPage } from '../KnowledgeBaseManagerPage'

function renderWithClient(node: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })

  function Wrapper({ children }: { children: ReactNode }): React.ReactElement {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }

  return render(node, { wrapper: Wrapper })
}

describe('KnowledgeBaseManagerPage', () => {
  const originalFetch = globalThis.fetch

  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.restoreAllMocks()
  })

  it('renders a create-first empty state when the inventory is empty', async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify({ items: [], total: 0 }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    ) as unknown as typeof fetch

    renderWithClient(<KnowledgeBaseManagerPage />)

    expect(await screen.findByText('No knowledge bases yet')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create knowledge base' })).toBeInTheDocument()
  })

  it('renders active backend knowledge base and document response shapes', async () => {
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url.endsWith('/knowledgebases')) {
        return new Response(
          JSON.stringify({
            items: [
              {
                id: 'kb-1',
                name: 'Fraud KB',
                description: 'Active backend shape',
                status: 'active',
                document_count: 0,
                entity_count: 2,
                relationship_count: 1,
                created_at: '2026-05-10T00:00:00Z',
              },
            ],
            total: 1,
          }),
          { status: 200, headers: { 'content-type': 'application/json' } },
        )
      }
      if (url.endsWith('/knowledgebases/kb-1/documents')) {
        return new Response(JSON.stringify({ items: [], total: 0 }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        })
      }
      if (url.endsWith('/knowledgebases/kb-1')) {
        return new Response(
          JSON.stringify({
            id: 'kb-1',
            name: 'Fraud KB',
            description: 'Active backend shape',
            status: 'active',
            document_count: 0,
            entity_count: 2,
            relationship_count: 1,
            created_at: '2026-05-10T00:00:00Z',
          }),
          { status: 200, headers: { 'content-type': 'application/json' } },
        )
      }
      return new Response('{}', {
        status: 404,
        headers: { 'content-type': 'application/json' },
      })
    }) as unknown as typeof fetch

    renderWithClient(<KnowledgeBaseManagerPage />)

    expect(await screen.findAllByText('Fraud KB')).toHaveLength(2)
    expect(screen.getByText('No documents yet')).toBeInTheDocument()
  })
})
