import { describe, expect, it, vi } from 'vitest'

import { apiFetch, apiPost } from '../client'
import type { PolicyBriefCreateRequest } from '../contracts'
import {
  createPolicyBrief,
  getPolicyGap,
  getPolicyGapCases,
  getPolicyGaps,
  policyGapCasesQueryKey,
  policyGapDetailQueryKey,
  policyGapsQueryKey,
} from '../policy'

vi.mock('../client', () => ({
  apiFetch: vi.fn(),
  apiPost: vi.fn(),
}))

const apiFetchMock = vi.mocked(apiFetch)
const apiPostMock = vi.mocked(apiPost)

describe('policy API', () => {
  it('exposes stable query keys', () => {
    expect(policyGapsQueryKey).toEqual(['policy', 'gaps'])
    expect(policyGapDetailQueryKey('gap-1')).toEqual(['policy', 'gaps', 'gap-1'])
    expect(policyGapCasesQueryKey('gap-1')).toEqual(['policy', 'gaps', 'gap-1', 'cases'])
  })

  it('fetches policy gap list, detail, and case paths', async () => {
    apiFetchMock.mockResolvedValue({ items: [], page: { page: 1, page_size: 25, total_items: 0 } })

    await getPolicyGaps()
    await getPolicyGap('gap-1')
    await getPolicyGapCases('gap-1')

    expect(apiFetchMock).toHaveBeenNthCalledWith(1, '/policy/gaps')
    expect(apiFetchMock).toHaveBeenNthCalledWith(2, '/policy/gaps/gap-1')
    expect(apiFetchMock).toHaveBeenNthCalledWith(3, '/policy/gaps/gap-1/cases')
  })

  it('creates policy briefs with the expected payload', async () => {
    const payload: PolicyBriefCreateRequest = {
      gap_id: 'gap-1',
      audience: 'CMS leadership',
      objective: 'Prioritize enforcement.',
    }
    apiPostMock.mockResolvedValue({ id: 'brief-1' })

    await createPolicyBrief(payload)

    expect(apiPostMock).toHaveBeenCalledWith('/policy/briefs', payload)
  })
})
