import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'

import { apiFetch } from '../client'
import {
  capabilityRegistryQueryKey,
  listCapabilities,
  useCapabilityRegistry,
} from '../capabilities'

vi.mock('../client', () => ({
  apiFetch: vi.fn(),
}))

const apiFetchMock = vi.mocked(apiFetch)

function createQueryWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

describe('capabilities API helpers', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('fetches a KB-scoped capability registry with filters', async () => {
    apiFetchMock.mockResolvedValue({ items: [], total: 0, limit: 100, offset: 0 })

    await listCapabilities('kb live', {
      role: 'viewer',
      sideEffectClass: 'read',
      module: 'rag',
      limit: 25,
      offset: 50,
    })

    expect(apiFetchMock).toHaveBeenCalledWith(
      '/knowledgebases/kb%20live/capabilities?role=viewer&module=rag&side_effect_class=read&limit=25&offset=50',
    )
  })

  it('keys capability registry queries by KB and filters', () => {
    expect(capabilityRegistryQueryKey('kb-1')).not.toEqual(
      capabilityRegistryQueryKey('kb-2'),
    )
    expect(capabilityRegistryQueryKey('kb-1', { role: 'viewer' })).not.toEqual(
      capabilityRegistryQueryKey('kb-1', { role: 'analyst' }),
    )
  })

  it('keeps the hook idle until a KB is selected', () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    const result = renderHook(() => useCapabilityRegistry(null), {
      wrapper: createQueryWrapper(queryClient),
    })

    expect(result.result.current.fetchStatus).toBe('idle')
    expect(apiFetchMock).not.toHaveBeenCalled()
  })
})
