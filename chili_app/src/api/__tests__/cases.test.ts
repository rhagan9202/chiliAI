import { describe, expect, it, vi } from 'vitest'

import {
  addCaseFeedback,
  caseDetailQueryKey,
  casesQueryKey,
  createCase,
  getCase,
  getCases,
  updateCase,
} from '../cases'
import { apiFetch, apiPatch, apiPost } from '../client'
import type {
  CaseCreateRequest,
  CaseFeedbackCreateRequest,
  CaseUpdateRequest,
} from '../contracts'

vi.mock('../client', () => ({
  apiFetch: vi.fn(),
  apiPatch: vi.fn(),
  apiPost: vi.fn(),
}))

const apiFetchMock = vi.mocked(apiFetch)
const apiPatchMock = vi.mocked(apiPatch)
const apiPostMock = vi.mocked(apiPost)

describe('cases API', () => {
  it('exposes stable query keys', () => {
    expect(casesQueryKey).toEqual(['cases'])
    expect(caseDetailQueryKey('case-1')).toEqual(['cases', 'case-1'])
  })

  it('fetches case lists and details from the expected paths', async () => {
    apiFetchMock.mockResolvedValueOnce({ items: [], page: { page: 1, page_size: 25, total_items: 0 } })
    apiFetchMock.mockResolvedValueOnce({ case: { id: 'case-1' } })

    await getCases()
    await getCase('case-1')

    expect(apiFetchMock).toHaveBeenNthCalledWith(1, '/cases')
    expect(apiFetchMock).toHaveBeenNthCalledWith(2, '/cases/case-1')
  })

  it('creates, updates, and appends feedback using mutation helpers', async () => {
    const createPayload: CaseCreateRequest = {
      title: 'Escalation',
      priority: 'high',
      alert_ids: ['alert-1'],
    }
    const updatePayload: CaseUpdateRequest = { status: 'in_review' }
    const feedbackPayload: CaseFeedbackCreateRequest = {
      label: 'suspicious',
      evidence_adequacy: 'high',
      missing_evidence: [],
      notes: 'Ready for review.',
    }
    apiPostMock.mockResolvedValue({ case: { id: 'case-1' } })
    apiPatchMock.mockResolvedValue({ case: { id: 'case-1' } })

    await createCase(createPayload)
    await updateCase('case-1', updatePayload)
    await addCaseFeedback('case-1', feedbackPayload)

    expect(apiPostMock).toHaveBeenNthCalledWith(1, '/cases', createPayload)
    expect(apiPatchMock).toHaveBeenCalledWith('/cases/case-1', updatePayload)
    expect(apiPostMock).toHaveBeenNthCalledWith(2, '/cases/case-1/feedback', feedbackPayload)
  })
})
