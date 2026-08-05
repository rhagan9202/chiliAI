import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { apiFetch } from '../client'
import {
  getGovernanceReport,
  governanceReportQueryKey,
  useGovernanceReport,
} from '../governance'

vi.mock('../client', () => ({
  apiFetch: vi.fn(),
}))

const apiFetchMock = vi.mocked(apiFetch)

function createQueryWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

describe('governance API', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('serializes governance report path by knowledge base', async () => {
    apiFetchMock.mockResolvedValue({ knowledge_base_id: 'kb live' })

    await getGovernanceReport('kb live')

    expect(apiFetchMock).toHaveBeenCalledWith('/knowledgebases/kb%20live/governance/report')
  })

  it('uses a stable missing query key when no knowledge base is selected', () => {
    expect(governanceReportQueryKey(null)).toEqual(['governance-report', 'missing'])
    expect(governanceReportQueryKey('kb-live')).toEqual(['governance-report', 'kb-live'])
  })

  it('fetches the report through the hook only when a knowledge base is selected', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    apiFetchMock.mockResolvedValue({
      knowledge_base_id: 'kb-live',
      release_ready: true,
      production_versions: [],
      pending_approvals: [],
      release_blockers: [],
      feedback_trends: { total_reviews: 0, challenged_reviews: 0, approved_reviews: 0, state_counts: {} },
    })

    const disabled = renderHook(() => useGovernanceReport(null), {
      wrapper: createQueryWrapper(queryClient),
    })

    expect(disabled.result.current.fetchStatus).toBe('idle')
    expect(apiFetchMock).not.toHaveBeenCalled()

    const enabled = renderHook(() => useGovernanceReport('kb-live'), {
      wrapper: createQueryWrapper(queryClient),
    })

    await waitFor(() => expect(enabled.result.current.isSuccess).toBe(true))
    expect(apiFetchMock).toHaveBeenCalledWith('/knowledgebases/kb-live/governance/report')
  })
})
