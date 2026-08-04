import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { apiFetch, apiPost } from '../client'
import {
  exportPlaybooks,
  importPlaybooks,
  listPlaybooks,
  playbooksQueryKey,
  publishPlaybook,
  usePlaybooks,
} from '../playbooks'

vi.mock('../client', () => ({
  apiFetch: vi.fn(),
  apiPost: vi.fn(),
}))

const apiFetchMock = vi.mocked(apiFetch)
const apiPostMock = vi.mocked(apiPost)

function createQueryWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

describe('playbooks API', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    apiPostMock.mockReset()
  })

  it('serializes playbook list by knowledge base', async () => {
    apiFetchMock.mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 })

    await listPlaybooks('kb-live')

    expect(apiFetchMock).toHaveBeenCalledWith('/knowledgebases/kb-live/playbooks?limit=50&offset=0')
  })

  it('uses a stable missing query key when no knowledge base is selected', () => {
    expect(playbooksQueryKey(null)).toEqual(['playbooks', 'missing'])
    expect(playbooksQueryKey('kb-live')).toEqual(['playbooks', 'kb-live'])
  })

  it('serializes publish, import, and export paths', async () => {
    apiPostMock.mockResolvedValue({ snapshot_id: 'snapshot-1' })
    apiFetchMock.mockResolvedValue({ artifact: {} })

    await publishPlaybook('kb live', 'billing-spike', { version: 'v2' })
    await importPlaybooks('kb live', { artifact: { playbooks: [] } })
    await exportPlaybooks('kb live')

    expect(apiPostMock).toHaveBeenNthCalledWith(
      1,
      '/knowledgebases/kb%20live/playbooks/billing-spike/publish',
      { version: 'v2' },
    )
    expect(apiPostMock).toHaveBeenNthCalledWith(
      2,
      '/knowledgebases/kb%20live/playbooks/import',
      { artifact: { playbooks: [] } },
    )
    expect(apiFetchMock).toHaveBeenCalledWith('/knowledgebases/kb%20live/playbooks/export')
  })

  it('fetches playbooks through the hook only when enabled', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    apiFetchMock.mockResolvedValue({ items: [], published: [], total: 0, limit: 50, offset: 0 })

    const disabled = renderHook(() => usePlaybooks('kb-live', false), {
      wrapper: createQueryWrapper(queryClient),
    })

    expect(disabled.result.current.fetchStatus).toBe('idle')
    expect(apiFetchMock).not.toHaveBeenCalled()

    const enabled = renderHook(() => usePlaybooks('kb-live'), {
      wrapper: createQueryWrapper(queryClient),
    })

    await waitFor(() => expect(enabled.result.current.isSuccess).toBe(true))
    expect(apiFetchMock).toHaveBeenCalledWith('/knowledgebases/kb-live/playbooks?limit=50&offset=0')
  })
})
