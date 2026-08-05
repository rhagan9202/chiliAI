import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'

import { apiFetch } from '../client'
import {
  getKnowledgeBaseReadiness,
  knowledgeBaseReadinessQueryKey,
  useKnowledgeBaseReadiness,
} from '../readiness'

vi.mock('../client', () => ({
  apiFetch: vi.fn(),
}))

const apiFetchMock = vi.mocked(apiFetch)

function createQueryWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

describe('readiness API helpers', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('fetches KB-scoped readiness with an encoded knowledge-base id', async () => {
    apiFetchMock.mockResolvedValue({
      active_domain_name: 'medicare_fraud',
      blockers: [],
      components: {},
      knowledge_base: {
        created_at: '2026-08-05T12:00:00Z',
        document_count: 3,
        entity_count: 25,
        id: 'kb live',
        name: 'CMS Fraud KB',
        relationship_count: 40,
        status: 'ready',
      },
      ready: true,
      warnings: [],
    })

    await getKnowledgeBaseReadiness('kb live')

    expect(apiFetchMock).toHaveBeenCalledWith('/knowledgebases/kb%20live/readiness')
  })

  it('keys readiness queries by knowledge base', () => {
    expect(knowledgeBaseReadinessQueryKey('kb-1')).not.toEqual(
      knowledgeBaseReadinessQueryKey('kb-2'),
    )
  })

  it('keeps the hook idle until a knowledge base is selected', () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    const result = renderHook(() => useKnowledgeBaseReadiness(null), {
      wrapper: createQueryWrapper(queryClient),
    })

    expect(result.result.current.fetchStatus).toBe('idle')
    expect(apiFetchMock).not.toHaveBeenCalled()
  })
})
