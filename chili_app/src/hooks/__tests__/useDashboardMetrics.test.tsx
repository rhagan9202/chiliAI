import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useDashboardMetrics } from '../useDashboardMetrics'

function makeFetch(): typeof globalThis.fetch {
  return (async (input: RequestInfo | URL): Promise<Response> => {
    const url =
      typeof input === 'string'
        ? input
        : input instanceof URL
          ? input.toString()
          : input.url
    if (url.endsWith('/knowledgebases')) {
      return new Response(
        JSON.stringify({
          items: [
            {
              id: 'kb-1',
              name: 'KB1',
              description: '',
              entity_count: 5,
              relationship_count: 3,
              document_count: 2,
              status: 'active',
              created_at: '2026-04-01T00:00:00Z',
            },
            {
              id: 'kb-2',
              name: 'KB2',
              description: '',
              entity_count: 7,
              relationship_count: 4,
              document_count: 1,
              status: 'archived',
              created_at: '2026-04-02T00:00:00Z',
            },
          ],
          total: 2,
        }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      )
    }
    if (url.includes('/alerts')) {
      return new Response(
        JSON.stringify({ items: [], total: 4 }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      )
    }
    return new Response('{}', {
      status: 200,
      headers: { 'content-type': 'application/json' },
    })
  }) as typeof globalThis.fetch
}

describe('useDashboardMetrics', () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    globalThis.fetch = makeFetch()
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  it('aggregates counts from KB list and alerts response', async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    function Wrapper({
      children,
    }: {
      children: ReactNode
    }): React.ReactElement {
      return (
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
      )
    }
    const { result } = renderHook(() => useDashboardMetrics(), {
      wrapper: Wrapper,
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual({
      totalEntities: 12,
      totalRelationships: 7,
      openAlerts: 4,
      activeKnowledgeBases: 1,
    })
  })

  it('reports a failure when the API rejects', async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response('{"detail":"boom"}', {
        status: 500,
        headers: { 'content-type': 'application/json' },
      }),
    ) as typeof globalThis.fetch
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    function Wrapper({
      children,
    }: {
      children: ReactNode
    }): React.ReactElement {
      return (
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
      )
    }
    const { result } = renderHook(() => useDashboardMetrics(), {
      wrapper: Wrapper,
    })
    await waitFor(() => expect(result.current.isError).toBe(true))
  })
})
