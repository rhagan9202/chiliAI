import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { RagChatPage } from '../RagChatPage'

function renderWithClient(node: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })

  function Wrapper({ children }: { children: ReactNode }): React.ReactElement {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }

  return render(node, { wrapper: Wrapper })
}

describe('RagChatPage', () => {
  const originalFetch = globalThis.fetch

  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.restoreAllMocks()
  })

  it('starts without fetching a hardcoded conversation', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url.endsWith('/knowledgebases')) {
        return new Response(
          JSON.stringify({
            items: [
              {
                id: 'kb-1',
                name: 'Fraud KB',
                description: '',
                status: 'ready',
                document_count: 1,
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
      return new Response('{"detail":"not found"}', {
        status: 404,
        headers: { 'content-type': 'application/json' },
      })
    })
    globalThis.fetch = fetchMock as unknown as typeof fetch

    renderWithClient(<RagChatPage />)

    expect(await screen.findByText('Start new thread')).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalledWith(
      expect.stringContaining('conversation-001'),
      expect.anything(),
    )
  })
})
